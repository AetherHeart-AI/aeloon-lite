# Unified stable release operations / 统一稳定版发布流程

Desktop and Runtime source repositories build independently. Public distribution is Desktop-versioned:
one `vX.Y.Z` Release contains six Desktop installers, the shared `aeloon-client-X.Y.Z.tar.gz`,
and the six Runtime archives pinned by that Desktop commit. Unified releases update both stable metadata files. A compatible server-only release may advance
Runtime stable independently; metadata contains no artifact hashes.

Desktop 与 Runtime 源仓库独立构建。公开分发统一使用 Desktop 版本号：每个 `vX.Y.Z`
Release 同时包含 6 个 Desktop 安装包、同一构建产生的 `aeloon-client-X.Y.Z.tar.gz`，
以及该 Desktop commit 锁定的 6 个 Runtime 包。
统一发布时两份 stable 元数据同时指向该 tag。兼容的服务器独立发布可单独推进 Runtime stable，
Desktop stable 保持原版本；元数据不包含产物哈希。

## Candidate and release flow / 候选版与正式版流程

1. Runtime `main` bumps its version and runs `runtime-release.yml`. The source Release contains the
   fixed six Runtime assets and dispatches `publish-runtime`.
2. Distribution validates the Runtime source tag and asset names, then dispatches the Desktop
   Runtime-lock workflow. That PR pins Runtime version, source commit, URLs, and protocol types.
3. After the lock PR merges, Desktop bumps its version and runs `desktop-release.yml`. Its immutable
   source Release contains the six Desktop installers plus the single shared client archive and dispatches `publish-desktop`.
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

For a server-only update, run the Runtime source release workflow with `client_release=vX.Y.Z`,
selecting an existing public Desktop release. Distribution compares the generated RPC manifests
against the Runtime originally paired with that client, verifies all source asset digests, and copies
the exact existing client archive into the new public `runtime-v<version>` release alongside the six
Runtime archives. No new client build or Desktop version is created. The manifest check is a protocol
guard, not a substitute for browser/Desktop compatibility acceptance. Without this explicit input,
the original Runtime-only six-asset publication remains available for subsequent Desktop builds.

For replay of a paired server release, supply the same `client_release`:

```sh
gh workflow run publish.yml --repo AetherHeart-AI/aeloon-lite \
  -f product=runtime -f version=0.4.1 -f client_release=v0.3.0
```

After the server pair passes acceptance, update only `channels/runtime/stable` through a checked PR:
keep schema v2, set the new Runtime version, `release=runtime-v<version>`, and its source commit.
The installer identifies the single client archive in that Release and verifies both downloads.
Desktop stable remains unchanged; the automated Desktop Runtime-lock PR prepares a future build but
does not publish one. Published asset names and bytes are immutable, including on replay. An old
six-asset release cannot be expanded in place. Roll back the affected stable metadata through a PR;
existing services stay pinned until an operator explicitly changes them.

服务器独立发布时，在 Runtime 构建工作流传入 `client_release=vX.Y.Z`，复用已有公开网页包。
发行流程校验协议清单一致和源文件摘要，把原网页包与新 Runtime 包发布到同一个
`runtime-v<版本>` Release。验收通过后仅通过受检查的 PR 更新 Runtime stable；Desktop
无需重新发版。重放必须传入相同网页版本，不能覆盖已发布文件或为旧 Release 追加产物。
候选过期时仍需重新验证 Desktop 候选，统一 Desktop 发布继续沿用上述流程。

The Desktop workflow builds `dist/client` once and shares it with every platform packaging job and
server archive. Server installation verifies both archives against GitHub Release asset digests and
installs a matching pair; it never starts, switches or upgrades an existing service. Acceptance uses a
fresh explicit data directory and separate service/port, with a certificate trusted for its address.
