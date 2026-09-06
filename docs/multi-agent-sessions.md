# Local multi-agent sessions

A local session is a shared transcript, a member list, the current workspace, and the files that
session produced. You and one or more Agent instances sit in the same conversation. Instances copy
their definition when they join and keep it for the life of the session.

## Members

One floor, one speaker. The session has a host: the first Agent in the member list. A message
reaches exactly one Agent -- the first one a mention block names, or the host when it names none.
Naming several reaches only the first; the rest stay in the message as ordinary content, where the
Agent holding the floor can see them. Agent replies never wake other Agents. Instances that have
never spoken can be removed, and any member can be made the host.

`@` in the composer still searches files. Choosing an Agent from the menu writes a mention block;
plain text that looks like `@name` does not route.

## Passing the floor

While it holds the floor, an Agent can call `transfer` to pass the conversation to another member.
That member answers with the same transcript in front of it, in the same workspace, and can pass it
on again. A turn that ends without transferring returns the floor to you, and nothing else runs.

The floor changes hands at most four times per message. At the limit `transfer` is simply not
offered, so the Agent holding the floor answers and the chain ends. Cancelling the Agent that holds
the floor ends the chain too. A failed instance does not advance its own read position.

## Compatibility

Sessions created before members existed still open as the default assistant. They do not gain a
member list, and nothing is offered to transfer to.

This Desktop release can connect to older Runtime versions for ordinary conversations. Mention
routing, session members, and workspace file mentions require a Runtime that advertises
`thread.member`. A Runtime older than this release does not accept `set_host` and cannot pass the
floor. When `fs.search` is unavailable, Desktop keeps the conversation usable and omits file
suggestions.
