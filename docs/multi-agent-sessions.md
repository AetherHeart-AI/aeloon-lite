# Local multi-agent sessions

A local session is a shared transcript, a member list, the current workspace, and the files that
session produced. You and one or more Agent instances sit in the same conversation. Instances copy
their definition when they join and keep it for the life of the session.

## Members

The first Agent to join is active. Later Agents join silent. An active Agent answers an unmentioned
user message. A silent Agent answers only when a mention block names it. Agent replies never wake
other Agents. Instances that have never spoken can be removed.

`@` in the composer still searches files. Choosing an Agent from the menu writes a mention block;
plain text that looks like `@name` does not route. Matching instances then run one after another in
join order, in the same workspace. Later instances can see earlier replies. A failed instance does
not advance its own read position.

Sessions created before members existed still open as the default assistant. They do not gain a
member list.

## Delegation

An Agent can still hand a scoped subtask to another definition through the `task` tool. That result
returns only to the caller and does not enter the conversation. Delegation is a tool, not a second
kind of Agent.

## Compatibility

This Desktop release can connect to older Runtime versions for ordinary conversations. Mention
routing, session members, and workspace file mentions require a Runtime that advertises
`thread.member`.
When `fs.search` is unavailable, Desktop keeps the conversation usable and omits file suggestions.
