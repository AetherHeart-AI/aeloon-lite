# Remote Runtime deployment

English | [简体中文](remote-deployment.zh-CN.md)

This guide installs Aeloon Runtime on a Linux server and connects Aeloon Desktop to it.

## 1. Check the server

You need:

- an ARM64 or x86_64 Linux host running systemd as PID 1;
- root or `sudo` access;
- inbound TCP port `7420` (or your chosen port);
- a public IPv4, RFC1918 address, or `100.64.0.0/10` CGNAT/Tailscale address reachable from Desktop.

```bash
ps -p 1 -o comm=
systemctl is-system-running
```

The first command must report `systemd`. Minimal containers whose PID 1 is `bash` cannot use the
service installer.

## 2. Install Runtime

For a public server whose address can be detected automatically:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh
```

To choose the address, port, and workspace explicitly:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh -s -- \
      --host runtime.example.com \
      --port 7420 \
      --workspace-root /srv/aeloon-workspaces
```

For a LAN or Tailscale deployment, use the reachable private address with `--host`, for example
`192.168.1.20` or `100.64.0.8`. Loopback, link-local, multicast, reserved addresses, and IPv6 are
not accepted.

Allow the selected TCP port in both the host firewall and any cloud security group. The installer
updates active UFW/firewalld rules it can manage, but it cannot change a cloud firewall.

## 3. Connect Desktop

The installer prints a QR code and a single-use `AELOON1-…` pairing code valid for ten minutes.

1. Install and open Aeloon Desktop.
2. Choose **Connect to a remote server**.
3. Scan the QR code or paste the complete pairing code.

If the code expires, generate a new one without reinstalling:

```bash
sudo aeloon-runtime-server pair
```

## 4. Optional: use a CA-issued certificate

Install a Desktop release with pairing-v3 support (0.0.25 or later in this release line), then pass
the PEM full chain and matching private key together:

```bash
sudo install -d -o root -g aeloon -m 0750 /srv/aeloon-tls
sudo install -o root -g aeloon -m 0640 /source/fullchain.pem /srv/aeloon-tls/fullchain.pem
sudo install -o root -g aeloon -m 0640 /source/privkey.pem /srv/aeloon-tls/privkey.pem

curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh \
  | sudo sh -s -- \
      --host runtime.example.com \
      --tls-cert /srv/aeloon-tls/fullchain.pem \
      --tls-key /srv/aeloon-tls/privkey.pem
```

Both files and their parent directories must be readable/traversable by the `aeloon` service user.
Do not make a private key world-readable. Default `/etc/letsencrypt/live` permissions are commonly
too restrictive, so use a protected `root:aeloon` location or a certificate-manager deploy hook.

Certificate renewal does not reload the running TLS context. Make the renewal hook refresh the
protected copies above, then restart the service:

```bash
sudo systemctl restart aeloon-runtime.service
```

## 5. Operate and upgrade

```bash
aeloon-runtime-server status              # systemd status
sudo aeloon-runtime-server status         # also version, endpoint, and device count
aeloon-runtime-server logs
sudo /opt/aeloon-runtime/upgrade           # upgrade to the current stable Runtime
sudo aeloon-runtime-server rollback        # return to the previous managed release
```

An upgrade preserves Runtime data, workspace configuration, TLS paths, and paired devices. When a
device already exists, upgrading or rolling back does not print a new pairing code.

If a certificate changes or a device token is revoked, use **Pair again** in Desktop with a newly
generated server pairing code. The repair flow keeps the existing connection profile.

## 6. Synchronize Runtime settings

Desktop treats its local Runtime as the single source of truth for portable configuration. Pairing a
new remote, opening Desktop, reconnecting a remote, saving local settings, or detecting remote drift
automatically copies the local snapshot to that remote. **Sync all remotes** applies it immediately
to online devices; offline devices remain pending and are synchronized after they reconnect. A failed
first sync does not remove the paired connection profile.

The snapshot includes agent defaults, providers and their credentials, models and endpoints, proxy
and header settings, skill/subagent/template/context switches, image processing, and web search/fetch
configuration. Machine-specific state stays local to each Runtime: workspaces, data/resource
directories, shell paths, plugin configuration, device profiles and tokens, projects, tasks, sessions,
UI preferences, model display filters, and Aeloon Cloud login state or machine name are not copied.

Credentials are exported only over the local Unix connection, remain in Electron main-process memory,
and are sent only through verified TLS/WSS or an SSH tunnel. They are not exposed to the renderer,
events, errors, or logs. Use Runtime 0.1.9 or later for secure settings synchronization. Older Runtime
versions can still connect, but Desktop marks synchronization as requiring an upgrade.

The workspace sidebar reports each device's actual connection state. Cached workspaces remain visible
and selectable while a device is **Offline**; selecting one starts a normal reconnect attempt.

## 7. Uninstall

Remove the service and managed releases while preserving Runtime data and the workspace:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes
```

Also remove private Runtime data under `/var/lib/aeloon-runtime`:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sudo sh -s -- --yes --purge-data
```

The configured workspace is always preserved.

## Quick troubleshooting

- Cannot connect: verify `systemctl status aeloon-runtime`, TCP port access, and cloud firewall rules.
- Pairing code expired: run `sudo aeloon-runtime-server pair`.
- Certificate rejected: check expiry, hostname/IP SAN, full chain, and the Desktop system trust store.
- Certificate files unreadable: verify access with `sudo -u aeloon test -r PATH` and parent-directory
  traversal permissions.
- Detailed logs: run `aeloon-runtime-server logs` or
  `journalctl -u aeloon-runtime.service -n 100 --no-pager`.
