# Unified stable release operations / 统一稳定版发布流程

Desktop and Runtime source repositories build independently. Public distribution is Desktop-versioned:
one `vX.Y.Z` Release contains five Desktop installers and the five Runtime archives pinned by that
Desktop commit. Both stable metadata files point to that same tag and contain no artifact hashes.

Desktop 与 Runtime 源仓库独立构建。公开分发统一使用 Desktop 版本号：每个 `vX.Y.Z`
Release 同时包含 5 个 Desktop 安装包，以及该 Desktop commit 锁定的 5 个 Runtime 包。
两份 stable 元数据同时指向该 tag，不包含产物哈希。

## Candidate and release flow / 候选版与正式版流程

1. Runtime `main` bumps its version and runs `runtime-release.yml`. The source Release contains the
   fixed five Runtime assets and dispatches `publish-runtime`.
2. Distribution validates the Runtime source tag and asset names, then dispatches the Desktop
   Runtime-lock workflow. That PR pins Runtime version, source commit, URLs, and protocol types.
3. After the lock PR merges, Desktop bumps its version and runs `desktop-release.yml`. Its immutable
   source Release contains the fixed five Desktop assets and dispatches `publish-desktop`.
4. `candidate.yml` handles that dispatch. It verifies the source tag and digests, then uploads a
   seven-day Actions artifact named `aeloon-lite-desktop-vX.Y.Z-candidate`. It does not create a tag
   or Release and cannot update stable metadata.
5. Testers download the candidate from the Actions run page and complete acceptance testing.
6. The release owner manually runs `publish.yml` with the tested candidate run ID and required
   Chinese and English summaries. The workflow promotes those exact Desktop files, resolves the
   Runtime pinned by the Desktop commit, and creates the public `vX.Y.Z` Release.
7. The publisher automatically records every merged PR between the previous and current official
   versions in UI, Runtime, and distribution, then updates both stable files through one protected PR.

对应中文流程：先发布 Runtime 并合入 Desktop Runtime-lock PR；Desktop 构建完成后只产生
可下载的 Actions 候选产物。候选版验收通过后，发布负责人手动选择该候选运行并填写中英文
说明；正式流程才创建公开 Release、生成两个正式版本之间三仓的完整 PR 清单，并更新 stable。

## Candidate isolation / 候选版隔离

A test candidate is an Actions artifact, not a GitHub prerelease, draft Release, or floating tag.
Therefore it never appears on the Releases page, cannot become Latest, cannot be consumed by the
installers, and expires automatically after seven days. The artifact contains `candidate.json` with
the source tag, full commit, asset names, sizes, and SHA-256 digests. Official publication requires
the candidate run ID and verifies those same bytes again before promotion.

测试候选版只使用 Actions artifact，不使用 GitHub prerelease、draft Release 或浮动 tag。
因此它不会出现在 Releases 页面、不会成为 Latest、不会被安装器读取，并会在 7 天后自动
过期。候选包中的 `candidate.json` 固定源 tag、完整 commit、资产名、大小与 SHA-256；正式
发布必须提供候选运行 ID，并在提升前再次校验同一批文件。

## Release notes / Release 说明

Every official Desktop Release requires a curated Chinese and English summary before it can start.
The workflow then generates the remaining notes. Each language section contains:

- the local Desktop and Remote Runtime installation commands;
- the bundled Desktop and Runtime versions;
- every PR associated with commits between the previous and current official source identities,
  grouped into UI, Runtime, and distribution, with its title and direct link.

每次正式 Desktop 发版前，发布负责人必须填写中英文说明，否则工作流直接拒绝发布。随后
工作流自动补全安装命令、Desktop/Runtime 版本，以及 UI、Runtime、发行仓库从上个正式版
到本次 source identity 之间的全部关联 PR，包含标题和直达链接。候选版不生成这份说明。

Recommended structure / 推荐结构：

```markdown
## 中文
### 本次说明
### 安装
### 版本
### 自上个正式版以来的 PR
#### Desktop / Runtime / 发行控制

## English
### Summary
### Installation
### Versions
### Pull requests since the previous official release
#### Desktop / Runtime / Distribution
```

## Replay and recovery / 重放与恢复

```bash
gh workflow run publish.yml --repo AetherHeart-AI/aeloon-lite \
  -f product=runtime -f version=0.1.7

gh workflow run candidate.yml --repo AetherHeart-AI/aeloon-lite \
  -f version=0.0.25

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
