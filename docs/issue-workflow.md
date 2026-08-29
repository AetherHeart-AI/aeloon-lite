# Public Issue and private implementation workflow

`AetherHeart-AI/aeloon-lite` is the single public Issue and public Release source. Implementation
work remains in the private UI and Runtime repositories. Native GitHub sub-issues connect the public
request to at most one work item in each affected repository.

## Triage and split

New Bug and Feature forms apply `status:needs-triage`. Use the project-level `aeloon-issue-flow`
Skill to inspect the three code boundaries and preview a split. The Skill must receive explicit user
confirmation before it runs `tools/issue_flow.py sync ... --apply`.

The approved split applies `status:in-progress` and one or more of `component:ui`,
`component:runtime`, and `component:distribution`. A distribution-only change may be implemented by a
public PR that directly closes the parent. When multiple repositories are affected, every repository
must have its own sub-issue.

## Pull requests

A user-visible PR uses all three lines below. `Closes` must target exactly one Issue in the PR's own
repository; that Issue must be a native child of the declared public Issue.

```text
Release-Impact: public
Public-Issue: AetherHeart-AI/aeloon-lite#123
Closes #456
```

Internal refactors, CI, dependencies, and release maintenance use:

```text
Release-Impact: internal
Public-Issue: none
```

Creating a PR establishes the relationship. GitHub closes the work item only when the PR merges into
`main`. The `Public issue policy` check rejects missing, ambiguous, or mismatched declarations.

## Completion and Release notes

Every 15 minutes, the public reconcile workflow checks native sub-issues. A child counts as complete
only when its latest close event identifies a merged PR targeting `main`; manual closure does not
complete the parent. Once every child is complete, the workflow closes the public parent with reason
`completed` and replaces `status:in-progress` with `status:implemented`.

Runtime and unified Desktop publication inspect the actual source commit ranges, find merged PRs and
their closing Issues, then follow native parent links back to closed public Issues. Release entries use
only the public Issue number and title. Private Issue and PR titles or URLs are never published.
Publication adds an idempotent Release-link comment to every included public Issue.

PRs merged before this policy, PRs with `Release-Impact: internal`, and PRs without a public parent are
not backfilled into the Issue update list.

## Automation credentials

The GitHub App `Aeloon Issue Automation` is installed only on `aeloon-lite`, `aeloon-lite-ui`, and
`aeloon-lite-runtime`. It needs Contents read, Pull requests read, and Issues read/write. Actions use
the organization variable `AELOON_ISSUE_APP_ID` and the three-repository organization secret
`AELOON_ISSUE_APP_PRIVATE_KEY`; the default `GITHUB_TOKEN` is intentionally not used for cross-repo
Issue operations.
