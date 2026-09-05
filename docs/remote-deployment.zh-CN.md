# 远程 Runtime 部署

[English](remote-deployment.md) | 简体中文

本教程用于在 Linux 服务器安装 Aeloon Runtime，并让 Aeloon Desktop 连接该服务器。

## 1. 检查服务器

需要满足：

- ARM64 或 x86_64 Linux 主机，PID 1 必须是 systemd；
- root 或 `sudo` 权限；
- 放行 TCP `7420`（或自定义端口）；
- Desktop 能访问的公网 IPv4、RFC1918 私网地址，或 `100.64.0.0/10` CGNAT/Tailscale 地址。

```bash
ps -p 1 -o comm=
systemctl is-system-running
```

第一条命令必须输出 `systemd`。PID 1 为 `bash` 的精简容器不能使用服务安装器。

## 2. 安装 Runtime

公网服务器且可自动检测地址时：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh
```

显式指定地址、端口和工作区：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh -s -- \
      --host runtime.example.com \
      --port 7420 \
      --workspace-root /srv/aeloon-workspaces
```

局域网或 Tailscale 部署时，通过 `--host` 指定 Desktop 可访问的地址，例如
`192.168.1.20` 或 `100.64.0.8`。不接受回环、链路本地、组播、保留地址和 IPv6。

需要同时在主机防火墙和云安全组中放行所选 TCP 端口。安装器会处理能够管理的活动
UFW/firewalld 规则，但无法修改云厂商安全组。

## 3. 连接 Desktop

安装成功后会打印二维码和有效期十分钟、仅可使用一次的 `AELOON1-…` 配对码。

1. 安装并打开 Aeloon Desktop。
2. 选择**连接远程服务器**。
3. 扫描二维码或粘贴完整配对码。

配对码过期后无需重装，执行以下命令生成新码：

```bash
sudo aeloon-runtime-server pair
```

## 4. 可选：使用 CA 签发证书

先安装支持 pairing v3 的 Desktop（本发布线为 0.0.25 或更新版本），然后同时传入 PEM
完整证书链和匹配私钥：

```bash
sudo install -d -o root -g aeloon -m 0750 /srv/aeloon-tls
sudo install -o root -g aeloon -m 0640 /source/fullchain.pem /srv/aeloon-tls/fullchain.pem
sudo install -o root -g aeloon -m 0640 /source/privkey.pem /srv/aeloon-tls/privkey.pem

curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh -s -- \
      --host runtime.example.com \
      --tls-cert /srv/aeloon-tls/fullchain.pem \
      --tls-key /srv/aeloon-tls/privkey.pem
```

`aeloon` 服务用户必须能读取这两个文件，并能穿过所有父目录。不要把私钥设为全局可读。
`/etc/letsencrypt/live` 的默认权限通常过严，建议使用受保护的 `root:aeloon` 目录，或由
证书管理器的 deploy hook 同步证书。

证书续期不会刷新运行中进程的 TLS 上下文，请在续期 hook 中同步上述受保护副本，然后
重启服务：

```bash
sudo systemctl restart aeloon-runtime.service
```

## 5. 日常管理与升级

```bash
aeloon-runtime-server status              # systemd 状态
sudo aeloon-runtime-server status         # 额外显示版本、端点和设备数
aeloon-runtime-server logs
sudo /opt/aeloon-runtime/upgrade           # 升级到当前稳定版 Runtime
sudo aeloon-runtime-server rollback        # 回滚到上一个托管版本
```

升级会保留 Runtime 数据、工作区配置、TLS 路径和已配对设备。已有设备时，升级或回滚不会
再次打印配对码。

证书变化或设备 token 被吊销后，在 Desktop 点击**重新配对**，并粘贴服务器新生成的配对码。
修复流程会保留原连接档案。

## 6. 团队主机：一人一个 Runtime 容器

一台 Docker 主机可以在单个 TLS 端口后面为每个人运行一个相互隔离的 Runtime。每个租户拥有
自己的容器、数据卷与工作区卷、设备列表和配对码。主机进程 `aeloon-gateway.service` 在一个
端口上终止 TLS，把 `wss://HOST:7420/<slug>` 经回环地址转发到对应容器，并钉扎该容器自己的
证书。

需要：带 systemd 与 Docker 的 Linux、root 权限、在主机上构建好的 Runtime 镜像（在 Runtime
源码目录执行 `docker build -f Dockerfile.runtime -t aeloon-runtime:dev .`）、在主机防火墙和云
安全组放行 TCP `7420`（或 `--port` 指定的端口），以及比 0.0.35 更新的 Desktop（旧版本会拒绝
带路径的端点）。

