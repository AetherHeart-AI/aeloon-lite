# Unified stable release operations / 统一稳定版发布流程

Desktop and Runtime source repositories build independently. Public distribution is Desktop-versioned:
one `vX.Y.Z` Release contains five Desktop installers and the five Runtime archives pinned by that
Desktop commit. Both stable metadata files point to that same tag and contain no artifact hashes.

Desktop 与 Runtime 源仓库独立构建。公开分发统一使用 Desktop 版本号：每个 `vX.Y.Z`
Release 同时包含 5 个 Desktop 安装包，以及该 Desktop commit 锁定的 5 个 Runtime 包。
两份 stable 元数据同时指向该 tag，不包含产物哈希。

## Release flow / 发布流程

1. Runtime `main` bumps its version and runs `runtime-release.yml`. The source Release contains the
   fixed five Runtime assets and dispatches `publish-runtime`.
2. Distribution validates the Runtime source tag and asset names, then dispatches the Desktop
   Runtime-lock workflow. That PR pins Runtime version, source commit, URLs, and protocol types.
3. After the lock PR merges, Desktop bumps its version and runs `desktop-release.yml`. Its source
   Release contains the fixed five Desktop assets and dispatches `publish-desktop`.
4. Distribution resolves `runtime-bundle.lock.json` at the Desktop tag, downloads both fixed source
   asset sets, and creates one public `vX.Y.Z` Release containing all ten assets.
5. One protected auto-merge PR updates `channels/desktop/stable` and `channels/runtime/stable`
   together. Installers read only these current stable records and do not verify artifact hashes.

对应中文流程：先发布 Runtime 源 Release 并合入 Desktop Runtime-lock PR；再发布 Desktop
源 Release；分发仓库从 Desktop tag 读取锁定的 Runtime，将两边共 10 个资产合入同一个
公开 `vX.Y.Z` Release，最后通过一个受保护 PR 同时更新两份 stable 元数据。

## Release notes / Release 说明

After every public release, the release owner must replace the generated reminder with a curated,
bilingual summary. Each language section must include:

- the local Desktop and Remote Runtime installation commands;
- the bundled Desktop and Runtime versions;
- major PRs merged since the previous public Desktop release, across UI, Runtime, and distribution;
- a direct PR link plus one plain-language sentence explaining what changed; and
- only user-visible or operationally important changes—omit version-bump and stable-pointer PRs.

每次公开发版后，发布负责人必须把自动生成的提示替换为人工整理的双语说明。中英文部分
都必须包含：本地 Desktop 与 Remote Runtime 安装命令、两个组件版本，以及自上一个公开
Desktop 版本以来 UI、Runtime、分发三仓的主要 PR。每个 PR 都要给出直达链接，并用一句
易懂的话说明改了什么；版本号提升和 stable 指针等纯机械 PR 不列入主要更改。

Recommended structure / 推荐结构：

```markdown
## 中文
### 安装
### 版本
### 主要更改
- [UI #123](...)：改动说明。

## English
### Installation
### Versions
### Major changes
- [UI #123](...): What changed.
```

## Replay and recovery / 重放与恢复

```bash
gh workflow run publish.yml --repo AetherHeart-AI/aeloon-lite \
  -f product=runtime -f version=0.1.7

gh workflow run publish.yml --repo AetherHeart-AI/aeloon-lite \
  -f product=desktop -f version=0.0.25
```

A Runtime replay only re-sends the Desktop lock update. A Desktop replay reconstructs the unified
asset set from immutable source tags. Published public assets are never overwritten; a different
asset set requires a new Desktop version. Rollback restores both stable files to the same older
unified tag through a normal PR.

Runtime 重放只会重新触发 Desktop 锁更新；Desktop 重放会从不可变源 tag 重建统一资产集。
已公开资产不可覆盖，资产集变化必须提升 Desktop 版本。回滚必须通过普通 PR，把两份
stable 文件同时恢复到同一个旧统一 tag。
