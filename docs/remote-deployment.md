# Browser and remote Desktop deployment

English | [简体中文](remote-deployment.zh-CN.md)

One Runtime serves a trusted team through the browser and Desktop. Accounts protect application
ownership and roles. Shell execution uses a shared system account; this is not isolation between
malicious users. Linux sandboxing stays enabled by default and requires Bubblewrap and user
namespaces. Failure to start the sandbox never silently bypasses it.

## Install the matched release

Use ARM64 or x86_64 Linux with `curl`, `tar`, `jq` and `sha256sum`. Production needs no Node, Bun or Vite.

```sh
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sh
```

The installer downloads Runtime and `aeloon-client-<Desktop version>.tar.gz` from one stable Release,
checks GitHub Release digests, and installs them together in
`~/.local/share/aeloon-runtime/releases/<Release tag>`. Desktop and server static files come from the
same `dist/client` build. Installation does not start a service or change existing data.

## Certificates, accounts and startup

An IP address or domain is supported. The certificate SAN must cover that exact address, and the
full chain must be trusted by every client: use a public CA or preinstall an internal CA. There is
no TOFU, certificate pinning, insecure fallback, or promise of self-signed certificates working by
default. Deployment tools handle issuance, renewal, replacement and subsequent service restart.
Open the chosen TCP port (default 7420) in both host and cloud firewalls.

Use a **new** data directory, port and service name for verification. Remote startup rejects old
data directories without migrating or resetting them. Keep old deployments and data independently.
Desktop local data retains its current generation.

```sh
aeloon-runtime-server account init --data-dir ~/.aeloon-server-accounts

aeloon-runtime-server run --host runtime.example.com --bind 0.0.0.0 --port 7420 \
  --data-dir ~/.aeloon-server-accounts \
  --client-dir ~/.local/share/aeloon-runtime/current/client \
  --tls-cert /path/to/fullchain.pem --tls-key /path/to/privkey.pem
```

Initialization prompts interactively for the first administrator and a password of at least 12
characters. Passwords are never command arguments. Remote startup refuses to run without an enabled
administrator. Visit `https://runtime.example.com:7420/`, or enter the same server address, username
and password in Desktop. `/`, `/login` and `/admin` support direct navigation and refresh.

## Administration and sessions

There is no public registration. `/admin` creates users, edits profiles and roles, resets passwords,
and enables or disables accounts. Disabling retains data. The final enabled administrator cannot
be disabled or demoted. Administrative status does not grant access to others' private content.
Administrators own global Provider, cloud account, search, default model and tool settings. Users
choose available models and retain personal Skills, Agents and conversation preferences; groups
remain visible only to their members. Only administrators can disable the remote Shell sandbox;
this runs Shell with the shared system account's permissions. Enabling sandboxing does not broaden
the trust promise.

Sessions expire after 30 days without use. Active clients renew through an authenticated endpoint;
network heartbeats never renew. Logout revokes the current session. Password changes, resets,
disabling and role changes revoke every session for that user and close connections. Recovery:

```sh
aeloon-runtime-server account reset-password --data-dir ~/.aeloon-server-accounts
```

Desktop retains local mode and multiple profiles. Only the main process stores revocable sessions
in an atomic, user-private file; passwords are not saved and sessions never reach the renderer.
Old pairing and system-keyring credentials are not read, migrated or deleted. Sign in again.

## Service management and updates

Use a new systemd user service with the complete command above as `ExecStart`, `Type=simple` and
`Restart=on-failure`. Production units should pin the verified `releases/<tag>` paths for both
Runtime and client, so installing another release does not change the old service. Operators grant
necessary read permissions to the certificate key. HTTPS, binding, ports and lifecycle belong to
CLI/service management, not the website.

Verify each matched Runtime, client and Desktop release on a separate directory and port before
an explicit deployment switch. Publishing never updates or switches an existing deployment.
Protocol mismatches produce a clear error; do not mix incompatible artifacts.

Uploads retain existing limits. Authenticated HTTP streams attachment and artifact downloads;
images, text and PDF can preview, while HTML/SVG and other active content force download. The file
manager entry is Desktop-only. Closing the browser does not stop server Agent work.

For certificate errors, check SAN, expiry and trust. For timeouts, check the listener and both
firewalls. For revoked sessions, sign in again. Never bypass errors by weakening TLS, copying old
credentials or resetting an old data directory.
