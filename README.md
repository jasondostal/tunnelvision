<p align="center">
  <img src="images/tunnelvision-readme-banner.png" alt="TunnelVision" width="800">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/jasondostal/tunnelvision?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/Alpine-3.21-0D597F?style=flat-square&logo=alpine-linux" alt="Alpine">
  <img src="https://img.shields.io/badge/WireGuard-built--in-88171A?style=flat-square&logo=wireguard" alt="WireGuard">
  <img src="https://img.shields.io/badge/qBittorrent-built--in-2F67BA?style=flat-square" alt="qBittorrent">
  <img src="https://img.shields.io/badge/Home%20Assistant-native-41BDF5?style=flat-square&logo=home-assistant" alt="Home Assistant">
</p>

---

qBittorrent + WireGuard VPN + killswitch + REST API + dashboard. One container. Full visibility.

Drop your WireGuard config, `docker compose up`, and you can see everything — what IP you're on, where you're exiting, transfer stats, killswitch state, qBittorrent health. From your Homepage dashboard, from Home Assistant, from Prometheus, from the built-in UI, from `curl`. No guessing. No SSH-ing in.

Works with **any WireGuard provider**. Mullvad, IVPN, Proton, AirVPN, PIA, or your own server.

## Quick Start

```bash
mkdir -p tunnelvision/wireguard
cp /path/to/wg0.conf tunnelvision/wireguard/

curl -O https://raw.githubusercontent.com/jasondostal/tunnelvision/main/docker-compose.yml
docker compose up -d
```

Three things are now running inside one container:
- **qBittorrent WebUI** on port `8080`
- **TunnelVision API + Dashboard** on port `8081`
- **WireGuard VPN** with nftables killswitch

```bash
curl http://localhost:8081/api/v1/health | jq .
```

## Integrations

### Homepage

