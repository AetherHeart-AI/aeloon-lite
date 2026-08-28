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

## 6. 卸载

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
