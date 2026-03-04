# Changelog

## v2.7.0 — Infrastructure Hardening (2026-03-04)

Security, resilience, and observability upgrades across the boot chain, VPN engine, port forwarding, and server management layers.

### Firewall-First Boot
- Pre-VPN firewall phase (`init-firewall-pre`) runs before the WireGuard tunnel comes up, eliminating the startup leak window
- Parses the VPN endpoint from the active config (WireGuard or OpenVPN), resolves hostnames, and locks down all traffic to that endpoint + loopback + LAN API before any packets flow
- Setup mode (no config yet) skips gracefully — the lock applies only when a config is present
- Boot chain: `init-environment → init-firewall-pre → init-wireguard → init-killswitch`

### Userspace WireGuard Fallback
- `WG_USERSPACE=auto|kernel|userspace` — automatic detection of kernel WireGuard support at startup
- In `auto` mode (default): probes for the `wireguard` kernel module and falls back to `wireguard-go` if unavailable
- Works in LXC containers, NAS devices, and any environment without kernel module access
- `WG_USERSPACE=kernel` forces kernel mode and logs an error if unavailable; `WG_USERSPACE=userspace` forces wireguard-go unconditionally
- Implementation written to state file (`/var/run/tunnelvision/wg_implementation`) for observability

### Port Forward Hooks
- `PORT_FORWARD_HOOK` — path to a script or command called with the assigned port number on every port change
- Called with `0` when the port is released (tunnel teardown, rotation, stop)
- Fires from both the WireGuard port forward service (PIA) and the NAT-PMP service (ProtonVPN)
- Non-blocking, failure-tolerant: hook errors are logged but never propagate to the VPN lifecycle
- Enables external automation: update qBittorrent, update *arr configs, ping a webhook, anything

### Server List Auto-Updater
- Background service refreshes provider server caches on a configurable interval
- `SERVER_LIST_AUTO_UPDATE=true` (default) / `SERVER_LIST_UPDATE_INTERVAL=<seconds>` (default: `PROVIDER_CACHE_TTL`)
- Only refreshes providers with active instances — no wasted API calls for providers you're not using
- Starts and stops cleanly with the application lifecycle

### Richer Server Filters
- `ServerFilter` dataclass replaces loose `country/city` kwargs across the provider layer
- New filter dimensions: `owned_only`, `p2p`, `streaming`, `port_forward`, `secure_core`, `multihop`, `max_load`
- Filters compose with AND logic — combine any number of dimensions
- `GET /api/v1/vpn/servers` exposes all filter dimensions as query params
- `POST /api/v1/vpn/connect` accepts filter fields in the request body
- Response expanded: `city_code`, `load`, `port_forward`, `p2p`, `streaming`, `secure_core`, `multihop`

### Tests
- 65 new tests covering pre-VPN firewall script parsing, userspace WireGuard detection, port forward hook execution, server filter logic, auto-updater settings and lifecycle
- 319 total tests (up from 254)

---

## v2.6.0 — Provider Framework Refactor (2026-03-04)

The foundation for scaling from 6 to 23+ native providers. Zero new user-facing features — all internal architecture. Every provider is now a single file, auto-discovered, auto-configured, and auto-tested.

### Provider Metadata Protocol
- `ProviderMeta` dataclass — single source of truth for each provider's identity, capabilities, setup type, and credential schema
- `CredentialField` dataclass — declarative credential definitions (key, label, type, secret flag, env var mapping, hints)
- Setup wizard, settings UI, and config system all read from provider metadata — no hardcoded field lists

### Unified Connect Pipeline
- Four near-identical `_connect_{mullvad,ivpn,pia,proton}` functions (320 lines) replaced by one generic `_connect_provider()` (60 lines)
- Pipeline: list servers → filter → pick server → `resolve_connect()` → write wg0.conf → reconnect → `post_connect()`
- `PeerConfig` dataclass — everything needed to write wg0.conf, returned by each provider's `resolve_connect()`
- Providers override `resolve_connect()` for custom auth (PIA key exchange) and `post_connect()` for hooks (port forwarding)
- `connect.py` reduced from 568 to 308 lines

