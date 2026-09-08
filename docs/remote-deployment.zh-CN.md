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

显式指定地址和端口：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh -s -- \
      --host runtime.example.com \
      --port 7420
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

升级会保留 Runtime 数据、TLS 路径和已配对设备。已有设备时，升级或回滚不会
再次打印配对码。

证书变化或设备 token 被吊销后，在 Desktop 点击**重新配对**，并粘贴服务器新生成的配对码。
修复流程会保留原连接档案。

## 6. 团队主机：一台 Runtime 服务整个团队

装好的这一台 Runtime 就服务所有人。没有一人一个容器，也没有网关：团队连的就是第 3 节那个
systemd 服务，设备令牌本身说明了来的是谁。把人加进去，把它打印的一次性配对码交给对方，兑换
这个码的设备从此就归到那个人名下。

```bash
sudo aeloon-runtime-server user add alice            # 加入 alice 并打印她的配对码
sudo aeloon-runtime-server user add alice --name "Alice Chen"
sudo aeloon-runtime-server user pair alice           # 之后再出一个新码；一个码对应一台设备
sudo aeloon-runtime-server user list                 # 这台 Runtime 上的所有人
sudo aeloon-runtime-server user remove alice         # 从名册上划掉；设备令牌要另外吊销
```

配对码十分钟过期，只能用一次。`user remove` 只是把人从名册上划掉——如果还要切断他的机器，
用 `aeloon-runtime devices revoke <device-id>` 吊销对应设备。

这份名册就是每个人联系人列表的来源，名册上的人都是管理员：谁都可以加人、改共享的 Agent、
改 Provider——包括全组织的请求发往哪个 endpoint。Provider 全组织共用一份，因此没有按人计量。
这套方案适合一个团队内部，不适合互不信任的多方：大家共用同一台主机，Agent 的 shell 能读到
整个数据目录。不该互相看到对方东西的人，不要放在同一台 Runtime 上。

## 7. 每台 Runtime 各自保存设置

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
- 配对被拒：用 `user list` 确认这个人在名册上；配对码十分钟过期、只能用一次，用
  `user pair <id>` 出一个新的。
