#!/usr/bin/env bash
set -euo pipefail

# SHA-256 from the Alibaba Cloud ossutil 2.4.0 download table.
readonly version=2.4.0
readonly archive="ossutil-${version}-linux-amd64.zip"
readonly digest=85edf66b2fb7238f5c7e25cab820cf29312319fe4935b7c86a6b8485eb434f3c
readonly root="${RUNNER_TEMP:-/tmp}/aeloon-ossutil-${version}"
mkdir -p "$root"
curl --fail --location --retry 3 \
  "https://gosspublic.alicdn.com/ossutil/v2/${version}/${archive}" \
  --output "$root/$archive"
printf '%s  %s\n' "$digest" "$root/$archive" | sha256sum --check -
unzip -q "$root/$archive" -d "$root"
binary="$root/ossutil-${version}-linux-amd64/ossutil"
test -f "$binary"
chmod 0755 "$binary"
test -n "${GITHUB_PATH:-}" || { echo 'GITHUB_PATH is required.' >&2; exit 1; }
printf '%s\n' "$(dirname "$binary")" >> "$GITHUB_PATH"
