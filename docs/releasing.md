# Atomic release operations

`AetherHeart-AI/aeloon-lite` is the only binary distribution repository. The Desktop and Runtime
source repositories retain source commits, immutable source tags, and Actions artifacts; they do
not create binary GitHub Releases.

## Required repository secrets

The workflows intentionally fail closed when a cross-repository credential is missing.

- Desktop source: `AELOON_INSTALL_REPO_TOKEN` (write/dispatch access to this repository) and an
  automation-only, unencrypted `RPM_SIGNING_PRIVATE_KEY` for stable RPM candidates.
- Runtime source: `AELOON_INSTALL_REPO_TOKEN` and `NPM_TOKEN`. npm publication is independent and
  cannot block a Runtime channel promotion.
- Public distribution: `AELOON_RELEASE_AUTOMATION_TOKEN` (branch/PR/auto-merge access here) and
  `AELOON_UI_REPOSITORY_TOKEN` (repository-dispatch access to the Desktop source repository).
- Desktop source Runtime-lock automation: `AELOON_RELEASE_AUTOMATION_TOKEN` with branch/PR access
  to that repository.

Tokens used for automatic PRs must be able to trigger required workflows; a recursive
`GITHUB_TOKEN` update is deliberately not used.

## Release transaction

1. Dispatch the source repository's release workflow from protected `main` with `version` and
   `channel`.
2. Candidate builds and real installation tests complete before an immutable source tag is made.
3. The source workflow creates or reconciles a draft public Release, uploads the exact accepted
   Actions artifacts and `release-manifest.json`, checks every GitHub digest, and publishes once.
4. A repository dispatch opens a deterministic promotion PR here. Public CI downloads every asset,
   recomputes SHA-256, and exercises the applicable installers before auto-merge changes one
   channel pointer.
5. A stable Runtime promotion dispatches the deterministic Runtime-lock PR in the Desktop source
   repository. Its aggregate gate includes the real Runtime integration when the lock changes.

Published assets are never deleted, replaced, clobbered, or converted back to draft. An exact
rerun succeeds without new bytes; different bytes fail and require a new version.

## Channels and rollback

The installers default to `channels/{product}/stable.json`. `prerelease` accepts only suffixed
SemVer versions and never changes stable. Version records under `releases/` are append-only and
contain only the immutable manifest URL and its SHA-256.

Rollback dispatches `.github/workflows/rollback.yml` with a non-prerelease tag already present in
the append-only history. It verifies the public Release again and opens a PR that changes only the
stable pointer. Tags, Releases, assets, and historical records remain untouched.

GitHub `latest` is presentation metadata for stable Releases. Installers never read it.
