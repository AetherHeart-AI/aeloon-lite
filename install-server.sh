#!/bin/sh
set -eu

REPOSITORY="AetherHeart-AI/aeloon-lite"
RAW_ROOT="https://raw.githubusercontent.com/$REPOSITORY/main"
HOST=""
PORT=""
WORKSPACE_ROOT=""
DOWNLOAD_ONLY=""
IF_INSTALLED=""
INSTALL_ACTION="install"

usage() {
  cat <<'EOF'
Usage: install-server.sh [--host DNS_OR_IPV4] [--port PORT]
                         [--workspace-root PATH] [--download-only DIRECTORY]
                         [--if-installed overwrite|update|skip]
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --host) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; HOST=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; PORT=$2; shift 2 ;;
    --workspace-root) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; WORKSPACE_ROOT=$2; shift 2 ;;
    --download-only) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; DOWNLOAD_ONLY=$2; shift 2 ;;
    --if-installed)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      case "$2" in
        overwrite|update|skip) IF_INSTALLED=$2 ;;
        *) echo "Unsupported installed action: $2" >&2; usage >&2; exit 2 ;;
      esac
      shift 2
      ;;
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
RELEASE_BACKUP=""
RELEASE_ROOT=""
INSTALL_COMMITTED=0
cleanup() {
  if [ -n "$STAGING" ] && [ -d "$STAGING" ]; then rm -rf "$STAGING"; fi
  if [ -n "$RELEASE_BACKUP" ] && { [ -e "$RELEASE_BACKUP" ] || [ -L "$RELEASE_BACKUP" ]; }; then
    if [ "$INSTALL_COMMITTED" -eq 1 ]; then
      rm -rf "$RELEASE_BACKUP"
    elif [ -n "$RELEASE_ROOT" ]; then
      rm -rf "$RELEASE_ROOT"
      mv "$RELEASE_BACKUP" "$RELEASE_ROOT"
      systemctl restart aeloon-runtime.service >/dev/null 2>&1 || true
    fi
  fi
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

detect_installed_version() {
  current_link="/opt/aeloon-runtime/current"
  state_file=${AELOON_RUNTIME_STATE_FILE:-/etc/aeloon-runtime/install.json}
  if [ -L "$current_link" ]; then
    current_target=$(readlink "$current_link" 2>/dev/null || true)
    if [ -n "$current_target" ]; then
      basename "$current_target"
      return 0
    fi
  fi
  if [ -r "$state_file" ]; then
    version=$(sed -n 's/.*"current_version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$state_file" | head -n 1)
    if [ -n "$version" ]; then
      printf '%s\n' "$version"
      return 0
    fi
    printf '%s\n' unknown
    return 0
  fi
  if [ -e /etc/systemd/system/aeloon-runtime.service ]; then
    printf '%s\n' unknown
    return 0
  fi
  return 1
}

semver_core() {
  printf '%s\n' "$1" | sed 's/^[0-9][0-9]*://' | sed -n \
    's/^[^0-9]*\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\).*$/\1/p'
}

semver_compare() {
  awk -v left="$1" -v right="$2" 'BEGIN {
    split(left, a, "."); split(right, b, ".")
    for (i = 1; i <= 3; i++) {
      if ((a[i] + 0) < (b[i] + 0)) { print -1; exit }
      if ((a[i] + 0) > (b[i] + 0)) { print 1; exit }
    }
    print 0
  }'
}

choose_installed_action() {
  if [ -n "$IF_INSTALLED" ]; then
    INSTALL_ACTION=$IF_INSTALLED
    return
  fi

  echo "Aeloon Runtime $1 is already installed; stable is $VERSION." >&2
  while :; do
    printf 'Choose [o]verwrite, [u]pdate, or [s]kip: ' >&2
    if [ -t 0 ]; then
      IFS= read -r reply || reply=""
    elif IFS= read -r reply 2>/dev/null </dev/tty; then
      :
    else
      echo >&2
      echo "No interactive terminal is available; rerun with --if-installed overwrite, update, or skip." >&2
      exit 2
    fi
    case "$reply" in
      o|O|overwrite|OVERWRITE) INSTALL_ACTION=overwrite; return ;;
      u|U|update|UPDATE) INSTALL_ACTION=update; return ;;
      s|S|skip|SKIP) INSTALL_ACTION=skip; return ;;
      *) echo "Please choose overwrite, update, or skip." >&2 ;;
    esac
  done
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

if [ -z "$DOWNLOAD_ONLY" ] && INSTALLED_VERSION=$(detect_installed_version); then
  choose_installed_action "$INSTALLED_VERSION"
  case "$INSTALL_ACTION" in
    skip)
      echo "Keeping the installed Aeloon Runtime $INSTALLED_VERSION."
      exit 0
      ;;
    update)
      INSTALLED_CORE=$(semver_core "$INSTALLED_VERSION")
      if [ -n "$INSTALLED_CORE" ] && [ "$(semver_compare "$INSTALLED_CORE" "$VERSION")" -ge 0 ]; then
        echo "Installed Aeloon Runtime $INSTALLED_VERSION is already at or newer than stable $VERSION; nothing to update."
        exit 0
      fi
      echo "Updating Aeloon Runtime $INSTALLED_VERSION to $VERSION."
      ;;
    overwrite)
      echo "Overwriting Aeloon Runtime $INSTALLED_VERSION with stable $VERSION."
      ;;
  esac
fi

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
if [ "$INSTALL_ACTION" = overwrite ] && { [ -e "$RELEASE_ROOT" ] || [ -L "$RELEASE_ROOT" ]; }; then
  RELEASE_BACKUP="/opt/aeloon-runtime/.release-$VERSION-backup.$$"
  if [ -e "$RELEASE_BACKUP" ] || [ -L "$RELEASE_BACKUP" ]; then
    echo "Runtime overwrite backup already exists: $RELEASE_BACKUP" >&2
    exit 2
  fi
  mv "$RELEASE_ROOT" "$RELEASE_BACKUP"
fi
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
  INSTALL_COMMITTED=1
  if [ -n "$RELEASE_BACKUP" ] && { [ -e "$RELEASE_BACKUP" ] || [ -L "$RELEASE_BACKUP" ]; }; then
    rm -rf "$RELEASE_BACKUP"
    RELEASE_BACKUP=""
  fi
  echo "Installed Aeloon Runtime $VERSION (source commit $SOURCE_COMMIT)."
else
  status=$?
  if [ -n "$RELEASE_BACKUP" ] && { [ -e "$RELEASE_BACKUP" ] || [ -L "$RELEASE_BACKUP" ]; }; then
    rm -rf "$RELEASE_ROOT"
    mv "$RELEASE_BACKUP" "$RELEASE_ROOT"
    RELEASE_BACKUP=""
    systemctl restart aeloon-runtime.service >/dev/null 2>&1 || true
  elif [ "$RELEASE_CREATED" -eq 1 ]; then
    rm -rf "$RELEASE_ROOT"
  fi
  exit "$status"
fi