### Shared Server Infrastructure
- Typed `ServerInfo` fields (`ipv4`, `public_key`, `port`, `port_forward`, `streaming`, `p2p`, `multihop`, `secure_core`, `tier`, `load`, `extra`) replace dynamic attribute hacking
- Server caching moved to base class with configurable TTL — providers override `_fetch_servers()`, not `list_servers()`
- Server filtering (`_filter_servers()`) deduplicated from 4 provider copies into one base class method
- Default `get_server_info()` searches by ipv4 match — providers only override if they need custom logic

### Self-Registering Provider Discovery
- `pkgutil`-based auto-discovery replaces hardcoded `PROVIDERS` dict
- Drop a file in `api/services/providers/`, it's registered everywhere — setup wizard, config, settings, connect pipeline
- `get_all_provider_meta()` generates setup wizard JSON from live provider metadata

### Metadata-Driven Config System
- `Config.__getattr__` dynamically resolves provider credentials from env vars and secret files — new providers don't need Config dataclass edits
- `get_all_configurable_fields()` merges base settings with provider credential fields — new providers are automatically configurable via settings UI
- `SettingsUpdate` accepts dynamic provider fields via Pydantic `extra="allow"`
- Backwards compatible — existing env vars, YAML settings, and Docker secrets continue to work unchanged

### Tests
- 94 new parametrized provider tests covering metadata completeness, interface compliance, API metadata, ServerInfo/PeerConfig integrity
- Cross-provider assertions: every provider gets the same validation (meta.id matches name, credentials use correct field types, secret fields use password type, filter capabilities are valid)
- DRY guardrails: `get_all_configurable_fields()` superset check, dynamic Config credential resolution, SettingsUpdate extra field acceptance
- 254 total tests (up from 157)

### Adding a New Provider
After this release, adding a provider is a single-file operation:
1. Create `api/services/providers/<name>.py`
2. Implement `name`, `meta`, `check_connection()`, `_fetch_servers()`
3. Optionally override `resolve_connect()` / `post_connect()` for custom auth
4. Auto-discovered, auto-configured, auto-tested — no other files need editing

---

## v2.5.0 — DNS, Proxies, ProtonVPN & DRY Refactor (2026-03-04)

### Docker Secrets Support
- Every `secret: true` field gains `_SECRETFILE` env var support (e.g. `ADMIN_PASS_SECRETFILE=/run/secrets/admin_pass`)
- 4-layer precedence: YAML > secret file > env var > default
- Works with Docker secrets, Kubernetes secrets, or any file-based secret injection
- 7 existing secret fields upgraded: `ADMIN_PASS`, `API_KEY`, `GLUETUN_API_KEY`, `PIA_PASS`, `WIREGUARD_PRIVATE_KEY`, `MQTT_PASS`, `NOTIFY_GOTIFY_TOKEN`

### Firewall Granularity
- `FIREWALL_VPN_INPUT_PORTS` — comma-separated ports to accept on VPN interface (TCP+UDP)
- `FIREWALL_OUTBOUND_SUBNETS` — CIDRs that bypass VPN (routed via host gateway)
- `FIREWALL_CUSTOM_RULES_FILE` — path to custom nftables rules file (loaded after base killswitch)
- Killswitch auto-opens ports for DNS, HTTP proxy, SOCKS proxy when those services are enabled

