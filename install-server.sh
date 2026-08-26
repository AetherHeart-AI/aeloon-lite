#!/bin/sh
set -eu

REPOSITORY="AetherHeart-AI/aeloon-lite"
RAW_ROOT="https://raw.githubusercontent.com/$REPOSITORY/main"
HOST=""
PORT=""
WORKSPACE_ROOT=""
DOWNLOAD_ONLY=""

usage() {
  cat <<'EOF'
Usage: install-server.sh [--host DNS_OR_IPV4] [--port PORT]
                         [--workspace-root PATH] [--download-only DIRECTORY]
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; HOST=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; PORT=$2; shift 2 ;;
    --workspace-root) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; WORKSPACE_ROOT=$2; shift 2 ;;
    --download-only) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; DOWNLOAD_ONLY=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ "$(uname -s)" = Linux ] || {
  echo "Aeloon Runtime server installation supports Linux systemd hosts only." >&2
  exit 2
}
for required_command in awk curl grep sed sha256sum tar; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "Required command is unavailable: $required_command" >&2
    exit 2
  }
done

TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/aeloon-runtime-install.XXXXXX")
STAGING=""
cleanup() {
  if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then rm -rf "$STAGING"; fi
  rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT HUP INT TERM

fetch() {
  curl --fail --location --retry 3 --proto '=https' --tlsv1.2 \
    --header 'Cache-Control: no-cache' "$1" --output "$2"
}

metadata_value() {
  awk -v key="$2" '
    index($0, "# " key "=") == 1 {
      print substr($0, length(key) + 4)
      count++
    }
    END { if (count != 1) exit 2 }
  ' "$1"
}

CHANNEL_FILE="$TEMP_ROOT/stable"
if [ -n "${AELOON_CHANNEL_FILE:-}" ]; then
  [ -r "$AELOON_CHANNEL_FILE" ] || { echo "AELOON_CHANNEL_FILE is not readable." >&2; exit 2; }
  cp "$AELOON_CHANNEL_FILE" "$CHANNEL_FILE"
else
  fetch "$RAW_ROOT/channels/runtime/stable" "$CHANNEL_FILE" || {
    echo "Could not resolve the stable Runtime release." >&2
    exit 2
  }
fi

[ "$(sed -n '1p' "$CHANNEL_FILE")" = "# aeloon-release-v1" ] || {
  echo "Unsupported Runtime release metadata." >&2
  exit 2
}
PRODUCT=$(metadata_value "$CHANNEL_FILE" product) || { echo "Invalid Runtime release metadata." >&2; exit 2; }
VERSION=$(metadata_value "$CHANNEL_FILE" version) || { echo "Invalid Runtime release metadata." >&2; exit 2; }
SOURCE=$(metadata_value "$CHANNEL_FILE" source) || { echo "Invalid Runtime release metadata." >&2; exit 2; }
[ "$PRODUCT" = runtime ] || { echo "Release metadata is not for Runtime." >&2; exit 2; }
printf '%s\n' "$VERSION" | LC_ALL=C grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' || {
  echo "Stable Runtime version is invalid." >&2
  exit 2
}
printf '%s\n' "$SOURCE" | LC_ALL=C grep -Eq '^AetherHeart-AI/aeloon-lite-runtime@[0-9a-f]{40}$' || {
  echo "Runtime source identity is invalid." >&2
  exit 2
}
SOURCE_COMMIT=${SOURCE#*@}
TAG="runtime-v$VERSION"

case "$(uname -m)" in
  aarch64|arm64) RELEASE_ARCH=aarch64 ;;
  x86_64|amd64) RELEASE_ARCH=x86_64 ;;
  *) echo "Unsupported Linux architecture: $(uname -m)" >&2; exit 2 ;;
