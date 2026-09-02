# aeloon-lite

English | [简体中文](README.zh-CN.md)

Stable installers for Aeloon Desktop and Aeloon Runtime Server. The installer always selects the
current stable release; historical version selection is intentionally unsupported.

## Local use

Install Aeloon Desktop, which already contains the matching Runtime:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh
```

On Windows, run this in PowerShell:

```powershell
irm https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.ps1 | iex
```

On first launch, choose **Run on this computer**. No separate Runtime download or server setup is
needed. Existing installations offer **overwrite**, **update**, or **skip**; automation can pass
`--if-installed overwrite|update|skip` (PowerShell: `-IfInstalled overwrite|update|skip`). To pass
arguments to the PowerShell script, run it as a script block:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.ps1))) -IfInstalled skip
```

Supported platforms are Apple Silicon Macs running macOS 13+, ARM64 and x86_64 DEB/RPM Linux,
and Windows 10+ on x64. The shell installer covers macOS and Linux; the PowerShell installer
covers Windows, where it downloads `aeloon-lite-<version>-x64.exe` and opens the setup wizard
(`-Silent` installs without prompts). These internal builds are unsigned, so Windows SmartScreen
may warn; choose **More info** > **Run anyway**.

## Remote use

First install Runtime on a Linux systemd server:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh
```

Use `--host`, `--port`, or `--workspace-root` when the detected defaults are unsuitable. The
installer prints a QR code and an `AELOON1-…` one-time pairing code.

Then install Desktop with the same local command, choose **Connect to a remote server**, and scan
the QR code or paste the pairing code. A successful connection is saved and reconnects
automatically.

For a short step-by-step guide covering public/private hosts, CA certificates, pairing, upgrades,
status checks, and removal, see [Remote deployment](docs/remote-deployment.md).

To define specialist subagents and use agent or workspace-file mentions in a conversation, see
[Subagents and mentions](docs/subagents-and-mentions.md).

## Uninstall and delete data

Remove Desktop while preserving settings, credentials, cache, Runtime data, and external projects:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.sh \
  | sh -s -- --yes
```

Remove Desktop and its private data:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.sh \
  | sh -s -- --yes --purge-data
```

The same two steps in PowerShell:

```powershell
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.ps1))) -Yes
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.ps1))) -Yes -PurgeData
```

External projects are never deleted.

Remove the Remote Runtime service and managed releases while preserving Runtime data and its
configured workspace:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes
```

Also delete private Runtime data under `/var/lib/aeloon-runtime`:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes --purge-data
```

The configured workspace is always preserved and must be removed separately only when the owner
explicitly intends to delete those projects.

Use `--help` on any script for all options. Release procedure and recovery details are in
[`docs/releasing.md`](docs/releasing.md).
