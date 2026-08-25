#!/bin/sh
set -eu

REPOSITORY="AetherHeart-AI/aeloon-lite"

# BEGIN AELOON_RUNTIME_RELEASE_PIN
PINNED_RUNTIME_VERSION="0.1.2"
PINNED_RUNTIME_TAG="runtime-v0.1.2"
PINNED_RUNTIME_COMMIT="481e996327b8a60999bd8a6efd881e4478d9a9e3"
PINNED_LINUX_AARCH64_ASSET="aeloon-runtime-linux-aarch64.tar.gz"
PINNED_LINUX_AARCH64_SHA256="888f9e7379a083f9e4b1bdf1b17bdfef4d2110731b43b83f93a6e495d1a53c92"
PINNED_LINUX_X86_64_ASSET="aeloon-runtime-linux-x86_64.tar.gz"
PINNED_LINUX_X86_64_SHA256="fee0fed6e36ac761f9193461920f587b86bbc4e8b656220ad81546f081ac5313"
# END AELOON_RUNTIME_RELEASE_PIN

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
    --host)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      HOST=$2
      shift 2
      ;;
    --port)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      PORT=$2
      shift 2
      ;;
    --workspace-root)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      WORKSPACE_ROOT=$2
      shift 2
      ;;
    --download-only)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      DOWNLOAD_ONLY=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[ "$(uname -s)" = "Linux" ] || {
  echo "Aeloon Runtime server installation supports Linux systemd hosts only." >&2
  exit 2
}

case "$(uname -m)" in
  aarch64|arm64)
    ASSET=$PINNED_LINUX_AARCH64_ASSET
    EXPECTED_SHA256=$PINNED_LINUX_AARCH64_SHA256
    ;;
  x86_64|amd64)
    ASSET=$PINNED_LINUX_X86_64_ASSET
    EXPECTED_SHA256=$PINNED_LINUX_X86_64_SHA256
    ;;
  *)
    echo "Unsupported Linux architecture: $(uname -m)" >&2
    exit 2
    ;;
esac

case "$EXPECTED_SHA256" in
  [0-9a-f][0-9a-f][0-9a-f][0-9a-f]*)
    [ "${#EXPECTED_SHA256}" -eq 64 ] || EXPECTED_SHA256=""
    ;;
  *) EXPECTED_SHA256="" ;;
esac
[ -n "$EXPECTED_SHA256" ] || {
  echo "No published self-contained server release is pinned yet." >&2
  echo "Publish the next Runtime release and merge its installer-pin PR first." >&2
  exit 2
}

for command in curl tar sha256sum; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Required command is unavailable: $command" >&2
    exit 2
  }
done

TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/aeloon-runtime-install.XXXXXX")
STAGING=""
cleanup() {
  if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then
    rm -rf "$STAGING"
  fi
  rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT HUP INT TERM

ARCHIVE="$TEMP_ROOT/$ASSET"
URL="https://github.com/$REPOSITORY/releases/download/$PINNED_RUNTIME_TAG/$ASSET"
echo "Downloading Aeloon Runtime $PINNED_RUNTIME_VERSION from GitHub..."
curl --fail --location --retry 3 --proto '=https' --tlsv1.2 "$URL" --output "$ARCHIVE"

ACTUAL_SHA256=$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)
[ "$ACTUAL_SHA256" = "$EXPECTED_SHA256" ] || {
  echo "Runtime archive SHA-256 mismatch; installation stopped." >&2
  exit 2
}

tar -tzf "$ARCHIVE" | awk '
  /^\// { exit 1 }
  /(^|\/)\.\.($|\/)/ { exit 1 }
  !/^aeloon-runtime\// { exit 1 }
' || {
  echo "Runtime archive contains an unsafe path." >&2
  exit 2
}

if [ -n "$DOWNLOAD_ONLY" ]; then
  mkdir -p "$DOWNLOAD_ONLY"
  cp "$ARCHIVE" "$DOWNLOAD_ONLY/$ASSET"
  if [ -n "${SUDO_UID:-}" ] && [ -n "${SUDO_GID:-}" ]; then
    chown "$SUDO_UID:$SUDO_GID" "$DOWNLOAD_ONLY/$ASSET"
  fi
  echo "Verified Runtime archive: $DOWNLOAD_ONLY/$ASSET"
  exit 0
fi

[ "$(id -u)" -eq 0 ] || {
  echo "Server deployment requires root; pipe this script to sudo sh." >&2
  exit 2
}
command -v systemctl >/dev/null 2>&1 || {
  echo "systemctl is unavailable; this host does not use systemd." >&2
  exit 2
}

RELEASES_ROOT="/opt/aeloon-runtime/releases"
RELEASE_ROOT="$RELEASES_ROOT/$PINNED_RUNTIME_VERSION"
RELEASE_CREATED=0
if [ ! -d "$RELEASE_ROOT" ]; then
  STAGING="$RELEASES_ROOT/.${PINNED_RUNTIME_VERSION}.$$"
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

set -- install \
  --runtime-command "$RUNTIME_COMMAND" \
  --release-root "$RELEASE_ROOT" \
  --release-version "$PINNED_RUNTIME_VERSION"
[ -z "$HOST" ] || set -- "$@" --host "$HOST"
[ -z "$PORT" ] || set -- "$@" --port "$PORT"
[ -z "$WORKSPACE_ROOT" ] || set -- "$@" --workspace-root "$WORKSPACE_ROOT"

if "$SERVER_COMMAND" "$@"; then
  exit 0
else
  status=$?
  if [ "$RELEASE_CREATED" -eq 1 ]; then
    rm -rf "$RELEASE_ROOT"
  fi
  exit "$status"
fi
