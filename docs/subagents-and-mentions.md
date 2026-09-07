# Agents, mentions, and delegation

This page used to describe “subagents”. There is only one kind of Agent now.

- To put more than one Agent in a local session, see [Local multi-agent sessions](multi-agent-sessions.md).
- To define a reusable Agent, keep one Markdown file in `<runtime-data-dir>/agents/` or
  `<workspace>/.aeloon-runtime/agents/`. Manage personal Agents from the Agents page.
- `@` in the composer inserts a mention block when you pick an Agent from the menu. Plain text
  `@name` does not wake anyone. `@file:` still names a workspace file.
- An Agent passes the conversation to another member with the `transfer` tool. That member answers
  you directly; nothing returns to the Agent that passed it on.
