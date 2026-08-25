#!/bin/bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: publish_release.sh --product desktop|runtime --version VERSION
       --channel stable|prerelease --source-repository OWNER/REPO
       --source-commit SHA --published-at ISO8601 --asset-dir DIRECTORY
EOF
}

product=""
version=""
channel=""
source_repository=""
source_commit=""
published_at=""
asset_dir=""
while (($#)); do
  case "$1" in
    --product) product=$2; shift 2 ;;
    --version) version=$2; shift 2 ;;
    --channel) channel=$2; shift 2 ;;
    --source-repository) source_repository=$2; shift 2 ;;
    --source-commit) source_commit=$2; shift 2 ;;
    --published-at) published_at=$2; shift 2 ;;
    --asset-dir) asset_dir=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for value in product version channel source_repository source_commit published_at asset_dir; do
  [[ -n "${!value}" ]] || { echo "Missing --${value//_/-}" >&2; exit 2; }
done
[[ -n "${GH_TOKEN:-}" ]] || { echo "GH_TOKEN with public distribution write access is required." >&2; exit 1; }
[[ "$channel" == stable || "$channel" == prerelease ]] || { echo "Invalid channel: $channel" >&2; exit 2; }
[[ -d "$asset_dir" ]] || { echo "Asset directory does not exist: $asset_dir" >&2; exit 2; }

script_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
tag_prefix=v
[[ "$product" == desktop ]] || tag_prefix=runtime-v
tag="${tag_prefix}${version}"
scratch="$(mktemp -d "${RUNNER_TEMP:-/tmp}/aeloon-publish.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
manifest="$scratch/release-manifest.json"
python3 "$script_root/tools/release_manifest.py" build \
  --product "$product" --version "$version" \
  --source-repository "$source_repository" --source-commit "$source_commit" \
  --published-at "$published_at" --asset-dir "$asset_dir" --output "$manifest"

release_json="$scratch/release.json"
if gh release view "$tag" --repo AetherHeart-AI/aeloon-lite \
  --json isDraft,isPrerelease,assets > "$release_json" 2>/dev/null; then
  if [[ "$(jq -r .isDraft "$release_json")" != true ]]; then
    gh release download "$tag" --repo AetherHeart-AI/aeloon-lite \
      --pattern release-manifest.json --dir "$scratch/published"
    python3 "$script_root/tools/release_manifest.py" compare-release \
      "$manifest" "$scratch/published/release-manifest.json"
    python3 "$script_root/tools/release_manifest.py" pointer \
      --manifest "$scratch/published/release-manifest.json" --channel "$channel" \
      --output "$scratch/pointer.json"
    python3 "$script_root/tools/verify_public_release.py" "$scratch/pointer.json"
    echo "Published $product release $tag already contains the exact source and artifacts."
    gh api --method POST repos/AetherHeart-AI/aeloon-lite/dispatches \
      -f event_type=promote-release \
      -f "client_payload[product]=$product" -f "client_payload[tag]=$tag" \
      -f "client_payload[channel]=$channel"
    exit 0
  fi
else
  gh release create "$tag" --repo AetherHeart-AI/aeloon-lite \
    --target main --title "Aeloon ${product} ${tag}" \
    --notes "Immutable Aeloon ${product} release built from ${source_repository}@${source_commit}." \
    --draft
fi

release_id="$(gh api "repos/AetherHeart-AI/aeloon-lite/releases/tags/$tag" --jq .id)"
while IFS= read -r asset_id; do
  gh api --method DELETE "repos/AetherHeart-AI/aeloon-lite/releases/assets/$asset_id"
done < <(gh api "repos/AetherHeart-AI/aeloon-lite/releases/$release_id" --jq '.assets[].id')

mapfile -t assets < <(python3 - "$manifest" "$asset_dir" <<'PY'
import json
import sys
from pathlib import Path
manifest = json.load(open(sys.argv[1]))
root = Path(sys.argv[2])
for artifact in manifest["artifacts"]:
    print(root / artifact["name"])
PY
)
gh release upload "$tag" --repo AetherHeart-AI/aeloon-lite "${assets[@]}" "$manifest"

expected_count=$((${#assets[@]} + 1))
actual_count="$(gh release view "$tag" --repo AetherHeart-AI/aeloon-lite --json assets --jq '.assets | length')"
[[ "$actual_count" -eq "$expected_count" ]] || { echo "Draft release asset count mismatch." >&2; exit 1; }
for path in "${assets[@]}" "$manifest"; do
  name="$(basename "$path")"
  digest="sha256:$(sha256sum "$path" | cut -d ' ' -f 1)"
  remote="$(gh release view "$tag" --repo AetherHeart-AI/aeloon-lite \
    --json assets --jq ".assets[] | select(.name == \"$name\") | .digest")"
  [[ "$remote" == "$digest" ]] || { echo "Draft digest mismatch for $name" >&2; exit 1; }
done

if [[ "$channel" == prerelease ]]; then
  gh release edit "$tag" --repo AetherHeart-AI/aeloon-lite --draft=false --prerelease --latest=false
else
  gh release edit "$tag" --repo AetherHeart-AI/aeloon-lite --draft=false --prerelease=false --latest
fi
python3 "$script_root/tools/release_manifest.py" pointer \
  --manifest "$manifest" --channel "$channel" --output "$scratch/pointer.json"
python3 "$script_root/tools/verify_public_release.py" "$scratch/pointer.json"
gh api --method POST repos/AetherHeart-AI/aeloon-lite/dispatches \
  -f event_type=promote-release \
  -f "client_payload[product]=$product" -f "client_payload[tag]=$tag" \
  -f "client_payload[channel]=$channel"
