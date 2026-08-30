from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call

from tools.issue_flow import (
    OWNER,
    PUBLIC_REPOSITORY,
    IssueFlowError,
    annotate_release,
    collect,
    reconcile,
    sync_issue,
)


def issue(
    repository: str,
    number: int,
    *,
    state: str = "open",
    labels: tuple[str, ...] = (),
    title: str = "Public title",
) -> dict[str, object]:
    return {
        "id": number * 100,
        "number": number,
        "state": state,
        "title": title,
        "html_url": f"https://github.com/{repository}/issues/{number}",
        "repository_url": f"https://api.github.com/repos/{repository}",
        "labels": [{"name": label} for label in labels],
    }


class IssueFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)

    def plan(self, items: list[dict[str, str]]) -> Path:
        path = Path(self.temporary.name) / "plan.json"
        path.write_text(json.dumps({"items": items}), encoding="utf-8")
        return path

    def test_sync_preview_performs_no_writes(self) -> None:
        client = Mock()
        client.get_issue.return_value = issue(
            PUBLIC_REPOSITORY, 12, labels=("bug", "status:needs-triage")
        )
        client.list_subissues.return_value = []
        client.find_marker_issues.return_value = []
        plan = self.plan(
            [
                {
                    "component": "ui",
                    "repository": f"{OWNER}/aeloon-lite-ui",
                    "title": "修复公开问题",
                    "body": "只包含实现所需上下文。",
                }
            ]
        )

        result = sync_issue(client, 12, plan, apply=False)

        self.assertEqual(result["mode"], "preview")
        self.assertEqual(result["items"][0]["action"], "create")
        client.create_issue.assert_not_called()
        client.link_subissue.assert_not_called()
        client.update_issue.assert_not_called()

    def test_sync_creates_two_repository_subissues_and_is_idempotent(self) -> None:
        parent = issue(
            PUBLIC_REPOSITORY, 12, labels=("enhancement", "status:needs-triage")
        )
        ui = issue(f"{OWNER}/aeloon-lite-ui", 41)
        runtime = issue(f"{OWNER}/aeloon-lite-runtime", 52)
        plan = self.plan(
            [
                {
                    "component": "ui",
                    "repository": f"{OWNER}/aeloon-lite-ui",
                    "title": "UI work",
                    "body": "UI boundary",
                },
                {
                    "component": "runtime",
                    "repository": f"{OWNER}/aeloon-lite-runtime",
                    "title": "Runtime work",
                    "body": "Runtime boundary",
                },
            ]
        )
        client = Mock()
        client.get_issue.return_value = parent
        client.list_subissues.return_value = []
        client.find_marker_issues.return_value = []
        client.create_issue.side_effect = [ui, runtime]

        first = sync_issue(client, 12, plan, apply=True)

        self.assertEqual(first["mode"], "applied")
        self.assertEqual(client.create_issue.call_count, 2)
        self.assertEqual(
            client.link_subissue.call_args_list,
            [call(12, ui["id"]), call(12, runtime["id"])],
        )
        labels = client.update_issue.call_args.kwargs["labels"]
        self.assertIn("enhancement", labels)
        self.assertIn("status:in-progress", labels)
        self.assertIn("component:ui", labels)
        self.assertIn("component:runtime", labels)

        rerun = Mock()
        rerun.get_issue.return_value = parent
        rerun.list_subissues.return_value = [ui, runtime]
        second = sync_issue(rerun, 12, plan, apply=True)

        self.assertEqual([item["action"] for item in second["items"]], ["reuse", "reuse"])
        rerun.create_issue.assert_not_called()
        rerun.link_subissue.assert_not_called()

    def test_sync_recovers_an_unlinked_issue_after_partial_failure(self) -> None:
        parent = issue(PUBLIC_REPOSITORY, 12, labels=("bug",))
        ui = issue(f"{OWNER}/aeloon-lite-ui", 41)
        orphan = issue(f"{OWNER}/aeloon-lite-runtime", 52)
        plan = self.plan(
            [
                {
                    "component": "ui",
                    "repository": f"{OWNER}/aeloon-lite-ui",
                    "title": "UI work",
                    "body": "",
                },
                {
                    "component": "runtime",
                    "repository": f"{OWNER}/aeloon-lite-runtime",
                    "title": "Runtime work",
                    "body": "",
                },
            ]
        )
        client = Mock()
        client.get_issue.return_value = parent
        client.list_subissues.return_value = [ui]
        client.find_marker_issues.return_value = [orphan]

        result = sync_issue(client, 12, plan, apply=True)

        self.assertEqual(result["items"][1]["action"], "recover")
        client.create_issue.assert_not_called()
        client.link_subissue.assert_called_once_with(12, orphan["id"])

    def test_distribution_only_plan_uses_the_public_issue_directly(self) -> None:
        parent = issue(PUBLIC_REPOSITORY, 12, labels=("bug", "status:needs-triage"))
        client = Mock()
        client.get_issue.return_value = parent
        client.list_subissues.return_value = []
        plan = self.plan(
            [
                {
                    "component": "distribution",
                    "repository": PUBLIC_REPOSITORY,
                    "title": "Distribution work",
                    "body": "",
                }
            ]
        )

        result = sync_issue(client, 12, plan, apply=True)

        self.assertEqual(result["items"][0]["action"], "direct")
        client.create_issue.assert_not_called()
        client.link_subissue.assert_not_called()
        labels = client.update_issue.call_args.kwargs["labels"]
        self.assertIn("status:in-progress", labels)
        self.assertIn("component:distribution", labels)

    def test_sync_rejects_conflicting_existing_work_items(self) -> None:
        parent = issue(PUBLIC_REPOSITORY, 12)
        duplicate_a = issue(f"{OWNER}/aeloon-lite-ui", 41)
        duplicate_b = issue(f"{OWNER}/aeloon-lite-ui", 42)
        client = Mock()
        client.get_issue.return_value = parent
        client.list_subissues.return_value = [duplicate_a, duplicate_b]
        plan = self.plan(
            [
                {
                    "component": "ui",
                    "repository": f"{OWNER}/aeloon-lite-ui",
                    "title": "UI work",
                    "body": "",
                }
            ]
        )

        with self.assertRaises(IssueFlowError):
            sync_issue(client, 12, plan, apply=True)
        client.create_issue.assert_not_called()

    def test_reconcile_does_not_count_a_manually_closed_child(self) -> None:
        parent = issue(PUBLIC_REPOSITORY, 12, labels=("status:in-progress",))
        child = issue(f"{OWNER}/aeloon-lite-runtime", 52, state="closed")
        client = Mock()
        client.get_issue.return_value = parent
        client.list_subissues.return_value = [child]
        client.graphql.return_value = {
            "repository": {
                "issue": {"timelineItems": {"nodes": [{"closer": None}]}}
            }
        }

        result = reconcile(client, 12)

        self.assertEqual(result["results"][0]["status"], "pending")
        client.update_issue.assert_not_called()

    def test_reconcile_closes_parent_after_both_merge_closures(self) -> None:
        parent = issue(PUBLIC_REPOSITORY, 12, labels=("bug", "status:in-progress"))
        children = [
            issue(f"{OWNER}/aeloon-lite-ui", 41, state="closed"),
            issue(f"{OWNER}/aeloon-lite-runtime", 52, state="closed"),
        ]
        client = Mock()
        client.get_issue.return_value = parent
        client.list_subissues.return_value = children
        client.graphql.side_effect = lambda _query, variables: {
            "repository": {
                "issue": {
                    "timelineItems": {
                        "nodes": [
                            {
                                "closer": {
                                    "__typename": "PullRequest",
                                    "merged": True,
                                    "baseRefName": "main",
                                    "repository": {
                                        "nameWithOwner": f"{OWNER}/{variables['name']}"
                                    },
                                },
                            }
                        ]
                    }
                }
            }
        }

        result = reconcile(client, 12)

        self.assertEqual(result["results"][0]["status"], "implemented")
        self.assertEqual(client.update_issue.call_count, 2)
        self.assertEqual(client.update_issue.call_args_list[0].kwargs["state_reason"], "completed")
        labels = client.update_issue.call_args_list[1].kwargs["labels"]
        self.assertIn("status:implemented", labels)
        self.assertIn("component:ui", labels)
        self.assertIn("component:runtime", labels)

    def test_reconcile_sweep_closes_a_reopened_implemented_parent(self) -> None:
        parent = issue(PUBLIC_REPOSITORY, 12, labels=("bug", "status:implemented"))
        child = issue(f"{OWNER}/aeloon-lite-ui", 41, state="closed")
        client = Mock()
        client.list_items.side_effect = [[], [parent]]
        client.list_subissues.return_value = [child]
        client.graphql.side_effect = lambda _query, variables: {
            "repository": {
                "issue": {
                    "timelineItems": {
                        "nodes": [
                            {
                                "closer": {
                                    "__typename": "PullRequest",
                                    "merged": True,
                                    "baseRefName": "main",
                                    "repository": {
                                        "nameWithOwner": f"{OWNER}/{variables['name']}"
                                    },
                                },
                            }
                        ]
                    }
                }
            }
        }

        result = reconcile(client)

        self.assertEqual(result["results"][0]["status"], "implemented")
        self.assertEqual(client.update_issue.call_args_list[0].kwargs["state"], "closed")

    def test_collect_maps_private_closing_issue_to_public_parent_and_deduplicates(self) -> None:
        client = Mock()
        client.pages.side_effect = [
            [{"status": "ahead", "commits": [{"sha": "a" * 40}]}],
            [{"status": "ahead", "commits": [{"sha": "b" * 40}]}],
        ]
        pull = {"number": 7, "merged_at": "2026-01-01", "base": {"ref": "main"}}
        client.api.return_value = [pull]
        client.graphql.return_value = {
            "repository": {
                "pullRequest": {
                    "closingIssuesReferences": {
                        "nodes": [
                            {
                                "number": 52,
                                "state": "CLOSED",
                                "repository": {
                                    "nameWithOwner": f"{OWNER}/aeloon-lite-runtime"
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
        client.parent_issue.return_value = issue(PUBLIC_REPOSITORY, 12, state="closed")
        client.get_issue.return_value = issue(
            PUBLIC_REPOSITORY, 12, state="closed", title="用户可见修复"
        )

        result = collect(
            client,
            [
                [f"{OWNER}/aeloon-lite-runtime", "old", "new"],
                [f"{OWNER}/aeloon-lite-runtime", "new", "newer"],
            ],
        )

        self.assertEqual(result, [{"number": 12, "title": "用户可见修复", "url": issue(PUBLIC_REPOSITORY, 12)["html_url"]}])

    def test_annotate_release_is_idempotent(self) -> None:
        client = Mock()
        marker = "<!-- aeloon-release:v1.2.3 -->"
        client.issue_comments.side_effect = [[], [{"body": marker}]]
        issues = [
            {"number": 12, "title": "One", "url": "unused"},
            {"number": 13, "title": "Two", "url": "unused"},
        ]

        result = annotate_release(
            client,
            issues,
            tag="v1.2.3",
            url=f"https://github.com/{PUBLIC_REPOSITORY}/releases/tag/v1.2.3",
        )

        self.assertEqual(result, {"annotated": [12], "skipped": [13]})
        self.assertIn(marker, client.create_comment.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
