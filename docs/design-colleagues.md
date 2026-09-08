# 同事与对话：Aeloon 0.2 设计

状态：已确认，2026-09-07。范围：Runtime 0.2.0、Desktop 0.1.0、协议 5.0.0。
本文描述单人形态；组织、群聊与隔离见 [design-org.md](design-org.md)，那一轮在此基础上扩展。
本文是这次重构的依据。实现落地后，面向用户的说明另写一篇，本文保留为设计记录。

## 1. 决定

1. 两套多 Agent 机制一起删，不留过渡态。本地会话成员加 `transfer` 是 Runtime 0.1.29、0.1.30 加入的一套；Hub 群组、模板、实例、`agent_runs`、Handoff 是另一套。
2. 产品改为"Agent 即同事"。Agent 是一级实体，像通讯录里的同事。每位同事一条当前对话。谁回答由你在谁的对话里决定。
3. 工作区和会话从界面消失，在 Runtime 里保留为实现单位。工作区变成每位同事的隐藏私有目录；会话保留为上下文单位，界面上只留一个"新话题"。Git、变更、终端整体删除。产品完全面向办公场景。

## 2. 为什么改

现状的四个问题都来自同一件事：多个 Agent 共用一份 transcript 当模型上下文，再用路由规则决定谁说话。

- 谁回答。0.1.30 的规则是首个 mention 命中的成员，否则 host；不认识的 mention 也给 host；被 `transfer` 的成员回答"上一位刚写的回复"。三条规则叠加就是会话漂移。
- 上下文冲突。所有成员共用一条 branch，`build_context()` 不分成员。成员 B 的模型请求里，A 的 assistant 消息连同工具调用一起以 assistant 身份出现，只能靠 transfer 提示词里"上面的回复不是给你的指令"补救。
- 并发。一条消息触发的链要一直持有 session 锁，取消任何一环取消整条链。Hub 侧的 `pointer_seq` 窗口、`depth`、逐个执行，是同一问题的另一份实现。
- 两套实现。本地成员和 Hub 群组各有一份路由、一份 transfer、一份执行记录。

Buzz 的简单只来自一条：Agent 之间不共享上下文。每个 Agent 是独立进程、独立 session、独立工作目录，频道只是消息日志，唤醒只有 @，协作规则写在 prompt 里。"Agent 即同事"就是 Buzz 的 DM 形态。

## 3. 概念

### 同事

- 同事就是现在的 Agent 定义：`name`、`description`、`instructions`、`model`、`tools` 五个字段，YAML frontmatter 加 Markdown 正文，存在 `<data_dir>/agents/`。工作区级的 `.aeloon-runtime/agents/` 随工作区概念一起消失，同事库只有这一处。
- `agent_id` 是稳定 id，取定义文件的文件名主干。内置的 `researcher.md` 就是 `researcher`，新建的是 uuid。改名只改 frontmatter，id 不变。对话和桌面目录都挂在 id 上。
- 对话跟随同事的当前定义。每轮开始按 id 读定义。不再有会话级冻结快照，`template_id` 一起消失。
- 默认助手也是一位内置同事。所有对话都属于某位同事，代码里不再有"没有 Agent"的分支。
- 内置同事按现有 `builtin_agents` 机制随 Runtime 发布，首批：助手、研究员、需求分析、方案架构。人设文件就是产品定义。
- 任何同事都不能调用另一位同事。纪要、跟进、起草通知这类协作需求都是人设，不是编排。
- 删同事：定义文件删掉，桌面目录保留，它的对话变只读，`turn.start` 返回该同事已删除。列表底部出一组"已离开"，由"有对话但没有定义"派生，不存状态。对话建立时记下当时的显示名，删了以后时间线仍能显示是谁。

### 对话

