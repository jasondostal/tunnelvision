# Changelog

## v1.2.0 — Full Stack (2026-03-03)

Everything from the roadmap, in one push.

### Auto-Reconnect Watchdog
- Health monitor detects sustained VPN failure (3 consecutive checks, ~90s)
- Automatically attempts `wg-quick up wg0` to restore the tunnel
- Configurable via `AUTO_RECONNECT=true` (default on)

### Notification Webhooks
- Discord, Slack, Gotify, and generic webhook support
- Fires on VPN disconnect, reconnect, port forwarding changes
- Set `NOTIFY_WEBHOOK_URL` for Discord/Slack/generic, `NOTIFY_GOTIFY_URL` + `NOTIFY_GOTIFY_TOKEN` for Gotify

### Speed Test
- `POST /api/v1/vpn/speedtest` — downloads 10MB from Cloudflare CDN, measures tunnel throughput
- Returns download_mbps, bytes, duration

### Config Backup/Restore
- `GET /api/v1/backup` — downloads tar.gz of tunnelvision.yml, qBittorrent.conf, and VPN configs
- `POST /api/v1/restore` — uploads backup archive, restores config (restart required)

### Connection History
- `GET /api/v1/vpn/history` — tracks server rotations, disconnects, reconnects
- Persists to `/config/connection-history.json` (survives container restarts)

### Grafana Dashboard Template
- Pre-built JSON at `examples/grafana-dashboard.json`
- VPN status, killswitch, uptime, transfer rates, total bytes, health — all wired to Prometheus metrics

### One-Liner Install Script
- `curl -fsSL https://raw.githubusercontent.com/jasondostal/tunnelvision/main/scripts/install.sh | bash`
- Creates directory, downloads docker-compose.yml, prompts for WireGuard config

### Settings Panel Updates
- PIA credentials (pia_user, pia_pass, port_forward_enabled)
- Auto-reconnect toggle
- Notification webhook configuration (Discord, Slack, Gotify)

---

## v1.1.0 — Provider Enrichment (2026-03-03)

Three deep provider integrations. Progressive enrichment — set your provider, features light up.

### IVPN Provider
- Public server list with WireGuard public keys (`api.ivpn.net/v5/servers.json`)
- Connection verification via `api.ivpn.net/v4/geo-lookup` (confirms IVPN exit IP)
- Auto-generate wg0.conf from server list — no manual config needed
- Server rotation by country/city
- Same pattern as Mullvad — set `VPN_PROVIDER=ivpn` + `WIREGUARD_PRIVATE_KEY` + `WIREGUARD_ADDRESSES`

### PIA (Private Internet Access) Provider
- Token-based auth with `PIA_USER` + `PIA_PASS` — no WireGuard private key needed
- Ephemeral key negotiation — generates fresh WireGuard keypair per connection
- Server list from `serverlist.piaservers.net` with port-forward capability flags
- **Port forwarding** — set `PORT_FORWARD_ENABLED=true`, TunnelVision gets a port assignment and keeps it alive (15-min refresh). Port visible in API (`forwarded_port` field) and state file.
- Prefers port-forward-capable servers when port forwarding is enabled

### Other
- `forwarded_port` field added to `/api/v1/vpn/status`
- Setup wizard updated with IVPN and PIA provider descriptions
- Provider count: custom + Mullvad + IVPN + PIA (4 total)

---

## v1.0.0 — Initial Release (2026-03-03)

Everything. The whole thing. One container, full visibility.

### Container
- Alpine 3.21 base with s6-overlay v3 process supervision
- WireGuard + OpenVPN dual-engine VPN (auto-detect from config)
- nftables killswitch — blocks all non-tunnel traffic, IPv6 disabled
- DNS resolution through tunnel (postrouting hook)
- qBittorrent-nox with localhost auth bypass for internal API access

### API (22+ endpoints)
- Health, VPN status, qBittorrent status, system info, config
- VPN control: restart, disconnect, reconnect, rotate server
- Killswitch control: enable, disable
- qBittorrent control: restart, pause, resume all torrents
- Provider abstraction: generic (any WireGuard) + Mullvad (server list, account, connection check)
- Server rotation by country/city
- Setup wizard API for guided first-run
- Settings API with persistent YAML config (`/config/tunnelvision.yml`)
- Prometheus metrics endpoint (`/metrics`)

### Dashboard
- React 19 + Vite + Tailwind v4 dark-first UI
- VPN status hero with location, IP, transfer stats, action buttons
- Health card, qBittorrent card, system info
- Setup wizard (5-step guided onboarding)
- Settings panel (gear icon) — configures auth, VPN, MQTT, general settings
- Login screen with session auth

### Authentication
- Optional single-user local login (`ADMIN_USER` + `ADMIN_PASS`)
- Reverse proxy header bypass (`AUTH_PROXY_HEADER`) — works with Authentik, Authelia, Traefik, nginx
- API key for programmatic access (`API_KEY` + `X-API-Key` header)
- All three layers stack, all optional

### Integrations
- Home Assistant MQTT auto-discovery (sensors, binary sensors, buttons, switch)
- Homepage customapi widget with configurable field selection
- Prometheus metrics for Grafana dashboards
- Sonarr/Radarr/Prowlarr compatible (standard qBittorrent download client)

### Deployment
- Multi-arch Docker images (amd64 + arm64)
- GitHub Actions CI/CD
- `docker compose up` — one command