Drops right into [Homepage](https://gethomepage.dev) using the `customapi` widget. Pick the fields you want to see:

```yaml
- TunnelVision:
    icon: /icons/tunnelvision.png   # or mdi-vpn
    href: http://your-host:8081
    description: VPN + qBittorrent
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

Native HACS integration. 25 entities, config flow, zero YAML.

1. Copy [`custom_components/tunnelvision`](https://github.com/jasondostal/tunnelvision-ha) to your HA `custom_components/` directory
2. Restart Home Assistant
3. **Settings > Integrations > Add > TunnelVision** — enter your host and port

You get:
- **12 sensors** — VPN state, public IP, location, speeds, transfer stats, torrent counts, provider
- **4 binary sensors** — VPN connected, killswitch active, healthy, qBittorrent running
- **9 buttons** — Restart VPN, rotate server, disconnect, reconnect, restart qBit, pause/resume torrents, enable/disable killswitch
- **3 services** — `tunnelvision.vpn`, `tunnelvision.qbittorrent`, `tunnelvision.killswitch` for automations

No MQTT required. Direct API polling every 15 seconds.

### Prometheus + Grafana

```bash
curl http://localhost:8081/metrics
```

Exports `tunnelvision_vpn_up`, `tunnelvision_killswitch_active`, `tunnelvision_transfer_rx_bytes_total`, `tunnelvision_transfer_tx_bytes_total`, `tunnelvision_vpn_connected_seconds`, and more. Scrape it, graph it, alert on it.

### Sonarr / Radarr / Prowlarr

Use `tunnelvision` (or your container name) as the download client host in your arr stack:
- **Host**: `tunnelvision` (Docker DNS) or your server IP
- **Port**: `8080`
- **Username**: `admin`
- **Password**: your qBittorrent password

All torrent traffic routes through the VPN. The killswitch ensures nothing leaks if the tunnel drops.

## Authentication

Off by default. Three layers, all optional, all additive:

| Method | Env Vars | How it works |
|--------|----------|-------------|
| **None** (default) | *(nothing set)* | Everything open |
| **API key** | `API_KEY` | `X-API-Key` header for programmatic access (Homepage, HACS, Prometheus) |
| **Local login** | `ADMIN_USER` + `ADMIN_PASS` | Login form in the dashboard, session cookie |
| **Proxy bypass** | `AUTH_PROXY_HEADER` | Trusted header from your reverse proxy (Authentik, Authelia, Traefik, nginx) — skips the login form |

Set `AUTH_PROXY_HEADER=Remote-User` (or `X-Forwarded-User`, whatever your proxy sends) and users authenticated by your reverse proxy get straight through. Direct users see the login form. API key always works for machine-to-machine.

## Settings

Configurable from the dashboard UI (gear icon) or by editing `/config/tunnelvision.yml` directly. Settings in the YAML file override environment variables.

```yaml
# /config/tunnelvision.yml
admin_user: admin
admin_pass: changeme
auth_proxy_header: Remote-User
vpn_provider: custom
health_check_interval: "30"
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
| `VPN_ENABLED` | `true` | Enable/disable VPN |
| `VPN_TYPE` | `auto` | VPN engine: `auto`, `wireguard`, or `openvpn` |
| `VPN_PROVIDER` | `custom` | VPN provider: `custom` or `mullvad` |
| `VPN_DNS` | *(from config)* | Override DNS server (default: provider DNS or `10.64.0.1`) |
| `VPN_COUNTRY` | *(empty)* | Filter server rotation by country (e.g. `ch`, `us`) |
| `VPN_CITY` | *(empty)* | Filter server rotation by city (e.g. `zurich`) |
| `KILLSWITCH_ENABLED` | `true` | Enable nftables killswitch |
| `WEBUI_PORT` | `8080` | qBittorrent WebUI port |
| `API_PORT` | `8081` | TunnelVision API port |
| `API_KEY` | *(empty)* | Set to require `X-API-Key` header on API calls |
| `UI_ENABLED` | `true` | Serve the web dashboard |
| `WEBUI_ALLOWED_NETWORKS` | `192.168.0.0/16,...` | Networks allowed to access WebUI and API |
| `MQTT_ENABLED` | `false` | Enable MQTT with Home Assistant auto-discovery |
| `MQTT_BROKER` | *(empty)* | MQTT broker hostname/IP |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USER` / `MQTT_PASS` | *(empty)* | MQTT authentication |
| `PUID` | `1000` | User ID for file permissions |
| `PGID` | `1000` | Group ID for file permissions |
| `TZ` | `America/Chicago` | Container timezone |
| `HEALTH_CHECK_INTERVAL` | `30` | Seconds between health checks |

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
| `GET /api/v1/health` | Container health — VPN, killswitch, qBittorrent, uptime |
| `GET /api/v1/vpn/status` | Full VPN status — IP, location, uptime, transfer stats |
| `GET /api/v1/vpn/ip` | Just the public IP |
| `GET /api/v1/vpn/check` | Provider-verified connection check |
| `GET /api/v1/qbt/status` | Speeds, torrent counts, version |
| `GET /api/v1/system` | Container versions and uptime |
| `GET /api/v1/config` | Current configuration (no secrets) |
| `GET /metrics` | Prometheus metrics |
| `POST /api/v1/vpn/restart` | Restart VPN tunnel |
| `POST /api/v1/vpn/rotate` | Rotate to a new server |
| `POST /api/v1/vpn/disconnect` | Disconnect VPN |
| `POST /api/v1/killswitch/enable` | Enable killswitch |
| `POST /api/v1/killswitch/disable` | Disable killswitch |
| `POST /api/v1/qbt/restart` | Restart qBittorrent |
| `POST /api/v1/qbt/pause` | Pause all torrents |
| `POST /api/v1/qbt/resume` | Resume all torrents |

</details>

<details>
<summary>Migrating from other setups</summary>

**From gluetun + qBittorrent:** Copy your qBittorrent config directory and your WireGuard config. Point the volumes. Done.

**From Trigus42/qbittorrentvpn:** Same config structure — mount `/config` and `/config/wireguard` the same way.

**From transmission-openvpn:** You'll need to switch to qBittorrent. The VPN config carries over if it's WireGuard.

</details>

<details>
<summary>Architecture</summary>

```
┌──────────────────────────────────────────────────────────┐
│  TunnelVision Container                                  │
│                                                          │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │  WireGuard VPN   │  │ qBittorrent  │  │ FastAPI    │  │
│  │  + nftables      │  │   -nox       │  │ REST API   │  │
│  │  killswitch      │  │              │  │ + React UI │  │
│  └────────┬─────────┘  └──────┬───────┘  └─────┬──────┘  │
│           │                   │                 │         │
│           │    s6-overlay (process supervision)  │         │
│           └───────────────────┼─────────────────┘         │
│                               │                           │
│  init-environment ──► init-wireguard ──► init-killswitch  │
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

## License

[MIT](LICENSE)
