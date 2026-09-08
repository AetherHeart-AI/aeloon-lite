from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
MODULE_PATH = ROOT / ".github/actions/public-issue-policy/validate.py"
SPEC = importlib.util.spec_from_file_location("public_issue_policy", MODULE_PATH)
assert SPEC and SPEC.loader
POLICY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(POLICY)

PUBLIC = "AetherHeart-AI/aeloon-lite"
RUNTIME = "AetherHeart-AI/aeloon-lite-runtime"


def closing(repository: str, number: int) -> dict[str, object]:
    return {"number": number, "repository": {"nameWithOwner": repository}}


def parent(number: int) -> dict[str, object]:
    return {
        "number": number,
        "repository_url": f"https://api.github.com/repos/{PUBLIC}",
    }


class PublicIssuePolicyTests(unittest.TestCase):
    def test_valid_public_pr(self) -> None:
        POLICY.validate_policy(
            "Release-Impact: public\nPublic-Issue: AetherHeart-AI/aeloon-lite#12\nCloses #52",
            RUNTIME,
            [closing(RUNTIME, 52)],
            lambda _repository, _number: parent(12),
        )

    def test_public_pr_rejects_wrong_parent(self) -> None:
        with self.assertRaises(POLICY.PolicyError):
            POLICY.validate_policy(
                "Release-Impact: public\nPublic-Issue: AetherHeart-AI/aeloon-lite#12\nCloses #52",
                RUNTIME,
                [closing(RUNTIME, 52)],
                lambda _repository, _number: parent(13),
            )

    def test_public_pr_requires_a_closing_issue(self) -> None:
        with self.assertRaises(POLICY.PolicyError):
            POLICY.validate_policy(
                "Release-Impact: public\nPublic-Issue: AetherHeart-AI/aeloon-lite#12",
                RUNTIME,
                [],
                lambda _repository, _number: parent(12),
            )

    def test_future_public_pr_validates_declared_native_child(self) -> None:
        POLICY.validate_policy(
            "Release-Impact: public\nPublic-Issue: AetherHeart-AI/aeloon-lite#12\nCloses #52",
            RUNTIME, [], lambda _repository, number: parent(12) if number == 52 else None,
            base_ref="future",
        )

    def test_future_does_not_relax_parent_or_cardinality(self) -> None:
        for declaration, owner in [
            ("Closes #52", 13), ("", 12), ("Closes #52\nFixes #53", 12),
            ("Closes other/repo#52", 12), ("Closes #52, #53", 12),
            ("<!-- Closes #52 -->", 12),
        ]:
            with self.subTest(declaration=declaration, owner=owner):
                with self.assertRaises(POLICY.PolicyError):
                    POLICY.validate_policy(
                        "Release-Impact: public\nPublic-Issue: AetherHeart-AI/aeloon-lite#12\n" + declaration,
                        RUNTIME, [], lambda _repository, _number: parent(owner), base_ref="future",
                    )

    def test_main_still_requires_github_closing_reference(self) -> None:
        with self.assertRaises(POLICY.PolicyError):
            POLICY.validate_policy(
                "Release-Impact: public\nPublic-Issue: AetherHeart-AI/aeloon-lite#12\nCloses #52",
                RUNTIME, [], lambda _repository, _number: parent(12), base_ref="main",
            )

    def test_future_internal_cannot_declare_public_child(self) -> None:
        with self.assertRaises(POLICY.PolicyError):
            POLICY.validate_policy(
                "Release-Impact: internal\nPublic-Issue: none\nCloses #52",
                RUNTIME, [], lambda _repository, _number: parent(12), base_ref="future",
            )

    def test_valid_internal_pr(self) -> None:
        POLICY.validate_policy(
            """Release-Impact: internal
Public-Issue: none
<!--
Release-Impact: public
Public-Issue: AetherHeart-AI/aeloon-lite#12
Closes #52
-->""",
            RUNTIME,
            [],
            lambda _repository, _number: None,
        )

    def test_internal_pr_rejects_public_child_closure(self) -> None:
        with self.assertRaises(POLICY.PolicyError):
            POLICY.validate_policy(
                "Release-Impact: internal\nPublic-Issue: none\nCloses #52",
                RUNTIME,
                [closing(RUNTIME, 52)],
                lambda _repository, _number: parent(12),
            )


if __name__ == "__main__":
    unittest.main()
