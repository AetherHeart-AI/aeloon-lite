---
name: aeloon-issue-flow
description: "Triage an Aeloon public Issue, inspect the UI, Runtime, and distribution repository boundaries, propose one private work item per affected repository, and safely synchronize approved native sub-issues. Use when splitting, syncing, retrying, or checking cross-repository work originating in AetherHeart-AI/aeloon-lite. Do not use for ordinary GitHub Issue authoring unrelated to this three-repository flow."
---

# Aeloon Issue Flow

Treat `AetherHeart-AI/aeloon-lite` as the only public Issue and public Release source. Treat
`aeloon-lite-ui` and `aeloon-lite-runtime` implementation details as private.

## Analyze the Issue

1. Locate the three repositories from the current workspace. Read the public Issue, its comments,
   labels, and existing sub-issues with `gh`; never echo authentication values.
2. Inspect the smallest relevant code boundary in UI, Runtime, and distribution. Do not assume that
   a component is affected merely because the Issue mentions it.
3. Propose at most one work item for each affected repository. Make each title implementation-focused
   and each body sufficient for private work without copying secrets, credentials, private logs, or
   unrelated user data.
4. Keep the public Issue title suitable for Release notes. Recommend `bug` or `enhancement` and the
   affected `component:*` labels, but do not rewrite the public report without being asked.

For a distribution-only fix, prefer a public PR that directly closes the public Issue. If two or more
repositories are affected, represent every repository—including distribution—as a native sub-issue.

## Preview Before Writing

Write the proposed plan to a temporary JSON file outside all repositories:

```json
{
  "items": [
    {
      "component": "ui",
      "repository": "AetherHeart-AI/aeloon-lite-ui",
      "title": "Implement the UI-side fix",
      "body": "Implementation boundary and acceptance notes."
    }
  ]
}
```

Run the deterministic preview from the public repository:

```bash
python3 tools/issue_flow.py sync --issue ISSUE_NUMBER --plan PLAN_FILE
```

Explain the proposed split and preview result. Ask for explicit user confirmation immediately before
any GitHub write. A request to analyze, triage, or propose a split is not confirmation to apply it.

## Apply an Approved Plan

After confirmation, run the same command with `--apply`. The tool reuses existing native sub-issues,
recovers a previously created but not yet linked work item, and never overwrites internal progress:

```bash
python3 tools/issue_flow.py sync --issue ISSUE_NUMBER --plan PLAN_FILE --apply
```

If the tool reports duplicate or conflicting work items, stop and show only the repository/component
conflict. Do not delete issues or retry creation manually. On a partial API failure, rerun the same
approved plan so the hidden idempotency marker can recover the existing item.

When reporting success, identify the public parent and affected components. Share private Issue links
only with a user who already has access; never copy private titles, bodies, or URLs into public comments
or public Actions logs.

See `docs/issue-workflow.md` in `aeloon-lite` for PR markers, completion semantics, and Release behavior.
