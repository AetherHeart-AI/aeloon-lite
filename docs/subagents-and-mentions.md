# Agents, mentions, and delegation

This page used to describe “subagents”. There is only one kind of Agent now.

- To put more than one Agent in a local session, see [Local multi-agent sessions](multi-agent-sessions.md).
- To define a reusable Agent, keep one Markdown file in `<runtime-data-dir>/agents/` or
  `<workspace>/.aeloon-runtime/agents/`. Manage personal Agents from the Agents page.
- `@` in the composer inserts a mention block when you pick an Agent from the menu. Plain text
  `@name` does not wake anyone. `@file:` still names a workspace file.
- The `task` tool still lets an Agent hand a scoped subtask to another definition. The result
  returns only to the caller.
