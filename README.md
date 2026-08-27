# aeloon-lite

Public stable installers for Aeloon Desktop and Aeloon Runtime. Product source lives in private repositories; this repository provides the user-facing install scripts and immutable GitHub Releases.

## Install Desktop

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh
```

The script downloads the current stable DMG, DEB, or RPM for the host. To download without installing:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh \
  | sh -s -- --download-only ./downloads
```

When aeloon-lite is already installed, the script asks whether to overwrite it with the current
stable release, update only when stable is newer, or skip. For a non-interactive run, select the
behavior explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh \
  | sh -s -- --if-installed update
```

Desktop supports macOS 13+ on Apple Silicon and DEB/RPM Linux on ARM64 and x86_64. RPM files are internal unsigned packages.

## Uninstall Desktop

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.sh \
  | sh -s -- --yes
```

The uninstaller preserves settings, credentials, cache, Runtime data, and external projects by
default. Add `--purge-data` to remove aeloon-lite-owned private user data; external projects are
never removed.

## Install Runtime server

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sudo sh
```

Runtime targets Linux systemd hosts on ARM64 and x86_64. Host, port, workspace root, and download-only options are shown by `install-server.sh --help`.

An existing Server installation gets the same overwrite, update, or skip choice. Automation can
pass `--if-installed overwrite|update|skip` explicitly.

## Uninstall Runtime server

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes
```

This removes the systemd service, installer-owned firewall rules, management link, install state,
and managed releases. Runtime data and the configured workspace are preserved. Add `--purge-data`
to remove `/var/lib/aeloon-runtime`; the workspace is always kept.

## Distribution contract

- `channels/desktop/stable` and `channels/runtime/stable` contain the stable version, source commit, and SHA-256 checksums.
- Each new GitHub Release contains the fixed product assets and the identical metadata as `SHA256SUMS`.
- Installers derive canonical GitHub URLs from the stable version and deterministic asset names, then verify SHA-256 before installing.
- Published Releases are immutable. Historical versions are downloaded directly from GitHub Releases; the curl interface intentionally exposes no channels or version selector.

Maintainer release and recovery procedures are documented in [`docs/releasing.md`](docs/releasing.md).
