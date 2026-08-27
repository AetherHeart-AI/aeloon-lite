# aeloon-lite

English | [简体中文](README.zh-CN.md)

Public, checksum-verified installers for Aeloon Desktop and Aeloon Runtime Server.

## Desktop

Install the current stable release:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh
```

If aeloon-lite is already installed, choose **overwrite**, **update**, or **skip**. For automation:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh \
  | sh -s -- --if-installed update
```

Supported platforms: macOS 13+ on Apple Silicon, plus DEB/RPM Linux on ARM64 and x86_64.

Uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.sh \
  | sh -s -- --yes
```

User data and external projects are preserved by default. Add `--purge-data` to remove private
settings, credentials, cache, and Runtime data. External projects are never removed.

## Runtime Server

Install on a Linux systemd host:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh
```

Existing installations offer the same **overwrite**, **update**, or **skip** choices. Automation
can pass `--if-installed overwrite|update|skip`.

Uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes
```

Runtime data and the configured workspace are preserved by default. Add `--purge-data` to remove
`/var/lib/aeloon-runtime`; the workspace is always kept.

Use `--help` on any script for all options. Release and recovery details are in
[`docs/releasing.md`](docs/releasing.md).
