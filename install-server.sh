#!/bin/sh
set -eu

REPOSITORY="AetherHeart-AI/aeloon-lite"
RAW_ROOT="https://raw.githubusercontent.com/$REPOSITORY/main"
CHANNEL="stable"
CHANNEL_SET=0
REQUESTED_VERSION=""
HOST=""
PORT=""
WORKSPACE_ROOT=""
DOWNLOAD_ONLY=""

usage() {
  cat <<'EOF'
Usage: install-server.sh [--channel stable|prerelease] [--version VERSION]
                         [--host DNS_OR_IPV4] [--port PORT]
                         [--workspace-root PATH] [--download-only DIRECTORY]
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --channel)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      case "$2" in stable|prerelease) CHANNEL=$2 ;; *) echo "Unsupported release channel: $2" >&2; exit 2 ;; esac
      CHANNEL_SET=1
      shift 2
      ;;
    --version)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      REQUESTED_VERSION=$2
      shift 2
      ;;
    --host) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; HOST=$2; shift 2 ;;
    --port) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; PORT=$2; shift 2 ;;
    --workspace-root) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; WORKSPACE_ROOT=$2; shift 2 ;;
    --download-only) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; DOWNLOAD_ONLY=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -z "$REQUESTED_VERSION" ] || [ "$CHANNEL_SET" -eq 0 ] || {
  echo "--version and --channel are mutually exclusive." >&2
  exit 2
}
[ "$(uname -s)" = "Linux" ] || {
  echo "Aeloon Runtime server installation supports Linux systemd hosts only." >&2
  exit 2
}

valid_semver() {
  printf '%s\n' "$1" | LC_ALL=C grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$'
}
valid_sha256() { printf '%s\n' "$1" | LC_ALL=C grep -Eq '^[0-9a-f]{64}$'; }

json_string() {
  awk -v field="$2" '
    $0 ~ "^[[:space:]]*\\\"" field "\\\"[[:space:]]*:" {
      value=$0; sub(/^[^:]*:[[:space:]]*\"/, "", value); sub(/\"[[:space:]]*,?[[:space:]]*$/, "", value)
      print value; count++
    }
    END { if (count != 1) exit 2 }
  ' "$1"
}

json_number() {
  awk -v field="$2" '
    $0 ~ "^[[:space:]]*\\\"" field "\\\"[[:space:]]*:" {
      value=$0; sub(/^[^:]*:[[:space:]]*/, "", value); sub(/,[[:space:]]*$/, "", value)
      print value; count++
    }
    END { if (count != 1) exit 2 }
  ' "$1"
}

artifact_string() {
  awk -v wanted="$2" -v field="$3" '
    /^[[:space:]]*"key"[[:space:]]*:/ {
      key=$0; sub(/^[^:]*:[[:space:]]*"/, "", key); sub(/"[[:space:]]*,?[[:space:]]*$/, "", key)
      active=(key == wanted); if (active) matches++
    }
    active && $0 ~ "^[[:space:]]*\\\"" field "\\\"[[:space:]]*:" {
      value=$0; sub(/^[^:]*:[[:space:]]*\"/, "", value); sub(/\"[[:space:]]*,?[[:space:]]*$/, "", value)
      print value; values++
    }
    active && /^[[:space:]]*}[,]?[[:space:]]*$/ { active=0 }
    END { if (matches != 1 || values != 1) exit 2 }
  ' "$1"
}

artifact_number() {
  awk -v wanted="$2" -v field="$3" '
    /^[[:space:]]*"key"[[:space:]]*:/ {
      key=$0; sub(/^[^:]*:[[:space:]]*"/, "", key); sub(/"[[:space:]]*,?[[:space:]]*$/, "", key)
      active=(key == wanted); if (active) matches++
    }
    active && $0 ~ "^[[:space:]]*\\\"" field "\\\"[[:space:]]*:" {
      value=$0; sub(/^[^:]*:[[:space:]]*/, "", value); sub(/,[[:space:]]*$/, "", value)
      print value; values++
    }
    active && /^[[:space:]]*}[,]?[[:space:]]*$/ { active=0 }
    END { if (matches != 1 || values != 1) exit 2 }
  ' "$1"
}

validate_pointer_shape() {
  awk '
    /^  "[^"]+"[[:space:]]*:/ {
      key=$0; sub(/^  "/, "", key); sub(/"[[:space:]]*:.*$/, "", key)
      if (key !~ /^(manifestUrl|manifestSha256)$/) exit 2
      count[key]++; total++
    }
    END {
      if (total != 2) exit 2
      split("manifestUrl manifestSha256", fields, " ")
      for (i in fields) if (count[fields[i]] != 1) exit 2
    }
  ' "$1"
}

