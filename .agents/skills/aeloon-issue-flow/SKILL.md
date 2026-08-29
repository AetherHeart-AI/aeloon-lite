---
name: aeloon-issue-flow
description: "Handle a user-visible Aeloon feature or bug end to end across the distribution, Runtime, and UI repositories: find or create the public parent Issue, synchronize native sub-issues, implement and test the change, merge green PRs, clean branches, and synchronize local checkouts. Use when a user requests an Aeloon product behavior change or asks to process an AetherHeart-AI/aeloon-lite Issue. Do not use for internal-only maintenance or ordinary GitHub Issue authoring outside this three-repository flow."
---

# Aeloon Change Flow

Treat `AetherHeart-AI/aeloon-lite` as the only public Issue and public Release source. Treat
`aeloon-lite-ui` and `aeloon-lite-runtime` implementation details as private. Execute this workflow
without asking the user for approval at intermediate stages.

## Establish the Public Parent

1. If the user supplied a public Issue number or URL, read that Issue, its comments, labels, and
   existing native sub-issues with `gh`.
2. Otherwise search all public Issues for a matching user-visible outcome. Reuse an open matching
   Issue; do not create a duplicate.
3. If no open Issue matches, create one in `AetherHeart-AI/aeloon-lite` before modifying code. Use a
   Release-note-quality title, a body containing the user-visible problem, outcome, compatibility,
   and acceptance criteria, and apply `bug` or `enhancement` plus `status:needs-triage`.

Never put credentials, private logs, private repository details, or unrelated user data in the public
Issue. Creating or reusing the parent is part of the requested workflow; do not pause for confirmation.

## Prepare the Canonical Checkouts

Locate the existing `aeloon-lite`, `aeloon-lite-runtime`, and `aeloon-lite-ui` checkouts in the current
workspace. Make source changes only in these canonical checkouts. Do not create a temporary worktree,
clone, or source copy, and do not implement code under `/tmp` or another temporary directory.

Before editing an affected repository, fetch and prune `origin`, then ensure the implementation branch
starts from current `origin/main` or a commit newer than it. Preserve unrelated user changes. If the
canonical checkout cannot be updated safely because unrelated local changes conflict, stop and report
that exact repository as blocked instead of moving the implementation elsewhere.

## Inspect and Split

1. Inspect the smallest relevant boundary in UI, Runtime, and distribution. Do not mark a repository
   affected merely because the request mentions it.
2. Plan at most one implementation work item for each affected repository. Keep private titles and
   bodies implementation-focused and free of secrets or unrelated user data.
3. For a distribution-only change, use a public PR that directly closes the parent Issue. If two or
   more repositories are affected, represent every affected repository, including distribution, as a
   native sub-issue.

Write a temporary JSON plan outside all repositories only for `issue_flow.py`; this file is workflow
metadata, never an implementation workspace:

```json
{
  "items": [
    {
      "component": "ui",
      "repository": "AetherHeart-AI/aeloon-lite-ui",
      "title": "Implement the UI-side change",
      "body": "Implementation boundary and acceptance notes."
    }
  ]
}
```

From the public repository, preview and validate the exact repository/component mapping, then apply
the same plan immediately without asking for confirmation:

```bash
python3 tools/issue_flow.py sync --issue ISSUE_NUMBER --plan PLAN_FILE
python3 tools/issue_flow.py sync --issue ISSUE_NUMBER --plan PLAN_FILE --apply
```

The tool reuses existing native sub-issues, recovers an unlinked work item, and preserves internal
progress. If it reports duplicate or conflicting work items, stop and report only the conflict. On a
partial API failure, rerun the same plan so its idempotency marker can recover the existing item.

## Implement and Verify

Create a feature branch in each affected canonical checkout and implement the smallest complete
change. Follow dependency order: merge a protocol-producing Runtime change before its UI consumer;
when the UI must ship a newly published Runtime, use a separate internal Runtime version PR, run the
Runtime Release, and wait for the automated UI Runtime-lock PR to merge before rebasing the UI branch.
Do not publish a new stable Desktop version unless the user explicitly requested a Desktop release.

Run the repository's relevant local test, lint, generated-artifact, build, and integration checks.
Treat secrets as unavailable to renderers, public Issues, PR text, events, errors, logs, and test output.

## Submit and Merge PRs

Every user-visible PR must contain exactly one closing Issue in its own repository and these markers:

```text
Release-Impact: public
Public-Issue: AetherHeart-AI/aeloon-lite#123
Closes #456
```

A distribution-only public PR closes the public parent. Internal release, dependency, CI, and
automation PRs use:

```text
Release-Impact: internal
Public-Issue: none
```

Push each branch, create its PR, wait for every required GitHub check, and fix failures on the same
branch. Never merge with a failed or pending required check. Once green, squash merge without asking
for approval. Preserve the dependency order established above.

## Clean Up and Synchronize

After each merge, delete the local and remote feature branch. In every affected canonical checkout,
switch to `main`, fetch and prune `origin`, and fast-forward to `origin/main`. Remove the temporary plan
file and verify the working tree is clean and `HEAD` equals `origin/main`.

Run or wait for the public reconciliation workflow, then verify that every child was closed by its
merged PR and the public parent is closed as `completed` with `status:implemented`.

Report the public parent, affected components, merged PRs, verification results, release result if any,
and final local synchronization state. Share private Issue or PR links only with a user who already has
access; never copy private titles, bodies, or URLs into public comments or public Actions logs.

See `docs/issue-workflow.md` in `aeloon-lite` for marker validation, completion semantics, and Release
behavior.
