#!/bin/sh
set -eu

REPOSITORY="AetherHeart-AI/aeloon-lite"
RAW_ROOT="https://raw.githubusercontent.com/$REPOSITORY/main"
CHANNEL="stable"
CHANNEL_SET=0
REQUESTED_VERSION=""
DOWNLOAD_ONLY=""
REQUESTED_FORMAT=""

usage() {
  cat <<'EOF'
Usage: install.sh [--channel stable|prerelease] [--version VERSION]
                  [--download-only DIRECTORY] [--format dmg|deb|rpm]
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --channel)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      case "$2" in
        stable|prerelease) CHANNEL=$2 ;;
        *) echo "Unsupported release channel: $2" >&2; exit 2 ;;
      esac
      CHANNEL_SET=1
      shift 2
      ;;
    --version)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      REQUESTED_VERSION=$2
      shift 2
      ;;
    --download-only)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      DOWNLOAD_ONLY=$2
      shift 2
      ;;
    --format)
      [ "$#" -ge 2 ] || { usage >&2; exit 2; }
      case "$2" in
        dmg|deb|rpm) REQUESTED_FORMAT=$2 ;;
        *) echo "Unsupported installer format: $2" >&2; usage >&2; exit 2 ;;
      esac
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -z "$REQUESTED_VERSION" ] || [ "$CHANNEL_SET" -eq 0 ] || {
  echo "--version and --channel are mutually exclusive." >&2
  exit 2
}

valid_semver() {
  printf '%s\n' "$1" | LC_ALL=C grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$'
}

valid_sha256() {
  printf '%s\n' "$1" | LC_ALL=C grep -Eq '^[0-9a-f]{64}$'
}

