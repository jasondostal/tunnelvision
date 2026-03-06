# Changelog

## Unreleased

---

## v3.5.0 — Security hardening + bug fixes (2026-03-06)

### Security
- **`TRUSTED_PROXY_IPS` — reverse proxy auth hardening**: `AUTH_PROXY_HEADER` previously
  accepted the configured header from any client on an allowed network. Any LAN host could
  forge `Remote-User: admin` and bypass authentication. `TRUSTED_PROXY_IPS` (IP or CIDR,
  comma-separated) restricts which source IPs can set the proxy header — all other sources
  have the header silently ignored. This is the standard pattern used by Traefik, Gitea,
  and Grafana for trusted proxy authentication.
  - If `AUTH_PROXY_HEADER` is set without `TRUSTED_PROXY_IPS`: startup warning logged,
    `security_warnings` array populated in `GET /api/v1/health`, behavior unchanged
    (backward compatible).
  - New env var: `TRUSTED_PROXY_IPS` (e.g. `172.20.0.2` or `172.20.0.0/16`).
  - `HealthResponse` gains a `security_warnings: list[str]` field — currently reports
    the proxy auth misconfiguration; extensible for future checks.

### Bug fixes
- **Sidecar mode watchdog**: health check was hitting `/v1/openvpn/status` — gluetun's
  unified status endpoint is `/v1/vpn/status`. Every sidecar health check was returning
  `unknown` (404) and being treated as a failure. Fixed.

- **Setup wizard gluetun validation**: same endpoint bug as watchdog — `/v1/openvpn/status`
  → `/v1/vpn/status`. Gluetun sidecar validation in the setup wizard was always failing.
- **Setup wizard blank screen for PASTE providers**: Surfshark, Windscribe, IPVanish,
  AirVPN, TorGuard, PrivateVPN, FastestVPN, SlickVPN, Giganews — selecting any of these
  in the wizard routed to "credentials" step with no form rendered. Now routed to the
  WireGuard config paste step, with the provider's own setup instructions shown as the
  description.
- **Mullvad account number not saved**: wizard collected private key + address for Mullvad
  but never showed or saved the account number. Account expiry was silently unavailable
  for all wizard-configured Mullvad users. Account number field added (optional) — when
  provided, saved to settings and used for expiry display in the health dashboard.

### Documentation
- **Gluetun provider docstring**: removed misleading "inherits all 30+ providers" claim.
  Sidecar mode reads gluetun's status — it does not inherit gluetun's provider logic.
- **Sidecar → native migration guide**: README "Migrating from other setups" now includes
  a step-by-step guide for moving from sidecar mode to a fully native TunnelVision setup
  (required capabilities, credentials, removing gluetun from the stack).
- **Sidecar mode positioning**: clarified that sidecar mode is an evaluation/parallel lane
  (read-only monitoring) rather than an intermediate adoption step. Gluetun remains in
  charge of the tunnel; TunnelVision adds dashboard, HA, Prometheus, and webhooks on top.

---

## v3.4.9 — Code quality + CI security pipeline (2026-03-05)

### Code quality
- **Zero Ruff findings** — removed 12 unused imports, 2 stale f-prefixes, 1 identity test
- **Zero Bandit high-severity** — added `usedforsecurity=False` to Shadowsocks MD5 (protocol-required, not security)
- **Zero mypy errors** — type annotations for all unchecked assignments, `ServiceState.STOPPED` added to enum,
  None-guard on MQTT publish, pydantic mypy plugin (`mypy.ini`) for Pydantic model validation
- **Zero ShellCheck findings** — quoted variable expansion in init-vpn.sh
- **Zero pip-audit CVEs** — all Python dependencies clean
- **Zero npm audit findings** — all frontend dependencies clean
- **Zero Hadolint findings** — Dockerfile best practices verified, redundant chmod removed
- **Zero Trivy CVEs** — container image scanned for OS-level vulnerabilities (CRITICAL/HIGH)
- `HEALTH_CHECK_INTERVAL` default corrected to 15 in Dockerfile (was still 30)