### Built-in DNS Service
- DNS-over-TLS (DoT) upstream resolution via dnspython
- Response caching with TTL awareness (LRU, configurable)
- Ad-blocking via StevenBlack/hosts blocklist
- Malware blocking via URLhaus blocklist
- Surveillance blocking via WindowsSpyBlocker blocklist
- Custom blocklist URL support
- Runs as s6 longrun service (survives API crashes)
- Hot-reloadable blocklist settings (toggle ad/malware/surveillance blocking without restart)
- Prometheus metrics: `tunnelvision_dns_queries_total`, `tunnelvision_dns_cache_hits_total`, `tunnelvision_dns_blocked_total`
- 8 new settings: `DNS_ENABLED`, `DNS_UPSTREAM`, `DNS_DOT_ENABLED`, `DNS_CACHE_ENABLED`, `DNS_BLOCK_ADS`, `DNS_BLOCK_MALWARE`, `DNS_BLOCK_SURVEILLANCE`, `DNS_CUSTOM_BLOCKLIST_URL`

### ProtonVPN Provider
- Native ProtonVPN integration with server list from `api.protonvpn.ch`
- Server filtering by country/city with port-forward capability flags
- NAT-PMP port forwarding (RFC 6886) — raw UDP, no library needed
- 45-second keep-alive with 60-second lifetime
- Port visible in API (`forwarded_port` field) and state file
- 2 new settings: `PROTON_USER`, `PROTON_PASS`
- Provider count: custom + Mullvad + IVPN + PIA + Gluetun + **Proton** (6 total)

### HTTP CONNECT Proxy
- RFC 7231 HTTP CONNECT proxy for routing non-Docker clients through VPN
- Optional Basic auth (`HTTP_PROXY_USER` + `HTTP_PROXY_PASS`)
- Bidirectional byte relay with asyncio
- Runs in FastAPI lifespan (same lifecycle as watchdog/MQTT)
- 4 new settings: `HTTP_PROXY_ENABLED`, `HTTP_PROXY_PORT`, `HTTP_PROXY_USER`, `HTTP_PROXY_PASS`

### SOCKS5 / Shadowsocks Proxy
- RFC 1928 SOCKS5 proxy with CONNECT support
- IPv4, IPv6, and domain name address types
- Optional RFC 1929 username/password authentication
- Shadowsocks AEAD encryption layer (AES-256-GCM, ChaCha20-Poly1305)
- Standard key derivation (EVP_BytesToKey + HKDF-SHA1)
- 7 new settings: `SOCKS_PROXY_ENABLED`, `SOCKS_PROXY_PORT`, `SOCKS_PROXY_USER`, `SOCKS_PROXY_PASS`, `SHADOWSOCKS_ENABLED`, `SHADOWSOCKS_PASSWORD`, `SHADOWSOCKS_CIPHER`

### Infrastructure
- 24 new configurable settings (total: 50)
- Health endpoint includes DNS, HTTP proxy, SOCKS proxy states
- Prometheus metrics for all new services
- Settings panel UI: 5 new sections (Firewall, DNS, ProtonVPN, HTTP Proxy, SOCKS5 Proxy)
- New dependencies: `dnspython`, `cachetools`, `cryptography`

### DRY Refactor
- `api/constants.py` — single source of truth for all timeouts, ports, paths, state enums, and helpers
- State enums (`VpnState`, `KillswitchState`, `ServiceState`, `WatchdogState`, `HealthState`) replace raw strings across all routes and services
- `http_client()` factory replaces ~24 instances of raw `httpx.AsyncClient`
- `activate_wg_config()` helper replaces 3x duplicated WireGuard symlink logic
- Four-tier subprocess timeout hierarchy: QUICK(5), DEFAULT(10), LONG(15), VPN(30)
- Four-tier HTTP timeout hierarchy: QUICK(5), DEFAULT(10), FETCH(15), DOWNLOAD(30)
- Configurable intervals: `PORT_FORWARD_INTERVAL`, `DNS_BLOCKLIST_REFRESH_INTERVAL`

### Tests
- 108 new unit tests across 7 test files (secrets, firewall, DNS, ProtonVPN, NAT-PMP, HTTP proxy, SOCKS5/Shadowsocks)
- 11 DRY guardrail tests (`test_dry.py`) — grep-based architectural tests that scan the codebase for raw httpx usage, hardcoded timeouts, state strings, paths, ports, and settings model drift
- 157 total tests

