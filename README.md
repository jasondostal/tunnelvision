<p align="center">
  <img src="images/tunnelvision-readme-banner.png" alt="TunnelVision" width="800">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/jasondostal/tunnelvision?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/Alpine-3.21-0D597F?style=flat-square&logo=alpine-linux" alt="Alpine">
  <img src="https://img.shields.io/badge/WireGuard-built--in-88171A?style=flat-square&logo=wireguard" alt="WireGuard">
  <img src="https://img.shields.io/badge/OpenVPN-built--in-EA7E20?style=flat-square&logo=openvpn" alt="OpenVPN">
  <img src="https://img.shields.io/badge/Home%20Assistant-native-41BDF5?style=flat-square&logo=home-assistant" alt="Home Assistant">
</p>

---

A Docker container that manages your VPN tunnel and everything that depends on it. WireGuard, OpenVPN, nftables killswitch, DNS with DoT and ad-blocking, HTTP/SOCKS5/Shadowsocks proxies, qBittorrent, real-time dashboard, REST API, Home Assistant, Prometheus. One container. Full visibility. Full control.

**25 native providers** — [Mullvad](https://mullvad.net), [ProtonVPN](https://protonvpn.com), [PIA](https://privateinternetaccess.com), [IVPN](https://ivpn.net), [NordVPN](https://nordvpn.com), [Surfshark](https://surfshark.com), and [19 more](#native-providers) — with smart server selection, automatic rotation, port forwarding, and connection monitoring. Or bring your own config from any provider.

<p align="center">
  <img src="images/screenshot-dashboard.png" alt="TunnelVision Dashboard" width="700">
</p>

## What you get

- **VPN tunnel** — WireGuard or OpenVPN, kernel or userspace, with nftables killswitch that blocks all traffic if the tunnel drops
- **25 native providers** — server browsing, scored selection (load + speed), automatic rotation, multi-config failover
- **Auto-reconnect watchdog** — detects drops, reconnects, fails over to backup servers, notifies you
- **Port forwarding** — PIA and ProtonVPN, with hook scripts for automatic qBittorrent integration
- **Built-in DNS** — DNS-over-TLS, caching, ad/malware/surveillance blocklists
- **Proxy stack** — HTTP CONNECT, SOCKS5, and Shadowsocks AEAD — route any app through the tunnel
- **qBittorrent** — built in, pre-wired through the tunnel, killswitch-protected
- **Real-time dashboard** — React UI with SSE updates, connection history, speed testing
- **REST API** — 30+ endpoints, Swagger docs, everything scriptable
- **Home Assistant** — native HACS integration, 30 entities, SSE real-time updates, zero YAML
- **Prometheus + Grafana** — metrics endpoint, ready-made dashboard
- **Notifications** — Discord, Slack, Gotify, generic webhooks
- **Settings UI** — hot-reloadable configuration, no restarts needed
- **Multi-arch** — linux/amd64, linux/arm64, linux/arm/v7

## Quick Start

**One-liner install:**

```bash
curl -fsSL https://raw.githubusercontent.com/jasondostal/tunnelvision/main/scripts/install.sh | bash
```

**Or manually:**

```bash
mkdir -p tunnelvision/wireguard
cp /path/to/wg0.conf tunnelvision/wireguard/

curl -O https://raw.githubusercontent.com/jasondostal/tunnelvision/main/docker-compose.yml
docker compose up -d
```

Three things are now running inside one container:
- **WireGuard/OpenVPN** with nftables killswitch
- **TunnelVision API + Dashboard** on port `8081`
- **qBittorrent WebUI** on port `8080`

```bash
curl http://localhost:8081/api/v1/health | jq .
```

## Native Providers

TunnelVision has built-in support for 25 providers. Select your provider in the setup wizard, enter your credentials, pick a server, and you're connected. No config files to find, no manual WireGuard key generation (we do that for you where the provider supports it).

[Mullvad](https://mullvad.net) · [ProtonVPN](https://protonvpn.com) · [PIA](https://privateinternetaccess.com) · [IVPN](https://ivpn.net) · [NordVPN](https://nordvpn.com) · [Windscribe](https://windscribe.com) · [AirVPN](https://airvpn.org) · [Surfshark](https://surfshark.com) · [ExpressVPN](https://expressvpn.com) · [IPVanish](https://ipvanish.com) · [TorGuard](https://torguard.net) · [PrivateVPN](https://privatevpn.com) · [Perfect Privacy](https://perfect-privacy.com) · [CyberGhost](https://cyberghostvpn.com) · [Privado](https://privadovpn.com) · [PureVPN](https://purevpn.com) · [VPN Secure](https://vpnsecure.me) · [VPN Unlimited](https://vpnunlimited.com) · [VyprVPN](https://vyprvpn.com) · [FastestVPN](https://fastestvpn.com) · [HideMyAss](https://hidemyass.com) · [SlickVPN](https://slickvpn.com) · [Giganews](https://giganews.com)

For providers not on the list, use `VPN_PROVIDER=custom` and mount your own WireGuard or OpenVPN config file. Any provider that gives you a `.conf` or `.ovpn` file works.

## Integrations

### Homepage

<p align="center">
  <img src="images/screenshot-homepage.png" alt="TunnelVision Homepage Widget" width="700">
</p>

Drops right into [Homepage](https://gethomepage.dev) using the `customapi` widget. Pick the fields you want to see:

```yaml
- TunnelVision:
    icon: https://raw.githubusercontent.com/jasondostal/tunnelvision/main/images/tunnelvision-mark-dark-512.png
    href: http://your-host:8081
    description: VPN Management
    widget:
      type: customapi
      url: http://tunnelvision:8081/api/v1/vpn/status
      mappings:
        - field: state
          label: VPN
          format: text
        - field: location
          label: Location
          format: text
        - field: public_ip
          label: IP
          format: text
        - field: uptime
          label: Uptime
          format: text
```

<details>
<summary>Available fields for your widget</summary>

Pick any 4 from `/api/v1/vpn/status`:

| Field | Example | Good for |
|-------|---------|----------|
| `state` | `up` | Connection status at a glance |
| `location` | `Zurich, Switzerland` | Where you're exiting |
| `public_ip` | `193.32.127.220` | Current VPN IP |
| `uptime` | `2h 34m` | How long the tunnel's been up |
| `killswitch` | `active` | Firewall status |
| `country` | `Switzerland` | Exit country only |
| `city` | `Zurich` | Exit city only |
| `provider` | `mullvad` | VPN provider |

Or use `/api/v1/qbt/status` for torrent-focused widgets:

| Field | Example | Good for |
|-------|---------|----------|
| `state` | `running` | qBit health |
| `download_speed` | `5242880` | Current download (bytes/s) |
| `upload_speed` | `1048576` | Current upload (bytes/s) |
| `active_torrents` | `3` | Active count |
| `total_torrents` | `47` | Library size |

</details>

### Home Assistant

<p align="center">
  <img src="images/screenshot-ha.png" alt="TunnelVision Home Assistant Entities" width="400">
</p>

Native [HACS integration](https://github.com/jasondostal/tunnelvision-ha). 30 entities, real-time SSE updates, config flow, zero YAML.

**Install via HACS:**
1. HACS → Integrations → Three dots → **Custom Repositories**
2. Paste `https://github.com/jasondostal/tunnelvision-ha` → category **Integration** → **Add**
3. Search **TunnelVision** → **Download** → Restart HA
4. **Settings → Integrations → Add → TunnelVision** — enter your host and port

You get:
- **16 sensors** — VPN state, public IP, location, speeds, transfer stats, torrent counts, provider, forwarded port, DNS/HTTP proxy/SOCKS proxy state
- **7 binary sensors** — VPN connected, killswitch active, healthy, qBittorrent running, DNS, HTTP proxy, SOCKS proxy
- **5 buttons** — Restart VPN, rotate server, restart qBit, pause/resume torrents
- **2 switches** — VPN on/off, Killswitch on/off (reflect actual state)
- **3 services** — `tunnelvision.vpn`, `tunnelvision.qbittorrent`, `tunnelvision.killswitch` for automations

No MQTT required. Real-time updates via Server-Sent Events (SSE) with polling fallback — state changes appear in HA within seconds, not minutes.

### Prometheus + Grafana

```bash
curl http://localhost:8081/metrics
```

Exports `tunnelvision_vpn_up`, `tunnelvision_killswitch_active`, `tunnelvision_transfer_rx_bytes_total`, `tunnelvision_transfer_tx_bytes_total`, `tunnelvision_vpn_connected_seconds`, and more. Scrape it, graph it, alert on it.

A ready-made Grafana dashboard is included at [`examples/grafana-dashboard.json`](examples/grafana-dashboard.json) — import it and point at your Prometheus data source.

### Sonarr / Radarr / Prowlarr

Use `tunnelvision` (or your container name) as the download client host in your arr stack:
- **Host**: `tunnelvision` (Docker DNS) or your server IP
- **Port**: `8080`
- **Username**: `admin`
- **Password**: your qBittorrent password

All torrent traffic routes through the VPN. The killswitch ensures nothing leaks if the tunnel drops.

### Notifications

Webhook notifications for VPN state changes — reconnects, failures, port forwarding updates. Supports Discord, Slack, Gotify, and generic webhooks out of the box.

| Variable | What it does |
|----------|-------------|
| `NOTIFY_WEBHOOK_URL` | Discord/Slack webhook URL, or any generic endpoint |
| `NOTIFY_GOTIFY_URL` | Gotify server URL |
| `NOTIFY_GOTIFY_TOKEN` | Gotify app token |

## Authentication

Off by default. Three layers, all optional, all additive:

| Method | Env Vars | How it works |
|--------|----------|-------------|
| **None** (default) | *(nothing set)* | Everything open |
| **API key** | `API_KEY` | `X-API-Key` header for programmatic access (Homepage, HACS, Prometheus) |
| **Local login** | `ADMIN_USER` + `ADMIN_PASS` | Login form in the dashboard, session cookie |
| **Proxy bypass** | `AUTH_PROXY_HEADER` + `TRUSTED_PROXY_IPS` | Trusted header from your reverse proxy — skips the login form for already-authenticated users |

### Reverse proxy SSO (Authentik, Authelia, Traefik, nginx)

When your reverse proxy authenticates users and forwards a header like `Remote-User`, TunnelVision can trust it and skip the login form:

```yaml
environment:
  - AUTH_PROXY_HEADER=Remote-User          # header your proxy sends
  - TRUSTED_PROXY_IPS=172.20.0.2          # your Traefik/proxy container IP or CIDR
  - ADMIN_USER=admin                       # still required for login_required mode
  - ADMIN_PASS=changeme
```

**`TRUSTED_PROXY_IPS` is required for secure deployments.** Without it, any client on an allowed network can forge the `Remote-User` header and bypass authentication — because HTTP headers are trivially spoofable. `TRUSTED_PROXY_IPS` restricts which source IPs can set the proxy header; requests from any other IP have the header ignored.

If `AUTH_PROXY_HEADER` is set without `TRUSTED_PROXY_IPS`, TunnelVision logs a startup warning and surfaces it in `GET /api/v1/health` under `security_warnings`. The feature still works (backward compatible), but the security model is weaker than intended.

To find your proxy's container IP: `docker inspect <traefik-container> | grep IPAddress`

API key always works for machine-to-machine regardless of login configuration.

## Docker Secrets

Any secret field supports file-based injection via `_SECRETFILE` suffix. This works with Docker secrets, Kubernetes secrets, or any file-mounted secret:

```yaml
services:
  tunnelvision:
    secrets:
      - admin_pass
      - api_key
    environment:
      - ADMIN_PASS_SECRETFILE=/run/secrets/admin_pass
      - API_KEY_SECRETFILE=/run/secrets/api_key

secrets:
  admin_pass:
    file: ./secrets/admin_pass.txt
  api_key:
    file: ./secrets/api_key.txt
```

Precedence: YAML settings > secret file > env var > default.

## Settings

Configurable from the dashboard UI (gear icon) or by editing `/config/tunnelvision.yml` directly. Settings in the YAML file override environment variables.

```yaml
# /config/tunnelvision.yml
admin_user: admin
admin_pass: changeme
auth_proxy_header: Remote-User
vpn_provider: custom
health_check_interval: "15"
```

## Configuration

<details>
<summary>Environment variables</summary>

All via environment variables. Sensible defaults for everything. Settings UI and `/config/tunnelvision.yml` override these.

| Variable | Default | What it does |
|----------|---------|-------------|
| `ADMIN_USER` | *(empty)* | Set to enable login (single user) |
| `ADMIN_PASS` | *(empty)* | Password for ADMIN_USER |
| `AUTH_PROXY_HEADER` | *(empty)* | Trusted header from reverse proxy (e.g. `Remote-User`) |
| `TRUSTED_PROXY_IPS` | *(empty)* | IPs or CIDRs of your reverse proxy — required with `AUTH_PROXY_HEADER` for secure deployments (e.g. `172.20.0.2` or `172.20.0.0/16`) |
| `VPN_ENABLED` | `true` | Enable/disable VPN |
| `VPN_TYPE` | `auto` | VPN engine: `auto`, `wireguard`, or `openvpn` |
| `VPN_PROVIDER` | `custom` | VPN provider: `custom`, `mullvad`, `ivpn`, `pia`, `proton`, `gluetun` (sidecar mode), or any of the 25 native providers |
| `MULLVAD_ACCOUNT` | *(empty)* | Mullvad account number (16-digit) |
| `PIA_USER` | *(empty)* | PIA username |
| `PIA_PASS` | *(empty)* | PIA password |
| `WIREGUARD_PRIVATE_KEY` | *(empty)* | WireGuard private key for Mullvad/IVPN/Proton (base64, 44 chars) |
| `WIREGUARD_ADDRESSES` | *(empty)* | WireGuard interface address (e.g. `10.66.0.1/32`) |
| `VPN_DNS` | *(from config)* | Override DNS server (default: provider DNS or `10.64.0.1`) |
| `VPN_COUNTRY` | *(empty)* | Filter server rotation by country (e.g. `ch`, `us`) |
| `VPN_CITY` | *(empty)* | Filter server rotation by city (e.g. `zurich`) |
| `KILLSWITCH_ENABLED` | `true` | Enable nftables killswitch |
| `WG_USERSPACE` | `auto` | WireGuard engine: `auto` (detect kernel support), `kernel`, or `userspace` (wireguard-go, for LXC/NAS) |
| `WEBUI_PORT` | `8080` | qBittorrent WebUI port |
| `API_PORT` | `8081` | TunnelVision API port |
| `API_KEY` | *(empty)* | Set to require `X-API-Key` header on API calls |
| `UI_ENABLED` | `true` | Serve the web dashboard |
| `WEBUI_ALLOWED_NETWORKS` | `192.168.0.0/16,...` | Networks allowed to access WebUI and API |
| `MQTT_ENABLED` | `false` | Enable MQTT with Home Assistant auto-discovery |
| `MQTT_BROKER` | *(empty)* | MQTT broker hostname/IP |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USER` / `MQTT_PASS` | *(empty)* | MQTT authentication |
| `GLUETUN_URL` | `http://gluetun:8000` | Gluetun API URL (sidecar mode) |
| `GLUETUN_API_KEY` | *(empty)* | Gluetun API key (if auth is enabled) |
| `AUTO_RECONNECT` | `true` | Auto-reconnect VPN on failure (watchdog) |
| `NOTIFY_WEBHOOK_URL` | *(empty)* | Discord/Slack/generic webhook for notifications |
| `NOTIFY_GOTIFY_URL` | *(empty)* | Gotify server URL |
| `NOTIFY_GOTIFY_TOKEN` | *(empty)* | Gotify app token |
| `PORT_FORWARD_ENABLED` | `false` | Enable port forwarding (PIA, ProtonVPN) |
| `PORT_FORWARD_HOOK` | *(empty)* | Script/command called with the assigned port number on each port change; called with `0` on release |
| `PROTON_USER` | *(empty)* | ProtonVPN username (OpenVPN/IKEv2 credentials) |
| `PROTON_PASS` | *(empty)* | ProtonVPN password |
| `FIREWALL_VPN_INPUT_PORTS` | *(empty)* | Comma-separated ports to accept on VPN interface |
| `FIREWALL_OUTBOUND_SUBNETS` | *(empty)* | CIDRs that bypass VPN (e.g. `192.168.1.0/24`) |
| `FIREWALL_CUSTOM_RULES_FILE` | *(empty)* | Path to custom nftables rules file |
| `DNS_ENABLED` | `false` | Enable built-in DNS (DoT, caching, blocking) |
| `DNS_UPSTREAM` | `1.1.1.1,1.0.0.1` | Upstream DNS servers |
| `DNS_DOT_ENABLED` | `true` | Use DNS-over-TLS for upstream queries |
| `DNS_BLOCK_ADS` | `false` | Block ads via StevenBlack/hosts blocklist |
| `DNS_BLOCK_MALWARE` | `false` | Block malware domains via URLhaus |
| `DNS_BLOCK_SURVEILLANCE` | `false` | Block surveillance domains |
| `HTTP_PROXY_ENABLED` | `false` | Enable HTTP CONNECT proxy |
| `HTTP_PROXY_PORT` | `8888` | HTTP proxy listen port |
| `SOCKS_PROXY_ENABLED` | `false` | Enable SOCKS5 proxy |
| `SOCKS_PROXY_PORT` | `1080` | SOCKS5 proxy listen port |
| `SHADOWSOCKS_ENABLED` | `false` | Enable Shadowsocks AEAD proxy |
| `SHADOWSOCKS_PORT` | `8388` | Shadowsocks proxy listen port |
| `SHADOWSOCKS_PASSWORD` | *(empty)* | Shadowsocks password (required when enabled) |
| `SHADOWSOCKS_CIPHER` | `aes-256-gcm` | Shadowsocks cipher (`aes-256-gcm` or `chacha20-ietf-poly1305`) |
| `PUID` | `1000` | User ID for file permissions |
| `PGID` | `1000` | Group ID for file permissions |
| `TZ` | `America/Chicago` | Container timezone |
| `HEALTH_CHECK_INTERVAL` | `15` | Seconds between health checks |
| `SERVER_LIST_AUTO_UPDATE` | `true` | Automatically refresh provider server lists in the background |
| `SERVER_LIST_UPDATE_INTERVAL` | `3600` | Seconds between server list refreshes |

</details>

<details>
<summary>Docker requirements</summary>

```yaml
cap_add:
  - NET_ADMIN          # Required for WireGuard and nftables
devices:
  - /dev/net/tun       # Required for WireGuard tunnel
sysctls:
  - net.ipv4.conf.all.src_valid_mark=1    # WireGuard routing
  - net.ipv6.conf.all.disable_ipv6=1      # IPv6 leak prevention
```

| Volume | Purpose |
|--------|---------|
| `/config` | qBittorrent config, runtime state |
| `/config/wireguard` | WireGuard config files (`wg0.conf`) |
| `/downloads` | Torrent download directory |

</details>

<details>
<summary>API endpoints</summary>

Interactive docs at `http://localhost:8081/api/docs` (Swagger) when running.

| Endpoint | What it returns |
|----------|----------------|
| `GET /api/v1/health` | Container health — VPN, killswitch, qBittorrent, watchdog, uptime |
| `GET /api/v1/vpn/status` | Full VPN status — IP, location, uptime, transfer stats |
| `GET /api/v1/vpn/ip` | Just the public IP |
| `GET /api/v1/vpn/check` | Provider-verified connection check |
| `GET /api/v1/vpn/configs` | Available VPN config files and active config |
| `GET /api/v1/qbt/status` | Speeds, torrent counts, version |
| `GET /api/v1/system` | Container versions and uptime |
| `GET /api/v1/config` | Current configuration (no secrets) |
| `GET /api/v1/settings` | Persistent settings (secrets masked) |
| `GET /api/v1/history` | Connection history — rotations, reconnects, watchdog events |
| `GET /api/v1/events` | SSE stream — real-time state changes |
| `GET /api/v1/speedtest` | Run a VPN speed test |
| `GET /metrics` | Prometheus metrics |
| `POST /api/v1/vpn/connect` | Connect to a specific server |
| `POST /api/v1/vpn/restart` | Restart VPN tunnel |
| `POST /api/v1/vpn/rotate` | Rotate to a new server |
| `POST /api/v1/vpn/disconnect` | Disconnect VPN |
| `POST /api/v1/killswitch/enable` | Enable killswitch |
| `POST /api/v1/killswitch/disable` | Disable killswitch |
| `POST /api/v1/qbt/restart` | Restart qBittorrent |
| `POST /api/v1/qbt/pause` | Pause all torrents |
| `POST /api/v1/qbt/resume` | Resume all torrents |
| `POST /api/v1/setup/credentials` | Validate and save provider-specific credentials |
| `POST /api/v1/setup/server` | Select a server during setup (generates WireGuard config) |
| `GET /api/v1/backup` | Export config backup (JSON) |
| `POST /api/v1/backup/restore` | Restore from backup |

</details>

<details>
<summary>Migrating from other setups</summary>

**From a separate VPN container + qBittorrent:** Copy your qBittorrent config and WireGuard/OpenVPN config, point the volumes, done. TunnelVision manages the tunnel, the killswitch, and qBittorrent in a single container.

**Not ready for a full switch?** TunnelVision can run in **sidecar mode** alongside your existing gluetun container — it adds the dashboard, API, Home Assistant integration, and Prometheus metrics without touching your tunnel. Set `VPN_PROVIDER=gluetun` and point `GLUETUN_URL` at your existing container's API.

In sidecar mode, TunnelVision is read-only: it monitors your VPN's state and surfaces it everywhere (HA, Prometheus, dashboard, webhooks), but gluetun remains in charge of the tunnel and reconnection. It's an evaluation lane — run them side-by-side with zero risk while you decide if you want to go fully native.

**When you're ready to go native** (TunnelVision manages the tunnel directly):

1. Make sure your provider is on the [native provider list](#native-providers). If not, use `VPN_PROVIDER=custom` with your own config file.
2. Add the required Docker capabilities to your TunnelVision service:
   ```yaml
   cap_add:
     - NET_ADMIN
   devices:
     - /dev/net/tun
   sysctls:
     - net.ipv4.conf.all.src_valid_mark=1
     - net.ipv6.conf.all.disable_ipv6=1
   ```
3. Set `VPN_PROVIDER` to your provider (e.g. `mullvad`, `pia`, `custom`) and configure credentials.
4. Remove gluetun from your stack (or keep it running other containers — TunnelVision is now independent).
5. Restart. TunnelVision takes over the tunnel, killswitch, auto-reconnect, and rotation.

**From Trigus42/qbittorrentvpn:** Same config structure — mount `/config` and `/config/wireguard` the same way.

**From transmission-openvpn:** You'll need to switch to qBittorrent. The VPN config carries over if it's WireGuard or OpenVPN.

</details>

<details>
<summary>Architecture</summary>

```
┌──────────────────────────────────────────────────────────┐
│  TunnelVision Container                                  │
│                                                          │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  WireGuard/OVPN  │  │ qBittorrent  │  │ FastAPI    │  │
│  │  + nftables      │  │   -nox       │  │ REST API   │  │
│  │  killswitch      │  │              │  │ + React UI │  │
│  └────────┬─────────┘  └──────┬───────┘  └─────┬──────┘  │
│           │                   │                 │         │
│           │    s6-overlay (process supervision)  │         │
│           └───────────────────┼─────────────────┘         │
│                               │                           │
│  init-environment ──► init-vpn ──► init-killswitch        │
│           │                                     │         │
│           └──► svc-qbittorrent    svc-api    svc-health   │
│                                                           │
│  Alpine Linux 3.21                                        │
└──────────────────────────────────────────────────────────┘
         │              │              │
    :8080 (WebUI)  :8081 (API)    wg0 (tunnel)
```

</details>

<details>
<summary>Building from source</summary>

```bash
git clone https://github.com/jasondostal/tunnelvision.git
cd tunnelvision
make build    # Build the Docker image
make dev      # Start development environment
```

</details>

## Supply Chain Security

Every image pushed to GHCR is signed with [cosign](https://docs.sigstore.dev/cosign/overview/) (Sigstore keyless). Verify before you pull:

```bash
cosign verify ghcr.io/jasondostal/tunnelvision:latest \
  --certificate-oidc-issuer=https://token.actions.githubusercontent.com \
  --certificate-identity-regexp=github.com/jasondostal/tunnelvision
```

The CI pipeline runs 8 static analysis tools, 734 tests, and a Trivy container scan on every push. Nothing ships unless everything passes.

## License

[GPL-3.0](LICENSE)
