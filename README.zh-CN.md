# aeloon-lite

[English](README.md) | 简体中文

Aeloon Desktop 与 Aeloon Runtime Server 的公开安装入口，所有安装包均进行校验和验证。

## 桌面端

安装当前稳定版：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh
```

如果已安装 aeloon-lite，可选择**覆盖**、**更新**或**跳过**。自动化安装可使用：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh \
  | sh -s -- --if-installed update
```

支持平台：Apple Silicon Mac（macOS 13+），以及 ARM64、x86_64 架构的 DEB/RPM Linux。

卸载：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.sh \
  | sh -s -- --yes
```

默认保留用户数据和外部项目。添加 `--purge-data` 可清除私有设置、凭据、缓存及 Runtime
数据；外部项目始终不会被删除。

## Runtime Server

在使用 systemd 的 Linux 主机上安装：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh
```

已有安装同样可选择**覆盖**、**更新**或**跳过**。自动化安装可传入
`--if-installed overwrite|update|skip`。

卸载：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes
```

默认保留 Runtime 数据和已配置的工作区。添加 `--purge-data` 可删除
`/var/lib/aeloon-runtime`；工作区始终保留。

所有脚本均可使用 `--help` 查看完整参数。发布与恢复流程参见
[`docs/releasing.md`](docs/releasing.md)。