---

## v2.4.0 — Setup Wizard & Dashboard Components (2026-03-04)

The wizard now knows what you're setting up. Pick your provider, enter the right credentials, pick a server — no more pasting configs for providers that have APIs.

### Setup Wizard — Provider-Specific Flows
- **Mullvad / IVPN**: Private key + address + optional DNS fields → server picker → verify
- **PIA**: Username + password + port forwarding toggle → validates credentials via PIA API → server picker → verify
- **Gluetun**: URL + optional API key → validates gluetun connection → straight to done (skips WG verify)
- **Custom / Proton**: Paste config textarea → verify (unchanged existing flow)
- Server picker step with country dropdown, search filter, server table (hostname, location, speed, owned badge)
- `POST /setup/credentials` — validates and persists provider-specific credentials to `/config/tunnelvision.yml`
- `POST /setup/server` — select a server by hostname, reuses existing connect logic to generate WireGuard config
- `complete_setup` now persists `vpn_provider` to settings YAML — survives container restarts

### Settings
- `wireguard_private_key` and `wireguard_addresses` added to configurable fields — editable from settings UI
- New "WireGuard" section in settings panel between VPN and Gluetun

### Dashboard Components
- Connection history card — event timeline with timestamps
- Server browser modal — country filter, search, connect-to-server
- Multi-config manager — switch VPN configs from dashboard

### Bug Fix
- `verify_connection` now always tears down WG tunnel, including when geo-IP lookup fails (previously left tunnel up on that path)

---

## v2.3.0 — Self-Healing VPN (2026-03-03)

If the tunnel drops at 3am, TunnelVision brings it back. No cron jobs, no external scripts.

### Auto-Reconnect Watchdog
- Background asyncio service with state machine: MONITORING → DEGRADED → RECONNECTING → FAILING_OVER → COOLDOWN
- WireGuard health: `wg show wg0 latest-handshakes` staleness (>180s = stale)
- OpenVPN health: `tun0` interface existence check
- Sidecar health: gluetun API read-only probe
- Escalation: 1-2 failures → degrade + broadcast. 3rd failure → reconnect. Reconnect fails → failover to next config. All configs exhausted → cooldown 5min, reset, retry
- SSE broadcasts on every state transition (`watchdog_degraded`, `watchdog_reconnecting`, `watchdog_failover`, `watchdog_recovered`, `watchdog_cooldown`)
- MQTT HA Discovery entities: `watchdog_state`, `active_config`
- Notification webhooks fire on reconnect attempts and recovery
- Runtime toggle: re-reads `auto_reconnect` from settings YAML each tick — togglable without restart

### Multi-Config Failover
- Scans `/config/wireguard/*.conf` + `/config/openvpn/*.ovpn` for available configs
- On reconnect failure, cycles to next untried config
- Strips PostUp/PostDown from configs before activation (safety)
- Re-applies killswitch after config switch (nftables rules hardcode endpoint IP)
- Resets tried-config list on recovery or after cooldown

### Settings Hot-Reload
- 7 fields now take effect immediately without restart: `auto_reconnect`, `health_check_interval`, `vpn_country`, `vpn_city`, `notify_webhook_url`, `notify_gotify_url`, `notify_gotify_token`
- Watchdog re-reads `health_check_interval` from settings YAML each tick
- Notifications re-read webhook URLs from settings YAML on each send
- Server rotation re-reads `vpn_country`/`vpn_city` from settings YAML
- All 25 configurable fields now persist correctly via settings API (8 were silently dropped before)
- `needs_restart` response flipped from blocklist to hot-reload whitelist

### Settings Panel UI
- Per-field dirty tracking with amber border on changed inputs
- Per-field hot-reload indicator: green zap (instant) vs amber refresh (needs restart)
- "Unsaved" badge in header when changes exist
- Confirm dialog on close/cancel when dirty
- Save button disabled when no changes
- Footer legend showing icon meanings

