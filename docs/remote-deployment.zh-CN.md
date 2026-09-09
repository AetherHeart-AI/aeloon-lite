# 远程 Runtime 部署

[English](remote-deployment.md) | 简体中文

本教程以你登录的那个普通用户身份在 Linux 服务器上安装并运行 Aeloon Runtime，然后让 Aeloon
Desktop 连接它。安装和运行 Runtime 不需要 root。

## 1. 检查服务器

需要满足：

- ARM64 或 x86_64 Linux 主机，以及一个普通用户账号；
- Agent 的 Shell 工具需要 Bubblewrap（`bwrap`），并允许使用用户命名空间。如果尚未安装，
  请管理员安装 `bubblewrap` 系统软件包；沙箱不能启动时，Shell 执行保持不可用；
- 在主机防火墙和云安全组中放行 TCP `7420`（或自定义端口）；
- Desktop 能访问的地址：公网 IPv4 或域名、RFC1918 私网地址，或 `100.64.0.0/10`
  CGNAT/Tailscale 地址。不接受回环、链路本地、组播、保留地址和 IPv6。

## 2. 安装 Runtime

每个配对用户都有独立的个人设置和模型凭据。新增用户需要配置自己的模型访问权限，配对不会
复制其他用户的 API 密钥。

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sh
```

安装脚本把稳定版解压到 `~/.local/share/aeloon-runtime/releases/<版本>`，把
`~/.local/share/aeloon-runtime/current` 指向它，并把 `aeloon-runtime` 与 `aeloon-runtime-server`
链接进 `~/.local/bin`。它不会启动任何东西。装完后会打印接下来的两步：怎么运行 Runtime，以及怎么
把它变成 systemd 用户服务。

如果 `~/.local/bin` 还不在 `PATH` 里，先加进去。

## 3. 运行并连接 Desktop

```bash
aeloon-runtime-server run --host runtime.example.com          # 也可以是 IPv4；--port 改端口，默认 7420
```

Runtime 监听所有网卡，使用配对码里钉住指纹的自签名证书，数据放在 `~/.aeloon-lite`。未配对的
Runtime 第一次启动会打印一个有效期十分钟、只能用一次的 `AELOON1-…` 配对码；之后的启动不再打印。

1. 安装并打开 Aeloon Desktop。
2. 选择**连接远程服务器**。
3. 粘贴配对码。

随时可以在另一个终端再出一个码：

```bash
aeloon-runtime-server pair
```

前台运行适合先试一下，`Ctrl-C` 停止。

## 4. 用 systemd 常驻

要让 Runtime 在你退出登录后继续运行，把它做成 systemd **用户**服务。安装脚本已经按你的路径打印过
这份单元文件；把 `<host>` 换成第 3 节的地址：

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/aeloon-runtime.service <<'UNIT'
[Unit]
Description=Aeloon Runtime
Wants=network-online.target
After=network-online.target

[Service]
Type=notify
ExecStart=%h/.local/share/aeloon-runtime/current/bin/aeloon-runtime-server run --host <host>
Restart=on-failure
RestartSec=2s
WatchdogSec=30s

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now aeloon-runtime
loginctl enable-linger "$USER"        # 退出登录后用户服务继续跑
aeloon-runtime-server pair            # 服务起来后，拿配对码
```

单元文件指向 `current`，所以升级后重启一次就生效。常用命令：

```bash
systemctl --user status aeloon-runtime
systemctl --user restart aeloon-runtime
journalctl --user -u aeloon-runtime -f
```

没有 systemd 用户会话的主机（`systemctl --user` 报错，或 `loginctl enable-linger` 被拒绝）可以
用 `nohup`、`tmux` 或任何你顺手的进程管理器跑同一条命令。

## 5. 可选：使用 CA 签发证书

先安装支持 pairing v3 的 Desktop（本发布线为 0.0.25 或更新版本），然后把 PEM 完整证书链和匹配
的私钥传给 `run`——前台运行或写在单元文件的 `ExecStart` 里都可以：

```bash
aeloon-runtime-server run --host runtime.example.com \
  --tls-cert ~/aeloon-tls/fullchain.pem --tls-key ~/aeloon-tls/privkey.pem
```

两个文件你的用户必须可读。证书续期只替换文件，不会刷新运行中进程的 TLS 上下文，请在续期 hook 里
重启 Runtime：

```bash
systemctl --user restart aeloon-runtime
```

## 6. 升级

