# aeloon-lite

[English](README.md) | 简体中文

Aeloon Desktop 与 Aeloon Runtime Server 的稳定安装入口。安装脚本始终选择当前稳定版，
不提供历史版本选择。

## 本地使用

安装已内置对应 Runtime 的 Aeloon Desktop：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh
```

首次启动时选择**在本机运行**，无需单独下载 Runtime 或部署服务器。若已安装，可选择
**覆盖**、**更新**或**跳过**；自动化场景可传入
`--if-installed overwrite|update|skip`。

支持平台：macOS 13+ 的 Apple Silicon Mac，以及 ARM64、x86_64 架构的 DEB/RPM Linux。

## Remote 使用

先在使用 systemd 的 Linux 服务器上安装 Runtime：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh
```

如果自动检测结果不适用，可传入 `--host`、`--port` 或 `--workspace-root`。安装完成后会
打印二维码和一次性 `AELOON1-…` 配对码。

然后使用与本地模式相同的命令安装 Desktop，首次启动时选择**连接 Remote 服务器**，
扫描二维码或粘贴配对码。连接成功后会保存配置，后续自动重连。

公网/私网地址、CA 证书、配对、升级、状态检查与卸载的简明步骤参见
[远程部署教程](docs/remote-deployment.zh-CN.md)。

## 卸载与删除数据

卸载 Desktop，但保留设置、凭据、缓存、Runtime 数据和外部项目：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.sh \
  | sh -s -- --yes
```

卸载 Desktop 并删除它的私有数据：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.sh \
  | sh -s -- --yes --purge-data
```

外部项目始终不会被删除。

卸载 Remote Runtime 服务和托管版本，但保留 Runtime 数据及已配置工作区：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes
```

同时删除 `/var/lib/aeloon-runtime` 下的私有 Runtime 数据：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes --purge-data
```

已配置工作区始终保留；只有项目所有者明确要删除这些项目时，才应另行手动处理。

所有脚本均可使用 `--help` 查看完整参数。发布与恢复流程参见
[`docs/releasing.md`](docs/releasing.md)。
