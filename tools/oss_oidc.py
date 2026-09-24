"""Exchange the current GitHub Actions OIDC identity for short-lived OSS credentials."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Credentials:
    access_key_id: str
    access_key_secret: str
    security_token: str
    expires_at: float


def _request_json(request: urllib.request.Request, service: str) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.load(response)
    except urllib.error.HTTPError as error:
        code = ""
        try:
            value = json.loads(error.read(8192))
            candidate = value.get("Code") if isinstance(value, dict) else None
            if isinstance(candidate, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,127}", candidate):
                code = f" ({candidate})"
        except (OSError, ValueError):
            pass
        raise RuntimeError(f"{service} returned HTTP {error.code}{code}") from None
    except (OSError, ValueError) as error:
        raise RuntimeError(f"Could not read {service} response: {type(error).__name__}") from None
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid {service} response")
    return value


def request_credentials(role_arn: str, provider_arn: str) -> Credentials:
    """Request fresh OIDC and STS tokens without putting either token in a URL or log."""
    request_url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    request_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not request_url or not request_token or not role_arn or not provider_arn:
        raise RuntimeError("GitHub OIDC and OSS role configuration are required")

    parsed = urllib.parse.urlsplit(request_url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("audience", "sts.aliyuncs.com"))
    audience_url = urllib.parse.urlunsplit(parsed._replace(query=urllib.parse.urlencode(query)))
    oidc = _request_json(urllib.request.Request(
        audience_url, headers={"Authorization": f"bearer {request_token}"},
    ), "GitHub OIDC")
    token = oidc.get("value")
    if not isinstance(token, str) or not token:
        raise RuntimeError("GitHub OIDC response has no token")

    query = urllib.parse.urlencode({
        "Action": "AssumeRoleWithOIDC",
        "Version": "2015-04-01",
        "Format": "JSON",
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    form = urllib.parse.urlencode({
        "OIDCProviderArn": provider_arn,
        "RoleArn": role_arn,
        "OIDCToken": token,
        "RoleSessionName": "aeloon-github-mirror",
        "DurationSeconds": "3600",
    }).encode("ascii")
    sts = _request_json(urllib.request.Request(
        f"https://sts.aliyuncs.com/?{query}", data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    ), "Alibaba Cloud STS")
    data = sts.get("Credentials")
    if not isinstance(data, dict):
        raise RuntimeError("Alibaba Cloud STS response has no credentials")
    try:
        access_key_id = data["AccessKeyId"]
        access_key_secret = data["AccessKeySecret"]
        security_token = data["SecurityToken"]
        expiration = data["Expiration"]
        expires_at = datetime.fromisoformat(expiration.replace("Z", "+00:00")).timestamp()
    except (KeyError, AttributeError, TypeError, ValueError):
        raise RuntimeError("Alibaba Cloud STS response has invalid credentials") from None
    if not all(isinstance(value, str) and value for value in
               (access_key_id, access_key_secret, security_token)) or expires_at <= time.time() + 600:
        raise RuntimeError("Alibaba Cloud STS credentials expire too soon")
    return Credentials(access_key_id, access_key_secret, security_token, expires_at)