validate_manifest_shape() {
  awk '
    function finish_artifact( fields, i) {
      split("key os arch format name url sha256 size", fields, " ")
      for (i in fields) {
        if (artifact[fields[i]] != 1) exit 2
        artifact[fields[i]]=0
      }
      artifacts++
    }
    /^  "[^"]+"[[:space:]]*:/ {
      key=$0; sub(/^  "/, "", key); sub(/"[[:space:]]*:.*$/, "", key)
      if (key !~ /^(schemaVersion|product|version|tag|source|publishedAt|artifacts)$/) exit 2
      top[key]++; top_total++
    }
    /^    "[^"]+"[[:space:]]*:/ {
      key=$0; sub(/^    "/, "", key); sub(/"[[:space:]]*:.*$/, "", key)
      if (key !~ /^(repository|commit)$/) exit 2
      source[key]++; source_total++
    }
    /^      "[^"]+"[[:space:]]*:/ {
      key=$0; sub(/^      "/, "", key); sub(/"[[:space:]]*:.*$/, "", key)
      if (key !~ /^(key|os|arch|format|name|url|sha256|size)$/) exit 2
      artifact[key]++
    }
    /^    }[,]?[[:space:]]*$/ { finish_artifact() }
    END {
      if (top_total != 7 || source_total != 2 || artifacts < 1) exit 2
      split("schemaVersion product version tag source publishedAt artifacts", fields, " ")
      for (i in fields) if (top[fields[i]] != 1) exit 2
      if (source["repository"] != 1 || source["commit"] != 1) exit 2
    }
  ' "$1"
}

for required_command in awk curl grep sha256sum tar wc; do
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

if [ -n "$REQUESTED_VERSION" ]; then
  valid_semver "$REQUESTED_VERSION" || { echo "--version must be a semantic version." >&2; exit 2; }
  REQUESTED_TAG="runtime-v$REQUESTED_VERSION"
  POINTER_URL="$RAW_ROOT/releases/runtime/$REQUESTED_TAG.json"
else
  POINTER_URL="$RAW_ROOT/channels/runtime/$CHANNEL.json"
fi

POINTER="$TEMP_ROOT/release-pointer.json"
if [ -n "${AELOON_POINTER_FILE:-}" ]; then
  [ -r "$AELOON_POINTER_FILE" ] || { echo "AELOON_POINTER_FILE is not readable." >&2; exit 2; }
  cp "$AELOON_POINTER_FILE" "$POINTER"
else
  fetch "$POINTER_URL" "$POINTER" || { echo "Could not resolve the requested Runtime release." >&2; exit 2; }
fi
validate_pointer_shape "$POINTER" || { echo "Release pointer is not strict generated JSON." >&2; exit 2; }
MANIFEST_URL=$(json_string "$POINTER" manifestUrl)
MANIFEST_SHA256=$(json_string "$POINTER" manifestSha256)
valid_sha256 "$MANIFEST_SHA256" || { echo "Release pointer contains invalid metadata." >&2; exit 2; }
printf '%s\n' "$MANIFEST_URL" | LC_ALL=C grep -Eq \
  '^https://github\.com/AetherHeart-AI/aeloon-lite/releases/download/runtime-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?/release-manifest\.json$' || {
  echo "Release pointer redirects outside the expected GitHub release." >&2
  exit 2
}

MANIFEST="$TEMP_ROOT/release-manifest.json"
fetch "$MANIFEST_URL" "$MANIFEST"
[ "$(sha256sum "$MANIFEST" | cut -d ' ' -f 1)" = "$MANIFEST_SHA256" ] || {
  echo "Release manifest SHA-256 mismatch." >&2
  exit 2
}
validate_manifest_shape "$MANIFEST" || { echo "Release manifest is not strict generated JSON." >&2; exit 2; }
[ "$(json_number "$MANIFEST" schemaVersion)" = "1" ] || { echo "Unsupported release manifest." >&2; exit 2; }
[ "$(json_string "$MANIFEST" product)" = "runtime" ] || { echo "Manifest is not for Runtime." >&2; exit 2; }
VERSION=$(json_string "$MANIFEST" version)
TAG=$(json_string "$MANIFEST" tag)
valid_semver "$VERSION" || { echo "Manifest version is invalid." >&2; exit 2; }
[ "$TAG" = "runtime-v$VERSION" ] || { echo "Manifest tag/version mismatch." >&2; exit 2; }
[ "$MANIFEST_URL" = "https://github.com/$REPOSITORY/releases/download/$TAG/release-manifest.json" ] || {
  echo "Manifest identity does not match its immutable URL." >&2
  exit 2
}
if [ -n "$REQUESTED_VERSION" ]; then
  [ "$VERSION" = "$REQUESTED_VERSION" ] || { echo "Version record mismatch." >&2; exit 2; }
else
  case "$CHANNEL:$VERSION" in
    stable:*-*) echo "Stable channel cannot select a prerelease." >&2; exit 2 ;;
    prerelease:*-*) ;;
    prerelease:*) echo "Prerelease channel must select a prerelease." >&2; exit 2 ;;
  esac
fi
[ "$(json_string "$MANIFEST" repository)" = "AetherHeart-AI/aeloon-lite-runtime" ] || {
  echo "Unexpected Runtime source repository." >&2
  exit 2
}
SOURCE_COMMIT=$(json_string "$MANIFEST" commit)
printf '%s\n' "$SOURCE_COMMIT" | LC_ALL=C grep -Eq '^[0-9a-f]{40}$' || { echo "Invalid Runtime source commit." >&2; exit 2; }

