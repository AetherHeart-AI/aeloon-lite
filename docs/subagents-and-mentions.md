# Subagents and mentions

Aeloon Desktop 0.0.26 can connect to older Runtime versions for ordinary conversations. Subagent
delegation, the subagent catalog, and workspace file mentions require Runtime 0.1.10 or later. When
`fs.search` is unavailable, Desktop keeps the conversation usable and omits file suggestions.

## Use mentions

Type `@` in the conversation composer to search available agents and files. Narrow the menu to one
source with a namespace:

```text
@agent:researcher compare the two implementations
@file:src/main.ts explain this entry point
@file:"docs/My File.md" summarize this document
```

Select a result with the pointer or the arrow keys and Enter. Desktop inserts a stable namespaced
token; paths containing whitespace, quotes, or backslashes are JSON-quoted automatically. File
results come only from the active conversation's authorized workspace.

The bundled `researcher` agent is read-only and reports file-and-line evidence. Other agents are
available after their definitions are discovered and **Settings → Subagents → Load subagents** is
enabled. A changed setting applies to new operations.

## Define a subagent

Place one Markdown file per agent in either location:

- Runtime data: `<runtime-data-dir>/agents/*.md`, for that Runtime installation.
- Workspace: `<workspace>/.aeloon-runtime/agents/*.md`, for that workspace.

Configured additional resource roots may also contain agent Markdown files. A definition uses YAML
frontmatter followed by its instructions:

```markdown
---
name: reviewer
description: Review a change for correctness and missing tests.
tools: [read, grep, find, ls]
---

Inspect the requested change and return findings ordered by severity with file-and-line evidence.
```

`description` is required. `name` defaults to the filename stem and may contain letters, numbers,
periods, underscores, and hyphens. `tools` is optional; omission requests the parent's available
tool set. A Runtime-data or additional-root definition may also specify `model`; workspace
definitions deliberately ignore `model` so a checked-out project cannot select a provider model.

## Security boundaries

- A child receives only the intersection of its requested tools and the parent's active tools. An
  agent definition cannot grant itself a capability that the parent does not have.
- Child agents cannot delegate another child, and each task has bounded progress and result output.
- File search stays inside the authorized workspace, skips symbolic links, observes repository
  ignore rules when available, and enforces timeout, candidate, and result limits.
- Agent files and mentions do not contain or reveal provider credentials. Model access remains under
  the Runtime's provider configuration and credential handling.
- Workspace definitions are project content. Review them like other project instructions before
  enabling them; disabling **Load subagents** prevents discovered agents from being offered to new
  operations.