### CI pipeline
- New **lint** job (8 tools) runs in parallel with tests — Ruff, Bandit, mypy, ShellCheck,
  pip-audit, Hadolint, npm audit
- New **scan** job — Trivy scans the built container image for Alpine apk package and
  system library CVEs at CRITICAL and HIGH severity
- Build gates on both `lint` and `test`; smoke gates on `build` and `scan`
- **cosign** — every pushed image is signed with Sigstore keyless signing (OIDC-backed,
  no keys to manage). Users can verify with `cosign verify`
- Total pipeline: lint (8 tools) + test (734 tests) → build (3 arches) + sign → scan (Trivy) → smoke

---

## v3.4.8 — Shadowsocks server + settings panel UX (2026-03-05)

### Shadowsocks proxy
The Shadowsocks AEAD crypto library (shipped in v2.5.0) is now wired into a real TCP proxy server.
Clients connect, exchange salts, and relay traffic through the VPN tunnel with full AEAD encryption.

- **ShadowsocksService** — standalone TCP server implementing the standard Shadowsocks protocol
  (salt exchange → AEAD-decrypt target address → connect → encrypted bidirectional relay)
- **AES-256-GCM** and **ChaCha20-Poly1305** ciphers
- Default port **8388**, configurable via `SHADOWSOCKS_PORT`
- Started/stopped in FastAPI lifespan alongside HTTP and SOCKS5 proxies
- Firewall rules added to killswitch (input + output from allowed networks)
- `shadowsocks_state` tracked in StateManager + snapshot
- Prometheus metric: `tunnelvision_shadowsocks_up`
- Full config chain: `SHADOWSOCKS_PORT` env → Config → settings YAML → UI

### Settings panel UX
- **Toggle switches** for all 17 boolean fields — no more typing "true"/"false"
- **Number inputs** for numeric fields (ports, intervals, thresholds)
- **Collapsible sections** with chevron — VPN section open by default, sections with
  unsaved changes auto-open, dirty indicator dot on collapsed headers
- Shadowsocks split into its own section (separate from SOCKS5)
- Groups reordered: VPN first, providers grouped, General last
- Env var names shown inline with labels (smaller, cleaner)

### Tests
- 734 passed (+25 new: address parsing, lifecycle, full connection flow, domain targets,
  error handling, config wiring, singleton)

---

## v3.4.7 — Rotate geographic diversity (2026-03-05)

### Bug fixes
- **Rotate no longer sticks to the same country** — when no country filter is set,
  `POST /vpn/rotate` now picks a random country (excluding the current one) before
  score-selecting within it. Previously, the globally highest-scoring country won
  every rotation (Switzerland in practice), making rotate feel broken even though
  it was technically working.
- **Filter-constrained rotation unchanged** — if `VPN_COUNTRY` or `VPN_CITY` is set,
  rotate still score-selects within that pool as before.

### Tests
- 716 passed (+7 rotate diversity tests)

---

## v3.4.6 — SSE reliability + full settings exposure (2026-03-05)

### Bug fixes
- **SSE-triggered refreshes no longer serve stale data** — the 5s GET cache in the
  frontend was returning cached responses when SSE events fired immediately after a
  user action (e.g. Disconnect fired SSE at T+0.1s, cache hit returned pre-disconnect
  state). Fixed by invalidating affected cache keys before bumping the refresh signal.
- **Watchdog events now trigger UI refresh** — `useSSE` only listened for `vpn_status`
  and `vpn_state`. All five watchdog events (`recovered`, `reconnecting`, `failover`,
  `degraded`, `cooldown`) were broadcast over SSE but silently dropped by the frontend.
  Added `SSE_REFRESH_EVENTS` list covering all event types.

### Features
- **Watchdog tuning exposed as live settings** — `HANDSHAKE_STALE_SECONDS`,
  `RECONNECT_THRESHOLD`, and `COOLDOWN_SECONDS` were previously hardcoded. Now
  configurable via env var, YAML file, or the Settings UI — and hot-reloadable
  without a container restart (watchdog reads them each tick via `_load_setting()`).
