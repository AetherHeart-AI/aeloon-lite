#!/usr/bin/env python3
"""Validate Aeloon PR metadata without exposing private Issue content."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from typing import Any, Callable, Sequence


PUBLIC_REPOSITORY = "AetherHeart-AI/aeloon-lite"
PUBLIC_REF_RE = re.compile(r"^AetherHeart-AI/aeloon-lite#([1-9][0-9]*)$")
IMPACT_RE = re.compile(r"^[ \t]*Release-Impact:[ \t]*(public|internal)[ \t]*$", re.MULTILINE)
PUBLIC_FIELD_RE = re.compile(r"^[ \t]*Public-Issue:[ \t]*([^\r\n]+?)[ \t]*$", re.MULTILINE)


class PolicyError(RuntimeError):
    pass


def repository_name(issue: dict[str, Any]) -> str:
    repository_url = issue.get("repository_url", "")
    prefix = "https://api.github.com/repos/"
    if repository_url.startswith(prefix):
        return repository_url[len(prefix) :]
    repository = issue.get("repository")
    if isinstance(repository, dict) and repository.get("nameWithOwner"):
        return repository["nameWithOwner"]
    raise PolicyError("GitHub did not identify an Issue repository.")


def validate_policy(
    body: str,
    current_repository: str,
    closing_issues: Sequence[dict[str, Any]],
    parent_loader: Callable[[str, int], dict[str, Any] | None],
) -> None:
    visible_body = re.sub(r"<!--.*?-->", "", body or "", flags=re.DOTALL)
    impacts = IMPACT_RE.findall(visible_body)
    public_fields = [value.strip() for value in PUBLIC_FIELD_RE.findall(visible_body)]
    if len(impacts) != 1 or len(public_fields) != 1:
        raise PolicyError("PR body must contain exactly one Release-Impact and Public-Issue field.")

    impact = impacts[0]
    public_field = public_fields[0]
    if impact == "public":
        match = PUBLIC_REF_RE.fullmatch(public_field)
        if not match:
            raise PolicyError("A public PR must declare AetherHeart-AI/aeloon-lite#NUMBER.")
        public_number = int(match.group(1))
        if len(closing_issues) != 1:
            raise PolicyError("A public PR must close exactly one Issue.")
        closing = closing_issues[0]
        closing_repository = repository_name(closing)
        if closing_repository != current_repository:
            raise PolicyError("The closing Issue must belong to the current repository.")
        closing_number = int(closing["number"])
        parent = parent_loader(closing_repository, closing_number)
        if (
            current_repository == PUBLIC_REPOSITORY
            and closing_number == public_number
            and parent is None
        ):
            return
        if parent is None:
            raise PolicyError("The closing Issue is not a native sub-issue.")
        if repository_name(parent) != PUBLIC_REPOSITORY or int(parent["number"]) != public_number:
            raise PolicyError("The closing Issue has a different public parent.")
        return

    if public_field != "none":
        raise PolicyError("An internal PR must declare Public-Issue: none.")
    for closing in closing_issues:
        closing_repository = repository_name(closing)
        closing_number = int(closing["number"])
        if closing_repository == PUBLIC_REPOSITORY:
            raise PolicyError("An internal PR cannot close a public Issue.")
        if closing_repository != current_repository:
            continue
        parent = parent_loader(closing_repository, closing_number)
        if parent is not None and repository_name(parent) == PUBLIC_REPOSITORY:
            raise PolicyError("An internal PR cannot close an Issue with a public parent.")


class GitHub:
    def __init__(self, token: str) -> None:
        self.environment = {**os.environ, "GH_TOKEN": token}

    def run(self, arguments: Sequence[str], *, input_data: str | None = None) -> str:
        result = subprocess.run(
            ["gh", *arguments],
            input=input_data,
            text=True,
            capture_output=True,
            env=self.environment,
            check=False,
        )
        if result.returncode:
            raise PolicyError("GitHub policy lookup failed.")
        return result.stdout

    def pull_request(self, repository: str, number: int) -> dict[str, Any]:
        owner, name = repository.split("/", 1)
        query = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      body
      closingIssuesReferences(first: 100) {
        nodes { number repository { nameWithOwner } }
        pageInfo { hasNextPage }
      }
    }
  }
}
"""
        response = json.loads(
            self.run(
                ("api", "graphql", "--input", "-"),
                input_data=json.dumps(
                    {
                        "query": query,
                        "variables": {"owner": owner, "name": name, "number": number},
                    }
                ),
            )
        )
        if response.get("errors"):
            raise PolicyError("GitHub policy lookup failed.")
        pull_request = response["data"]["repository"]["pullRequest"]
        if pull_request["closingIssuesReferences"]["pageInfo"]["hasNextPage"]:
            raise PolicyError("A PR cannot close more than 100 Issues.")
        return pull_request

    def parent(self, repository: str, number: int) -> dict[str, Any] | None:
        result = subprocess.run(
            [
                "gh",
                "api",
                "-H",
                "Accept: application/vnd.github+json",
                "-H",
                "X-GitHub-Api-Version: 2026-03-10",
                f"repos/{repository}/issues/{number}/parent",
            ],
            text=True,
            capture_output=True,
            env=self.environment,
            check=False,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        if "HTTP 404" in result.stderr or "Not Found" in result.stderr:
            return None
        raise PolicyError("GitHub parent-Issue lookup failed.")


def main() -> int:
    token = os.environ.get("ISSUE_GH_TOKEN", "")
    repository = os.environ.get("POLICY_REPOSITORY", "")
    number_text = os.environ.get("POLICY_PR_NUMBER", "")
    if not token or not re.fullmatch(r"[^/]+/[^/]+", repository) or not number_text.isdigit():
        print("public-issue-policy: invalid Action configuration.", file=sys.stderr)
        return 2
    try:
        client = GitHub(token)
        pull_request = client.pull_request(repository, int(number_text))
        validate_policy(
            pull_request.get("body") or "",
            repository,
            pull_request["closingIssuesReferences"]["nodes"],
            client.parent,
        )
    except PolicyError as error:
        print(f"public-issue-policy: {error}", file=sys.stderr)
        return 1
    print("Public issue policy passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
