#!/bin/sh
set -eu

ASSUME_YES=0
PURGE_DATA=0
PREFIX=${AELOON_RUNTIME_PREFIX:-$HOME/.local/share/aeloon-runtime}
BIN_DIR=${AELOON_RUNTIME_BIN_DIR:-$HOME/.local/bin}
UNIT_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/aeloon-runtime.service"
DATA_ROOT="$HOME/.aeloon-lite"

usage() {
  cat <<'EOF'
Usage: uninstall-server.sh [--purge-data] [--yes]

Stops the aeloon-runtime systemd user service if there is one, then removes the
Runtime releases under ~/.local/share/aeloon-runtime and the command links in
~/.local/bin. Runtime data under ~/.aeloon-lite is preserved unless
--purge-data is specified.
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
  echo "Aeloon Runtime server uninstall supports Linux hosts only." >&2
  exit 2
}

INSTALLED=0
if [ -e "$PREFIX" ] || [ -e "$UNIT_FILE" ] || [ -L "$BIN_DIR/aeloon-runtime" ] || [ -L "$BIN_DIR/aeloon-runtime-server" ]; then
  INSTALLED=1
fi
if [ "$INSTALLED" -eq 0 ] && { [ "$PURGE_DATA" -eq 0 ] || [ ! -e "$DATA_ROOT" ]; }; then
  echo "Aeloon Runtime server is not installed."
  exit 0
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  detail=""
  [ "$PURGE_DATA" -eq 0 ] || detail=" and delete private Runtime data"
  printf 'Uninstall Aeloon Runtime%s? [y/N] ' "$detail" >&2
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

if [ -e "$UNIT_FILE" ] && command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now aeloon-runtime.service >/dev/null 2>&1 || true
fi
rm -f "$UNIT_FILE"
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload >/dev/null 2>&1 || true
  systemctl --user reset-failed aeloon-runtime.service >/dev/null 2>&1 || true
fi

for name in aeloon-runtime aeloon-runtime-server; do
  [ ! -L "$BIN_DIR/$name" ] || rm -f "$BIN_DIR/$name"
done
rm -rf "$PREFIX"
[ "$PURGE_DATA" -eq 0 ] || rm -rf "$DATA_ROOT"

echo "Uninstalled Aeloon Runtime server."
if [ "$PURGE_DATA" -eq 0 ] && [ -e "$DATA_ROOT" ]; then
  echo "Preserved Runtime data: $DATA_ROOT"
fi