- **Settings panel is now a single pane of glass** — 9 previously env-only fields
  added to the UI: `vpn_enabled`, `vpn_type`, `wireguard_dns`, `qbt_enabled`,
  `webui_port`, `mqtt_topic_prefix`, `mqtt_discovery_prefix`, `allowed_networks`, `tz`.
  Each shows its `$ENV_VAR` name and the ⚡/🔄 indicator for hot-reload vs restart.
- **New Watchdog and qBittorrent groups** in the Settings panel.
- **Watchdog check interval tightened** — default `HEALTH_CHECK_INTERVAL` reduced from
  30s to 15s. Halves worst-case autonomous VPN drop detection latency.

### Tests
- 709 passed (unchanged)

---

## v3.4.5 — Internal code quality pass II (2026-03-05)

### Bug fixes
- **MQTT async regression fixed** — `do_qbt_pause`/`do_qbt_resume` were converted to
  `async def` in v3.4.4 but `_on_message()` (a paho sync callback thread) called them
  synchronously, receiving back a coroutine object instead of an `ActionResponse`. Fixed
  with `asyncio.run_coroutine_threadsafe()` against the event loop captured at startup.

### Refactoring
- **qBittorrent status endpoint uses httpx** — three `subprocess.run(["curl"...])` calls
  replaced with a single shared `http_client()` async context; deferred `import json`
  removed (httpx exposes `.json()` natively).
- **Deferred imports moved to module level** — `from datetime import datetime` inside
  try-blocks in `system.py` and `metrics.py`; `import os` inside `run()` in `dns.py`.
- **`/system` Alpine version uses `Path.read_text()`** — replaced `subprocess.run(["cat",
  "/etc/alpine-release"])` with a direct file read.
- **`tar.extract()` now passes `filter="data"`** — suppresses Python 3.12 deprecation
  warning and prevents path traversal via symlinks in restored backup archives.
- **`asyncio.get_event_loop()` replaced** — `dns.py` and `natpmp.py` now use
  `asyncio.get_running_loop()` / `asyncio.ensure_future()` (deprecated API removed).
- **MQTT `sw_version` uses `__version__`** — was hardcoded as `"0.1.0"`.

### Tests
- 709 passed (unchanged)

---

## v3.4.4 — Internal code quality pass (2026-03-05)

### Refactoring
- **Eliminated duplicated WireGuard activation logic** — `bring_up_wireguard_file()` is now
  a single shared utility in `constants.py`. Previously the PostUp/PostDown strip + wg-quick
  sequence existed independently in both `connect.py` and `watchdog.py`, with subtle divergence
  in killswitch handling.
- **Eliminated duplicated config-file enumeration** — `list_config_files()` moved to
  `constants.py`; both `connect.py` and `watchdog.py` now share it.
- **Provider metadata no longer allocates on every access** — `VPNProvider.get_meta()` is a
  new classmethod that caches `ProviderMeta` per class. The previous pattern of
  `cls.__new__(cls)` + `cls.meta.fget(instance)` appeared in 5 places; all replaced.
- **Server cache refresh properly encapsulated** — `VPNProvider.refresh_cache()` is a new
  base-class method. The server-list updater no longer reaches into `_server_cache`/
  `_cache_time` from outside the class.
- **Sidecar mode detection unified** — watchdog was checking `gluetun_url != default`,
  status route was checking `vpn_provider == "gluetun"`. Both now use the same condition.
- **`_select_server()` scores precomputed once** — previously scored each server 2N+1 times
  (sort + top-score check + uniform check); now computed once and reused.
- **qBittorrent API calls no longer block the event loop** — `do_qbt_pause/resume` converted
  from blocking subprocess curl to async httpx. Same for the qBittorrent health check and
  geo-IP check in the setup wizard.
- **Setup wizard handles all WireGuard providers generically** — `setup_credentials()`
  previously hardcoded `("mullvad", "ivpn")` for WireGuard credential validation. Now
  checks `provider_meta.supports_wireguard` — NordVPN, Windscribe, Surfshark, AirVPN, etc.
  correctly save private key + address through the wizard.
- **PIA key exchange uses `self.WG_PORT`** — hardcoded `1337` in the URL replaced with
  the class constant.
