# Unified stable release operations / 统一稳定版发布流程

Desktop and Runtime source repositories build independently. Public distribution is Desktop-versioned:
one `vX.Y.Z` Release contains six Desktop installers and the six Runtime archives pinned by that
Desktop commit. Both stable metadata files point to that same tag and contain no artifact hashes.

Desktop 与 Runtime 源仓库独立构建。公开分发统一使用 Desktop 版本号：每个 `vX.Y.Z`
Release 同时包含 6 个 Desktop 安装包，以及该 Desktop commit 锁定的 6 个 Runtime 包。
两份 stable 元数据同时指向该 tag，不包含产物哈希。

## Candidate and release flow / 候选版与正式版流程

1. Runtime `main` bumps its version and runs `runtime-release.yml`. The source Release contains the
   fixed six Runtime assets and dispatches `publish-runtime`.
2. Distribution validates the Runtime source tag and asset names, then dispatches the Desktop
   Runtime-lock workflow. That PR pins Runtime version, source commit, URLs, and protocol types.
3. After the lock PR merges, Desktop bumps its version and runs `desktop-release.yml`. Its immutable
   source Release contains the fixed six Desktop assets and dispatches `publish-desktop`.
4. `candidate.yml` handles that dispatch. It verifies the source tag and digests, then uploads a
   seven-day, all-platform Actions artifact. A manual run may instead select only macOS arm64,
   Linux arm64, Linux x86_64, or Windows x64 for focused testing. No candidate creates a tag or Release or can
   update stable metadata.
5. Testers download the candidate from the Actions run page and complete acceptance testing.
6. The release owner manually runs `publish.yml` with the tested candidate run ID and required
   Chinese and English summaries. Official publication accepts only an `all` candidate, promotes
   those exact Desktop files, resolves the Runtime pinned by the Desktop commit, and creates the
   public `vX.Y.Z` Release.
7. The publisher resolves merged PRs in the actual UI, Runtime, and distribution source ranges back
   to completed public Issues, publishes the deduplicated public Issue list, then updates both stable
   files through one protected PR.

对应中文流程：先发布 Runtime 并合入 Desktop Runtime-lock PR；Desktop 构建完成后只产生
可下载的 Actions 候选产物。手动运行候选流程时，可以只选择 macOS arm64、Linux arm64、
Linux x86_64 或 Windows x64；正式发版必须使用全平台 `all` 候选。候选版验收通过后，发布负责人手动选择
该候选运行并填写中英文说明；正式流程才创建公开 Release、从三个实际 source range 生成已完成
公开 Issue 清单，并更新 stable。

## Candidate isolation / 候选版隔离

A test candidate is an Actions artifact, not a GitHub prerelease, draft Release, or floating tag.
Therefore it never appears on the Releases page, cannot become Latest, cannot be consumed by the
installers, and expires automatically after seven days. The artifact contains `candidate.json` with
the selected platform, source tag, full commit, asset names, sizes, and SHA-256 digests. Official
publication requires an all-platform candidate run ID and verifies those same bytes again before
promotion.

测试候选版只使用 Actions artifact，不使用 GitHub prerelease、draft Release 或浮动 tag。
因此它不会出现在 Releases 页面、不会成为 Latest、不会被安装器读取，并会在 7 天后自动
过期。候选包中的 `candidate.json` 固定所选平台、源 tag、完整 commit、资产名、大小与
SHA-256；正式发布必须提供全平台候选运行 ID，并在提升前再次校验同一批文件。

## Release notes / Release 说明

Every official Desktop Release requires a curated Chinese and English summary before it can start.
The workflow then generates the remaining notes. Each language section contains:

- the bundled Desktop and Runtime versions;
- every completed public Issue associated with merged PRs between the previous and current official
  source identities, deduplicated across UI, Runtime, and distribution.

每次正式 Desktop 发版前，发布负责人必须填写中英文说明，否则工作流直接拒绝发布。随后
工作流自动补全 Desktop/Runtime 版本，并从 UI、Runtime、发行仓库的实际 source range 反查
已完成的公开 Issue。条目只使用公开 Issue 标题与链接，不公开私有 PR 标题或链接。候选版不生成
这份说明；发布后每个 Issue 会收到带幂等标记的 Release 链接评论。

Recommended structure / 推荐结构：

```markdown
## 中文
### 本次说明
### 版本
### 已完成的公开 Issue

## English
### Summary
### Versions
### Resolved public Issues
```

## Replay and recovery / 重放与恢复

```bash
gh workflow run publish.yml --repo AetherHeart-AI/aeloon-lite \
  -f product=runtime -f version=0.1.7

gh workflow run candidate.yml --repo AetherHeart-AI/aeloon-lite \
  -f version=0.0.25 -f platform=linux-arm64

gh workflow run publish.yml --repo AetherHeart-AI/aeloon-lite \
  -f product=desktop -f version=0.0.25 \
  -f candidate_run_id=123456789 \
  -f summary_zh='本次正式版说明。' \
  -f summary_en='Official release summary.'
```

A Runtime replay only re-sends the Desktop lock update. If a Desktop candidate expires, rerun
`candidate.yml` for the same immutable source version and test the new candidate run before official
publication. Published public assets are never overwritten; a different asset set requires a new
Desktop version. Rollback restores both stable files to the same older unified tag through a normal PR.

Runtime 重放只会重新触发 Desktop 锁更新。Desktop 候选产物过期后，可针对同一不可变源
版本重跑 `candidate.yml`，但必须重新验收新的候选运行后才能正式发布。已公开资产不可覆盖，
资产集变化必须提升 Desktop 版本；回滚仍通过普通 PR 恢复两份 stable 文件。
