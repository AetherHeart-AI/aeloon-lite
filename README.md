# aeloon-lite

English | [简体中文](README.zh-CN.md)

Stable installers for Aeloon Desktop and Aeloon Runtime Server. The installer always selects the
current stable release; historical version selection is intentionally unsupported.

Start at the [official download page](https://downloads.aeloon-lite.aetherheart.com/download.html)
for a native terminal installer for Windows, macOS, or Linux. Select local Desktop or Runtime Server
on the current Linux host, then the official mirror (default) or GitHub. Packages are checked for
size and SHA-256 before installation.

## Local use

Install Aeloon Desktop, which already contains the matching Runtime:

```bash
curl -fsSL https://downloads.aeloon-lite.aetherheart.com/install.sh | sh
```

On Windows, run this in PowerShell:

```powershell
irm https://downloads.aeloon-lite.aetherheart.com/install.ps1 | iex
```

On first launch, choose **Run on this computer**. No separate Runtime download or server setup is
needed. Existing installations offer **overwrite**, **update**, or **skip**; automation can pass
`--if-installed overwrite|update|skip` (PowerShell: `-IfInstalled overwrite|update|skip`). To pass
arguments to the PowerShell script, run it as a script block:

```powershell
& ([scriptblock]::Create((irm https://downloads.aeloon-lite.aetherheart.com/install.ps1))) -IfInstalled skip
```

Supported platforms are Apple Silicon Macs running macOS 13+, ARM64 and x86_64 DEB/RPM Linux,
and Windows 10+ on x64. The shell installer covers macOS and Linux; the PowerShell installer
covers Windows, where it downloads `aeloon-lite-<version>-x64.exe` and opens the setup wizard
(`-Silent` installs without prompts). These internal builds are unsigned, so Windows SmartScreen
may warn; choose **More info** > **Run anyway**.

## Remote use

Install Runtime on a Linux server as the user you log in as — no root:

```bash
curl -fsSL https://downloads.aeloon-lite.aetherheart.com/install-server.sh | sh
```

Then run it with the address Desktop will connect to. The first start prints an `AELOON1-…`
one-time pairing code:

```bash
aeloon-runtime-server run --host runtime.example.com
```

Then install Desktop with the same local command, choose **Connect to a remote server**, and paste
the pairing code. A successful connection is saved and reconnects automatically.

For a short step-by-step guide covering keeping it running with systemd, CA certificates, pairing,
upgrades, team hosts, and removal, see [Remote deployment](docs/remote-deployment.md).

The command-line scripts use the official mirror by default. To select GitHub, download the script
and run `sh install.sh --source github` or `sh install-server.sh --source github`; use `-Source github`
on Windows. The server installer places a matching Runtime and web client without creating,
restarting, or replacing an existing systemd service.

Aeloon is a set of Agents that work like colleagues, each with one conversation and its own
desk. See [Colleagues and conversations](docs/colleagues.md).

## Uninstall and delete data

Remove Desktop while preserving settings, credentials, cache, and Runtime data:

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

Remove the Remote Runtime releases, links, and user service while preserving Runtime data:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sh -s -- --yes
```

Also delete private Runtime data under `~/.aeloon-lite`:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sh -s -- --yes --purge-data
```

Use `--help` on any script for all options. Release procedure and recovery details are in
[`docs/releasing.md`](docs/releasing.md).
