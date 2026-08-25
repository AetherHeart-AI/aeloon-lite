#!/usr/bin/env python3
"""Verify a release pointer against the immutable public GitHub Release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.request
from pathlib import Path

from release_manifest import (
    REPOSITORY,
    loads_json,
    pointer_identity,
    read_json,
    validate_pointer,
    validate_release,
)


def request(url: str) -> bytes:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "aeloon-release-verifier"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("pointer", type=Path)
    parser.add_argument("--download-assets", action="store_true")
    args = parser.parse_args()
    pointer = read_json(args.pointer)
    validate_pointer(pointer)
    pointer_product, pointer_version, pointer_tag = pointer_identity(pointer)

    manifest_bytes = request(pointer["manifestUrl"])
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_digest != pointer["manifestSha256"]:
        raise SystemExit("remote release-manifest.json does not match manifestSha256")
    manifest = loads_json(manifest_bytes)
    validate_release(manifest)
    if manifest["product"] != pointer_product or manifest["tag"] != pointer_tag:
        raise SystemExit("release pointer and remote manifest identify different releases")

    release = json.loads(
        request(f"https://api.github.com/repos/{REPOSITORY}/releases/tags/{pointer_tag}")
    )
    if release.get("draft"):
        raise SystemExit("release is still a draft")
    expected_prerelease = "-" in pointer_version
    if bool(release.get("prerelease")) != expected_prerelease:
        raise SystemExit("GitHub prerelease flag does not match the release pointer")
    remote_assets = {asset["name"]: asset for asset in release.get("assets", [])}
    expected_names = {artifact["name"] for artifact in manifest["artifacts"]} | {"release-manifest.json"}
    if set(remote_assets) != expected_names:
        raise SystemExit("public release contains missing or unexpected assets")
    for artifact in manifest["artifacts"]:
        remote = remote_assets[artifact["name"]]
        if remote.get("digest") != f"sha256:{artifact['sha256']}":
            raise SystemExit(f"GitHub digest mismatch for {artifact['name']}")
        if remote.get("size") != artifact["size"]:
            raise SystemExit(f"GitHub size mismatch for {artifact['name']}")
        if args.download_assets:
            digest = hashlib.sha256()
            size = 0
            with urllib.request.urlopen(
                urllib.request.Request(artifact["url"], headers={"User-Agent": "aeloon-release-verifier"}),
                timeout=120,
            ) as response:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
            if size != artifact["size"] or digest.hexdigest() != artifact["sha256"]:
                raise SystemExit(f"downloaded bytes mismatch for {artifact['name']}")
    manifest_asset = remote_assets["release-manifest.json"]
    if manifest_asset.get("digest") != f"sha256:{manifest_digest}":
        raise SystemExit("GitHub digest mismatch for release-manifest.json")
    print(f"Verified {pointer_product} {pointer_tag} from {args.pointer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