- **`forwarded_port` setter accepts `None` to delete** — consistent with StateManager's
  property pattern; `delete_forwarded_port()` delegates to it.
- Deferred stdlib imports (`asyncio`, `shutil`, `subprocess`) moved to module level.

### Tests
- 709 passed (unchanged — test patches updated to follow `bring_up_wireguard_file`
  moving from watchdog to constants)

---

## v3.4.3 — Fix server selection bias + killswitch on rotate (2026-03-05)

### Bug fixes
- **Rotate now picks genuinely random servers** — when a provider returns no load data
  (Mullvad: `load=null` for all 567 servers), all scores were equal and Python's stable
  sort meant the "top 5" was always the first 5 alphabetically (Albania + Argentina every
  time). Fixed: uniform scores now pick from the full candidate pool. Pool size is also
  dynamic — 20% of candidates, min 5, max 25 — rather than a hard-coded 5.
- **Speed normalization cap raised to 20 Gbps** — providers with 10 and 20 Gbps tiers
  were both capping at 1.0 (10 Gbps was the old ceiling), making speed useless as a
  signal. 20 Gbps = max now differentiates the tiers.
- **Killswitch no longer blocks WireGuard handshake after rotate/reconnect** *(from v3.4.2)*
  — `_reconnect_vpn` now re-runs `init-killswitch.sh` after `wg-quick up` so nftables
  allows the new server's endpoint. Previously the old server's IP was locked in, silently
  dropping all handshake packets (interface up, 0 B received).

### Tests
- `test_uniform_scores_pick_from_full_pool` — verifies >5 distinct servers appear across
  200 rotations when all scores are equal

---

## v3.4.2 — Fix killswitch blocking rotate/reconnect (2026-03-05)

### Bug fix
- **Rotate/reconnect now works with killswitch enabled** — `_reconnect_vpn` wasn't re-running
  `init-killswitch.sh` after `wg-quick up`. The killswitch locks nftables to the previous
  server's endpoint IP, so WireGuard handshake packets to the new server were silently dropped
  (interface up, 0 B received). `init-killswitch.sh` now runs after every `wg-quick up`,
  updating the allowed endpoint to match the new server. `activate_config` already did this
  correctly; `_reconnect_vpn` now matches.

---

## v3.4.1 — Rotate fix + build hardening (2026-03-05)

### Bug fixes
- **Server rotation now works** — rotate/connect was writing the new WireGuard config to
  `/config/wireguard/wg0.conf` but `wg-quick` was reading the stale `/etc/wireguard/wg0.conf`
  copied once at startup. `_reconnect_vpn` now syncs the config before every `wg-quick up`.