json_string() {
  awk -v field="$2" '
    $0 ~ "^[[:space:]]*\\\"" field "\\\"[[:space:]]*:" {
      value=$0
      sub(/^[^:]*:[[:space:]]*\"/, "", value)
      sub(/\"[[:space:]]*,?[[:space:]]*$/, "", value)
      print value
      count++
    }
    END { if (count != 1) exit 2 }
  ' "$1"
}

json_number() {
  awk -v field="$2" '
    $0 ~ "^[[:space:]]*\\\"" field "\\\"[[:space:]]*:" {
      value=$0
      sub(/^[^:]*:[[:space:]]*/, "", value)
      sub(/,[[:space:]]*$/, "", value)
      print value
      count++
    }
    END { if (count != 1) exit 2 }
  ' "$1"
}

artifact_string() {
  awk -v wanted="$2" -v field="$3" '
    /^[[:space:]]*"key"[[:space:]]*:/ {
      key=$0
      sub(/^[^:]*:[[:space:]]*"/, "", key)
      sub(/"[[:space:]]*,?[[:space:]]*$/, "", key)
      active=(key == wanted)
      if (active) matches++
    }
    active && $0 ~ "^[[:space:]]*\\\"" field "\\\"[[:space:]]*:" {
      value=$0
      sub(/^[^:]*:[[:space:]]*\"/, "", value)
      sub(/\"[[:space:]]*,?[[:space:]]*$/, "", value)
      print value
      values++
    }
    active && /^[[:space:]]*}[,]?[[:space:]]*$/ { active=0 }
    END { if (matches != 1 || values != 1) exit 2 }
  ' "$1"
}

artifact_number() {
  awk -v wanted="$2" -v field="$3" '
    /^[[:space:]]*"key"[[:space:]]*:/ {
      key=$0
      sub(/^[^:]*:[[:space:]]*"/, "", key)
      sub(/"[[:space:]]*,?[[:space:]]*$/, "", key)
      active=(key == wanted)
      if (active) matches++
    }
    active && $0 ~ "^[[:space:]]*\\\"" field "\\\"[[:space:]]*:" {
      value=$0
      sub(/^[^:]*:[[:space:]]*/, "", value)
      sub(/,[[:space:]]*$/, "", value)
      print value
      values++
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

for required_command in awk curl grep wc; do
  command -v "$required_command" >/dev/null 2>&1 || {
    echo "Required command is unavailable: $required_command" >&2
    exit 2
  }
done

TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/aeloon-ui-install.XXXXXX")
cleanup() { rm -rf "$TEMP_ROOT"; }
trap cleanup EXIT HUP INT TERM

fetch() {
  curl --fail --location --retry 3 --proto '=https' --tlsv1.2 \
    --header 'Cache-Control: no-cache' "$1" --output "$2"
}

if [ -n "$REQUESTED_VERSION" ]; then
  valid_semver "$REQUESTED_VERSION" || { echo "--version must be a semantic version." >&2; exit 2; }
  REQUESTED_TAG="v$REQUESTED_VERSION"
  POINTER_URL="$RAW_ROOT/releases/desktop/$REQUESTED_TAG.json"
else
  POINTER_URL="$RAW_ROOT/channels/desktop/$CHANNEL.json"
fi

POINTER="$TEMP_ROOT/release-pointer.json"
if [ -n "${AELOON_POINTER_FILE:-}" ]; then
  [ -r "$AELOON_POINTER_FILE" ] || { echo "AELOON_POINTER_FILE is not readable." >&2; exit 2; }
  cp "$AELOON_POINTER_FILE" "$POINTER"
else
  fetch "$POINTER_URL" "$POINTER" || { echo "Could not resolve the requested desktop release." >&2; exit 2; }
fi
validate_pointer_shape "$POINTER" || { echo "Release pointer is not strict generated JSON." >&2; exit 2; }

MANIFEST_URL=$(json_string "$POINTER" manifestUrl)
MANIFEST_SHA256=$(json_string "$POINTER" manifestSha256)
valid_sha256 "$MANIFEST_SHA256" || {
  echo "Release pointer contains invalid metadata." >&2
  exit 2
}
printf '%s\n' "$MANIFEST_URL" | LC_ALL=C grep -Eq \
  '^https://github\.com/AetherHeart-AI/aeloon-lite/releases/download/v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?/release-manifest\.json$' || {
  echo "Release pointer redirects outside the expected GitHub release." >&2
  exit 2
}

MANIFEST="$TEMP_ROOT/release-manifest.json"
fetch "$MANIFEST_URL" "$MANIFEST"
if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL_MANIFEST_SHA256=$(sha256sum "$MANIFEST" | cut -d ' ' -f 1)
else
  command -v shasum >/dev/null 2>&1 || { echo "A SHA-256 tool is required." >&2; exit 2; }
  ACTUAL_MANIFEST_SHA256=$(shasum -a 256 "$MANIFEST" | cut -d ' ' -f 1)
fi
[ "$ACTUAL_MANIFEST_SHA256" = "$MANIFEST_SHA256" ] || {
  echo "Release manifest SHA-256 mismatch." >&2
  exit 2
}
validate_manifest_shape "$MANIFEST" || { echo "Release manifest is not strict generated JSON." >&2; exit 2; }
[ "$(json_number "$MANIFEST" schemaVersion)" = "1" ] || { echo "Unsupported release manifest." >&2; exit 2; }
[ "$(json_string "$MANIFEST" product)" = "desktop" ] || { echo "Manifest is not for desktop." >&2; exit 2; }
VERSION=$(json_string "$MANIFEST" version)
TAG=$(json_string "$MANIFEST" tag)
valid_semver "$VERSION" || { echo "Manifest version is invalid." >&2; exit 2; }
[ "$TAG" = "v$VERSION" ] || { echo "Manifest tag/version mismatch." >&2; exit 2; }
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
[ "$(json_string "$MANIFEST" repository)" = "AetherHeart-AI/aeloon-lite-ui" ] || {
  echo "Unexpected desktop source repository." >&2
  exit 2
}
SOURCE_COMMIT=$(json_string "$MANIFEST" commit)
printf '%s\n' "$SOURCE_COMMIT" | LC_ALL=C grep -Eq '^[0-9a-f]{40}$' || {
  echo "Invalid desktop source commit." >&2
  exit 2
}

SYSTEM=$(uname -s)
MACHINE=$(uname -m)
PACKAGE_KIND=""
if [ "$SYSTEM" = "Darwin" ]; then
  [ -z "$REQUESTED_FORMAT" ] || [ "$REQUESTED_FORMAT" = "dmg" ] || {
    echo "macOS supports only the dmg installer format." >&2
    exit 2
  }
  MAC_MAJOR=$(sw_vers -productVersion | cut -d . -f 1)
  [ "$MAC_MAJOR" -ge 13 ] || { echo "aeloon-lite requires macOS 13 or later." >&2; exit 2; }
  if [ "$MACHINE" != "arm64" ]; then
    TRANSLATED=$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')
    [ "$TRANSLATED" = "1" ] || { echo "Intel Mac is not supported." >&2; exit 2; }
  fi
  ASSET_KEY="darwin-arm64-dmg"
  PACKAGE_KIND="dmg"
  EXPECTED_OS="darwin"
  EXPECTED_ARCH="arm64"
elif [ "$SYSTEM" = "Linux" ]; then
  [ "$REQUESTED_FORMAT" != "dmg" ] || { echo "Linux supports only deb and rpm." >&2; exit 2; }
  case "$MACHINE" in
    aarch64|arm64) RELEASE_ARCH="arm64" ;;
    x86_64|amd64) RELEASE_ARCH="x86_64" ;;
    *) echo "Unsupported Linux architecture: $MACHINE" >&2; exit 2 ;;
  esac
  OS_ID=""
  OS_LIKE=""
  OS_RELEASE_FILE=${AELOON_UI_OS_RELEASE_FILE:-/etc/os-release}
  if [ -r "$OS_RELEASE_FILE" ]; then
    OS_ID=$(sed -n 's/^ID=//p' "$OS_RELEASE_FILE" | head -n 1 | tr -d '"')
    OS_LIKE=$(sed -n 's/^ID_LIKE=//p' "$OS_RELEASE_FILE" | head -n 1 | tr -d '"')
  fi
  if [ -n "$REQUESTED_FORMAT" ]; then
    PACKAGE_KIND=$REQUESTED_FORMAT
  else
    case " $OS_ID $OS_LIKE " in
      *" debian "*|*" ubuntu "*|*" kylin "*) PACKAGE_KIND="deb" ;;
      *" rhel "*|*" fedora "*|*" centos "*|*" suse "*|*" opensuse "*) PACKAGE_KIND="rpm" ;;
      *)
        if command -v apt-get >/dev/null 2>&1 || command -v dpkg >/dev/null 2>&1; then
          PACKAGE_KIND="deb"
        elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1 || command -v zypper >/dev/null 2>&1; then
          PACKAGE_KIND="rpm"
        else
          echo "Unsupported Linux distribution: ${OS_ID:-unknown}" >&2
          exit 2
        fi
        ;;
    esac
  fi
  ASSET_KEY="linux-$RELEASE_ARCH-$PACKAGE_KIND"
  EXPECTED_OS="linux"
  EXPECTED_ARCH=$RELEASE_ARCH
else
  echo "Unsupported operating system: $SYSTEM. Windows is not supported." >&2
  exit 2
fi

ASSET=$(artifact_string "$MANIFEST" "$ASSET_KEY" name)
ASSET_URL=$(artifact_string "$MANIFEST" "$ASSET_KEY" url)
EXPECTED_SHA256=$(artifact_string "$MANIFEST" "$ASSET_KEY" sha256)
EXPECTED_SIZE=$(artifact_number "$MANIFEST" "$ASSET_KEY" size)
[ "$(artifact_string "$MANIFEST" "$ASSET_KEY" os)" = "$EXPECTED_OS" ] || { echo "Artifact OS mismatch." >&2; exit 2; }
[ "$(artifact_string "$MANIFEST" "$ASSET_KEY" arch)" = "$EXPECTED_ARCH" ] || { echo "Artifact architecture mismatch." >&2; exit 2; }
[ "$(artifact_string "$MANIFEST" "$ASSET_KEY" format)" = "$PACKAGE_KIND" ] || { echo "Artifact format mismatch." >&2; exit 2; }
valid_sha256 "$EXPECTED_SHA256" || { echo "Artifact has an invalid SHA-256." >&2; exit 2; }
printf '%s\n' "$EXPECTED_SIZE" | LC_ALL=C grep -Eq '^[1-9][0-9]*$' || { echo "Artifact has an invalid size." >&2; exit 2; }
[ "$ASSET_URL" = "https://github.com/$REPOSITORY/releases/download/$TAG/$ASSET" ] || {
  echo "Artifact URL is outside the selected release." >&2
  exit 2
}

ARCHIVE="$TEMP_ROOT/$ASSET"
echo "Downloading aeloon-lite $VERSION from GitHub..."
fetch "$ASSET_URL" "$ARCHIVE"
[ "$(wc -c < "$ARCHIVE" | tr -d ' ')" = "$EXPECTED_SIZE" ] || {
  echo "Installer size mismatch; installation stopped." >&2
  exit 2
}
if [ "$SYSTEM" = "Darwin" ]; then
  ACTUAL_SHA256=$(shasum -a 256 "$ARCHIVE" | cut -d ' ' -f 1)
else
  ACTUAL_SHA256=$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)
fi
[ "$ACTUAL_SHA256" = "$EXPECTED_SHA256" ] || {
  echo "Installer SHA-256 mismatch; installation stopped." >&2
  exit 2
}

save_installer() {
  destination=$1
  mkdir -p "$destination"
  SAVED_INSTALLER="$destination/$ASSET"
  cp "$ARCHIVE" "$SAVED_INSTALLER"
  echo "Verified installer: $SAVED_INSTALLER"
}

if [ -n "$DOWNLOAD_ONLY" ]; then
  save_installer "$DOWNLOAD_ONLY"
  exit 0
fi

if [ "$PACKAGE_KIND" = "dmg" ]; then
  if [ -n "${HOME:-}" ] && [ -d "$HOME/Downloads" ]; then MACOS_DESTINATION="$HOME/Downloads"; else MACOS_DESTINATION=$PWD; fi
  save_installer "$MACOS_DESTINATION"
  command -v open >/dev/null 2>&1 && open "$SAVED_INSTALLER" || true
  echo "Drag aeloon-lite.app into Applications."
  echo "This build is not notarized; macOS may require approval in System Settings > Privacy & Security."
  exit 0
fi

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  command -v sudo >/dev/null 2>&1 || { echo "sudo is required to install the Linux package." >&2; exit 2; }
  SUDO="sudo"
fi

if [ "$PACKAGE_KIND" = "deb" ]; then
  command -v apt-get >/dev/null 2>&1 || { echo "apt-get is required to install the DEB package." >&2; exit 2; }
  if ! $SUDO apt-get install -y "$ARCHIVE"; then $SUDO dpkg -i "$ARCHIVE" && $SUDO apt-get -f install -y; fi
elif command -v dnf >/dev/null 2>&1; then
  $SUDO dnf install -y "$ARCHIVE"
elif command -v yum >/dev/null 2>&1; then
  $SUDO yum install -y "$ARCHIVE"
elif command -v zypper >/dev/null 2>&1; then
  $SUDO zypper --non-interactive install "$ARCHIVE"
else
  echo "No supported RPM package manager is installed." >&2
  exit 2
fi

echo "Installed aeloon-lite $VERSION (release commit $SOURCE_COMMIT)."
