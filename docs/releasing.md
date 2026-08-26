# Stable release operations

Desktop and Runtime each have one manually dispatched source workflow. The workflow derives the version from its source manifest, builds and verifies every product artifact, creates the immutable source tag, and invokes `tools/publish_release.sh`.

## Credential

Store the same fine-grained token as `AELOON_RELEASE_TOKEN` in the Desktop and Runtime source repositories. It needs:

- `AetherHeart-AI/aeloon-lite`: Contents read/write;
- `AetherHeart-AI/aeloon-lite-ui`: Contents and Pull requests read/write.

The distribution ruleset must allow that automation identity to update `channels/*/stable` on `main`. Source tags use each source repository's `GITHUB_TOKEN`. No RPM signing or promotion credential is required.

## Release transaction

1. Merge a stable version bump into protected `main` and wait for normal source CI.
2. Dispatch the source Release workflow from `main`; it has no inputs.
3. Platform jobs build and verify the final artifacts. No public state changes before every required smoke test succeeds.
4. The publisher creates or resumes a Draft, uploads the fixed asset set and `SHA256SUMS`, and compares every GitHub digest.
5. The publisher makes the Release public and updates the matching stable file through the GitHub Contents API.
6. A Runtime release dispatches the Desktop Runtime-lock workflow. That workflow opens one auto-merge PR; Desktop remains on its previous Runtime until its own CI passes.

An interrupted Draft can be rerun with the same version. A published release can be rerun only with byte-identical artifacts; the rerun repairs a failed stable update. Different bytes always require a new version.

## Recovery

- A build, package, or installation failure leaves the current stable file unchanged.
- If publication succeeds but the stable update fails, rerun the same source workflow.
- To roll back, restore an older `channels/<product>/stable` value from Git history. Never delete, replace, or mutate a published Release.
