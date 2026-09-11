#!/bin/sh
set -eu

REPOSITORY="AetherHeart-AI/aeloon-lite"
RAW_ROOT="https://raw.githubusercontent.com/$REPOSITORY/main"
PREFIX=${AELOON_RUNTIME_PREFIX:-$HOME/.local/share/aeloon-runtime}
BIN_DIR=${AELOON_RUNTIME_BIN_DIR:-$HOME/.local/bin}
DOWNLOAD_ONLY=""

usage() {
  cat <<'EOF'
Usage: install-server.sh [--download-only DIRECTORY]

Installs the stable Aeloon Runtime for the current user under
~/.local/share/aeloon-runtime and links its commands into ~/.local/bin.
Nothing is started and nothing outside the home directory is touched.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --download-only) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; DOWNLOAD_ONLY=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ "$(uname -s)" = Linux ] || {
  echo "Aeloon Runtime server installation supports Linux hosts only." >&2
  exit 2
}
for required_command in awk curl grep sed tar jq sha256sum; do
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

# Point a symlink at a target; refuse to touch anything that is not a symlink.
link() {
  target=$1
  path=$2
  if [ -e "$path" ] && [ ! -L "$path" ]; then
    echo "Refusing to replace $path: it is not a symlink." >&2
    exit 2
  fi
  rm -f "$path"
  ln -s "$target" "$path"
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

CHANNEL_SCHEMA=$(sed -n '1p' "$CHANNEL_FILE")
case "$CHANNEL_SCHEMA" in
  "# aeloon-release-v1"|"# aeloon-release-v2") ;;
  *)
  echo "Unsupported Runtime release metadata." >&2
  exit 2
  ;;
esac
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
if [ "$CHANNEL_SCHEMA" = "# aeloon-release-v2" ]; then
  TAG=$(metadata_value "$CHANNEL_FILE" release) || { echo "Invalid Runtime release metadata." >&2; exit 2; }
  printf '%s\n' "$TAG" | LC_ALL=C grep -Eq '^(runtime-)?v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' || {
    echo "Runtime release tag is invalid." >&2
    exit 2
  }
else
  TAG="runtime-v$VERSION"
fi

RELEASES_ROOT="$PREFIX/releases"
RELEASE_ROOT="$RELEASES_ROOT/$TAG"
CURRENT_LINK="$PREFIX/current"
SERVER_COMMAND="$BIN_DIR/aeloon-runtime-server"

print_next_steps() {
  case ":$PATH:" in
    *":$BIN_DIR:"*) ;;
    *) echo "Add $BIN_DIR to your PATH, or call the commands by their full path." ;;
  esac
  cat <<EOF

Initialize deployment settings and the first administrator (interactive):

  $SERVER_COMMAND init

The default data directory is ~/.aeloon-lite. An incompatible existing directory
is refused; use init --data-dir <new-directory> and the same option with run.
Enter the certificate-covered IP or domain once. Settings are saved in server.json.
Install a trusted certificate chain and private key at:
  ~/.aeloon-lite/tls/fullchain.pem
  ~/.aeloon-lite/tls/privkey.pem
Or save your certificate tool's paths with init --tls-cert <path> --tls-key <path>.
Certificate issuance, renewal and service restart belong to your deployment tools.

Start with saved settings and the automatically located matching web client:

  $SERVER_COMMAND run

The default listener is 0.0.0.0:7420. Open https://<IP-or-domain>:7420/.
Allow TCP 7420 in the firewall and cloud security group. No service was started.
For persistence, create a NEW systemd service (Type=simple, Restart=on-failure)
using $RELEASE_ROOT/bin/aeloon-runtime-server run and the service user's data directory.
This pins both Runtime and web client. Existing deployments and data are preserved.

Password recovery:
  $SERVER_COMMAND account reset-password

EOF
}

INSTALLED_VERSION=""
if [ -L "$CURRENT_LINK" ]; then
  INSTALLED_VERSION=$(basename "$(readlink "$CURRENT_LINK")")
fi
if [ -z "$DOWNLOAD_ONLY" ] && [ "$INSTALLED_VERSION" = "$TAG" ] && [ -x "$RELEASE_ROOT/bin/aeloon-runtime-server" ] && [ -f "$RELEASE_ROOT/client/index.html" ]; then
  echo "Aeloon Runtime $VERSION is already installed under $PREFIX."
  print_next_steps
  exit 0
fi

case "$(uname -m)" in
  aarch64|arm64) RELEASE_ARCH=aarch64 ;;
  x86_64|amd64) RELEASE_ARCH=x86_64 ;;
  *) echo "Unsupported Linux architecture: $(uname -m)" >&2; exit 2 ;;