### Bug Fix
- `active_config` in StateManager now set correctly for custom config rotation (was only set for Mullvad/IVPN/PIA)

### Tests
- 40 unit tests covering state transitions, health probes, escalation, failover, cooldown, config activation, settings hot-reload, singleton pattern, model alignment

---

## v2.2.0 — Architecture Cleanup (2026-03-04)

Internal refactor. Zero new features, zero breaking changes. The plumbing got proper.

### StateManager
- New singleton service (`api/services/state.py`) owns all `/var/run/tunnelvision/*` file I/O
- Typed property accessors for every state key, `snapshot()` for bulk reads
- Eliminates 5 duplicated `_read_state()` helpers scattered across routes

### Config Consolidation
- `os.getenv()` now only appears in `config.py` (and the intentional `settings.py` YAML fallback)
- All provider classes accept `Config` in `__init__` instead of reading env directly
- Added missing config fields: `mullvad_account`, `wireguard_private_key`, `wireguard_addresses`, `wireguard_dns`, `allowed_networks`, notification settings

### MQTT Dispatch
- `_on_message` now calls `do_vpn_restart()`, `do_qbt_pause()` etc. directly
- Killed subprocess curl to localhost — MQTT and REST share the same code path
- Control route handlers extracted into standalone `do_*()` functions

### Verification
- Zero `_read_state()` helpers remain
- Zero `subprocess curl localhost` calls
- `os.getenv` confined to `config.py`
- 30 files touched, +368/-318 lines

---

## v2.1.0 — Real-Time Events (2026-03-03)

### Server-Sent Events (SSE)
- `GET /api/v1/events` — persistent SSE stream for real-time state push
- Broadcasts on VPN state changes, control actions, IP changes
- 30s keepalive to prevent connection drops
- Dashboard UI now uses SSE — instant updates instead of 10s polling
- HACS integration uses SSE — instant HA entity updates instead of 15s polling
- Polling remains as fallback for resilience

### HACS Integration v0.2.0
- VPN switch — toggle on/off maps to connect/disconnect
- Killswitch switch — toggle on/off maps to enable/disable
- Removed redundant buttons (disconnect, reconnect, killswitch enable/disable)
- IoT class upgraded from `local_polling` to `local_push`
- Entity count: 12 sensors + 4 binary sensors + 5 buttons + 2 switches = 23

---

## v2.0.0 — Sidecar Mode (2026-03-03)

TunnelVision can now front gluetun. Use gluetun for the tunnel, TunnelVision for the eyes.

### Gluetun Sidecar Mode
- Set `VPN_PROVIDER=gluetun` — TunnelVision reads VPN state from gluetun's control server API
- Inherits all 30+ providers that gluetun supports — no provider-specific code needed
- Reads public IP, VPN status, and forwarded port from gluetun
- Enriches with geo-IP for country/city (gluetun's API only returns the IP)
- Full observability stack works in sidecar mode: dashboard, HA integration, Homepage widget, Prometheus, notifications
- Example compose at `examples/docker-compose.sidecar.yml`

### Two Modes, One Product
- **Standalone** — all-in-one container with built-in VPN, killswitch, qBittorrent (existing behavior)
- **Sidecar** — pairs with gluetun, adds dashboard + API + integrations on top

### New Env Vars
- `GLUETUN_URL` — gluetun control server URL (default `http://gluetun:8000`)
- `GLUETUN_API_KEY` — gluetun API key (if auth enabled)

### Provider Count: 5
custom, mullvad, ivpn, pia, gluetun (sidecar)

---

## v1.2.0 — Full Stack (2026-03-03)

Everything from the roadmap, in one push.

### Reconnect Endpoint
- `POST /api/v1/vpn/reconnect` — manually trigger VPN reconnection
- `AUTO_RECONNECT` config flag (default on) — foundation for future watchdog
- Server rotation reconnects through provider-aware logic (Mullvad, PIA, IVPN pick new servers)

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
