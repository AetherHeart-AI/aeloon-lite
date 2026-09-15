# Colleagues and conversations

English | [简体中文](colleagues.zh-CN.md)

Every Agent in Aeloon is a colleague: it has a name, a role, and a desk of its own. You and a
colleague share one continuous conversation. There is no workspace to choose and no session to
manage.

## The colleague list

- The sidebar lists your colleagues. A fresh install ships four: Assistant, Researcher,
  Requirements Analyst, and Solution Architect. The Group Assistant that hosts rooms is not among
  them; it belongs to groups and is edited there.
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

## Consulting another colleague

- Install the **Consult a colleague** skill on a colleague and it can privately ask another
  colleague a question when it needs their expertise to carry on. Without the skill it never does.
- The colleague you are talking to is still the one answering you: it reads the reply and writes
  its own answer in its own words. The colleague it asked never speaks to you.
- Under the reply, a **Consulted** section shows one card per question: who was asked, how it went,
  and the first line of the answer. Open a card to read the question as it was actually put and the
  answer as it came back. The card is there to read; you cannot join that exchange.
- A consultation is not a conversation. It never appears in your list, and in a group nothing about
  it is said in the room.
- Limits: a colleague asks at most three times per answer, the colleague it asks cannot ask anybody
  else, and stopping the answer stops the question with it. The group assistant never consults; in a
  room it hands work out instead.
- Files the colleague you asked produces are not delivered separately. They share a desk, so the
  colleague answering you decides what to hand over.

## Groups

- A group is a room you and several colleagues share. Every group comes with a **Group Assistant**:
  it works out what you are asking for, splits it up, hands each part to the right colleague, and
  sums up what comes back. When it is the only Agent in the room it does the work itself.
- The group assistant is not in the colleague list and not in the Agent market. You cannot talk to
  it alone, add it, or remove it from a group, because a room always needs one.
- To change how it works, open the group's member list and select it: name, description,
  instructions, model and skills are edited there like any other colleague, and the next answer
  follows the change.
- A group created before the group assistant existed switches over the next time somebody speaks in
  it. The assistant that used to run that room leaves it once it has nothing in hand; everything it
  already said stays in the room.

## Remote Runtimes

With a remote server, the colleagues and their desks live on the server; this machine is only a
client. Installation and pairing are described in [Remote deployment](remote-deployment.md).