case "$(uname -m)" in
  aarch64|arm64) RELEASE_ARCH="aarch64" ;;
  x86_64|amd64) RELEASE_ARCH="x86_64" ;;
  *) echo "Unsupported Linux architecture: $(uname -m)" >&2; exit 2 ;;
esac
ASSET_KEY="linux-$RELEASE_ARCH-tar.gz"
ASSET=$(artifact_string "$MANIFEST" "$ASSET_KEY" name)
ASSET_URL=$(artifact_string "$MANIFEST" "$ASSET_KEY" url)
EXPECTED_SHA256=$(artifact_string "$MANIFEST" "$ASSET_KEY" sha256)
EXPECTED_SIZE=$(artifact_number "$MANIFEST" "$ASSET_KEY" size)
[ "$(artifact_string "$MANIFEST" "$ASSET_KEY" os)" = "linux" ] || { echo "Runtime artifact OS mismatch." >&2; exit 2; }
[ "$(artifact_string "$MANIFEST" "$ASSET_KEY" arch)" = "$RELEASE_ARCH" ] || { echo "Runtime artifact architecture mismatch." >&2; exit 2; }
[ "$(artifact_string "$MANIFEST" "$ASSET_KEY" format)" = "tar.gz" ] || { echo "Runtime artifact format mismatch." >&2; exit 2; }
valid_sha256 "$EXPECTED_SHA256" || { echo "Runtime artifact has an invalid SHA-256." >&2; exit 2; }
printf '%s\n' "$EXPECTED_SIZE" | LC_ALL=C grep -Eq '^[1-9][0-9]*$' || { echo "Runtime artifact has an invalid size." >&2; exit 2; }
[ "$ASSET_URL" = "https://github.com/$REPOSITORY/releases/download/$TAG/$ASSET" ] || {
  echo "Runtime artifact URL is outside the selected release." >&2
  exit 2
}

ARCHIVE="$TEMP_ROOT/$ASSET"
echo "Downloading Aeloon Runtime $VERSION from GitHub..."
fetch "$ASSET_URL" "$ARCHIVE"
[ "$(wc -c < "$ARCHIVE" | tr -d ' ')" = "$EXPECTED_SIZE" ] || {
  echo "Runtime archive size mismatch; installation stopped." >&2
  exit 2
}
[ "$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)" = "$EXPECTED_SHA256" ] || {
  echo "Runtime archive SHA-256 mismatch; installation stopped." >&2
  exit 2
}

tar -tzf "$ARCHIVE" | awk '
  /^\// { exit 1 }
  /(^|\/)\.\.($|\/)/ { exit 1 }
  !/^aeloon-runtime\// { exit 1 }
' || { echo "Runtime archive contains an unsafe path." >&2; exit 2; }

if [ -n "$DOWNLOAD_ONLY" ]; then
  mkdir -p "$DOWNLOAD_ONLY"
  cp "$ARCHIVE" "$DOWNLOAD_ONLY/$ASSET"
  if [ -n "${SUDO_UID:-}" ] && [ -n "${SUDO_GID:-}" ]; then chown "$SUDO_UID:$SUDO_GID" "$DOWNLOAD_ONLY/$ASSET"; fi
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
  [ -x "$STAGING/aeloon-runtime/bin/aeloon-runtime" ] || { echo "Runtime archive is missing bin/aeloon-runtime." >&2; exit 2; }
  [ -x "$STAGING/aeloon-runtime/bin/aeloon-runtime-server" ] || { echo "Runtime archive is missing bin/aeloon-runtime-server." >&2; exit 2; }
  chown -R root:root "$STAGING/aeloon-runtime"
  chmod -R a+rX "$STAGING/aeloon-runtime"
  mv "$STAGING/aeloon-runtime" "$RELEASE_ROOT"
  rmdir "$STAGING"
  STAGING=""
  RELEASE_CREATED=1
fi

SERVER_COMMAND="$RELEASE_ROOT/bin/aeloon-runtime-server"
RUNTIME_COMMAND="$RELEASE_ROOT/bin/aeloon-runtime"
[ -x "$SERVER_COMMAND" ] && [ -x "$RUNTIME_COMMAND" ] || { echo "Installed Runtime release is incomplete: $RELEASE_ROOT" >&2; exit 2; }

set -- install --runtime-command "$RUNTIME_COMMAND" --release-root "$RELEASE_ROOT" --release-version "$VERSION"
[ -z "$HOST" ] || set -- "$@" --host "$HOST"
[ -z "$PORT" ] || set -- "$@" --port "$PORT"
[ -z "$WORKSPACE_ROOT" ] || set -- "$@" --workspace-root "$WORKSPACE_ROOT"

if "$SERVER_COMMAND" "$@"; then
  echo "Installed Aeloon Runtime $VERSION (release commit $SOURCE_COMMIT)."
else
  status=$?
  if [ "$RELEASE_CREATED" -eq 1 ]; then rm -rf "$RELEASE_ROOT"; fi
  exit "$status"
fi