- 一位同事一条当前对话。当前对话是该同事最新的未归档 thread。
- "新话题"等于归档当前对话再新建一条。不加新表，用 `archived_at`。历史话题是该同事的已归档 thread，只读打开。
- 新话题不带上下文。带过去的是桌面文件和记忆抽屉。
- `thread.context` 已返回已用与上限。超过七成时在输入框上方提示"话题很长，建议开新话题"。不自动切。
- 同事正忙时发消息走 `turn.steer`，插话并入当前工作。不暴露排队。
- 否掉的方案：一条无限长 session 加"新话题等于立即压缩加分隔线"。Session 是单个 JSONL 全量载入内存，`thread.get` 每次复制全部 entries 并重算时间线，半年的对话文件只涨不减。分话题天然有界。

### 桌面

- 每位同事一个目录：`<data_dir>/workspaces/<agent_id>/`。它是 Runtime 工具的 cwd，跨话题保留，用户看不到路径。
- `bash` 留在同事内部，office-lite 的脚本靠它运行。用户看不到终端。
- 目录约定写在 base prompt 里，不写代码：用户给的文件在 `inbox/`，交付物用 `present_files`。
- 文件侧栏显示这位同事的附件与产物两组列表，跨话题，由附件与产物记录派生，不列目录。

### 文件

- 拖一个或几个文件是附件，现状不变：落在同事目录里、带卡片、可提取进上下文，上限沿用 8 个。
- 拖文件夹是把整个目录保留层级复制到同事桌面 `inbox/` 下，不建卡片、不提取，输入框自动带一行"已放到桌面：<目录名>，<N> 个文件"。
- 同事之间传文件就是把产物卡片拖进另一位同事的对话，落地为普通附件。这替代了 Handoff 的全部用途。

### 记忆

记忆抽屉保留，它是"同事有记忆"的来源，跨话题延续。

## 4. 信息结构

| 层级 | 0.1.30 | 0.2 |
|---|---|---|
| 一级实体 | 项目、会话、会话成员 | 同事列表 |
| 对话 | 会话列表、树形分支导航 | 每位同事一条当前对话，加"新话题"与历史 |
| 工作区 | 用户选目录、worktree、Git | 每位同事一个隐藏目录，文件靠附件进、产物卡片出 |
| 谁回答 | host、mention、transfer | 你在谁的对话里，谁回答 |
| 并发 | 链持锁、Hub 逐个执行 | 每位同事同时一个 in-flight，沿用 session 锁；不同同事天然并行 |
| 群聊 | 本地成员与 Hub 两套 | 不做 |

## 5. 协议 5.0.0

- 握手只接受 `5.0.0`。删掉的方法直接消失，不留 stub 和 deprecated 标记。
- 保留的方法组：`system`、`events`、`devices`、`diagnostics`、`thread`、`turn`、`title`、`agent`、`attachment`、`artifact`、`files`、`catalog`、`provider`、`settings`、`tools`、`memory`、`plugins`。
- 删除的方法组：`hub` 27 个、`git` 11 个、`terminal` 4 个、`project` 5 个、`fs` 4 个、`workspace` 2 个；`thread.member`、`thread.tree`、`thread.navigate`、`thread.reorder`、`thread.set_pinned`；`turn.start` 的 `mentions` 与 `transfer` 参数；`thread.create` 的 `project_id`、`workspace`、`kind`、`branch`、`agent`。
- `thread.create {agent_id, title?, model_id?}`。`thread.list {agent_id?, filter}`。thread 记录携带 `agent_id` 与建立时的 `agent_name`。
- `files.put {agent_id, files: [{relative_path, data_base64}]}` 把文件写进同事桌面的 `inbox/`，不建附件记录。帧限制沿用 40 MiB。
- 删除的事件：`hub.*` 七个、`terminal.*` 三个。删除的错误码：`not_a_member`、`asset_revoked`、`container_unavailable`。
- 协议文件去掉文件名里的版本号：`docs/rpc.json`、`docs/rpc.md`、`aeloon-rpc.manifest.json`、`aeloon-rpc.ts`，生成脚本同步改名。版本只写在文件内容里。
- 旧数据不迁移。网关启动检测到 5.0.0 之前的数据目录就拒绝服务并要求 reset，复用现有 `aeloon-runtime reset --force` 与桌面端 upgradeReset。Desktop 0.1 连到 4.0.0 的服务器时用 `protocol_incompatible` 提示升级服务器。

