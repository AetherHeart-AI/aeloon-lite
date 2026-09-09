# Remote Runtime deployment

English | [简体中文](remote-deployment.zh-CN.md)

This guide installs Aeloon Runtime on a Linux server for the user you log in as, runs it, and
connects Aeloon Desktop to it. Nothing needs root.

## 1. Check the server

You need:

- an ARM64 or x86_64 Linux host and a normal user account on it;
- TCP `7420` (or a port of your choice) open in the host firewall and any cloud security group;
- an address Desktop can reach: a public IPv4 address or DNS name, an RFC1918 LAN address, or a
  `100.64.0.0/10` CGNAT/Tailscale address. Loopback, link-local, multicast, reserved addresses, and
  IPv6 are not accepted.

## 2. Install Runtime

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/install-server.sh | sh
```

The installer unpacks the stable release under `~/.local/share/aeloon-runtime/releases/<version>`,
points `~/.local/share/aeloon-runtime/current` at it, and links `aeloon-runtime` and
`aeloon-runtime-server` into `~/.local/bin`. It starts nothing. When it is done it prints the two
things you do next: how to run the Runtime, and how to turn that into a systemd user service.

Add `~/.local/bin` to your `PATH` if it is not there already.

## 3. Run it and connect Desktop

```bash
aeloon-runtime-server run --host runtime.example.com          # or an IPv4 address; --port to change 7420
```

The Runtime listens on every interface with a self-signed certificate that the pairing code pins,
and keeps its data under `~/.aeloon-lite`. The first start of an unpaired Runtime prints a
ten-minute, single-use `AELOON1-…` pairing code; later starts do not.

1. Install and open Aeloon Desktop.
2. Choose **Connect to a remote server**.
3. Paste the pairing code.

For another code at any time, in a second terminal:

```bash
aeloon-runtime-server pair
```

Running in the foreground is fine for trying it out. Stop it with `Ctrl-C`.

## 4. Keep it running with systemd

To keep the Runtime running after you log out, make it a systemd *user* service. The installer
prints this unit with your paths filled in; replace `<host>` with the address from section 3:

```bash
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/aeloon-runtime.service <<'UNIT'
[Unit]
Description=Aeloon Runtime
Wants=network-online.target
After=network-online.target

[Service]
Type=notify
ExecStart=%h/.local/share/aeloon-runtime/current/bin/aeloon-runtime-server run --host <host>
Restart=on-failure
RestartSec=2s
WatchdogSec=30s

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now aeloon-runtime
loginctl enable-linger "$USER"        # keep user services running after logout
aeloon-runtime-server pair            # the pairing code, now that the service is up
```

The unit points at `current`, so an upgrade takes effect on the next restart. Useful commands:

```bash
systemctl --user status aeloon-runtime
systemctl --user restart aeloon-runtime
journalctl --user -u aeloon-runtime -f
```

Hosts without a systemd user session (`systemctl --user` fails, or `loginctl enable-linger` is
refused) can run the same command under `nohup`, `tmux`, or a supervisor of your choice.

## 5. Optional: use a CA-issued certificate

Install a Desktop that supports pairing v3 first (0.0.25 or newer on this release line), then pass
the PEM full chain and the matching private key to `run`, in the foreground or in the unit's
`ExecStart`:

```bash
aeloon-runtime-server run --host runtime.example.com \
  --tls-cert ~/aeloon-tls/fullchain.pem --tls-key ~/aeloon-tls/privkey.pem
