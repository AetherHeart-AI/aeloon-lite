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

Desktop supports macOS 13+ on Apple Silicon and DEB/RPM Linux on ARM64 and x86_64. RPM files are internal unsigned packages.

## Install Runtime server

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sudo sh
```

Runtime targets Linux systemd hosts on ARM64 and x86_64. Host, port, workspace root, and download-only options are shown by `install-server.sh --help`.

## Distribution contract

- `channels/desktop/stable` and `channels/runtime/stable` contain the stable version, source commit, and SHA-256 checksums.
- Each new GitHub Release contains the fixed product assets and the identical metadata as `SHA256SUMS`.
- Installers derive canonical GitHub URLs from the stable version and deterministic asset names, then verify SHA-256 before installing.
- Published Releases are immutable. Historical versions are downloaded directly from GitHub Releases; the curl interface intentionally exposes no channels or version selector.

Maintainer release and recovery procedures are documented in [`docs/releasing.md`](docs/releasing.md).
