# Colleagues and conversations

English | [简体中文](colleagues.zh-CN.md)

Every Agent in Aeloon is a colleague: it has a name, a role, and a desk of its own. You and a
colleague share one continuous conversation. There is no workspace to choose and no session to
manage.

## The colleague list

- The sidebar lists your colleagues. A fresh install ships four: Assistant, Researcher,
  Requirements Analyst, and Solution Architect.
- The Agents page adds a colleague, edits a persona (name, description, instructions, model,
  available tools), or deletes one.
- Edits apply immediately: the colleague's next answer follows the new persona. After a colleague is
  deleted its conversations stay readable, but nothing can be sent to it any more.

## Conversations and new topics

- Opening a colleague shows the current conversation; just type.
- When a topic has grown long, press **New topic**. The old topic is archived under that colleague's
  history and stays readable; the new topic starts empty, while the colleague's desk files and memory
  remain.
- You can send while the colleague is busy; the message is woven into the current work.

## Files

- Dropping files into the conversation attaches them to that colleague: they appear as cards and
  their content can enter the conversation.
- Dropping a folder copies it as-is into the colleague's desk under `inbox/`: no cards, no
  conversation budget, and the message lists what was delivered. Use it for a batch of documents.
- Files a colleague delivers appear as artifact cards you can open or save. Dragging an artifact card
  into another colleague's conversation hands the file over.
- The **Files** panel lists the attachments this colleague received and the artifacts it delivered.

## Remote Runtimes

With a remote server, the colleagues and their desks live on the server; this machine is only a
client. Installation and pairing are described in [Remote deployment](remote-deployment.md).