重新执行安装脚本。它把新版本解压到旧版本旁边，重新指向 `current` 和命令链接，`~/.aeloon-lite`
里的数据、TLS 材料和已配对设备原样不动。然后重启 Runtime。已配对的 Runtime 重启不会再打印配对码。

要回退，把 `current` 指回上一个版本目录再重启。旧版本一直留在
`~/.local/share/aeloon-runtime/releases` 下，不需要了自己删。

证书变化或设备 token 被吊销后，在 Desktop 点击**重新配对**，并粘贴新生成的配对码。修复流程会保留
原连接档案。

## 7. 团队主机：一台 Runtime 服务整个团队

跑起来的这一个 Runtime 就服务所有人。没有一人一个容器，也没有网关：团队连的就是第 3 或第 4 节
那个进程，设备令牌本身说明了来的是谁。把人加进去，把它打印的一次性配对码交给对方，兑换这个码的
设备从此就归到那个人名下。

```bash
aeloon-runtime-server user add alice            # 加入 alice 并打印她的配对码
aeloon-runtime-server user add alice --name "Alice Chen"
aeloon-runtime-server user pair alice           # 之后再出一个新码；一个码对应一台设备
aeloon-runtime-server user list                 # 这台 Runtime 上的所有人
aeloon-runtime-server user remove alice         # 从名册上划掉；设备令牌要另外吊销
```

配对码十分钟过期，只能用一次。`user remove` 只是把人从名册上划掉——如果还要切断他的机器，
用 `aeloon-runtime devices revoke <device-id>` 吊销对应设备。

这份名册就是每个人联系人列表的来源，名册上的人都是管理员：谁都可以加人、改共享的 Agent、
改 Provider——包括全组织的请求发往哪个 endpoint。Provider 全组织共用一份，因此没有按人计量。
这套方案适合一个团队内部，不适合互不信任的多方：大家共用同一台主机，Agent 的 shell 就是以运行
Runtime 的这个用户身份跑的，能读到整个数据目录。不该互相看到对方东西的人，不要放在同一台
Runtime 上。

## 8. 每台 Runtime 各自保存设置

设置属于 Runtime，不属于 Desktop。设置面板读写的是你当前正在使用的那台设备，标题里会写明
是哪一台；设备之间不会复制任何内容。要配置另一台设备，先在侧栏切换过去。

按设备各自保存的内容：Provider 及其密钥、端点、模型与 Header；模型目录和默认模型；Agent
默认设置；技能、Agent、提示模板与上下文文件开关；Web Search 与 Fetch（含 Search 的 API
key）；图片处理；shell 路径；以及 Aeloon Cloud 登录。

因此新配对的 Runtime 从它自己的默认值开始：没有 Provider，也没有登录云账号。在任意一台设备
上配一次即可：这些设置属于组织，不属于设备。

只有该设备处于连接状态时才能读写它的设置：当前设备离线或正在重连时，面板会显示连接错误并
提供重试，而不是展示另一台设备的值。

工作区侧栏展示每台设备的真实连接状态。设备**离线**时，缓存工作区仍会显示且可以点击；
点击后会正常尝试重新连接。

## 9. 卸载

停掉用户服务（如果有），删除版本目录和命令链接，但保留 Runtime 数据：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sh -s -- --yes
```

同时删除 `~/.aeloon-lite` 下的私有 Runtime 数据：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sh -s -- --yes --purge-data
```

每位同事的桌子都在该数据目录内，`--purge-data` 会一并删除。

v0.1.1 及之前的版本装的是 root 所有的系统服务，放在 `/opt/aeloon-runtime` 和
`/var/lib/aeloon-lite`。那种安装要用那个版本的卸载脚本清理：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/v0.1.1/uninstall-server.sh \
  | sudo sh -s -- --yes
```

## 快速排障

- 无法连接：确认 Runtime 在跑（`systemctl --user status aeloon-runtime`，或看它所在的终端），
  再检查 TCP 端口和云安全组。
- 配对码过期：执行 `aeloon-runtime-server pair`。
- 证书被拒绝：检查有效期、主机名/IP SAN、完整证书链以及 Desktop 系统信任库。
- 查看详细日志：`journalctl --user -u aeloon-runtime -n 100 --no-pager`，或前台输出。
- 退出登录后服务就停：执行 `loginctl enable-linger "$USER"`。
- 配对被拒：用 `user list` 确认这个人在名册上；配对码十分钟过期、只能用一次，用
  `user pair <id>` 出一个新的。
