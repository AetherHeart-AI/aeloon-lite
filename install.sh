#!/bin/sh
set -eu

REPOSITORY="AetherHeart-AI/aeloon-lite"

# BEGIN AELOON_DESKTOP_RELEASE_PIN
PINNED_UI_VERSION="0.0.17"
PINNED_UI_TAG="v0.0.17"
PINNED_UI_COMMIT="3ec61be3eca11caa712e14016d9bd9adaff2a9b4"
PINNED_MACOS_ARM64_ASSET="aeloon-lite-0.0.17-arm64.dmg"
PINNED_MACOS_ARM64_SHA256=""
PINNED_LINUX_ARM64_DEB_ASSET="aeloon-lite-0.0.17-arm64.deb"
PINNED_LINUX_ARM64_DEB_SHA256=""
PINNED_LINUX_ARM64_RPM_ASSET="aeloon-lite-0.0.17-arm64.rpm"
PINNED_LINUX_ARM64_RPM_SHA256=""
PINNED_LINUX_X86_64_DEB_ASSET="aeloon-lite-0.0.17-x86_64.deb"
PINNED_LINUX_X86_64_DEB_SHA256=""
PINNED_LINUX_X86_64_RPM_ASSET="aeloon-lite-0.0.17-x86_64.rpm"
PINNED_LINUX_X86_64_RPM_SHA256=""
# END AELOON_DESKTOP_RELEASE_PIN

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

SYSTEM=$(uname -s)
MACHINE=$(uname -m)
PACKAGE_KIND=""

if [ "$SYSTEM" = "Darwin" ]; then
  [ -z "$REQUESTED_FORMAT" ] || [ "$REQUESTED_FORMAT" = "dmg" ] || {
    echo "macOS supports only the dmg installer format." >&2
    exit 2
  }
  MAC_MAJOR=$(sw_vers -productVersion | cut -d . -f 1)
  [ "$MAC_MAJOR" -ge 13 ] || {
    echo "aeloon-lite requires macOS 13 or later." >&2
    exit 2
  }
  if [ "$MACHINE" != "arm64" ]; then
    TRANSLATED=$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')
    [ "$TRANSLATED" = "1" ] || {
      echo "Intel Mac is not supported; an Apple Silicon Mac is required." >&2
      exit 2
    }
  fi
  ASSET=$PINNED_MACOS_ARM64_ASSET
  EXPECTED_SHA256=$PINNED_MACOS_ARM64_SHA256
  PACKAGE_KIND="dmg"
elif [ "$SYSTEM" = "Linux" ]; then
  [ "$REQUESTED_FORMAT" != "dmg" ] || {
    echo "Linux supports only the deb and rpm installer formats." >&2
    exit 2
  }
  case "$MACHINE" in
    aarch64|arm64) RELEASE_ARCH="arm64" ;;
    x86_64|amd64) RELEASE_ARCH="x86_64" ;;
    *)
      echo "Unsupported Linux architecture: $MACHINE" >&2
      exit 2
      ;;
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
  if [ "$RELEASE_ARCH" = "arm64" ] && [ "$PACKAGE_KIND" = "deb" ]; then
    ASSET=$PINNED_LINUX_ARM64_DEB_ASSET
    EXPECTED_SHA256=$PINNED_LINUX_ARM64_DEB_SHA256
  elif [ "$RELEASE_ARCH" = "arm64" ]; then
    ASSET=$PINNED_LINUX_ARM64_RPM_ASSET
    EXPECTED_SHA256=$PINNED_LINUX_ARM64_RPM_SHA256
  elif [ "$PACKAGE_KIND" = "deb" ]; then
    ASSET=$PINNED_LINUX_X86_64_DEB_ASSET
    EXPECTED_SHA256=$PINNED_LINUX_X86_64_DEB_SHA256
  else
    ASSET=$PINNED_LINUX_X86_64_RPM_ASSET
    EXPECTED_SHA256=$PINNED_LINUX_X86_64_RPM_SHA256
  fi
else
  echo "Unsupported operating system: $SYSTEM. Windows is not supported in this release." >&2
  exit 2
fi

[ "${#EXPECTED_SHA256}" -eq 64 ] || {
  echo "No verified $SYSTEM/$MACHINE installer is pinned yet." >&2
  echo "Merge the installer-pin PR produced by the next desktop Release first." >&2
  exit 2
}

command -v curl >/dev/null 2>&1 || {
  echo "curl is required to download the GitHub Release asset." >&2
  exit 2
}

TEMP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/aeloon-ui-install.XXXXXX")
cleanup() {
  rm -rf "$TEMP_ROOT"
}
trap cleanup EXIT HUP INT TERM

ARCHIVE="$TEMP_ROOT/$ASSET"
URL="https://github.com/$REPOSITORY/releases/download/$PINNED_UI_TAG/$ASSET"
echo "Downloading aeloon-lite $PINNED_UI_VERSION from GitHub..."
curl --fail --location --retry 3 --proto '=https' --tlsv1.2 "$URL" --output "$ARCHIVE"

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
  if [ -n "${HOME:-}" ] && [ -d "$HOME/Downloads" ]; then
    MACOS_DESTINATION="$HOME/Downloads"
  else
    MACOS_DESTINATION=$PWD
  fi
  save_installer "$MACOS_DESTINATION"
  if command -v open >/dev/null 2>&1; then
    open "$SAVED_INSTALLER" || true
  fi
  echo "Drag aeloon-lite.app into Applications."
  echo "This build is not notarized; macOS may require approval in System Settings > Privacy & Security."
  exit 0
fi

if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  command -v sudo >/dev/null 2>&1 || {
    echo "sudo is required to install the Linux package." >&2
    exit 2
  }
  SUDO="sudo"
fi

if [ "$PACKAGE_KIND" = "deb" ]; then
  command -v apt-get >/dev/null 2>&1 || {
    echo "apt-get is required to install the DEB package." >&2
    exit 2
  }
  if ! $SUDO apt-get install -y "$ARCHIVE"; then
    $SUDO dpkg -i "$ARCHIVE" && $SUDO apt-get -f install -y
  fi
elif command -v dnf >/dev/null 2>&1; then
  $SUDO dnf install -y --nogpgcheck "$ARCHIVE"
elif command -v yum >/dev/null 2>&1; then
  $SUDO yum install -y --nogpgcheck "$ARCHIVE"
elif command -v zypper >/dev/null 2>&1; then
  $SUDO zypper --non-interactive --no-gpg-checks install "$ARCHIVE"
else
  echo "No supported RPM package manager is installed." >&2
  exit 2
fi

echo "Installed aeloon-lite $PINNED_UI_VERSION (release commit $PINNED_UI_COMMIT)."
