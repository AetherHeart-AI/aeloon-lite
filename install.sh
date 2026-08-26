#!/bin/sh
set -eu

REPOSITORY="AetherHeart-AI/aeloon-lite"
RAW_ROOT="https://raw.githubusercontent.com/$REPOSITORY/main"
DOWNLOAD_ONLY=""
REQUESTED_FORMAT=""

usage() {
  cat <<'EOF'
Usage: install.sh [--download-only DIRECTORY] [--format dmg|deb|rpm]
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
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

for required_command in awk curl grep sed; do
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
  fetch "$RAW_ROOT/channels/desktop/stable" "$CHANNEL_FILE" || {
    echo "Could not resolve the stable desktop release." >&2
    exit 2
  }
fi

[ "$(sed -n '1p' "$CHANNEL_FILE")" = "# aeloon-release-v1" ] || {
  echo "Unsupported desktop release metadata." >&2
  exit 2
}
PRODUCT=$(metadata_value "$CHANNEL_FILE" product) || { echo "Invalid desktop release metadata." >&2; exit 2; }
VERSION=$(metadata_value "$CHANNEL_FILE" version) || { echo "Invalid desktop release metadata." >&2; exit 2; }
SOURCE=$(metadata_value "$CHANNEL_FILE" source) || { echo "Invalid desktop release metadata." >&2; exit 2; }
[ "$PRODUCT" = desktop ] || { echo "Release metadata is not for desktop." >&2; exit 2; }
printf '%s\n' "$VERSION" | LC_ALL=C grep -Eq '^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' || {
  echo "Stable desktop version is invalid." >&2
  exit 2
}
printf '%s\n' "$SOURCE" | LC_ALL=C grep -Eq '^AetherHeart-AI/aeloon-lite-ui@[0-9a-f]{40}$' || {
  echo "Desktop source identity is invalid." >&2
  exit 2
}
SOURCE_COMMIT=${SOURCE#*@}
TAG="v$VERSION"

SYSTEM=$(uname -s)
MACHINE=$(uname -m)
PACKAGE_KIND=""
if [ "$SYSTEM" = Darwin ]; then
  [ -z "$REQUESTED_FORMAT" ] || [ "$REQUESTED_FORMAT" = dmg ] || {
    echo "macOS supports only the dmg installer format." >&2
    exit 2
  }
  MAC_MAJOR=$(sw_vers -productVersion | cut -d . -f 1)
  [ "$MAC_MAJOR" -ge 13 ] || { echo "aeloon-lite requires macOS 13 or later." >&2; exit 2; }
  if [ "$MACHINE" != arm64 ]; then
    TRANSLATED=$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')
    [ "$TRANSLATED" = 1 ] || { echo "Intel Mac is not supported." >&2; exit 2; }
  fi
  RELEASE_ARCH=arm64
  PACKAGE_KIND=dmg
elif [ "$SYSTEM" = Linux ]; then
  [ "$REQUESTED_FORMAT" != dmg ] || { echo "Linux supports only deb and rpm." >&2; exit 2; }
  case "$MACHINE" in
    aarch64|arm64) RELEASE_ARCH=arm64 ;;
    x86_64|amd64) RELEASE_ARCH=x86_64 ;;
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
      *" debian "*|*" ubuntu "*|*" kylin "*) PACKAGE_KIND=deb ;;
      *" rhel "*|*" fedora "*|*" centos "*|*" suse "*|*" opensuse "*) PACKAGE_KIND=rpm ;;
      *)
        if command -v apt-get >/dev/null 2>&1 || command -v dpkg >/dev/null 2>&1; then
          PACKAGE_KIND=deb
        elif command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1 || command -v zypper >/dev/null 2>&1; then
          PACKAGE_KIND=rpm
        else
          echo "Unsupported Linux distribution: ${OS_ID:-unknown}" >&2
          exit 2
        fi
        ;;
    esac
  fi
else
  echo "Unsupported operating system: $SYSTEM. Windows is not supported." >&2
  exit 2
fi

ASSET="aeloon-lite-${VERSION}-${RELEASE_ARCH}.${PACKAGE_KIND}"
EXPECTED_SHA256=$(awk -v name="$ASSET" '
  $2 == name && $1 ~ /^[0-9a-f]{64}$/ { print $1; count++ }
  END { if (count != 1) exit 2 }
' "$CHANNEL_FILE") || { echo "Stable metadata does not contain exactly one checksum for $ASSET." >&2; exit 2; }
ASSET_URL="https://github.com/$REPOSITORY/releases/download/$TAG/$ASSET"
ARCHIVE="$TEMP_ROOT/$ASSET"

echo "Downloading aeloon-lite $VERSION from GitHub..."
fetch "$ASSET_URL" "$ARCHIVE"
if [ "$SYSTEM" = Darwin ]; then
  command -v shasum >/dev/null 2>&1 || { echo "shasum is required." >&2; exit 2; }
  ACTUAL_SHA256=$(shasum -a 256 "$ARCHIVE" | cut -d ' ' -f 1)
else
  command -v sha256sum >/dev/null 2>&1 || { echo "sha256sum is required." >&2; exit 2; }
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

if [ "$PACKAGE_KIND" = dmg ]; then
  if [ -n "${HOME:-}" ] && [ -d "$HOME/Downloads" ]; then
    MACOS_DESTINATION="$HOME/Downloads"
  else
    MACOS_DESTINATION=$PWD
  fi
  save_installer "$MACOS_DESTINATION"
  command -v open >/dev/null 2>&1 && open "$SAVED_INSTALLER" || true
  echo "Drag aeloon-lite.app into Applications."
  echo "This internal build is not notarized; macOS may require approval in System Settings > Privacy & Security."
  exit 0
fi

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  command -v sudo >/dev/null 2>&1 || { echo "sudo is required to install the Linux package." >&2; exit 2; }
  SUDO=sudo
fi

if [ "$PACKAGE_KIND" = deb ]; then
  command -v apt-get >/dev/null 2>&1 || { echo "apt-get is required to install the DEB package." >&2; exit 2; }
  if ! $SUDO apt-get install -y "$ARCHIVE"; then
    $SUDO dpkg -i "$ARCHIVE"
    $SUDO apt-get -f install -y
  fi
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

echo "Installed aeloon-lite $VERSION (source commit $SOURCE_COMMIT)."
