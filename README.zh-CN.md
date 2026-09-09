# aeloon-lite

[English](README.md) | 简体中文

Aeloon Desktop 与 Aeloon Runtime Server 的稳定安装入口。安装脚本始终选择当前稳定版，
不提供历史版本选择。

## 本地使用

安装已内置对应 Runtime 的 Aeloon Desktop：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh
```

Windows 请在 PowerShell 中运行：

```powershell
irm https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.ps1 | iex
```

首次启动时选择**在本机运行**，无需单独下载 Runtime 或部署服务器。若已安装，可选择
**覆盖**、**更新**或**跳过**；自动化场景可传入
`--if-installed overwrite|update|skip`（PowerShell 为 `-IfInstalled overwrite|update|skip`）。
PowerShell 脚本需要传参时，用脚本块方式运行：

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.ps1))) -IfInstalled skip
```

支持平台：macOS 13+ 的 Apple Silicon Mac，ARM64、x86_64 架构的 DEB/RPM Linux，以及 x64 架构的
Windows 10+。shell 安装脚本覆盖 macOS 与 Linux；Windows 由 PowerShell 脚本覆盖，它会下载
`aeloon-lite-<版本>-x64.exe` 并打开安装向导（`-Silent` 可静默安装）。内部构建未签名，
Windows SmartScreen 可能拦截，请选择**更多信息** > **仍要运行**。

## Remote 使用

以你登录的普通用户身份在 Linux 服务器上安装 Runtime，不需要 root：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sh
```

然后带上 Desktop 将要连接的地址运行它。第一次启动会打印一次性 `AELOON1-…` 配对码：

```bash
aeloon-runtime-server run --host runtime.example.com
```

然后使用与本地模式相同的命令安装 Desktop，首次启动时选择**连接 Remote 服务器**，
粘贴配对码。连接成功后会保存配置，后续自动重连。

用 systemd 常驻、CA 证书、配对、升级、团队主机与卸载的简明步骤参见
[远程部署教程](docs/remote-deployment.zh-CN.md)。

Aeloon 里的 Agent 像同事一样各有一条对话和一张桌面，说明见
[同事与对话](docs/colleagues.zh-CN.md)。

## 卸载与删除数据

卸载 Desktop，但保留设置、凭据、缓存和 Runtime 数据：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.sh \
  | sh -s -- --yes
```

卸载 Desktop 并删除它的私有数据：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.sh \
  | sh -s -- --yes --purge-data
```

以上两步在 PowerShell 中的写法：

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.ps1))) -Yes
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.ps1))) -Yes -PurgeData
```

卸载 Remote Runtime 的版本目录、命令链接和用户服务，但保留 Runtime 数据：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sh -s -- --yes
```

同时删除 `~/.aeloon-lite` 下的私有 Runtime 数据：

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sh -s -- --yes --purge-data
```

所有脚本均可使用 `--help` 查看完整参数。发布与恢复流程参见
[`docs/releasing.md`](docs/releasing.md)。
