#!/bin/sh
set -eu

ASSUME_YES=0
PURGE_DATA=0

usage() {
  cat <<'EOF'
Usage: uninstall.sh [--purge-data] [--yes]

Removes the aeloon-lite desktop application. User settings and Runtime data are
preserved unless --purge-data is specified. External projects are never removed.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --purge-data) PURGE_DATA=1; shift ;;
    -y|--yes) ASSUME_YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

SYSTEM=$(uname -s)
case "$SYSTEM" in
  Darwin|Linux) ;;
  *)
    echo "Unsupported operating system: $SYSTEM. On Windows, run this in PowerShell:" >&2
    echo "  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall.ps1))) -Yes" >&2
    exit 2
    ;;
esac

confirm_uninstall() {
  [ "$ASSUME_YES" -eq 0 ] || return 0
  printf 'Uninstall aeloon-lite%s? [y/N] ' "$1" >&2
  if [ -t 0 ]; then
    IFS= read -r reply || reply=""
  elif IFS= read -r reply 2>/dev/null </dev/tty; then
    :
  else
    echo >&2
    echo "No interactive terminal is available; rerun with --yes." >&2
    exit 2
  fi
  case "$reply" in
    y|Y|yes|YES) ;;
    *) echo "Uninstall cancelled."; exit 0 ;;
  esac
}

sudo_command() {
  if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
  else
    command -v sudo >/dev/null 2>&1 || {
      echo "sudo is required to remove the system installation." >&2
      exit 2
    }
    SUDO=sudo
  fi
}

purge_user_data() {
  [ "$PURGE_DATA" -eq 1 ] || return 0
  case "${HOME:-}" in
    /*) ;;
    *) echo "An absolute home directory is required for --purge-data." >&2; exit 2 ;;
  esac
  [ "$HOME" != / ] || {
    echo "A safe home directory is required for --purge-data." >&2
    exit 2
  }
  if [ "$SYSTEM" = Darwin ]; then
    rm -rf "$HOME/Library/Application Support/dev.aeloon.desktop"
    rm -rf "$HOME/Library/Caches/dev.aeloon.desktop"
  else
    config_root=${XDG_CONFIG_HOME:-$HOME/.config}
    cache_root=${XDG_CACHE_HOME:-$HOME/.cache}
    case "$config_root:$cache_root" in
      /*:/*) ;;
      *) echo "Absolute config and cache roots are required for --purge-data." >&2; exit 2 ;;
    esac
    [ "$config_root" != / ] && [ "$cache_root" != / ] || {
      echo "Refusing to purge data from a filesystem root." >&2
      exit 2
    }
    rm -rf "$config_root/dev.aeloon.desktop"
    rm -rf "$cache_root/dev.aeloon.desktop"
  fi
  echo "Removed aeloon-lite private settings, credentials, cache, and Runtime data."
}

if [ "$SYSTEM" = Darwin ]; then
  FOUND=0
  [ -d /Applications/aeloon-lite.app ] && FOUND=1
  [ -n "${HOME:-}" ] && [ -d "$HOME/Applications/aeloon-lite.app" ] && FOUND=1
  if [ "$FOUND" -eq 0 ] && [ "$PURGE_DATA" -eq 0 ]; then
    echo "aeloon-lite is not installed."
    exit 0
  fi
  detail=""
  [ "$PURGE_DATA" -eq 0 ] || detail=" and delete its private user data"
  confirm_uninstall "$detail"
  if [ -d /Applications/aeloon-lite.app ]; then
    sudo_command
    $SUDO rm -rf /Applications/aeloon-lite.app
  fi
  if [ -n "${HOME:-}" ] && [ -d "$HOME/Applications/aeloon-lite.app" ]; then
    rm -rf "$HOME/Applications/aeloon-lite.app"
  fi
  purge_user_data
  echo "Uninstalled aeloon-lite."
  exit 0
fi

PACKAGE_KIND=""
if command -v dpkg-query >/dev/null 2>&1; then
  package_state=$(dpkg-query -W -f='${Status}\n' aeloon-lite 2>/dev/null || true)
  [ "$package_state" != "install ok installed" ] || PACKAGE_KIND=deb
fi
if [ -z "$PACKAGE_KIND" ] && command -v rpm >/dev/null 2>&1; then
  if rpm -q aeloon-lite >/dev/null 2>&1; then
    PACKAGE_KIND=rpm
  fi
fi

if [ -z "$PACKAGE_KIND" ] && [ "$PURGE_DATA" -eq 0 ]; then
  echo "aeloon-lite is not installed."
  exit 0
fi
detail=""
[ "$PURGE_DATA" -eq 0 ] || detail=" and delete its private user data"
confirm_uninstall "$detail"

if [ -n "$PACKAGE_KIND" ]; then
  sudo_command
  if [ "$PACKAGE_KIND" = deb ]; then
    if command -v apt-get >/dev/null 2>&1; then
      if [ "$PURGE_DATA" -eq 1 ]; then
        $SUDO apt-get purge -y aeloon-lite
      else
        $SUDO apt-get remove -y aeloon-lite
      fi
    elif [ "$PURGE_DATA" -eq 1 ]; then
      $SUDO dpkg --purge aeloon-lite
    else
      $SUDO dpkg --remove aeloon-lite
    fi
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf remove -y aeloon-lite
  elif command -v yum >/dev/null 2>&1; then
    $SUDO yum remove -y aeloon-lite
  elif command -v zypper >/dev/null 2>&1; then
    $SUDO zypper --non-interactive remove aeloon-lite
  else
    $SUDO rpm -e aeloon-lite
  fi
fi

purge_user_data
echo "Uninstalled aeloon-lite."
