#!/bin/bash
set -euo pipefail

readonly DISTRIBUTION_REPOSITORY="AetherHeart-AI/aeloon-lite"

usage() {
  cat <<'EOF'
Usage: publish_release.sh --desktop-version VERSION --desktop-source-commit SHA
       --runtime-version VERSION --runtime-source-commit SHA --asset-dir DIRECTORY
EOF
}

desktop_version=""
desktop_source_commit=""
runtime_version=""
runtime_source_commit=""
asset_dir=""
while (($#)); do
  case "$1" in
    --desktop-version) desktop_version=$2; shift 2 ;;
    --desktop-source-commit) desktop_source_commit=$2; shift 2 ;;
    --runtime-version) runtime_version=$2; shift 2 ;;
    --runtime-source-commit) runtime_source_commit=$2; shift 2 ;;
    --asset-dir) asset_dir=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

for version in "$desktop_version" "$runtime_version"; do
  [[ "$version" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || {
    echo "Only stable semantic versions are supported: $version" >&2
    exit 2
  }
done
for commit in "$desktop_source_commit" "$runtime_source_commit"; do
  [[ "$commit" =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid source commit: $commit" >&2; exit 2; }
done
[[ -d "$asset_dir" ]] || { echo "Asset directory does not exist: $asset_dir" >&2; exit 2; }
[[ -n "${GH_TOKEN:-}" ]] || { echo "AELOON_RELEASE_TOKEN is required through GH_TOKEN." >&2; exit 1; }

tag="v$desktop_version"
expected=(
  "aeloon-lite-$desktop_version-arm64.deb"
  "aeloon-lite-$desktop_version-arm64.dmg"
  "aeloon-lite-$desktop_version-arm64.rpm"
  "aeloon-lite-$desktop_version-x86_64.deb"
  "aeloon-lite-$desktop_version-x86_64.rpm"
  "aeloon-runtime-darwin-aarch64.tar.zst"
  "aeloon-runtime-linux-aarch64.tar.gz"
  "aeloon-runtime-linux-aarch64.tar.zst"
  "aeloon-runtime-linux-x86_64.tar.gz"
  "aeloon-runtime-linux-x86_64.tar.zst"
)
declare -A expected_names=()
for name in "${expected[@]}"; do
  [[ -f "$asset_dir/$name" ]] || { echo "Missing release asset: $name" >&2; exit 1; }
  expected_names["$name"]=1
done
while IFS= read -r name; do
  [[ -n "${expected_names[$name]+present}" ]] || { echo "Unexpected release asset: $name" >&2; exit 1; }
done < <(find "$asset_dir" -maxdepth 1 -type f -printf '%f\n' | sort)
[[ "$(find "$asset_dir" -maxdepth 1 -type f | wc -l)" -eq "${#expected[@]}" ]] || {
  echo "Release asset count does not match the fixed unified contract." >&2
  exit 1
}

scratch="$(mktemp -d "${RUNNER_TEMP:-/tmp}/aeloon-publish.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
body="$scratch/release-notes.md"
cat > "$body" <<EOF
## 中文

### 安装

- 本地使用（Desktop，已内置 Runtime）：
  \`curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh\`
- Remote 使用（Linux systemd 服务器）：
  \`curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sudo sh\`

### 版本

- Desktop: \`$desktop_version\`
- Runtime: \`$runtime_version\`

> 发布负责人需在发布后按 \`docs/releasing.md\` 补充自上个公开版本以来的主要 PR 与改动说明。

## English

### Installation

- Local use (Desktop with bundled Runtime):
  \`curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install.sh | sh\`
- Remote use (Linux systemd server):
  \`curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sudo sh\`

### Versions

- Desktop: \`$desktop_version\`
- Runtime: \`$runtime_version\`

> After publication, the release owner must add the major PRs and their changes since the previous public release, following \`docs/releasing.md\`.
EOF

release_id="$(gh api "repos/$DISTRIBUTION_REPOSITORY/releases?per_page=100" \
  --jq "map(select(.tag_name == \"$tag\")) | first | .id // empty")"
if [[ -z "$release_id" ]]; then
  release_id="$(gh api --method POST "repos/$DISTRIBUTION_REPOSITORY/releases" \
    -f "tag_name=$tag" -f target_commitish=main -f "name=Aeloon $tag" \
    -F "body=@$body" -F draft=true --jq .id)"
fi

release_json="$scratch/release.json"
gh api "repos/$DISTRIBUTION_REPOSITORY/releases/$release_id" > "$release_json"
is_draft="$(jq -r .draft "$release_json")"

verify_remote_assets() {
  gh api "repos/$DISTRIBUTION_REPOSITORY/releases/$release_id" > "$release_json"
  mapfile -t remote_names < <(jq -r '.assets[].name' "$release_json" | sort)
  mapfile -t expected_remote < <(printf '%s\n' "${expected[@]}" | sort)
  [[ "${remote_names[*]}" == "${expected_remote[*]}" ]] || {
    echo "Release $tag does not contain the exact unified asset set." >&2
    printf 'Expected: %s\nActual: %s\n' "${expected_remote[*]}" "${remote_names[*]}" >&2
    return 1
  }
}

if [[ "$is_draft" == true ]]; then
  mapfile -t existing_names < <(jq -r '.assets[].name' "$release_json")
  for name in "${existing_names[@]}"; do
    [[ -n "${expected_names[$name]+present}" ]] || {
      echo "Draft $tag contains unexpected asset $name; remove it or use a new version." >&2
      exit 1
    }
  done
  upload_paths=()
  for name in "${expected[@]}"; do upload_paths+=("$asset_dir/$name"); done
  gh release upload "$tag" --repo "$DISTRIBUTION_REPOSITORY" --clobber "${upload_paths[@]}"
  verify_remote_assets
  gh release edit "$tag" --repo "$DISTRIBUTION_REPOSITORY" --draft=false --latest
else
  verify_remote_assets || {
    echo "Published release $tag has a different asset set; use a new Desktop version." >&2
    exit 1
  }
fi

desktop_channel="$scratch/desktop-stable"
runtime_channel="$scratch/runtime-stable"
cat > "$desktop_channel" <<EOF
# aeloon-release-v2
# product=desktop
# version=$desktop_version
# release=$tag
# source=AetherHeart-AI/aeloon-lite-ui@$desktop_source_commit
EOF
cat > "$runtime_channel" <<EOF
# aeloon-release-v2
# product=runtime
# version=$runtime_version
# release=$tag
# source=AetherHeart-AI/aeloon-lite-runtime@$runtime_source_commit
EOF

channel_matches_main() {
  path=$1
  expected_file=$2
  json="$scratch/main-${path//\//-}.json"
  current="$scratch/current-${path//\//-}"
  gh api "repos/$DISTRIBUTION_REPOSITORY/contents/$path?ref=main" > "$json" 2>/dev/null || return 1
  jq -r .content "$json" | base64 --decode > "$current"
  cmp -s "$expected_file" "$current"
}
if channel_matches_main channels/desktop/stable "$desktop_channel" \
  && channel_matches_main channels/runtime/stable "$runtime_channel"; then
  echo "Unified stable already points to $tag."
  exit 0
fi

branch="automation/stable-$tag"
main_commit="$(gh api "repos/$DISTRIBUTION_REPOSITORY/git/ref/heads/main" --jq .object.sha)"
if ! gh api "repos/$DISTRIBUTION_REPOSITORY/git/ref/heads/$branch" >/dev/null 2>&1; then
  gh api --method POST "repos/$DISTRIBUTION_REPOSITORY/git/refs" \
    -f "ref=refs/heads/$branch" -f "sha=$main_commit" >/dev/null
fi

update_channel() {
  path=$1
  source_file=$2
  encoded="$(base64 < "$source_file" | tr -d '\n')"
  current_json="$scratch/branch-${path//\//-}.json"
  file_sha=""
  if gh api "repos/$DISTRIBUTION_REPOSITORY/contents/$path?ref=$branch" > "$current_json" 2>/dev/null; then
    file_sha="$(jq -r .sha "$current_json")"
  fi
  if [[ -n "$file_sha" ]]; then
    jq -n --arg message "release: set unified $tag stable" --arg content "$encoded" \
      --arg sha "$file_sha" --arg branch "$branch" \
      '{message:$message,content:$content,sha:$sha,branch:$branch}' > "$scratch/update.json"
  else
    jq -n --arg message "release: set unified $tag stable" --arg content "$encoded" \
      --arg branch "$branch" '{message:$message,content:$content,branch:$branch}' > "$scratch/update.json"
  fi
  gh api --method PUT "repos/$DISTRIBUTION_REPOSITORY/contents/$path" \
    --input "$scratch/update.json" >/dev/null
}
update_channel channels/desktop/stable "$desktop_channel"
update_channel channels/runtime/stable "$runtime_channel"

pr="$(gh pr list --repo "$DISTRIBUTION_REPOSITORY" --head "$branch" --state open \
  --json number --jq '.[0].number // empty')"
if [[ -z "$pr" ]]; then
  gh pr create --repo "$DISTRIBUTION_REPOSITORY" --base main --head "$branch" \
    --title "release: set unified $tag stable" \
    --body "Publishes Desktop $desktop_version and Runtime $runtime_version together and updates both stable metadata files." >/dev/null
  pr="$(gh pr view "$branch" --repo "$DISTRIBUTION_REPOSITORY" --json number --jq .number)"
fi
gh pr merge "$pr" --repo "$DISTRIBUTION_REPOSITORY" --auto --squash >/dev/null

deadline=$((SECONDS + 1100))
while :; do
  state="$(gh pr view "$pr" --repo "$DISTRIBUTION_REPOSITORY" --json state --jq .state)"
  case "$state" in
    MERGED) echo "Published $tag and updated both stable files through PR #$pr."; break ;;
    CLOSED) echo "Stable channel PR #$pr was closed without merging." >&2; exit 1 ;;
  esac
  (( SECONDS < deadline )) || { echo "Timed out waiting for stable channel PR #$pr to merge." >&2; exit 1; }
  sleep 10
done