```bash
sudo aeloon-runtime-server tenant init --host 47.94.133.59 --image aeloon-runtime:dev \
     --proxy http://172.17.0.1:7890         # 所有容器共用的出网代理，可选
sudo aeloon-runtime-server tenant add alice          # 创建卷、容器并打印配对码
sudo aeloon-runtime-server tenant pair alice         # 之后再出一个新码；一个码对应一台设备
sudo aeloon-runtime-server tenant list               # 状态、运行时长、在线设备、CPU、内存、磁盘
sudo aeloon-runtime-server tenant status alice       # 单个租户的同样信息，外加设备列表
sudo aeloon-runtime-server tenant logs alice -f
sudo aeloon-runtime-server tenant stop alice         # 也有 start、restart
sudo aeloon-runtime-server tenant remove alice       # 保留卷和端口；`add` 可以恢复
sudo aeloon-runtime-server tenant purge alice --yes  # 删除容器、卷和状态
```

`tenant init` 还接受 `--port`、`--memory`、`--cpus`、`--pids`（租户默认值，`tenant add` 可以
覆盖）。它会在 `~/.aeloon-runtime/gateway/tls` 下生成自签的网关证书，并把指纹写进每个配对码；
传入 `--tls-cert` 与 `--tls-key` 则改用 CA 签发的证书。CA 证书续期时替换文件后执行
`sudo systemctl restart aeloon-gateway` 即可。重复执行 `tenant init` 会沿用已有证书，已配对
的设备不受影响。

每台 Runtime 各自保存自己的设置、Provider 与密钥（见下一节）。可以用
`tenant add --config-template config.json` 预置：这是一份 Runtime 的 `config.json`，其中的
Provider id 需要与团队默认模型所引用的一致。各租户共用主机内核，且在容器内使用相同的
uid，因此这套方案适合同一个团队内部使用，不适合互不信任的多方共用一台机器。

在网关出现之前就已运行租户的主机：重新执行 `tenant init`，再对每个租户执行
`tenant pair <slug>`（端点变了，所有人需要重新配对）。方便时用 `tenant remove` 加
`tenant add` 重建容器，让它们不再各自发布公网端口，并在安全组里关掉那些端口。

### 群组与 Hub

升级宿主机 Runtime 后，沿用现有公网地址和端口重新运行 `tenant init`。它保留证书和租户，
在 `team.json` 补充 Hub 配置，并更新网关 unit 的可写状态目录。`/hub` 复用现有 TLS 端口；
Desktop 使用当前租户的设备 token 连接。本地连接隐藏协作入口，群容器不向 Desktop 直接开放。

```bash
# 模板保存群容器模型和提供商配置，权限应为 0600。
aeloon-runtime-server tenant init --host example.com --port 7420 \
  --hub-port 42000 --group-config-template /root/group-config.json
aeloon-runtime-server group add design --owner alice --member bob --title '设计组'
aeloon-runtime-server group list --json
aeloon-runtime-server group members design add carol
```

Hub 需要 root 和本机 dockerd，以便直接读取用户租户 data 卷中的设备凭证。不支持 rootless
或远程 Docker。用户身份就是租户 slug，`hub` 为保留字，群组与用户共享 slug 命名空间。
成员可配置 Agent，只有群主能增删成员。宿主机配置群模型模板后，任意租户用户均可在 Desktop 建群。

CLI 首次使用普通租户配对码登录，之后复用保存在本机的凭证：

```bash
aeloon-runtime hub login --pairing 'AELOON1-…'
aeloon-runtime hub conversations
aeloon-runtime hub agents design add --file writer.md
aeloon-runtime hub send design '起草方案' --mention agent:writer
aeloon-runtime hub tail design --follow --deltas
aeloon-runtime hub handoff create --from-conversation design --select 1-3 --no-files
aeloon-runtime hub forward ASSET_ID --to dm:alice:bob
aeloon-runtime hub card attach ASSET_ID --thread THREAD_ID --text '审阅这些上下文'
aeloon-runtime hub handoff revoke ASSET_ID
```

先用 `hub dm bob` 建立用户单聊。导出私人会话用 `handoff create --from-thread THREAD_ID`。
`--select` 在私人会话中按从 1 开始的轮次选择，在共享会话中按消息 seq 选择。
`--file` 指定文件 ID（私人产物使用路径），`--no-files` 不包含文件。
只有显式 mention 块触发 Agent，普通文本中的 @ 和卡片内部旧提及均不会触发。
每个 Agent 使用独立项目目录和 thread，跨环境文件通过消息传递。

