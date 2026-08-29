#!/usr/bin/env python3
"""Deterministic cross-repository issue and release-note automation for Aeloon."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable, Sequence


OWNER = "AetherHeart-AI"
PUBLIC_REPOSITORY = f"{OWNER}/aeloon-lite"
COMPONENT_REPOSITORIES = {
    "ui": f"{OWNER}/aeloon-lite-ui",
    "runtime": f"{OWNER}/aeloon-lite-runtime",
    "distribution": PUBLIC_REPOSITORY,
}
REPOSITORY_COMPONENTS = {value: key for key, value in COMPONENT_REPOSITORIES.items()}
PUBLIC_REF_RE = re.compile(rf"^{re.escape(PUBLIC_REPOSITORY)}#([1-9][0-9]*)$")
RELEASE_TAG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
API_HEADERS = (
    "Accept: application/vnd.github+json",
    "X-GitHub-Api-Version: 2026-03-10",
)


class IssueFlowError(RuntimeError):
    """A user-actionable validation or GitHub API error."""


class GitHub:
    """Small gh CLI adapter; ISSUE_GH_TOKEN takes precedence when present."""

    def _run(
        self,
        arguments: Sequence[str],
        *,
        input_data: str | None = None,
        allow_404: bool = False,
    ) -> str | None:
        environment = os.environ.copy()
        if issue_token := environment.get("ISSUE_GH_TOKEN"):
            environment["GH_TOKEN"] = issue_token
        result = subprocess.run(
            ["gh", *arguments],
            input=input_data,
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout
        if allow_404 and ("HTTP 404" in result.stderr or "Not Found" in result.stderr):
            return None
        operation = next((arg for arg in arguments if arg.startswith("repos/")), arguments[0])
        raise IssueFlowError(f"GitHub request failed for {operation}.")

    def api(
        self,
        endpoint: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        paginate: bool = False,
        allow_404: bool = False,
    ) -> Any:
        arguments = ["api"]
        for header in API_HEADERS:
            arguments.extend(("-H", header))
        if method != "GET":
            arguments.extend(("--method", method))
        if paginate:
            arguments.extend(("--paginate", "--slurp"))
        arguments.append(endpoint)
        input_data = None
        if body is not None:
            arguments.extend(("--input", "-"))
            input_data = json.dumps(body)
        output = self._run(arguments, input_data=input_data, allow_404=allow_404)
        if output is None:
            return None
        return json.loads(output) if output.strip() else None

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        output = self._run(
            ("api", "graphql", "--input", "-"),
            input_data=json.dumps({"query": query, "variables": variables}),
        )
        assert output is not None
        response = json.loads(output)
        if response.get("errors"):
            raise IssueFlowError("GitHub GraphQL request failed.")
        return response["data"]

    def pages(self, endpoint: str) -> list[Any]:
        pages = self.api(endpoint, paginate=True)
        if not isinstance(pages, list):
            raise IssueFlowError(f"Unexpected paginated response for {endpoint}.")
        return pages

    def list_items(self, endpoint: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for page in self.pages(endpoint):
            if not isinstance(page, list):
                raise IssueFlowError(f"Unexpected list response for {endpoint}.")
            items.extend(page)
        return items

    def get_issue(self, repository: str, number: int) -> dict[str, Any]:
        return self.api(f"repos/{repository}/issues/{number}")

    def list_subissues(self, number: int) -> list[dict[str, Any]]:
        return self.list_items(
            f"repos/{PUBLIC_REPOSITORY}/issues/{number}/sub_issues?per_page=100"
        )

    def find_marker_issues(self, repository: str, marker: str) -> list[dict[str, Any]]:
        return [
            issue
            for issue in self.list_items(f"repos/{repository}/issues?state=all&per_page=100")
            if "pull_request" not in issue and marker in (issue.get("body") or "")
        ]

    def create_issue(
        self,
        repository: str,
        title: str,
        body: str,
        labels: list[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        return self.api(f"repos/{repository}/issues", method="POST", body=payload)

    def link_subissue(self, parent_number: int, child_id: int) -> None:
        self.api(
            f"repos/{PUBLIC_REPOSITORY}/issues/{parent_number}/sub_issues",
            method="POST",
            body={"sub_issue_id": child_id},
        )

    def update_issue(self, repository: str, number: int, **fields: Any) -> None:
        self.api(f"repos/{repository}/issues/{number}", method="PATCH", body=fields)

    def issue_events(self, repository: str, number: int) -> list[dict[str, Any]]:
        return self.list_items(f"repos/{repository}/issues/{number}/events?per_page=100")

    def parent_issue(self, repository: str, number: int) -> dict[str, Any] | None:
        return self.api(
            f"repos/{repository}/issues/{number}/parent",
            allow_404=True,
        )

    def issue_comments(self, number: int) -> list[dict[str, Any]]:
        return self.list_items(
            f"repos/{PUBLIC_REPOSITORY}/issues/{number}/comments?per_page=100"
        )

    def create_comment(self, number: int, body: str) -> None:
        self.api(
            f"repos/{PUBLIC_REPOSITORY}/issues/{number}/comments",
            method="POST",
            body={"body": body},
        )


def _label_names(issue: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for label in issue.get("labels", []):
        names.append(label["name"] if isinstance(label, dict) else str(label))
    return names


def _repository_name(issue: dict[str, Any]) -> str:
    if repository := issue.get("repository"):
        if isinstance(repository, dict) and repository.get("full_name"):
            return repository["full_name"]
    repository_url = issue.get("repository_url", "")
    prefix = "https://api.github.com/repos/"
    if repository_url.startswith(prefix):
        return repository_url[len(prefix) :]
    html_url = issue.get("html_url", "")
    match = re.match(r"https://github\.com/([^/]+/[^/]+)/issues/[0-9]+$", html_url)
    if match:
        return match.group(1)
    raise IssueFlowError("A sub-issue response did not identify its repository.")


def _marker(parent_number: int, component: str) -> str:
    return (
        f"<!-- aeloon-public-parent:{PUBLIC_REPOSITORY}#{parent_number} "
        f"component:{component} -->"
    )


def _set_public_labels(
    client: GitHub,
    issue: dict[str, Any],
    *,
    status: str,
    components: Iterable[str] = (),
) -> None:
    labels = [
        label
        for label in _label_names(issue)
        if label not in {"status:needs-triage", "status:in-progress", "status:implemented"}
        and not label.startswith("component:")
    ]
    labels.append(f"status:{status}")
    labels.extend(f"component:{component}" for component in sorted(set(components)))
    client.update_issue(PUBLIC_REPOSITORY, issue["number"], labels=labels)


def _validate_plan(plan_path: Path) -> list[dict[str, str]]:
    try:
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IssueFlowError(f"Cannot read a valid JSON plan: {plan_path}") from error
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list) or not items:
        raise IssueFlowError("The plan must contain a non-empty items array.")
    normalized: list[dict[str, str]] = []
    seen_repositories: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise IssueFlowError("Every plan item must be an object.")
        component = item.get("component")
        repository = item.get("repository")
        title = item.get("title")
        body = item.get("body", "")
        if component not in COMPONENT_REPOSITORIES:
            raise IssueFlowError(f"Unsupported component: {component!r}.")
        if repository != COMPONENT_REPOSITORIES[component]:
            raise IssueFlowError(f"Repository does not match component {component}.")
        if repository in seen_repositories:
            raise IssueFlowError(f"Only one work item is allowed for {repository}.")
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 256:
            raise IssueFlowError("Every work item needs a title of at most 256 characters.")
        if not isinstance(body, str):
            raise IssueFlowError("Every work item body must be a string.")
        if "<!-- aeloon-public-parent:" in body:
            raise IssueFlowError("Plan bodies cannot contain automation markers.")
        seen_repositories.add(repository)
        normalized.append(
            {
                "component": component,
                "repository": repository,
                "title": title.strip(),
                "body": body.strip(),
            }
        )
    return normalized


def sync_issue(
    client: GitHub,
    parent_number: int,
    plan_path: Path,
    *,
    apply: bool,
) -> dict[str, Any]:
    parent = client.get_issue(PUBLIC_REPOSITORY, parent_number)
    if parent.get("pull_request") or parent.get("state") != "open":
        raise IssueFlowError("The public parent must be an open Issue.")
    items = _validate_plan(plan_path)
    direct_distribution = len(items) == 1 and items[0]["component"] == "distribution"
    subissues = client.list_subissues(parent_number)
    existing_by_repository: dict[str, dict[str, Any]] = {}
    for subissue in subissues:
        repository = _repository_name(subissue)
        if repository not in REPOSITORY_COMPONENTS:
            raise IssueFlowError("The public Issue already has an unsupported sub-issue.")
        if repository in existing_by_repository:
            raise IssueFlowError(f"The public Issue has multiple work items in {repository}.")
        existing_by_repository[repository] = subissue

    preview: list[dict[str, Any]] = []
    recovered: dict[str, dict[str, Any]] = {}
    for item in items:
        repository = item["repository"]
        action = (
            "direct"
            if direct_distribution and not subissues
            else "reuse" if repository in existing_by_repository else "create"
        )
        if action == "create":
            marker = _marker(parent_number, item["component"])
            marker_issues = client.find_marker_issues(repository, marker)
            if len(marker_issues) > 1:
                raise IssueFlowError(f"Multiple unlinked automation work items exist in {repository}.")
            if marker_issues:
                action = "recover"
                recovered[repository] = marker_issues[0]
        preview.append(
            {
                "component": item["component"],
                "repository": repository,
                "title": item["title"],
                "action": action,
            }
        )
    if not apply:
        return {"mode": "preview", "parent": parent_number, "items": preview}

    if direct_distribution and not subissues:
        _set_public_labels(client, parent, status="in-progress", components=("distribution",))
        return {"mode": "applied", "parent": parent_number, "items": preview}

    category_labels = [
        label for label in _label_names(parent) if label in {"bug", "enhancement"}
    ]
    results: list[dict[str, Any]] = []
    for item, planned in zip(items, preview):
        repository = item["repository"]
        child = existing_by_repository.get(repository) or recovered.get(repository)
        if child is None:
            marker = _marker(parent_number, item["component"])
            body_parts = [marker, f"Public-Issue: {PUBLIC_REPOSITORY}#{parent_number}"]
            if item["body"]:
                body_parts.extend(("", item["body"]))
            child = client.create_issue(
                repository,
                item["title"],
                "\n".join(body_parts),
                category_labels,
            )
        if repository not in existing_by_repository:
            client.link_subissue(parent_number, child["id"])
            existing_by_repository[repository] = child
        results.append(
            {
                "component": item["component"],
                "repository": repository,
                "number": child["number"],
                "action": planned["action"],
            }
        )

    actual_components = {
        REPOSITORY_COMPONENTS[repository] for repository in existing_by_repository
    }
    _set_public_labels(client, parent, status="in-progress", components=actual_components)
    return {"mode": "applied", "parent": parent_number, "items": results}


def _last_close_has_commit(client: GitHub, repository: str, number: int) -> bool:
    closed_events = [
        event for event in client.issue_events(repository, number) if event.get("event") == "closed"
    ]
    if not closed_events:
        return False
    last = max(closed_events, key=lambda event: (event.get("created_at", ""), event.get("id", 0)))
    return bool(last.get("commit_id"))


def _reconcile_one(client: GitHub, parent: dict[str, Any]) -> dict[str, Any]:
    parent_number = parent["number"]
    subissues = client.list_subissues(parent_number)
    components: set[str] = set()
    complete = True
    if subissues:
        for subissue in subissues:
            repository = _repository_name(subissue)
            component = REPOSITORY_COMPONENTS.get(repository)
            if component is None:
                raise IssueFlowError("The public Issue has an unsupported sub-issue repository.")
            components.add(component)
            complete = complete and subissue.get("state") == "closed" and _last_close_has_commit(
                client, repository, subissue["number"]
            )
    else:
        components.add("distribution")
        complete = parent.get("state") == "closed" and _last_close_has_commit(
            client, PUBLIC_REPOSITORY, parent_number
        )

    if not complete:
        return {"issue": parent_number, "status": "pending"}
    if parent.get("state") != "closed":
        client.update_issue(
            PUBLIC_REPOSITORY,
            parent_number,
            state="closed",
            state_reason="completed",
        )
        parent = {**parent, "state": "closed"}
    _set_public_labels(client, parent, status="implemented", components=components)
    return {"issue": parent_number, "status": "implemented"}


def reconcile(client: GitHub, issue_number: int | None = None) -> dict[str, Any]:
    if issue_number is not None:
        issues = [client.get_issue(PUBLIC_REPOSITORY, issue_number)]
    else:
        issues = [
            issue
            for issue in client.list_items(
                f"repos/{PUBLIC_REPOSITORY}/issues?state=all&labels=status%3Ain-progress&per_page=100"
            )
            if "pull_request" not in issue
        ]
    results = [_reconcile_one(client, issue) for issue in issues]
    return {"checked": len(results), "results": results}


CLOSING_ISSUES_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: 100, after: $cursor) {
        nodes { number state repository { nameWithOwner } }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""


def _closing_issues(client: GitHub, repository: str, pr_number: int) -> list[dict[str, Any]]:
    owner, name = repository.split("/", 1)
    cursor: str | None = None
    issues: list[dict[str, Any]] = []
    while True:
        data = client.graphql(
            CLOSING_ISSUES_QUERY,
            {"owner": owner, "name": name, "number": pr_number, "cursor": cursor},
        )
        connection = data["repository"]["pullRequest"]["closingIssuesReferences"]
        issues.extend(connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]:
            return issues
        cursor = connection["pageInfo"]["endCursor"]


def _comparison_commits(
    client: GitHub, repository: str, base: str, head: str
) -> list[str]:
    if base == head:
        return []
    pages = client.pages(f"repos/{repository}/compare/{base}...{head}?per_page=100")
    commits: set[str] = set()
    statuses: set[str] = set()
    for page in pages:
        if not isinstance(page, dict):
            raise IssueFlowError(f"Unexpected comparison response for {repository}.")
        if status := page.get("status"):
            statuses.add(status)
        commits.update(commit["sha"] for commit in page.get("commits", []))
    if statuses and not statuses.issubset({"ahead", "identical"}):
        raise IssueFlowError(f"Release range is not forward for {repository}.")
    return sorted(commits)


def collect(
    client: GitHub, ranges: Sequence[Sequence[str]]
) -> list[dict[str, Any]]:
    public_numbers: set[int] = set()
    seen_prs: set[tuple[str, int]] = set()
    for repository, base, head in ranges:
        if repository not in REPOSITORY_COMPONENTS:
            raise IssueFlowError(f"Unsupported release repository: {repository}.")
        for commit in _comparison_commits(client, repository, base, head):
            pulls = client.api(f"repos/{repository}/commits/{commit}/pulls")
            for pull in pulls:
                key = (repository, pull["number"])
                if (
                    key in seen_prs
                    or not pull.get("merged_at")
                    or pull.get("base", {}).get("ref") != "main"
                ):
                    continue
                seen_prs.add(key)
                for issue in _closing_issues(client, repository, pull["number"]):
                    issue_repository = issue["repository"]["nameWithOwner"]
                    if issue_repository == PUBLIC_REPOSITORY:
                        public_numbers.add(issue["number"])
                        continue
                    if issue_repository not in REPOSITORY_COMPONENTS:
                        continue
                    parent = client.parent_issue(issue_repository, issue["number"])
                    if parent is not None and _repository_name(parent) == PUBLIC_REPOSITORY:
                        public_numbers.add(parent["number"])

    issues: list[dict[str, Any]] = []
    for number in sorted(public_numbers):
        issue = client.get_issue(PUBLIC_REPOSITORY, number)
        if issue.get("state") != "closed" or issue.get("pull_request"):
            continue
        issues.append(
            {
                "number": number,
                "title": issue["title"],
                "url": issue["html_url"],
            }
        )
    return issues


def annotate_release(
    client: GitHub,
    issues: Sequence[dict[str, Any]],
    *,
    tag: str,
    url: str,
) -> dict[str, Any]:
    if not RELEASE_TAG_RE.fullmatch(tag):
        raise IssueFlowError("Release tag contains unsupported characters.")
    if not url.startswith(f"https://github.com/{PUBLIC_REPOSITORY}/releases/"):
        raise IssueFlowError("Release URL must belong to the public distribution repository.")
    marker = f"<!-- aeloon-release:{tag} -->"
    annotated: list[int] = []
    skipped: list[int] = []
    for item in issues:
        number = item.get("number")
        if not isinstance(number, int) or number < 1:
            raise IssueFlowError("Issue collection contains an invalid number.")
        if any(marker in (comment.get("body") or "") for comment in client.issue_comments(number)):
            skipped.append(number)
            continue
        client.create_comment(
            number,
            f"{marker}\n已收录于 [{tag}]({url})。 / Included in [{tag}]({url}).",
        )
        annotated.append(number)
    return {"annotated": annotated, "skipped": skipped}


def _read_issue_collection(path: Path) -> list[dict[str, Any]]:
    try:
        contents = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IssueFlowError(f"Cannot read issue collection: {path}") from error
    if not isinstance(contents, list):
        raise IssueFlowError("Issue collection must be a JSON array.")
    return contents


def _write_json(value: Any, output: Path | None = None) -> None:
    serialized = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if output is None:
        sys.stdout.write(serialized)
    else:
        output.write_text(serialized, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    sync_parser = commands.add_parser("sync", help="Preview or apply an approved split plan")
    sync_parser.add_argument("--issue", type=int, required=True)
    sync_parser.add_argument("--plan", type=Path, required=True)
    sync_parser.add_argument("--apply", action="store_true")

    reconcile_parser = commands.add_parser("reconcile", help="Close completed public parents")
    reconcile_parser.add_argument("--issue", type=int)

    collect_parser = commands.add_parser("collect", help="Collect public Issues from source ranges")
    collect_parser.add_argument(
        "--range",
        dest="ranges",
        action="append",
        nargs=3,
        metavar=("REPOSITORY", "BASE", "HEAD"),
        required=True,
    )
    collect_parser.add_argument("--output", type=Path)

    annotate_parser = commands.add_parser(
        "annotate-release", help="Add idempotent public Release comments"
    )
    annotate_parser.add_argument("--issues", type=Path, required=True)
    annotate_parser.add_argument("--tag", required=True)
    annotate_parser.add_argument("--url", required=True)
    return parser


def main(argv: Sequence[str] | None = None, client: GitHub | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    github = client or GitHub()
    try:
        if arguments.command == "sync":
            result = sync_issue(
                github,
                arguments.issue,
                arguments.plan,
                apply=arguments.apply,
            )
            _write_json(result)
        elif arguments.command == "reconcile":
            _write_json(reconcile(github, arguments.issue))
        elif arguments.command == "collect":
            _write_json(collect(github, arguments.ranges), arguments.output)
        else:
            issues = _read_issue_collection(arguments.issues)
            _write_json(
                annotate_release(github, issues, tag=arguments.tag, url=arguments.url)
            )
    except IssueFlowError as error:
        print(f"issue-flow: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