esac
ASSET="aeloon-runtime-linux-${RELEASE_ARCH}.tar.gz"
ASSET_URL="https://github.com/$REPOSITORY/releases/download/$TAG/$ASSET"
ARCHIVE="$TEMP_ROOT/$ASSET"

[ "$CHANNEL_SCHEMA" = "# aeloon-release-v2" ] || {
  echo "A matching Runtime and client release is required." >&2; exit 2;
}
RELEASE_JSON="$TEMP_ROOT/release.json"
fetch "https://api.github.com/repos/$REPOSITORY/releases/tags/$TAG" "$RELEASE_JSON"
jq -e --arg tag "$TAG" '.tag_name == $tag and .draft == false and .prerelease == false' "$RELEASE_JSON" >/dev/null || {
  echo "Invalid stable Release identity." >&2; exit 2;
}
CLIENT_ASSET=$(jq -er '[.assets[].name | select(test("^aeloon-client-[0-9]+\\.[0-9]+\\.[0-9]+\\.tar\\.gz$"))] | if length == 1 then .[0] else error("matching client asset missing or ambiguous") end' "$RELEASE_JSON")
CLIENT_ARCHIVE="$TEMP_ROOT/$CLIENT_ASSET"
verify_asset() {
  expected=$(jq -er --arg name "$1" '[.assets[] | select(.name == $name) | .digest] | if length == 1 then .[0] else error("asset missing or ambiguous") end' "$RELEASE_JSON")
  printf '%s\n' "$expected" | grep -Eq '^sha256:[a-f0-9]{64}$' || { echo "Release asset digest unavailable." >&2; exit 2; }
  actual="sha256:$(sha256sum "$2" | awk '{print $1}')"
  [ "$actual" = "$expected" ] || { echo "Release asset digest mismatch: $1" >&2; exit 2; }
}

echo "Downloading Aeloon Runtime $VERSION from GitHub..."
fetch "$ASSET_URL" "$ARCHIVE"
verify_asset "$ASSET" "$ARCHIVE"
fetch "https://github.com/$REPOSITORY/releases/download/$TAG/$CLIENT_ASSET" "$CLIENT_ARCHIVE"
verify_asset "$CLIENT_ASSET" "$CLIENT_ARCHIVE"
CLIENT_PATHS="$TEMP_ROOT/client-paths"
tar -tzf "$CLIENT_ARCHIVE" > "$CLIENT_PATHS"
awk '/^\// {exit 1} /(^|\/)\.\.($|\/)/ {exit 1} !/^client\// {exit 1}' "$CLIENT_PATHS" || {
  echo "Client archive contains an unsafe path." >&2; exit 2;
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
  cp "$CLIENT_ARCHIVE" "$DOWNLOAD_ONLY/$CLIENT_ASSET"
  cp "$RELEASE_JSON" "$DOWNLOAD_ONLY/release.json"
  echo "Downloaded Runtime archive: $DOWNLOAD_ONLY/$ASSET"
  exit 0
fi

mkdir -p "$RELEASES_ROOT" "$BIN_DIR"
STAGING="$RELEASES_ROOT/.$TAG.$$"
mkdir -p "$STAGING"
tar -xzf "$ARCHIVE" -C "$STAGING"
for name in aeloon-runtime aeloon-runtime-server; do
  [ -x "$STAGING/aeloon-runtime/bin/$name" ] || {
    echo "Runtime archive is missing bin/$name." >&2
    exit 2
  }
done
tar -xzf "$CLIENT_ARCHIVE" -C "$STAGING/aeloon-runtime"
[ -f "$STAGING/aeloon-runtime/client/index.html" ] || { echo "Client index is missing." >&2; exit 2; }
[ ! -e "$RELEASE_ROOT" ] || { echo "Release directory already exists; refusing to replace it: $RELEASE_ROOT" >&2; exit 2; }
cp "$RELEASE_JSON" "$STAGING/aeloon-runtime/release.json"
mv "$STAGING/aeloon-runtime" "$RELEASE_ROOT"
rmdir "$STAGING"
STAGING=""

link "$RELEASE_ROOT" "$CURRENT_LINK"
for name in aeloon-runtime aeloon-runtime-server; do
  link "$CURRENT_LINK/bin/$name" "$BIN_DIR/$name"
done

if [ -n "$INSTALLED_VERSION" ]; then
  echo "Upgraded Aeloon Runtime $INSTALLED_VERSION to $VERSION (source commit $SOURCE_COMMIT) under $PREFIX."
  echo "Existing services and data were preserved. Start this release with a new data directory and service."
  echo "The old release stays in $RELEASES_ROOT; delete it when you no longer need it."
else
  echo "Installed Aeloon Runtime $VERSION (source commit $SOURCE_COMMIT) under $PREFIX."
fi
print_next_steps