esac
ASSET="aeloon-runtime-linux-${RELEASE_ARCH}.tar.gz"
EXPECTED_SHA256=$(awk -v name="$ASSET" '
  $2 == name && $1 ~ /^[0-9a-f]{64}$/ { print $1; count++ }
  END { if (count != 1) exit 2 }
' "$CHANNEL_FILE") || { echo "Stable metadata does not contain exactly one checksum for $ASSET." >&2; exit 2; }
ASSET_URL="https://github.com/$REPOSITORY/releases/download/$TAG/$ASSET"
ARCHIVE="$TEMP_ROOT/$ASSET"

echo "Downloading Aeloon Runtime $VERSION from GitHub..."
fetch "$ASSET_URL" "$ARCHIVE"
[ "$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)" = "$EXPECTED_SHA256" ] || {
  echo "Runtime archive SHA-256 mismatch; installation stopped." >&2
  exit 2
}
ARCHIVE_PATHS="$TEMP_ROOT/archive-paths"
tar -tzf "$ARCHIVE" > "$ARCHIVE_PATHS" || { echo "Runtime archive is unreadable." >&2; exit 2; }
awk '
  /^\// { exit 1 }
  /(^|\/)\.\.($|\/)/ { exit 1 }
  !/^aeloon-runtime\// { exit 1 }
' "$ARCHIVE_PATHS" || { echo "Runtime archive contains an unsafe path." >&2; exit 2; }

if [ -n "$DOWNLOAD_ONLY" ]; then
  mkdir -p "$DOWNLOAD_ONLY"
  cp "$ARCHIVE" "$DOWNLOAD_ONLY/$ASSET"
  if [ -n "${SUDO_UID:-}" ] && [ -n "${SUDO_GID:-}" ]; then
    chown "$SUDO_UID:$SUDO_GID" "$DOWNLOAD_ONLY/$ASSET"
  fi
  echo "Verified Runtime archive: $DOWNLOAD_ONLY/$ASSET"
  exit 0
fi

[ "$(id -u)" -eq 0 ] || { echo "Server deployment requires root; pipe this script to sudo sh." >&2; exit 2; }
command -v systemctl >/dev/null 2>&1 || { echo "systemctl is unavailable; this host does not use systemd." >&2; exit 2; }

RELEASES_ROOT="/opt/aeloon-runtime/releases"
RELEASE_ROOT="$RELEASES_ROOT/$VERSION"
RELEASE_CREATED=0
if [ ! -d "$RELEASE_ROOT" ]; then
  STAGING="$RELEASES_ROOT/.$VERSION.$$"
  mkdir -p "$STAGING" "$RELEASES_ROOT"
  tar -xzf "$ARCHIVE" -C "$STAGING" --no-same-owner
  [ -x "$STAGING/aeloon-runtime/bin/aeloon-runtime" ] || {
    echo "Runtime archive is missing bin/aeloon-runtime." >&2
    exit 2
  }
  [ -x "$STAGING/aeloon-runtime/bin/aeloon-runtime-server" ] || {
    echo "Runtime archive is missing bin/aeloon-runtime-server." >&2
    exit 2
  }
  chown -R root:root "$STAGING/aeloon-runtime"
  chmod -R a+rX "$STAGING/aeloon-runtime"
  mv "$STAGING/aeloon-runtime" "$RELEASE_ROOT"
  rmdir "$STAGING"
  STAGING=""
  RELEASE_CREATED=1
fi

SERVER_COMMAND="$RELEASE_ROOT/bin/aeloon-runtime-server"
RUNTIME_COMMAND="$RELEASE_ROOT/bin/aeloon-runtime"
[ -x "$SERVER_COMMAND" ] && [ -x "$RUNTIME_COMMAND" ] || {
  echo "Installed Runtime release is incomplete: $RELEASE_ROOT" >&2
  exit 2
}

set -- install --runtime-command "$RUNTIME_COMMAND" --release-root "$RELEASE_ROOT" --release-version "$VERSION"
[ -z "$HOST" ] || set -- "$@" --host "$HOST"
[ -z "$PORT" ] || set -- "$@" --port "$PORT"
[ -z "$WORKSPACE_ROOT" ] || set -- "$@" --workspace-root "$WORKSPACE_ROOT"

if "$SERVER_COMMAND" "$@"; then
  echo "Installed Aeloon Runtime $VERSION (source commit $SOURCE_COMMIT)."
else
  status=$?
  if [ "$RELEASE_CREATED" -eq 1 ]; then rm -rf "$RELEASE_ROOT"; fi
  exit "$status"
fi