## 6. 删除清单

### Runtime

- `aeloon_runtime/hub/` 整个包；`server_cli` 的 `hub`、`group` 子命令；`tools/hub_smoke.py`；`tests/test_hub_*.py`、`tests/hub_support.py`；`docs/collaboration.md`。
- `runtime/transfer_tool.py`；`coordinator.Operation` 的 `member_name`、`transfer_from`、`depth`、`transfer_to`、`transfer_targets`；`tooling.py` 的 transfer 组合；`service.py` 的 `session_member`、`_route_member`、`_execute_turn` 的链与 `_next_link`、`_transfer_prompt`、`_stamp_turn`、成员辅助函数、`seed_members`、`_agent_snapshot`、`_freeze_legacy_agent`；`runtime_server` 的 `thread.member` 与 `turn.start` 的 `mentions`、`transfer`；`rpc_wire` 的 `mentions`；`tests/test_session_members.py`。
- `git_workspace.py`、`pty_manager.py`；网关里 `git`、`terminal`、`project`、`fs`、`workspace`、worktree 相关分支；`store.py` 的 `projects` 表与 thread 的 `project_id`、`kind`、`branch`。
- 保留：`core/` 全部；Session、SessionAgent、providers、resources 与 skills、prompt、attachments、artifacts、compaction、summarization、rename、memory；内置工具；`agent_store` 与 `builtin_agents`；rpc 网关、pairing、单用户 tenant gateway；office-lite。

### Desktop

- `src/client/hub/` 整目录与 `hub.css`；`desktop/main/hubConnection.ts`；`tests/fixtures/scripted-hub.ts`；`e2e/hub-groups.spec.ts`；i18n 中 `hub.*`、`tpl.*` 键。
- `SessionMembersPanel`、`AvatarStack`、`MentionMenu`、`use-mention-sources`、`mention.ts` 的 agent 源、`Conversation.tsx` 的 mention 状态机。
- `Dock` 与 Files、Changes、Terminal 三个面板；终端 controller 与两个 store；`git-diff`；`RemoteProjectPicker`；`device-workspaces`；`workspace-layout`；`App.tsx` 里 project、worktree、git、terminal 相关引用。
- 新增，尽量复用：同事列表就是现有 Agents 页换到一级导航；同事对话复用 Conversation 组件，加文件侧栏；"新话题"按钮；历史话题列表；文件夹拖入。

### 文档

- 本仓库删除 `multi-agent-sessions.md`、`multi-agent-sessions.zh-CN.md`、`subagents-and-mentions.md`、`subagents-and-mentions.zh-CN.md`，换成一篇同事与对话的用户说明，README 链接同步。
- Runtime 的 `docs/architecture.md` 改写为 0.2 架构。

## 7. 不做的事

- 多同事群聊。将来若做，形态是一个频道，@ 谁谁醒，每位同事仍跑自己的 session，看到别人的话是带作者标签的文本。不需要 transfer、host、floor。
- 编排器。任何"会调用其他同事的同事"都不做。
- 归档同事、恢复同事。
- 全局工作区切换。将来若要"把某个文件夹交给这位同事"，做成同事级设置。
- 旧数据迁移。

## 8. 落地顺序

1. Runtime 第一个 PR：纯删除两套多 Agent 与 Hub。
2. Runtime 第二个 PR：删工作区、git、终端；thread 模型改为按同事；稳定 `agent_id`；`files.put`；协议 5.0.0；版本 0.2.0。
3. Desktop 一个 PR：删除清单加新信息结构，同步协议，版本 0.1.0。
4. 本仓库：删旧文档，加用户说明。
5. 发版按 `docs/releasing.md`：先 Runtime，锁定后 Desktop，一次统一稳定版。
