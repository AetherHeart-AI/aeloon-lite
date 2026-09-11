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
same `dist/client` build. A compatible independent Runtime update can carry the exact existing client
archive in a `runtime-v<version>` Release without rebuilding Desktop. Installation does not start a service or change existing data.

## Certificates, accounts and startup

An IP address or domain is supported. The certificate SAN must cover that exact address, and the
full chain must be trusted by every client: use a public CA or preinstall an internal CA. There is
no TOFU, certificate pinning, insecure fallback, or promise of self-signed certificates working by
default. Deployment tools handle issuance, renewal, replacement and subsequent service restart.
Open the chosen TCP port (default 7420) in both host and cloud firewalls.

Initialize once, then start using saved settings:

```sh
aeloon-runtime-server init
# Install your trusted certificate chain and key at the paths printed by init.
aeloon-runtime-server run
```

`init` asks for the certificate-covered IP/domain (without scheme or port), then the first
administrator and a password of at least 12 characters. Passwords are never command arguments.
The instance directory defaults to `~/.aeloon-lite`; `server.json` stores deployment options with
atomic private-file writes. Certificates default to `tls/fullchain.pem` and `tls/privkey.pem` under
that directory. Initialize before placing files there. Certificate issuance and renewal remain
external; missing certificates fail explicitly. No enabled administrator means no remote startup.

The listener defaults to `0.0.0.0:7420`, and the client is discovered beside the running release.
DNS maps a domain to its public IP, not its port. The saved host controls browser Origin validation;
it does not configure DNS or trust arbitrary incoming Host headers. Visit
`https://runtime.example.com:7420/`, or enter that address and account credentials in Desktop.
`/`, `/login` and `/admin` support direct navigation and refresh.

To use an existing certificate renewal directory, save its paths once:

```sh
aeloon-runtime-server init --tls-cert /path/to/fullchain.pem --tls-key /path/to/privkey.pem
```

Rerunning `init` updates deployment settings without resetting accounts or sessions. Use
`init --host runtime.example.com --port 8443` to save a changed host or port. Explicit `run` options
override only that invocation. HTTPS port 443 is omitted from the access URL; service operators
provide the OS permissions required to bind it.

An incompatible existing default directory is refused without migration or reset. Choose a fresh
custom directory when needed, and use the same `--data-dir` for initialization, startup and recovery:

```sh
aeloon-runtime-server init --data-dir /path/to/new-data
aeloon-runtime-server run --data-dir /path/to/new-data
```

Verification uses a separate data directory, port and service name. Preserve old deployments and
Desktop local data. The former `account init` and fully explicit `run` commands remain supported.

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
aeloon-runtime-server account reset-password
```

Desktop retains local mode and multiple profiles. Only the main process stores revocable sessions
in an atomic, user-private file; passwords are not saved and sessions never reach the renderer.
Old pairing and system-keyring credentials are not read, migrated or deleted. Sign in again.

## Service management and updates

Use a new systemd user service with the absolute verified
`releases/<tag>/bin/aeloon-runtime-server run` command as `ExecStart`, `Type=simple` and
`Restart=on-failure`. Data defaults to the service user's home; append `--data-dir` for custom instances.
The client follows that pinned release automatically. Do not use the floating `current` path in a
production unit. Installing another release does not change the pinned service. Operators grant
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
