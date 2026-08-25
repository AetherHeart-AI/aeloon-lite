# aeloon-lite

Public, verified installers and release assets for aeloon-lite. Product source lives in private repositories; this repository contains only the user-facing installer scripts and mirrored binary releases.

## Install the desktop app

\`\`\`bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh
\`\`\`

On macOS, the verified DMG is saved to \`~/Downloads\` and opened for manual drag-to-Applications installation. On Linux, the verified DEB or RPM installs automatically.

## Install Aeloon Runtime server

\`\`\`bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sudo sh
\`\`\`

The standalone Runtime server supports Linux systemd hosts only.

## Supported platforms

| Product | Operating system | Architecture | Format |
| --- | --- | --- | --- |
| Desktop | macOS 13+ | Apple Silicon | DMG |
| Desktop | Debian/Ubuntu/Kylin Linux | ARM64, x86_64 | DEB |
| Desktop | RPM-based Linux | ARM64, x86_64 | RPM |
| Runtime server | Linux with systemd | ARM64, x86_64 | tar.gz |

Every downloaded artifact is selected from a pinned release and verified with a SHA-256 embedded in the corresponding script. Empty or incomplete pins fail closed.