`team.json` 默认配置：

| 字段 | 默认值 | 说明 |
|---|---:|---|
| `hub_port` | 42000 | 回环监听，不得与网关或租户端口 41000–41999 重叠 |
| `hub_idle_stop_s` | 1800 | 群容器空闲停止秒数；0 禁用空闲停止 |
| `hub_file_quota_bytes` | 1073741824 | 每用户累计上传逻辑字节数，包括产物及快照保留文件 |
| `group_config_template` | null | 新群必需的模型配置模板 |

单文件限制 25 MiB，消息每页最多 200 条。同内容文件复用不可变 blob，但每次上传引用均计入
所属用户配额。根据磁盘容量配置正数配额，调低配额不会阻止读取现有文件。修改配置后重启网关。
群容器停止时仍能读取消息和卡片，下一次提及 Agent 会自动启动容器。失败或取消不推进消息指针；
Hub 重启会将中断运行标为失败，重新提及可重试这段上下文。

`group remove GROUP` 保留卷和 Hub 历史。`group purge GROUP --yes` 永久删除容器、卷和会话，
须先取消排队或运行中的任务。清理回收无引用 blob，冻结资产引用的文件继续保留。
撤销阻止接收者后续读取，无法收回已经下载或加入 Agent 上下文的副本。
备份时使用 SQLite backup API 备份数据库，再复制 `hub/files/`，同时保留租户状态和卷；
不要只复制正在使用 WAL 的数据库主文件。

```bash
journalctl -u aeloon-gateway -n 100 --no-pager
aeloon-runtime-server group status design
aeloon-runtime-server group logs design
aeloon-runtime hub runs design
aeloon-runtime hub run cancel RUN_ID
```

Hub 入口缺失时，检查宿主机 Runtime 版本、网关 unit 的 `ReadWritePaths`、回环端口和本机
Docker 权限。`not_a_member` 表示当前成员资格不足，`asset_revoked` 表示资产已撤销，
`container_unavailable` 表示群执行环境不可用。tail 断线后用 `--after LAST_SEQ` 补齐。

## 7. 每台 Runtime 各自保存设置

设置属于 Runtime，不属于 Desktop。设置面板读写的是你当前正在使用的那台设备，标题里会写明
是哪一台；设备之间不会复制任何内容。要配置另一台设备，先在侧栏切换过去。

按设备各自保存的内容：Provider 及其密钥、端点、模型与 Header；模型目录和默认模型；Agent
默认设置；技能、子代理、提示模板与上下文文件开关；Web Search 与 Fetch（含 Search 的 API
key）；图片处理；shell 路径；以及 Aeloon Cloud 登录。

因此新配对的 Runtime 从它自己的默认值开始：没有 Provider，也没有登录云账号。团队主机上的
租户可以用 `tenant add --config-template config.json` 预置（见上一节）。

只有该设备处于连接状态时才能读写它的设置：当前设备离线或正在重连时，面板会显示连接错误并
提供重试，而不是展示另一台设备的值。

工作区侧栏展示每台设备的真实连接状态。设备**离线**时，缓存工作区仍会显示且可以点击；
点击后会正常尝试重新连接。

## 8. 卸载

删除服务与托管版本，但保留 Runtime 数据和工作区：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes
```

同时删除 `/var/lib/aeloon-runtime` 下的私有 Runtime 数据：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes --purge-data
```

已配置工作区始终保留。

## 快速排障

- 无法连接：检查 `systemctl status aeloon-runtime`、TCP 端口和云安全组。
- 配对码过期：执行 `sudo aeloon-runtime-server pair`。
- 证书被拒绝：检查有效期、主机名/IP SAN、完整证书链以及 Desktop 系统信任库。
- 证书文件不可读：使用 `sudo -u aeloon test -r 路径` 检查读取权限，并检查父目录穿越权限。
- 查看详细日志：执行 `aeloon-runtime-server logs`，或
  `journalctl -u aeloon-runtime.service -n 100 --no-pager`。
- 租户网关：查看 `systemctl status aeloon-gateway` 与
  `journalctl -u aeloon-gateway -n 100 --no-pager`。`404` 表示路径对应的租户不存在、已移除，
  或是在 `tenant pair` 记录指纹之前配对的；`502` 表示容器已停止或证书已变化（重新执行
  `tenant pair <slug>`）。
