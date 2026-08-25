# aeloon-lite

Public, verified installers, immutable binary releases and release-channel metadata for aeloon-lite. Product source lives in private repositories; this repository is the single user-facing distribution source.

## Install the desktop app

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh
```

The default is the audited `stable` channel. Use `--channel prerelease` to opt in to a prerelease or `--version X.Y.Z` to select an immutable release explicitly; the two options are mutually exclusive. On macOS, the verified DMG is saved to `~/Downloads`; on Linux, the verified DEB or signed RPM installs automatically.

## Install Aeloon Runtime server

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sudo sh
```

The server installer supports the same channel/version selection and targets Linux systemd hosts only.

## Supported platforms

| Product | Operating system | Architecture | Format |
| --- | --- | --- | --- |
| Desktop | macOS 13+ | Apple Silicon | DMG |
| Desktop | Debian/Ubuntu/Kylin Linux | ARM64, x86_64 | DEB |
| Desktop | RPM-based Linux | ARM64, x86_64 | RPM; new stable candidates require signing |
| Runtime server | Linux with systemd | ARM64, x86_64 | tar.gz |

Every installer first resolves a small pointer under `channels/`, verifies the SHA-256 of the selected immutable `release-manifest.json`, and then verifies the artifact name, URL, size and SHA-256. The scripts accept only canonical metadata for this repository and fail closed on missing, duplicated or inconsistent fields.

## Release contract

- `channels/{desktop|runtime}/{stable|prerelease}.json` is the only mutable user-facing pointer.
- `releases/{desktop|runtime}/{tag}.json` records promoted versions and is append-only.
- Binary assets and `release-manifest.json` live only in this public repository's GitHub Releases.
- Published tags and assets are never replaced. Failed candidates leave the current channel unchanged.
- Rollback changes only the audited stable pointer to a previously promoted immutable release.

Maintainer workflow, credentials, retry semantics, and rollback procedures are documented in
[`docs/releasing.md`](docs/releasing.md).
