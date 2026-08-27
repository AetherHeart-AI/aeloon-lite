#!/bin/sh
set -eu

ASSUME_YES=0
PURGE_DATA=0
INSTALL_ROOT="/opt/aeloon-runtime"
STATE_FILE="/etc/aeloon-runtime/install.json"
UNIT_FILE="/etc/systemd/system/aeloon-runtime.service"
MANAGEMENT_LINK="/usr/local/bin/aeloon-runtime-server"
DATA_ROOT="/var/lib/aeloon-runtime"

usage() {
  cat <<'EOF'
Usage: uninstall-server.sh [--purge-data] [--yes]

Removes the Aeloon Runtime systemd service and managed releases. Runtime data is
preserved unless --purge-data is specified. The configured workspace is always
preserved.
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

[ "$(uname -s)" = Linux ] || {
  echo "Aeloon Runtime server uninstall supports Linux systemd hosts only." >&2
  exit 2
}

INSTALLED=0
if [ -e "$INSTALL_ROOT" ] || [ -e "$STATE_FILE" ] || [ -e "$UNIT_FILE" ] || [ -L "$MANAGEMENT_LINK" ]; then
  INSTALLED=1
fi
if [ "$INSTALLED" -eq 0 ] && { [ "$PURGE_DATA" -eq 0 ] || [ ! -e "$DATA_ROOT" ]; }; then
  echo "Aeloon Runtime server is not installed."
  exit 0
fi

[ "$(id -u)" -eq 0 ] || {
  echo "Server uninstall requires root; pipe this script to sudo sh." >&2
  exit 2
}

WORKSPACE_ROOT=""
if [ -r "$STATE_FILE" ]; then
  WORKSPACE_ROOT=$(sed -n 's/.*"workspace_root"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$STATE_FILE" | head -n 1)
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  detail=""
  [ "$PURGE_DATA" -eq 0 ] || detail=" and delete private Runtime data"
  printf 'Uninstall Aeloon Runtime%s? The workspace will be preserved. [y/N] ' "$detail" >&2
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
fi

json_number() {
  sed -n "s/.*\"$1\"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p" "$STATE_FILE" | head -n 1
}

remove_ufw_rules() {
  port=$1
  command -v ufw >/dev/null 2>&1 || return 0
  while :; do
    rule=$(ufw status numbered 2>/dev/null | awk -v port="$port" '
      $0 ~ "Aeloon Runtime" && $0 ~ (port "/tcp") {
        value=$0; sub(/^\[[[:space:]]*/, "", value); sub(/\].*$/, "", value); number=value + 0
        if (number > maximum) maximum=number
      }
      END { if (maximum > 0) print maximum }
    ')
    [ -n "$rule" ] || break
    ufw --force delete "$rule" >/dev/null 2>&1 || break
  done
}

if command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now aeloon-runtime.service >/dev/null 2>&1 || true
fi

if [ -r "$STATE_FILE" ]; then
  ufw_port=$(json_number ufw)
  [ -z "$ufw_port" ] || remove_ufw_rules "$ufw_port"
  runtime_port=$(json_number firewalld_runtime)
  permanent_port=$(json_number firewalld_permanent)
  legacy_port=$(json_number firewalld)
  if command -v firewall-cmd >/dev/null 2>&1; then
    [ -z "$runtime_port" ] || firewall-cmd "--remove-port=$runtime_port/tcp" >/dev/null 2>&1 || true
    [ -z "$permanent_port" ] || firewall-cmd --permanent "--remove-port=$permanent_port/tcp" >/dev/null 2>&1 || true
    if [ -n "$legacy_port" ]; then
      firewall-cmd "--remove-port=$legacy_port/tcp" >/dev/null 2>&1 || true
      firewall-cmd --permanent "--remove-port=$legacy_port/tcp" >/dev/null 2>&1 || true
    fi
  fi
fi

rm -f "$UNIT_FILE"
if [ -L "$MANAGEMENT_LINK" ]; then
  management_target=$(readlink -f "$MANAGEMENT_LINK" 2>/dev/null || readlink "$MANAGEMENT_LINK" 2>/dev/null || true)
  case "$management_target" in
    "$INSTALL_ROOT"/releases/*) rm -f "$MANAGEMENT_LINK" ;;
  esac
fi
rm -rf "$INSTALL_ROOT"
[ "$PURGE_DATA" -eq 0 ] || rm -rf "$DATA_ROOT"
rm -f "$STATE_FILE"
rmdir "$(dirname "$STATE_FILE")" >/dev/null 2>&1 || true

if command -v systemctl >/dev/null 2>&1; then
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl reset-failed aeloon-runtime.service >/dev/null 2>&1 || true
fi

echo "Uninstalled Aeloon Runtime server."
if [ "$PURGE_DATA" -eq 0 ] && [ -e "$DATA_ROOT" ]; then
  echo "Preserved Runtime data: $DATA_ROOT"
fi
if [ -n "$WORKSPACE_ROOT" ]; then
  echo "Preserved workspace: $WORKSPACE_ROOT"
fi
