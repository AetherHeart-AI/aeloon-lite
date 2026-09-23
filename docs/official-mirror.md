# Official CDN mirror and native installer operations

The public entry point is `https://downloads.aeloon-lite.aetherheart.com/download.html`.
The origin is the private Beijing OSS bucket `aeloon-lite`. CDN private-bucket origin access
authenticates the CDN to OSS; every object reachable through this CDN hostname is public to
anyone who knows its URL. Keep credentials, test data, and private files out of this bucket.

## One-time Alibaba Cloud setup

1. In RAM SSO management, create an OIDC IdP with issuer
   `https://token.actions.githubusercontent.com` and audience/client ID `sts.aliyuncs.com`.
   The GitHub Actions credentials action uses this audience by default.
2. Create a RAM role trusted by that IdP. Restrict the trust policy using `StringEquals` on
   `oidc:iss`, `oidc:aud`, and `oidc:sub`. This repository was created after GitHub's July 2026
   immutable-subject transition, and its GitHub OIDC setting reports the subject prefix
   shown below. The exact `main` branch subject is
   `repo:AetherHeart-AI@277445285/aeloon-lite@1346161707:ref:refs/heads/main`.
   Do not use a wildcard or trust pull requests. The role must have no permanent AccessKey.

   ```json
   {
     "Version": "1",
     "Statement": [{
       "Effect": "Allow",
       "Principal": {"Federated": "acs:ram::<account-id>:oidc-provider/<provider-name>"},
       "Action": "sts:AssumeRole",
       "Condition": {"StringEquals": {
         "oidc:iss": "https://token.actions.githubusercontent.com",
         "oidc:aud": "sts.aliyuncs.com",
         "oidc:sub": "repo:AetherHeart-AI@277445285/aeloon-lite@1346161707:ref:refs/heads/main"
       }}
     }]
   }
   ```

3. Attach a custom RAM permission policy limited to distribution object keys. `ossutil cp`
   needs `PutObject`, `ListParts`, and `AbortMultipartUpload` for multipart transfers. The
   mirror uses `stat` and reads small legacy sidecars, with a full-object comparison only
   when no digest attestation exists.

   ```json
   {
     "Version": "1",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["oss:GetBucketInfo"],
         "Resource": ["acs:oss:*:*:aeloon-lite"]
       },
       {
         "Effect": "Allow",
         "Action": ["oss:PutObject", "oss:GetObject", "oss:GetObjectAcl", "oss:PutObjectAcl", "oss:ListParts", "oss:AbortMultipartUpload"],
         "Resource": [
           "acs:oss:*:*:aeloon-lite/releases/*",
           "acs:oss:*:*:aeloon-lite/channels/desktop/stable",
           "acs:oss:*:*:aeloon-lite/channels/runtime/stable",
           "acs:oss:*:*:aeloon-lite/installer/*",
           "acs:oss:*:*:aeloon-lite/download.html",
           "acs:oss:*:*:aeloon-lite/install.sh",
           "acs:oss:*:*:aeloon-lite/install.ps1",
           "acs:oss:*:*:aeloon-lite/install-server.sh"
         ]
       }
     ]
   }
   ```

4. Set GitHub repository variables `AELOON_OSS_OIDC_PROVIDER_ARN` and
   `AELOON_OSS_ROLE_ARN` to the IdP and role ARNs. Do not store AccessKeys in GitHub.
5. Keep the bucket private and CDN private-bucket origin enabled. Configure CDN HTTPS for
   `downloads.aeloon-lite.aetherheart.com`, redirect HTTP port 80 to HTTPS, and alert the
   certificate owner before expiry. Set CDN cache rules for `releases/` and `installer/`
   versioned paths to at least 30 days; set `channels/`, root install scripts, and
   `/download.html` to 60 seconds. Confirm HTTPS and redirect from an external network.

## Automated flow

`publish.yml` verifies the accepted source assets, uploads a GitHub draft Release, compares
GitHub asset digests to the same local bytes, mirrors immutable files to OSS with size and
CRC-64 checks, writes `manifest.json` last, then publishes the GitHub Release and opens the
existing stable PR. An OSS failure leaves the Release draft and does not advance stable.
Runtime-only Releases mirror six archives, plus the matched client archive when paired.
Only a tested pair may advance Runtime stable. Candidate packages remain in Actions.

Immutable objects are `releases/<tag>/<asset>`, `releases/<tag>/checksums.txt`, and
`releases/<tag>/manifest.json`. The text index lists each asset's SHA-256 and byte size
for the POSIX Desktop script without requiring `jq`; the JSON manifest provides the same
values to the other installers. New package objects also carry SHA-256 metadata. A repeat
run checks the GitHub asset digest and size against the OSS object metadata, then skips
matching packages without downloading them from GitHub or OSS. Older packages can be
verified through their existing small `.sha256` sidecars and OSS size/CRC-64 headers; if
neither proof exists, the mirror downloads the package to verify its SHA-256. The upload
switches to multipart above 16 MiB with 16 MiB chunks and ten parallel parts. A digest
mismatch fails without overwriting the object.
The manifest is uploaded after all packages and `checksums.txt` verify.

After a stable PR merges, `mirror-channels.yml` reads the then-current `main` copies of
both stable files, requires matching OSS manifests, and updates the two channel objects.
Rollback is a stable-file PR; versioned files remain intact. After Distribution CI passes
for an installer-source change on `main`, the installer workflow embeds the scripts at
that commit, tests and builds four targets, uploads them under
`installer/<commit>/<platform>/`, confirms both stable channels, and finally updates the
fixed scripts and `download.html`. A superseded build cannot roll the page back.

## First rollout and recovery

1. Configure RAM, GitHub variables, private origin, HTTPS, caching, and certificate alert.
2. Run `mirror-release.yml` on `main` with `tag=v0.4.1`, the tag currently used by both
   stable files. Inspect the run for exact asset count, SHA-256, object sizes, and CRC-64.
   This bootstrap run also uploads both current stable files.
3. Compare CDN channel bytes with repository files. After the feature PR merges and its
   Distribution CI passes, `publish-installer.yml` automatically publishes the four native
   packages, scripts, and `/download.html` after the channel preflight passes.
4. From outside the Alibaba Cloud account, fetch a full Desktop package and the Runtime
   plus web-client pair through HTTPS and compare SHA-256 with the manifest. Check the
   fixed page, HTTP-to-HTTPS redirect, large-file transfer, and certificate expiry alert.
5. On a disposable Linux host, use the Runtime mode and confirm the existing running
   service stays running and unchanged. The installer writes a versioned user directory
   and links commands; an administrator separately chooses any systemd service change.

If a public Release needs repair, run `mirror-release.yml` with its tag. It checks GitHub
Release digests and sizes against OSS metadata or verified legacy sidecars, then downloads
only missing or unverified GitHub assets. Downloaded assets are SHA-256 checked before
upload. A different existing object aborts the run and must be investigated; never
overwrite a versioned key. Re-run `mirror-channels.yml` after a stable rollback or repair.

Sources: [GitHub OIDC subject format](https://docs.github.com/en/actions/reference/security/oidc),
[Alibaba Cloud OIDC role trust](https://help.aliyun.com/en/ram/user-guide/create-a-ram-role-for-a-trusted-idp),
[ossutil multipart permissions](https://help.aliyun.com/en/oss/developer-reference/cp-upload-file),
[CDN private OSS origin](https://help.aliyun.com/en/cdn/user-guide/grant-alibaba-cloud-cdn-access-permissions-on-private-oss-buckets).