- **arm/v7 builds fixed** — `lightningcss` (Tailwind v4's Rust CSS compiler) has no
  arm-musl binary. The UI builder stage is now pinned to `linux/amd64`; the output
  (static HTML/CSS/JS) is architecture-agnostic.

### Housekeeping
- `init-wireguard.sh` → `init-vpn.sh` — the script handles both WireGuard and OpenVPN;
  the old name was misleading. All s6 dependency tokens and Python references updated.
- `tests/test_s6_service_graph.py` — new pure-filesystem validator catches dangling s6
  service references after renames (exactly the class of bug this rename introduced).

### Tests
- 706 total (up from 698): 4 reconnect-sync tests, 4 s6 graph-validator tests

---

## v3.4.0 — Multi-Architecture: linux/arm/v7 (2026-03-04)

### Multi-architecture builds
TunnelVision now ships native images for `linux/arm/v7` in addition to `amd64` and `arm64`.
Raspberry Pi 2 and Pi 3 users (running 32-bit OS) can now pull a native image — no QEMU overhead.

- Build matrix extended to `linux/amd64,linux/arm64,linux/arm/v7`
- s6-overlay ARCH mapping extended: `arm → armhf`, with stubs for `386 → i686` and `ppc64le → powerpc64le`
- `cryptography` removed from pip requirements; replaced by Alpine's `py3-cryptography` package (44.0.0, pre-compiled for all arches)
- `uvicorn[standard]` → `uvicorn` — drops `watchfiles` (no arm/v7 wheel; unused in production anyway)

---

## v3.3.0 — Provider Health Dashboard + CI Test Pipeline (2026-03-04)

### Provider Health Dashboard
New dashboard card exposing live observability for the active VPN provider.

- **API reachability** — HEAD-pings the provider's API endpoint with 3s timeout; shows green/red dot and round-trip latency
- **Server cache status** — number of servers in cache and age since last refresh; amber dot when stale (>1h)
- **Account expiry** — for Mullvad and AirVPN: expiry date, days remaining, and a color-coded progress bar (green >30d, amber 7–30d, red <7d)
- **Manual refresh** — Refresh button triggers a new check without waiting for the 5-minute poll interval
- New `GET /api/v1/vpn/provider-health` endpoint
- `HEALTH_PING_URL` class constant added to `VPNProvider` base; Mullvad, IVPN, PIA, and ProtonVPN configured

### CI test pipeline
Tests now run in GitHub Actions on every push and pull request.

- New `test` job: Python 3.12, installs requirements, runs `pytest tests/ -q --tb=short`
- `build` job depends on `test` — broken tests block Docker image pushes

### Tests
- 698 total tests (up from 691)

---

## v3.2.0 — Smart Server Selection + WireGuard Key Generation (2026-03-04)

### Smart server selection
Server rotation is no longer random. Servers are now scored by load and speed, and the connect
pipeline picks from the top tier — distributing traffic across the best options while reliably
avoiding bad ones.

- **Load-aware**: servers with lower load score higher (load=0/unknown treated as 50%)
- **Speed-aware**: `speed_gbps` contributes 30% of the score (providers that expose it: NordVPN, Mullvad)
- **Top-5 jitter**: picks randomly from the top 5 to avoid thundering-herd on a single "best" server
- **Rotation avoidance**: `POST /vpn/rotate` now excludes the current server, guaranteeing a server change
- **Worst servers excluded**: with 6+ servers in the pool, the bottom tier is never selected

### WireGuard key generation in setup wizard
Mullvad and IVPN users no longer need to leave the wizard to generate a keypair.

- New "Generate Key" button in the credentials step — generates a keypair server-side via `wg genkey`
- Private key is pre-filled in the private key field
- Public key is displayed in a copyable box with provider-specific registration instructions
- New `POST /setup/generate-keypair` backend endpoint

### Tests
- 691 total tests (up from 681)

---

## v3.1.0 — Full OpenVPN Parity (2026-03-04)

Setup wizard now fully supports OpenVPN-only providers. Previously, providers like HideMyAss,
VyprVPN, VPNSecure, CyberGhost, Perfect Privacy, and Giganews would drop users into a dead-end
credentials step. Now they get a proper config paste flow, optional credential fields, and a live
verify step — same first-class experience as WireGuard.

### Setup wizard
- OpenVPN-only providers now route to an OpenVPN config paste step instead of a credentials dead-end
- New `.ovpn` textarea with OpenVPN-appropriate placeholder and provider-specific instructions
- Optional username/password fields for providers that require credentials alongside the config
- Verify step now supports OpenVPN: starts the daemon, waits for `tun0`, runs geo-IP check, tears down cleanly

### Backend
- New `POST /setup/openvpn` endpoint — validates, writes `/config/openvpn/provider.ovpn`, optionally writes `credentials.txt`
- `POST /setup/verify` now auto-detects WireGuard vs. OpenVPN config and branches accordingly
- `POST /setup/complete` accepts OpenVPN config as valid; writes `vpn_type=openvpn` to settings when appropriate
- `GET /setup/status` now returns `has_config: true` when an OpenVPN config is present
- New constants: `OPENVPN_CONF_PATH`, `OPENVPN_CREDS_PATH` in `api/constants.py`

### Tests
- 681 total tests (up from 673)

---

## v3.0.0 — Provider Wave 3 (2026-03-04)

Nine more provider integrations — brings the total to 25 supported VPN providers.

### Privado
- Connection monitoring via geo-IP
- Setup: log into your Privado account → Apps → Manual → WireGuard. Download config and place in `/config/wireguard/wg0.conf`.

### PureVPN
- Connection monitoring via geo-IP
- Setup: purevpn.com → Members Area → Manually configure → WireGuard. Note: configs expire after 30 minutes — regenerate as needed.

### VPNSecure
- Connection monitoring via geo-IP
- WireGuard not supported (OpenVPN only). Setup: vpnsecure.me account → Manual OpenVPN configs. Set `VPN_TYPE=openvpn`.

### VPN Unlimited
- Connection monitoring via geo-IP
- Setup: my.keepsolid.com → Manage Devices → Manual Config → WireGuard.

### VyprVPN
- Connection monitoring via geo-IP
- WireGuard is app-only — no manual config export available. Requires OpenVPN for container deployments — set `VPN_TYPE=openvpn`.

### FastestVPN
- Connection monitoring via geo-IP
- Setup: contact FastestVPN support (support@fastestvpn.com) to request WireGuard config files.

### HideMyAss
- Connection monitoring via geo-IP
- WireGuard is app-only (Windows). Requires OpenVPN — log into HMA account → Servers → Manual setup → OpenVPN. Set `VPN_TYPE=openvpn`.

### SlickVPN
- Connection monitoring via geo-IP
- Note: SlickVPN is no longer accepting new subscriptions. Existing subscribers: download config from your SlickVPN dashboard.

### Giganews
- Connection monitoring via geo-IP
- Giganews bundles VyprVPN. WireGuard is app-only — manual config export not available. Requires OpenVPN — set `VPN_TYPE=openvpn`.

### Tests
- 673 total tests (up from 513)

---

## v2.9.0 — Provider Wave 2 (2026-03-04)

Five more provider integrations. Reality check included — not every provider has a clean API.

### IPVanish
- Server browser via public GeoJSON API — hostname, country, city, load
- Setup: log into IPVanish account → Service Management → WireGuard → Generate. Note: configs expire after 30 days.

### TorGuard
- Connection monitoring (IP, country, city) via geo-IP
- Setup: torguard.net → Tools → Config Generator → WireGuard. Note: configs expire after 12-24 hours by design.

### PrivateVPN
- Connection monitoring via geo-IP
- Setup: privatevpn.com account → WireGuard Configurations → Generate Config.

### Perfect Privacy
- Connection monitoring via geo-IP
- WireGuard is explicitly not supported by Perfect Privacy (architectural decision). Requires OpenVPN — set `VPN_TYPE=openvpn`.

### CyberGhost
- Connection monitoring via geo-IP
- WireGuard is app-only — no manual config export. Requires OpenVPN for container deployments — set `VPN_TYPE=openvpn`.

### Tests
- 513 total tests (up from 420)

---

## v2.8.0 — Provider Wave 1 (2026-03-04)

Five new native provider integrations. All auto-discovered, auto-configured, auto-tested.

### NordVPN
- Full server rotation via the NordVPN public API — server list includes WireGuard public keys, load, and categories
- P2P and Double VPN (multi-hop) servers correctly flagged for filtering
- Dual connection check: NordVPN's IP lookup endpoint with generic geo-IP fallback
- Setup: add a WireGuard key in your NordVPN dashboard, set `WIREGUARD_PRIVATE_KEY` and `WIREGUARD_ADDRESSES`

### Windscribe
- Server browser via public server list — country, city, hostname, P2P flag
- Setup: download WireGuard config from the Windscribe website and place in `/config/wireguard/wg0.conf`

### AirVPN
- Server browser via public status API — country, city, IP, load
- Optional `AIRVPN_API_KEY` for account info in the dashboard (days remaining, status)
- Setup: generate a WireGuard config from the AirVPN config generator and paste it in

### Surfshark
- Server browser via Surfshark cluster API — country, city, load
- Setup: generate a WireGuard key pair on the Surfshark website and download the config

### ExpressVPN
- Connection monitoring (IP, country, city) via geo-IP
- Setup: download WireGuard config from the ExpressVPN app or website

### Tests
- 420 total tests (up from 319)

---

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
