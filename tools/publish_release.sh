#!/bin/bash
set -euo pipefail

readonly DISTRIBUTION_REPOSITORY="AetherHeart-AI/aeloon-lite"

usage() {
  cat <<'EOF'
Usage: publish_release.sh --product desktop|runtime --version VERSION
       --source-commit SHA --asset-dir DIRECTORY
EOF
}

product=""
version=""
source_commit=""
asset_dir=""
while (($#)); do
  case "$1" in
    --product) product=$2; shift 2 ;;
    --version) version=$2; shift 2 ;;
    --source-commit) source_commit=$2; shift 2 ;;
    --asset-dir) asset_dir=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$product" == desktop || "$product" == runtime ]] || { echo "Invalid product: $product" >&2; exit 2; }
[[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || {
  echo "Only stable semantic versions are supported: $version" >&2
  exit 2
}
[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid source commit: $source_commit" >&2; exit 2; }
[[ -d "$asset_dir" ]] || { echo "Asset directory does not exist: $asset_dir" >&2; exit 2; }
[[ -n "${GH_TOKEN:-}" ]] || { echo "AELOON_RELEASE_TOKEN is required through GH_TOKEN." >&2; exit 1; }

if [[ "$product" == desktop ]]; then
  tag="v$version"
  source_repository="AetherHeart-AI/aeloon-lite-ui"
  channel_path="channels/desktop/stable"
  expected=(
    "aeloon-lite-$version-arm64.deb"
    "aeloon-lite-$version-arm64.dmg"
    "aeloon-lite-$version-arm64.rpm"
    "aeloon-lite-$version-x86_64.deb"
    "aeloon-lite-$version-x86_64.rpm"
  )
else
  tag="runtime-v$version"
  source_repository="AetherHeart-AI/aeloon-lite-runtime"
  channel_path="channels/runtime/stable"
  expected=(
    "aeloon-runtime-darwin-aarch64.tar.zst"
    "aeloon-runtime-linux-aarch64.tar.gz"
    "aeloon-runtime-linux-aarch64.tar.zst"
    "aeloon-runtime-linux-x86_64.tar.gz"
    "aeloon-runtime-linux-x86_64.tar.zst"
  )
fi

declare -A expected_names=()
for name in "${expected[@]}"; do
  [[ -f "$asset_dir/$name" ]] || { echo "Missing release asset: $name" >&2; exit 1; }
  expected_names["$name"]=1
done
while IFS= read -r name; do
  [[ -n "${expected_names[$name]+present}" ]] || { echo "Unexpected release asset: $name" >&2; exit 1; }
done < <(find "$asset_dir" -maxdepth 1 -type f -printf '%f\n' | sort)
[[ "$(find "$asset_dir" -maxdepth 1 -type f | wc -l)" -eq "${#expected[@]}" ]] || {
  echo "Release asset count does not match the fixed $product contract." >&2
  exit 1
}

scratch="$(mktemp -d "${RUNNER_TEMP:-/tmp}/aeloon-publish.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
checksums="$scratch/SHA256SUMS"
{
  echo "# aeloon-release-v1"
  echo "# product=$product"
  echo "# version=$version"
  echo "# source=$source_repository@$source_commit"
  while IFS= read -r name; do
    printf '%s  %s\n' "$(sha256sum "$asset_dir/$name" | awk '{print $1}')" "$name"
  done < <(printf '%s\n' "${expected[@]}" | sort)
} > "$checksums"

release_id="$(gh api "repos/$DISTRIBUTION_REPOSITORY/releases?per_page=100" \
  --jq "map(select(.tag_name == \"$tag\")) | first | .id // empty")"
if [[ -z "$release_id" ]]; then
  release_id="$(gh api --method POST "repos/$DISTRIBUTION_REPOSITORY/releases" \
    -f "tag_name=$tag" \
    -f target_commitish=main \
    -f "name=Aeloon $product $tag" \
    -f "body=Stable Aeloon $product release built from $source_repository@$source_commit." \
    -F draft=true \
    --jq .id)"
fi

release_json="$scratch/release.json"
gh api "repos/$DISTRIBUTION_REPOSITORY/releases/$release_id" > "$release_json"
is_draft="$(jq -r .draft "$release_json")"

verify_remote_assets() {
  gh api "repos/$DISTRIBUTION_REPOSITORY/releases/$release_id" > "$release_json"
  mapfile -t remote_names < <(jq -r '.assets[].name' "$release_json" | sort)
  mapfile -t expected_remote < <(printf '%s\n' "${expected[@]}" SHA256SUMS | sort)
  [[ "${remote_names[*]}" == "${expected_remote[*]}" ]] || {
    echo "Release $tag does not contain the exact expected asset set." >&2
    printf 'Expected: %s\nActual: %s\n' "${expected_remote[*]}" "${remote_names[*]}" >&2
    return 1
  }
  for path in "${expected[@]}"; do
    local_file="$asset_dir/$path"
    local_digest="sha256:$(sha256sum "$local_file" | awk '{print $1}')"
    remote_digest="$(jq -r --arg name "$path" '.assets[] | select(.name == $name) | .digest' "$release_json")"
    [[ "$remote_digest" == "$local_digest" ]] || { echo "Release digest mismatch for $path" >&2; return 1; }
  done
  local_digest="sha256:$(sha256sum "$checksums" | awk '{print $1}')"
  remote_digest="$(jq -r '.assets[] | select(.name == "SHA256SUMS") | .digest' "$release_json")"
  [[ "$remote_digest" == "$local_digest" ]] || { echo "Release digest mismatch for SHA256SUMS" >&2; return 1; }
}

if [[ "$is_draft" == true ]]; then
  mapfile -t existing_names < <(jq -r '.assets[].name' "$release_json")
  for name in "${existing_names[@]}"; do
    if [[ "$name" != SHA256SUMS && -z "${expected_names[$name]+present}" ]]; then
      echo "Draft $tag contains unexpected asset $name; remove it or use a new version." >&2
      exit 1
    fi
  done
  upload_paths=()
  for name in "${expected[@]}"; do upload_paths+=("$asset_dir/$name"); done
  upload_paths+=("$checksums")
  gh release upload "$tag" --repo "$DISTRIBUTION_REPOSITORY" --clobber "${upload_paths[@]}"
  verify_remote_assets
  gh release edit "$tag" --repo "$DISTRIBUTION_REPOSITORY" --draft=false --latest
else
  verify_remote_assets || {
    echo "Published release $tag differs from this build; bump the version." >&2
    exit 1
  }
fi

contents_json="$scratch/channel.json"
current_channel="$scratch/current-stable"
if gh api "repos/$DISTRIBUTION_REPOSITORY/contents/$channel_path?ref=main" > "$contents_json" 2>/dev/null; then
  jq -r .content "$contents_json" | base64 --decode > "$current_channel"
  if cmp -s "$checksums" "$current_channel"; then
    echo "$product stable already points to $tag."
    exit 0
  fi
fi

encoded="$(base64 < "$checksums" | tr -d '\n')"
branch="automation/stable-$product-$tag"
main_commit="$(gh api "repos/$DISTRIBUTION_REPOSITORY/git/ref/heads/main" --jq .object.sha)"
if ! gh api "repos/$DISTRIBUTION_REPOSITORY/git/ref/heads/$branch" >/dev/null 2>&1; then
  gh api --method POST "repos/$DISTRIBUTION_REPOSITORY/git/refs" \
    -f "ref=refs/heads/$branch" \
    -f "sha=$main_commit" >/dev/null
fi

branch_channel="$scratch/branch-channel.json"
branch_file_sha=""
if gh api "repos/$DISTRIBUTION_REPOSITORY/contents/$channel_path?ref=$branch" > "$branch_channel" 2>/dev/null; then
  branch_file_sha="$(jq -r .sha "$branch_channel")"
fi
if [[ -n "$branch_file_sha" ]]; then
  jq -n --arg message "release: set $product $tag stable" \
    --arg content "$encoded" --arg sha "$branch_file_sha" --arg branch "$branch" \
    '{message:$message,content:$content,sha:$sha,branch:$branch}' > "$scratch/update.json"
else
  jq -n --arg message "release: set $product $tag stable" \
    --arg content "$encoded" --arg branch "$branch" \
    '{message:$message,content:$content,branch:$branch}' > "$scratch/update.json"
fi
gh api --method PUT "repos/$DISTRIBUTION_REPOSITORY/contents/$channel_path" \
  --input "$scratch/update.json" >/dev/null

pr="$(gh pr list --repo "$DISTRIBUTION_REPOSITORY" --head "$branch" --state open --json number --jq '.[0].number // empty')"
if [[ -z "$pr" ]]; then
  gh pr create --repo "$DISTRIBUTION_REPOSITORY" --base main --head "$branch" \
    --title "release: set $product $tag stable" \
    --body "Updates $channel_path to the verified $tag release." >/dev/null
  pr="$(gh pr view "$branch" --repo "$DISTRIBUTION_REPOSITORY" --json number --jq .number)"
fi
gh pr merge "$pr" --repo "$DISTRIBUTION_REPOSITORY" --auto --squash >/dev/null

deadline=$((SECONDS + 1100))
while :; do
  state="$(gh pr view "$pr" --repo "$DISTRIBUTION_REPOSITORY" --json state --jq .state)"
  case "$state" in
    MERGED)
      echo "Published $tag and updated $channel_path through PR #$pr."
      break
      ;;
    CLOSED)
      echo "Stable channel PR #$pr was closed without merging." >&2
      exit 1
      ;;
  esac
  if (( SECONDS >= deadline )); then
    echo "Timed out waiting for stable channel PR #$pr to merge." >&2
    exit 1
  fi
  sleep 10
done
