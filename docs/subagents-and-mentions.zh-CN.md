# Agent、提及与委派

本页过去把委派叫做「子代理」。现在只有一种 Agent。

- 要在本地会话里放入多个 Agent，见[本地多 Agent 会话](multi-agent-sessions.zh-CN.md)。
- 可复用的定义仍是 `<runtime-data-dir>/agents/` 或 `<workspace>/.aeloon-runtime/agents/` 下的 Markdown。个人 Agent 在 Agent 页管理。
- 输入框里从菜单选中 Agent 会写入 mention 块。纯文本 `@名` 不会唤醒任何人。`@file:` 仍用来点名工作区文件。
- `task` 工具仍可把一段有范围的子任务交给另一个定义，结果只回到调用者。