```

Both files must be readable by your user. Renewal replaces the files but does not reload the
running process, so restart the Runtime from the renewal hook:

```bash
systemctl --user restart aeloon-runtime
```

## 6. Upgrade

Re-run the installer. It unpacks the new release next to the old one, repoints `current` and the
links, and leaves `~/.aeloon-lite` — data, TLS material, and paired devices — untouched. Then
restart the Runtime. An already-paired Runtime does not print a new pairing code on restart.

To go back, point `current` at the previous release directory and restart. Old releases stay under
`~/.local/share/aeloon-runtime/releases` until you delete them.

If a certificate changes or a device token is revoked, use **Pair again** in Desktop with a newly
generated pairing code. The repair flow keeps the existing connection profile.

## 7. Team hosts: one Runtime for the whole team

One running Runtime serves everybody. There are no per-person containers and no gateway: the same
process from section 3 or 4 is what a team connects to, and a device token is what says who is
calling. Add people to it, hand each of them the one-time code it prints, and every device that
redeems one is filed under that person from then on.

```bash
aeloon-runtime-server user add alice            # adds alice and prints her pairing code
aeloon-runtime-server user add alice --name "Alice Chen"
aeloon-runtime-server user pair alice           # a fresh code later; one code per device
aeloon-runtime-server user list                 # everybody on this Runtime
aeloon-runtime-server user remove alice         # off the roster; revoke her devices separately
```

A code expires in ten minutes and is good for one device. `user remove` only takes somebody off
the roster — revoke their devices with `aeloon-runtime devices revoke <device-id>` if you also
want to cut their machines off.

That roster is what everyone's contact list is drawn from, and everyone on it is an admin: any of
them can add people, edit shared Agents, and change the providers — including the endpoint every
prompt in the organisation is sent to. The providers are one global set, so there is no per-person
metering. This suits one team, not mutually distrusting parties: colleagues share the host, and an
Agent's shell runs as the user the Runtime runs as and reaches the whole data directory. Do not put
people on one Runtime who must not read each other's work.

## 8. Each Runtime keeps its own settings

Settings belong to the Runtime, not to Desktop. The Settings panel reads and writes the device you
are currently using — its heading names that device — and nothing is copied between devices. Switch
devices in the sidebar to configure another one.

Per device: providers, their credentials, endpoints, models and headers; the model catalog and the
default model; agent defaults; skills, Agents, prompt templates and context files; web search and
fetch, including the search API key; image processing; the shell path; and the Aeloon Cloud login.

A newly paired Runtime therefore starts from its own defaults, with no providers and no cloud
account. Configure it once from any device on it: the settings are the organisation's, not the
device's.

Settings are readable and writable only while that device is connected: when the active device is
offline or reconnecting, the panel reports the connection error and offers a retry instead of
showing another device's values.

The workspace sidebar reports each device's actual connection state. Cached workspaces remain visible
and selectable while a device is **Offline**; selecting one starts a normal reconnect attempt.

## 9. Uninstall

Stop the user service if there is one and remove the releases and links, preserving Runtime data:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sh -s -- --yes
```

Also remove private Runtime data under `~/.aeloon-lite`:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/main/uninstall-server.sh \
  | sh -s -- --yes --purge-data
```

Every colleague's desk lives inside that data directory, so `--purge-data` removes them too.

Releases up to v0.1.1 installed a root-owned system service under `/opt/aeloon-runtime` and
`/var/lib/aeloon-lite`. Remove one of those with the uninstaller from that release:

```bash
curl -fsSL https://raw.githubusercontent.com/AetherHeart-AI/aeloon-lite/v0.1.1/uninstall-server.sh \
  | sudo sh -s -- --yes
```

## Quick troubleshooting

- Cannot connect: check that the Runtime is running (`systemctl --user status aeloon-runtime`, or
  the terminal it runs in), TCP port access, and cloud firewall rules.
- Pairing code expired: run `aeloon-runtime-server pair`.
- Certificate rejected: check expiry, hostname/IP SAN, full chain, and the Desktop system trust store.
- Detailed logs: `journalctl --user -u aeloon-runtime -n 100 --no-pager`, or the foreground output.
- The service does not survive logout: run `loginctl enable-linger "$USER"`.
- Pairing refused: `user list` shows whether the person is on the roster, and a code lasts ten
  minutes for one device — `user pair <id>` issues a fresh one.
