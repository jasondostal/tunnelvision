# TunnelVision Technical Primer

*A systems hacker's guide to the architecture, internals, and design philosophy of TunnelVision — from the tiniest nftables rule to the highest-level service orchestration.*

**Version:** 3.5.0 | **Stack:** Alpine 3.21, s6-overlay 3.2.2, Python 3.12 / FastAPI, React 19 / Vite / Tailwind v4

---

## Table of Contents

1. [What Is TunnelVision?](#1-what-is-tunnelvision)
2. [High-Level Architecture](#2-high-level-architecture)
3. [The Container: Dockerfile & Build Pipeline](#3-the-container-dockerfile--build-pipeline)
4. [Boot Sequence: s6-overlay Process Supervision](#4-boot-sequence-s6-overlay-process-supervision)
5. [The Firewall: nftables Killswitch](#5-the-firewall-nftables-killswitch)
6. [Life of a Packet](#6-life-of-a-packet)
7. [VPN Connection Pipeline](#7-vpn-connection-pipeline)
8. [Provider System & Auto-Discovery](#8-provider-system--auto-discovery)
9. [Smart Server Selection & Rotation](#9-smart-server-selection--rotation)
10. [Watchdog: Self-Healing State Machine](#10-watchdog-self-healing-state-machine)
11. [The API Layer](#11-the-api-layer)
12. [Configuration System](#12-configuration-system)
13. [Setup Wizard](#13-setup-wizard)
14. [Services Layer](#14-services-layer)
15. [React Frontend](#15-react-frontend)
16. [SSE Real-Time Architecture](#16-sse-real-time-architecture)
17. [Testing & Quality Gates](#17-testing--quality-gates)
18. [CI/CD Pipeline](#18-cicd-pipeline)
19. [Security Model](#19-security-model)
20. [Appendix: File Map](#20-appendix-file-map)

---

## 1. What Is TunnelVision?

TunnelVision is an all-in-one Docker container that bundles qBittorrent, a WireGuard/OpenVPN VPN tunnel, a nftables killswitch, and a full management API + dashboard into a single image. It operates in two modes:

- **Standalone:** Container manages its own VPN tunnel (WireGuard or OpenVPN), firewall, DNS, proxies, and torrent client.
- **Sidecar:** Container reads VPN state from an external Gluetun container, managing only qBittorrent and the dashboard.

The project integrates 25 native VPN providers — from Mullvad and PIA to NordVPN, Surfshark, and 6 OpenVPN-only providers — with auto-discovery, smart server selection, port forwarding, and a self-healing watchdog that reconnects when the tunnel drops.

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        Docker Container                              │
│                                                                      │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────────┐  │
│  │ s6-overlay   │    │  nftables    │    │  WireGuard / OpenVPN   │  │
│  │ init system  │───▶│  killswitch  │───▶│  tunnel (wg0 / tun0)   │  │
│  └──────┬───────┘    └──────────────┘    └─────────────────────────┘  │
│         │                                                             │
│  ┌──────▼───────────────────────────────────────────────────────────┐ │
│  │                    FastAPI (uvicorn :8081)                        │ │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │ │
│  │  │ Routes  │ │ Watchdog │ │ Provider │ │ Settings │ │  SSE   │ │ │
│  │  │ (14)    │ │ State    │ │ System   │ │ Service  │ │ Events │ │ │
│  │  │         │ │ Machine  │ │ (25 VPN) │ │ (YAML)   │ │        │ │ │
│  │  └─────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │ │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │ │
│  │  │  MQTT   │ │   DNS    │ │  HTTP    │ │  SOCKS5  │ │Shadow- │ │ │
│  │  │  HA     │ │  DoT +   │ │  CONNECT │ │  Proxy   │ │socks   │ │ │
│  │  │  Disc.  │ │  Block   │ │  Proxy   │ │  :1080   │ │  AEAD  │ │ │
│  │  └─────────┘ └──────────┘ └──────────┘ └──────────┘ └────────┘ │ │
│  └──────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌──────────────────────┐    ┌──────────────────────────────────────┐ │
│  │ qBittorrent-nox      │    │  React 19 Dashboard                 │ │
│  │ :8080 (WebUI)        │    │  Served as static files at /        │ │
│  └──────────────────────┘    └──────────────────────────────────────┘ │
│                                                                      │
│  Volumes: /config (persistent), /downloads                           │
└──────────────────────────────────────────────────────────────────────┘
```

**Process tree** (managed by s6-overlay):

```
/init (s6-overlay)
 ├── init-environment     (oneshot: user setup, gateway detection)
 ├── init-firewall-pre    (oneshot: pre-VPN lockdown)
 ├── init-vpn             (oneshot: bring up wg0/tun0)
 ├── init-killswitch      (oneshot: full firewall rules)
 ├── svc-api              (longrun: FastAPI on :8081)
 ├── svc-dns              (longrun: DNS on :53, if enabled)
 ├── svc-healthcheck      (longrun: geo-IP polling loop)
 └── svc-qbittorrent      (longrun: qbittorrent-nox on :8080)
```

---

## 3. The Container: Dockerfile & Build Pipeline

### Three-Stage Multi-Arch Build

**Stage 1 — UI Builder** (Node.js 22, pinned to `--platform=linux/amd64`):

```dockerfile
FROM --platform=linux/amd64 node:22-alpine AS ui-builder
```

The UI is built on amd64 only because lightningcss (the Rust CSS engine powering Tailwind v4) has no musl ARM binary. The output is architecture-agnostic static HTML/JS/CSS — cross-compilation is unnecessary.

**Stage 2 — API Builder** (Python 3.12):

```dockerfile
FROM python:3.12-alpine AS api-builder
RUN pip install --no-cache-dir --target=/install -r requirements.txt
```

Dependencies installed to `/install` for clean COPY into the runtime stage. The `cryptography` package is excluded from requirements.txt — it's installed via Alpine's `py3-cryptography` APK package, which provides prebuilt wheels for all architectures (amd64, arm64, armhf).

**Stage 3 — Runtime** (Alpine 3.21):

Key packages: `bash`, `bind-tools`, `curl`, `iproute2`, `jq`, `nftables`, `python3`, `openvpn`, `qbittorrent-nox`, `wireguard-tools`, and `wireguard-go` (from Alpine edge/community — removed from 3.21 stable).

**Build targets:** `linux/amd64`, `linux/arm64`, `linux/arm/v7`

### Environment Defaults

The Dockerfile sets production defaults that can be overridden at runtime:

| Variable | Default | Purpose |
|----------|---------|---------|
| `VPN_ENABLED` | `true` | Enable VPN tunnel |
| `VPN_TYPE` | `wireguard` | `wireguard`, `openvpn`, or `auto` |
| `KILLSWITCH_ENABLED` | `true` | nftables firewall |
| `HEALTH_CHECK_INTERVAL` | `15` | Seconds between health checks |
| `S6_BEHAVIOUR_IF_STAGE2_FAILS` | `0` | Halt container on init failure |
| `S6_CMD_WAIT_FOR_SERVICES_MAXTIME` | `30000` | 30s service startup timeout |

### Python Dependencies

10 direct dependencies (requirements.txt):
- **fastapi** — async web framework
- **uvicorn** — ASGI server (without `[standard]` extra — watchfiles has no armv7 wheel)
- **pydantic** — data validation & models
- **httpx** — async HTTP client (provider APIs, geo-IP)
- **paho-mqtt** — MQTT client for Home Assistant
- **pyyaml** — settings persistence
- **python-multipart** — file upload (backup/restore)
- **dnspython** — DNS wire protocol
- **cachetools** — TTL cache for provider server lists
- **cryptography** — installed via APK, not pip (multi-arch)

### JavaScript Dependencies

3 runtime: React 19, React DOM, Lucide React (icons).
Dev: Vite 6, TypeScript 5.6, Tailwind CSS 4, `@tailwindcss/vite`.

---

## 4. Boot Sequence: s6-overlay Process Supervision

s6-overlay is a process supervisor designed for containers. TunnelVision uses s6-rc (the dependency-aware service manager) to orchestrate 8 services in a strict DAG.

### Service Dependency Graph

```
base (s6 virtual)
 └─→ init-environment
      └─→ init-firewall-pre
           └─→ init-vpn
                ├─→ init-killswitch
                │    ├─→ svc-api
                │    ├─→ svc-dns
                │    └─→ svc-qbittorrent
                └─→ svc-healthcheck
```

All services are registered in the `user` bundle (`rootfs/etc/s6-overlay/s6-rc.d/user/contents.d/`).

### Stage-by-Stage Boot

**1. init-environment** (`rootfs/etc/s6-overlay/scripts/init-environment.sh`, 206 lines)

The foundation. Runs first, sets up everything the rest of the boot depends on:

- **PUID/PGID mapping** — modifies the `tunnelvision` user/group to match host IDs (avoids permission issues on bind-mounted volumes)
- **Directory creation** — `/config/wireguard`, `/var/run/tunnelvision`, qBittorrent config dirs
- **qBittorrent patching** — sets WebUI port, enables localhost auth bypass (so the API can query qBt without credentials)
- **Default gateway detection** — captures Docker's bridge gateway IP and interface name:

```bash
DEFAULT_GW=$(ip route show default | awk '/default/ {print $3}' | head -1)
DEFAULT_IF=$(ip route show default | awk '/default/ {print $5}' | head -1)
echo "$DEFAULT_GW" > /var/run/tunnelvision/default_gateway
echo "$DEFAULT_IF" > /var/run/tunnelvision/default_interface
```

This is critical: when `wg-quick` sets up the VPN, it replaces the default route with `wg0`. Without these saved values, the killswitch can't route LAN traffic back through Docker's bridge.

**2. init-firewall-pre** (`init-firewall-pre.sh`, 159 lines)

Pre-VPN lockdown. Applies strict nftables rules BEFORE the tunnel comes up, preventing any traffic leak during the WireGuard/OpenVPN handshake:

- Blocks ALL IPv6 (priority -1, runs before everything)
- Allows only: loopback, VPN endpoint handshake, API port from allowed networks
- Everything else: DROP

**3. init-vpn** (`init-vpn.sh`, 211 lines)

The VPN initialization script. Handles both WireGuard and OpenVPN in a single script (renamed from `init-wireguard.sh` in v3.4.0).

Config file discovery order:
1. `/config/wireguard/wg0.conf`
2. `/config/wireguard/wg-tunnel.conf`
3. `/config/wireguard/*.conf` (any)
4. `/config/openvpn/*.ovpn`
5. `/config/openvpn/*.conf`

If no config is found, the script writes `setup_required=true` to `/var/run/tunnelvision/setup_required` and exits. The API starts in setup mode, presenting the wizard UI.

**WireGuard path:**
1. Strips `PostUp`/`PostDown` directives (may conflict with container nftables)
2. Wraps `/sbin/sysctl` to silently handle read-only container filesystems
3. Probes for kernel WireGuard module; falls back to `wireguard-go` (userspace)
4. Runs `wg-quick up wg0`
5. Captures VPN IP, endpoint, interface name to state files

**OpenVPN path:**
1. Launches `openvpn --daemon` with config
2. Polls for `tun0` interface (up to 30 seconds)
3. Captures VPN IP and writes state files

**4. init-killswitch** (`init-killswitch.sh`, 280 lines)

The full firewall, applied after VPN is up. Replaces the pre-VPN rules with comprehensive nftables that know the VPN endpoint and interface. Detailed in [Section 5](#5-the-firewall-nftables-killswitch).

**5–8. Longrun Services**

After all oneshots complete, s6 starts the longrun services in parallel:

| Service | Script | Purpose |
|---------|--------|---------|
| `svc-api` | `uvicorn api.main:app` on `:8081` | FastAPI server — API, UI, SSE |
| `svc-dns` | `python3 -m api.services.dns` | DNS server on `:53` (if `DNS_ENABLED=true`) |
| `svc-healthcheck` | Bash loop at `HEALTH_CHECK_INTERVAL` | Geo-IP polling, WireGuard stats, state file updates |
| `svc-qbittorrent` | `qbittorrent-nox --profile=/config` on `:8080` | Torrent client (if `QBT_ENABLED=true`) |

Each service runs under `s6-supervise` with automatic restart on crash. If a service is disabled (e.g., `DNS_ENABLED=false`), the run script executes `sleep infinity` — keeping the s6 process slot occupied but idle.

### s6 Environment Variables

| Variable | Value | Effect |
|----------|-------|--------|
| `S6_KEEP_ENV=1` | Preserve Docker env vars | All `VPN_*`, `WEBUI_*` etc. are available to scripts |
| `S6_BEHAVIOUR_IF_STAGE2_FAILS=0` | Halt on init failure | If any oneshot fails, container stops (no traffic leak) |
| `S6_CMD_WAIT_FOR_SERVICES_MAXTIME=30000` | 30s service timeout | Allows OpenVPN's 30s tun0 polling window |

---

## 5. The Firewall: nftables Killswitch

The killswitch is the security backbone. It enforces a default-DROP policy on all traffic, with an explicit allowlist for VPN tunnel traffic and local services.

### Design Philosophy

**Firewall-first boot:** The pre-VPN lockdown (`init-firewall-pre`) applies DROP rules before the VPN handshake even begins. There is never a window where traffic can leak.

**Explicit allowlist:** Every allowed traffic path is a named rule. Nothing is implicitly permitted.

**IPv6 total block:** A separate `ip6 block_ipv6` table at priority -1 drops ALL IPv6 traffic across all hooks (input, output, forward). This prevents IPv6 DNS leaks, tracker connections, and DHCPv6 address assignment.

### Rule Structure

The main `ip tunnelvision` table has three chains:

**INPUT chain** (policy: DROP):
```
1. Loopback                              → accept
2. Established/related connections        → accept
3. VPN tunnel interface (wg0/tun0)        → accept
4. VPN handshake from endpoint            → accept
5. VPN input ports (configurable)         → accept
6. WebUI from allowed networks            → accept (if qBt enabled)
7. API from allowed networks              → accept
8. DNS from allowed networks              → accept (if DNS enabled)
9. HTTP/SOCKS/Shadowsocks proxies         → accept (if enabled)
10. ICMP utilities                        → accept
```

**OUTPUT chain** (policy: DROP, postrouting hook):
```
1. Loopback                              → accept
2. All traffic through VPN interface      → accept
3. VPN handshake TO endpoint              → accept (must exit via eth0, not wg0!)
4. Outbound bypass subnets               → accept (if configured)
5. Service responses to allowed networks  → accept
6. ICMP                                   → accept
```

**FORWARD chain** (policy: DROP):
```
1. Outbound through VPN                  → accept
2. Established return from VPN            → accept
```

### Allowed Networks

The `allowed_networks` nftables set determines which source IPs can access the WebUI, API, and proxy services:

```
set allowed_networks {
    type ipv4_addr
    flags interval
    elements = { 192.168.0.0/16, 172.16.0.0/12, 10.0.0.0/8 }
}
```

Default covers all RFC 1918 private ranges (Docker bridge, LAN, VPN subnet).

### Route Management

When `wg-quick up wg0` runs, it sets the default route to `wg0` (metric 0). Docker's `eth0` becomes secondary. Without intervention, all responses — including WebUI responses to the browser — would route through the VPN tunnel and never reach the host.

The killswitch fixes this by adding explicit routes for allowed networks through the original gateway:

```bash
ip route add 172.16.0.0/12 via 172.17.0.1 dev eth0
ip route add 192.168.0.0/16 via 172.17.0.1 dev eth0
ip route add 10.0.0.0/8 via 172.17.0.1 dev eth0
```

### Customization

Three environment variables allow advanced firewall tuning:

- `FIREWALL_VPN_INPUT_PORTS` — open ports on the VPN interface (e.g., `6881,6889-6899` for torrenting)
- `FIREWALL_OUTBOUND_SUBNETS` — subnets that bypass the VPN entirely (e.g., a local NAS at `192.168.100.0/24`)
- `FIREWALL_CUSTOM_RULES_FILE` — path to an nftables rules file loaded after the base table

---

## 6. Life of a Packet

### Outbound: qBittorrent → Tracker

```
1. qBittorrent sends TCP packet to tracker (8.8.8.8:443)

2. Kernel routing table:
   - Default route: 0.0.0.0/0 via wg0 (metric 0)
   - No more-specific route for 8.8.8.8
   → Route through wg0

3. nftables OUTPUT chain:
   - "oifname wg0 accept" → PASS

4. WireGuard interface (wg0):
   - AllowedIPs = 0.0.0.0/0 → packet matches
   - Encrypt with peer's public key
   - Wrap in UDP: src=container, dst=45.76.34.12:51820

5. Kernel routing (outer UDP packet):
   - Destination 45.76.34.12 has no wg0 route (fwmark routing)
   - Falls through to Docker bridge: eth0 via 172.17.0.1

6. nftables OUTPUT chain (second pass, outer packet):
   - "ip daddr 45.76.34.12 udp dport 51820 accept" → PASS

7. Docker bridge → host → ISP → VPN server

8. VPN server decrypts, forwards to 8.8.8.8
```

### Inbound: Tracker → qBittorrent

```
1. VPN server encrypts response, sends to container wg0

2. nftables INPUT chain:
   - "iifname wg0 accept" → PASS

3. WireGuard decrypts, delivers TCP response to qBittorrent
```

### WebUI Access: Host → Container

```
1. Browser: http://localhost:8080 → Docker forwards to container:8080

2. nftables INPUT chain:
   - Source 172.17.0.1 matches allowed_networks set
   - "ip saddr @allowed_networks tcp dport 8080 accept" → PASS

3. qBittorrent responds

4. nftables OUTPUT chain:
   - "ip daddr @allowed_networks tcp sport 8080 accept" → PASS
   - Route: 172.17.0.0/12 via 172.17.0.1 dev eth0 (explicit route)
   → Response goes through Docker bridge, NOT through wg0
```

### DNS Resolution

When `DNS_ENABLED=true`:
- `/etc/resolv.conf` points to `127.0.0.1`
- The built-in DNS server handles queries (DoT upstream, blocklists, caching)
- DNS traffic from qBittorrent → local DNS → DoT upstream through VPN tunnel

When `DNS_ENABLED=false`:
- `/etc/resolv.conf` points to the VPN provider's DNS (e.g., Mullvad's `10.64.0.1`)
- DNS queries go through the VPN tunnel like any other traffic

---

## 7. VPN Connection Pipeline

The connection pipeline handles everything from "user clicks Connect" to "tunnel is up with firewall rules updated."

### Two Paths

**Path A — API Providers** (Mullvad, PIA, Proton, NordVPN, etc.):

```
POST /vpn/connect { country: "CH" }
  ↓
connect_to_server()
  ↓
_connect_provider():
  1. provider.list_servers(filter=ServerFilter(country="CH"))
  2. _select_server(servers)  — score by load×0.7 + speed×0.3, pick from top tier
  3. provider.resolve_connect(server, config)  — key exchange (PIA) or static key (Mullvad)
  4. Write /config/wireguard/wg0.conf:
     [Interface]
     PrivateKey = <key>
     Address = 10.66.0.42/32
     DNS = 10.64.0.1
     [Peer]
     PublicKey = <server_pubkey>
     Endpoint = 185.220.101.45:51820
     AllowedIPs = 0.0.0.0/0
  5. _reconnect_vpn("wireguard")
  6. provider.post_connect()  — start port forwarding if applicable
```

**Path B — Config File Rotation** (Custom, OpenVPN-only providers):

```
POST /vpn/connect
  ↓
list_config_files()  — scan /config/wireguard/*.conf + /config/openvpn/*.ovpn
  ↓
Pick random config
  ↓
_reconnect_vpn(vpn_type)
```

### The Critical Config Sync

The most important implementation detail in the reconnect path is the **wg0.conf two-path synchronization** (fixed in v3.4.0).

Two separate locations hold the WireGuard config:
- `/config/wireguard/wg0.conf` — where the API writes new configs (persistent volume)
- `/etc/wireguard/wg0.conf` — where `wg-quick` reads from (OpenRC standard)

`init-vpn.sh` syncs these once at boot. But when the API writes a new config during rotation, `wg-quick up wg0` would read the stale copy from `/etc/wireguard/`. The fix:

```python
# In _reconnect_vpn(), BEFORE wg-quick up:
if WG_CONF_PATH.exists():
    shutil.copy2(WG_CONF_PATH, WG_RUNTIME_CONF)
    os.chmod(WG_RUNTIME_CONF, 0o600)
```

After `wg-quick up`, the killswitch is re-run so nftables knows the new endpoint:

```python
subprocess.run([str(SCRIPT_KILLSWITCH)], capture_output=True)
```

This is essential because the killswitch reads the endpoint from `wg show wg0 endpoints` — if the endpoint changed, the old nftables rules would block the new VPN handshake.

### WireGuard vs OpenVPN

| Aspect | WireGuard | OpenVPN |
|--------|-----------|---------|
| Interface | `wg0` | `tun0` |
| Config path | `/config/wireguard/wg0.conf` | `/config/openvpn/provider.ovpn` |
| Credentials | WireGuard keypairs | `/config/openvpn/credentials.txt` |
| Startup | `wg-quick up wg0` (sync, ~1s) | `openvpn --daemon` (async, poll tun0 for 30s) |
| Health check | Handshake age (`wg show wg0 latest-handshakes`) | Interface existence (`ip link show tun0`) |
| Endpoint extraction | `wg show wg0 endpoints` | `grep ^remote config.ovpn` |
| Config sync needed | Yes (two-path) | No (daemon reads directly) |

---

## 8. Provider System & Auto-Discovery

### Architecture

Every VPN provider is a Python class that implements the `VPNProvider` base class and declares a `ProviderMeta` dataclass:

```python
@dataclass
class ProviderMeta:
    id: str                        # "mullvad"
    display_name: str              # "Mullvad VPN"
    description: str               # Shown in wizard
    setup_type: SetupType          # ACCOUNT, PASTE, or SIDECAR
    supports_server_list: bool
    supports_account_check: bool
    supports_port_forwarding: bool
    supports_wireguard: bool
    supports_openvpn: bool
    credentials: list[CredentialField]
    default_dns: str
    filter_capabilities: list[str]  # ["country", "city", "owned_only"]
```

### Auto-Discovery via pkgutil

Providers are discovered at import time — no manual registration required:

```python
# api/services/vpn.py
def _discover_providers() -> dict[str, type[VPNProvider]]:
    package = importlib.import_module("api.services.providers")
    for _, module_name, _ in pkgutil.iter_modules(package.__path__):
        if module_name == "base": continue
        mod = importlib.import_module(f"api.services.providers.{module_name}")
        for attr_name in dir(mod):
            cls = getattr(mod, attr_name)
            if isinstance(cls, type) and issubclass(cls, VPNProvider) and cls is not VPNProvider:
                meta = cls.get_meta()
                providers[meta.id] = cls
    return providers
```

Drop a new `.py` file in `api/services/providers/`, implement `VPNProvider`, and it's automatically available in the API, setup wizard, and settings panel.

### The 25 Providers

| Wave | Providers | Notes |
|------|-----------|-------|
| Core | mullvad, ivpn, pia, proton, custom, gluetun | Custom = BYO config; Gluetun = sidecar |
| Wave 1 | nordvpn, windscribe, airvpn, surfshark, expressvpn | Full WireGuard + server lists |
| Wave 2 | ipvanish, torguard, privatevpn, perfectprivacy, cyberghost | PP + CG are OVPN-only |
| Wave 3 | privado, purevpn, vpnsecure, vpnunlimited, vyprvpn, fastestvpn, hidemyass, slickvpn, giganews | 4 OVPN-only |

**OVPN-only providers** (6): perfectprivacy, cyberghost, vpnsecure, vyprvpn, hidemyass, giganews — these have `supports_wireguard=False` and use `SetupType.PASTE` (user downloads config from provider portal).

### Provider Capabilities

**resolve_connect()** — How credentials become a running tunnel:
- **Mullvad, IVPN, NordVPN:** Static WireGuard keypair. User registers public key with provider, private key stored in config. `resolve_connect()` just reads the stored key and builds PeerConfig.
- **PIA:** Ephemeral key exchange per connection. Authenticates with username/password, gets token, generates fresh `wg genkey`/`wg pubkey`, exchanges public key with server via `POST /addKey`. Server responds with its public key + assigned IP.
- **Proton:** Similar to PIA but with feature-bitmask server metadata (SECURE_CORE, TOR, P2P, STREAMING, PORT_FORWARD).

**post_connect()** — Actions after tunnel is up:
- **PIA:** Starts port forwarding service (getSignature + bindPort loop every 15 minutes)
- **Proton:** Starts NAT-PMP port forwarding (raw UDP to gateway:5351)
- **Others:** No-op

### Server Data & Caching

Server lists are cached per-provider instance (singleton pattern) with a 1-hour TTL (`PROVIDER_CACHE_TTL = 3600`). The cache stores the unfiltered list; filtering happens on every call. PIA auth tokens are cached for 12 hours (`PIA_TOKEN_CACHE_TTL = 43200`).

---

## 9. Smart Server Selection & Rotation

### Scoring Algorithm

```python
def _score(server: ServerInfo) -> float:
    load_pct = server.load if server.load and server.load > 0 else 50
    load_score = 1.0 - (load_pct / 100.0)          # 0-100% → 1.0-0.0
    speed_score = min((server.speed_gbps or 0) / 20.0, 1.0)  # 0-20 Gbps → 0.0-1.0
    return load_score * 0.7 + speed_score * 0.3     # Load: 70%, Speed: 30%
```

Key decisions:
- **Load = 0 or None treated as 50** (unknown, not "best"). A server reporting 10% load always beats an unknown-load server.
- **Top-tier pool:** Best 20% of candidates (min 5, max 25). Random pick from this pool prevents alphabetical bias and distributes traffic.
- **Exclude hostname:** Rotation passes `exclude_hostname=current` to avoid reconnecting to the same server.

### Geographic Diversity in Rotation

Without intervention, rotation always picks the globally highest-scoring country (e.g., Netherlands for Mullvad). The two-stage rotation fix (v3.4.7):

```python
# Stage 1: Pick random country (excluding current)
if not country_filter and not city_filter:
    current_country = find_country_of(current_server)
    countries = all_countries - {current_country}
    random_country = random.choice(countries)

# Stage 2: Score-select within that country
connect(country=random_country, exclude_hostname=current_server)
```

When a country or city filter IS set, rotation stays within the filter and just excludes the current server.

---

## 10. Watchdog: Self-Healing State Machine

The watchdog monitors VPN health and automatically reconnects when the tunnel drops.

### State Machine

```
IDLE
 │ (VPN enabled, 10s startup delay)
 ▼
MONITORING ←──────────────────────────┐
 │ (health check every 15s)            │
 │                                     │
 │ failure detected                    │ success
 ▼                                     │
DEGRADED ──────────────────────────────┘
 │ (1-2 consecutive failures,
 │  waiting to confirm)
 │
 │ threshold reached (3 failures)
 ▼
RECONNECTING
 │ (wg-quick down + up current config)
 ├─ success → MONITORING
 │
 │ failure
 ▼
FAILING_OVER
 │ (cycle through alternate config files)
 ├─ one succeeds → MONITORING
 │
 │ all exhausted
 ▼
COOLDOWN
 │ (pause qBittorrent, wait 5 minutes)
 │ (tried_configs cleared, counters reset)
 └─→ MONITORING
```

### Health Checks

**WireGuard:** Parses `wg show wg0 latest-handshakes`. If the handshake timestamp is older than `HANDSHAKE_STALE_SECONDS` (180s default), the tunnel is considered unhealthy. A timestamp of 0 means no handshake has ever occurred.

**OpenVPN:** Checks if `tun0` interface exists via `ip link show tun0`. Simpler than WireGuard because OpenVPN doesn't expose handshake metadata.

**Sidecar (Gluetun):** Read-only HTTP check to `gluetun_url/v1/openvpn/status`. The watchdog can detect outages but cannot reconnect — Gluetun manages the tunnel externally.

### Hot-Reloadable Tuning

All watchdog parameters are re-read from the YAML settings file on every tick:

| Setting | Default | Effect |
|---------|---------|--------|
| `health_check_interval` | 15s | How often to check |
| `handshake_stale_seconds` | 180s | WireGuard handshake age threshold |
| `reconnect_threshold` | 3 | Consecutive failures before action |
| `cooldown_seconds` | 300s | Wait time after all configs fail |
| `auto_reconnect` | true | Enable/disable autonomous recovery |

### Integrations

On every state transition, the watchdog:
1. **Broadcasts SSE event** — UI updates in real-time
2. **Publishes MQTT state** — Home Assistant sees changes
3. **Logs to connection history** — persisted to `/config/connection-history.json`
4. **Sends webhook notification** — Discord, Slack, Gotify (on `vpn_down` and `vpn_recovered`)
5. **Pauses qBittorrent** — during COOLDOWN state, prevents traffic from leaking

---

## 11. The API Layer

### FastAPI Application (`api/main.py`)

The application is organized around a lifespan context manager:

**Startup:**
1. Load `Config` from environment (frozen dataclass, immutable)
2. Initialize `StateManager` (typed accessors for `/var/run/tunnelvision/*` files)
3. Start background services: MQTT, Watchdog, HTTP Proxy, SOCKS Proxy, Shadowsocks, Server List Updater
4. Mount 14 route modules + metrics endpoint

**Shutdown:**
Stop all services in reverse order (graceful).

**Middleware:**
- CORS: Allows all origins (container is behind Docker networking)
- Auth: Layered check on every request — proxy header → API key → session cookie. Exempts `/api/v1/auth/`, `/api/v1/setup/`, docs, metrics, static assets.

### Route Modules

All routes are mounted at `/api/v1`:

| Module | Key Endpoints | Purpose |
|--------|---------------|---------|
| `auth` | `POST /auth/login`, `GET /auth/me` | Session-based auth (7-day cookies) |
| `health` | `GET /health` | System health + watchdog snapshot |
| `vpn` | `GET /vpn/status`, `GET /vpn/history` | VPN state, connection history |
| `qbt` | `GET /qbt/status` | qBittorrent speeds, torrents |
| `system` | `GET /system` | Versions, uptimes |
| `config` | `GET /config` | Safe config subset (no secrets) |
| `provider` | `GET /vpn/servers`, `GET /vpn/provider-health` | Provider APIs, server lists |
| `setup` | `POST /setup/verify`, `POST /setup/complete` | First-run wizard |
| `connect` | `POST /vpn/connect`, `POST /vpn/rotate` | Server selection & connection |
| `control` | `POST /vpn/disconnect`, `POST /killswitch/enable` | VPN & firewall control |
| `settings` | `GET /settings`, `PUT /settings` | Configuration management |
| `speedtest` | `POST /vpn/speedtest` | 10MB download test through VPN |
| `backup` | `GET /backup`, `POST /restore` | Config export/import (tar.gz) |
| `events` | `GET /events` | SSE stream |
| `metrics` | `GET /metrics` (root) | Prometheus text exposition |

### Pydantic Models

All API responses use typed Pydantic models (`api/models.py`):
- `HealthResponse` — healthy, setup_required, per-service states, watchdog snapshot
- `VPNStatusResponse` — state, IPs, location, transfer stats, killswitch, forwarded_port
- `QBTStatusResponse` — speeds, torrent counts, version
- `SystemResponse` — versions (Alpine, qBt, WireGuard, Python), uptimes

### Authentication

Three auth methods, checked in order by middleware:

1. **Proxy header** (`auth_proxy_header`): Trusted reverse proxy sets a header (e.g., `X-Forwarded-User`). If present and matches, auth passes.
2. **API key** (`api_key`): Header `X-API-Key` matches configured key. Used for programmatic access.
3. **Session cookie** (`tv_session`): 7-day session from `POST /auth/login` with username + password.

If none configured, all endpoints are open (single-user container use case).

### Prometheus Metrics

```
tunnelvision_vpn_up                    # 0 or 1
tunnelvision_vpn_connected_seconds     # gauge
tunnelvision_killswitch_active         # 0 or 1
tunnelvision_public_ip_info            # gauge with ip/country/city labels
tunnelvision_transfer_rx_bytes_total   # counter
tunnelvision_transfer_tx_bytes_total   # counter
tunnelvision_healthy                   # 0 or 1
tunnelvision_dns_queries_total         # counter (if DNS enabled)
tunnelvision_dns_blocked_total         # counter
```

---

## 12. Configuration System

TunnelVision has a layered configuration system with three sources, checked in priority order:

### Precedence Hierarchy

```
1. YAML file (/config/tunnelvision.yml)     ← highest priority
2. Docker secret file ({ENV}_SECRETFILE)     ← for secrets only
3. Environment variable ({ENV})
4. Hardcoded default (constants.py)          ← lowest priority
```

### Config vs Settings

Two distinct concepts:

**Config** (`api/config.py`): Frozen dataclass loaded once at startup from environment variables. Immutable during a container run. Contains all 80+ configuration fields.

**Settings** (`api/services/settings.py`): YAML-backed store that can be modified at runtime via the API. The `CONFIGURABLE_FIELDS` dictionary defines 120+ fields with metadata:

```python
CONFIGURABLE_FIELDS = {
    "vpn_provider": {"env": "VPN_PROVIDER", "default": "custom", "secret": False},
    "wireguard_private_key": {"env": "WIREGUARD_PRIVATE_KEY", "default": "", "secret": True},
    "health_check_interval": {"env": "HEALTH_CHECK_INTERVAL", "default": "15", "secret": False},
    # ... 100+ more
}
```

Provider credential fields are auto-merged from provider metadata — new providers automatically expose their credentials in the settings panel without code changes.

### Hot-Reload

14 fields take effect immediately without container restart:

```
auto_reconnect, health_check_interval, handshake_stale_seconds,
reconnect_threshold, cooldown_seconds, vpn_country, vpn_city,
notify_webhook_url, notify_gotify_url, notify_gotify_token,
dns_block_ads, dns_block_malware, dns_block_surveillance
```

The watchdog and DNS services re-read settings from YAML on every tick. All other changes require a container restart.

### Docker Secrets

For sensitive values, use the `{ENV}_SECRETFILE` pattern:

```yaml
# docker-compose.yml
environment:
  PIA_PASS_SECRETFILE: /run/secrets/pia_password
secrets:
  pia_password:
    file: ./pia_password.txt
```

The settings loader checks `{ENV}_SECRETFILE` first, reads the file content, and uses it as the value.

---

## 13. Setup Wizard

First-boot experience: when no VPN config is found, the container enters setup mode.

### Detection

`init-vpn.sh` writes `setup_required=true` → health endpoint returns `setup_required: true` → React app renders the wizard instead of the dashboard.

### Wizard Flow

```
Welcome → Provider Selection → Credentials/Config → Server Pick → Verify → Complete
```

The flow adapts based on provider type:

**Account providers (Mullvad, IVPN, PIA, etc.):**
1. Enter credentials (private key + address, or username + password)
2. Pick server from filterable table
3. Verify connection (temporary tunnel up, check public IP)
4. Complete

**OVPN-only providers (CyberGhost, Perfect Privacy, etc.):**
1. Paste OpenVPN config + optional credentials
2. Verify connection
3. Complete

**Gluetun sidecar:**
1. Enter Gluetun URL + optional API key
2. Validate connectivity
3. Complete (no VPN config needed locally)

### Key Generation

For Mullvad and IVPN, the wizard can generate WireGuard keypairs in-container:

```
POST /api/v1/setup/generate-keypair
→ { private_key: "...", public_key: "..." }
```

Uses `wg genkey` and `wg pubkey`. The user copies the public key to their provider's portal, then enters the assigned address.

### Verification

The verify step temporarily brings up the VPN tunnel, checks the public IP via geo-IP services, then tears it down:

**WireGuard:** `wg-quick up wg0` → check ipwho.is → `wg-quick down wg0`

**OpenVPN:** `openvpn --daemon` → poll for tun0 (30s) → check ipwho.is → kill daemon

### Completion

`POST /setup/complete`:
1. Persists provider + vpn_type to YAML
2. Sets `setup_required = false`
3. Signals s6 to restart services
4. UI reloads to dashboard

---

## 14. Services Layer

### StateManager (`api/services/state.py`)

The single source of truth for runtime state. Every file in `/var/run/tunnelvision/` is accessed through typed properties:

```python
class StateManager:
    @property
    def vpn_state(self) -> str: return self.read("vpn_state", "unknown")

    @vpn_state.setter
    def vpn_state(self, value: str): self.write("vpn_state", value)

    # Properties for: vpn_type, vpn_ip, vpn_endpoint, vpn_server_hostname,
    # last_handshake, public_ip, country, city, rx_bytes, tx_bytes,
    # killswitch_state, setup_required, watchdog_state, forwarded_port, ...
```

**Why files instead of a Python object?** Multi-process compatibility (DNS runs as a separate s6 process), visibility from shell scripts and monitoring tools, atomic writes with no race conditions.

### DNS Service (`api/services/dns.py`, 1,388 lines)

A standalone DNS server running as a separate s6 process:

- **DNSServer** — UDP listener on `:53`, query pipeline: blocklist → cache → upstream
- **DNSResolver** — Upstream resolution via DNS-over-TLS (Cloudflare default) or plain UDP
- **DNSCache** — TTL-aware LRU cache (4096 entries default)
- **BlocklistManager** — Downloads StevenBlack/URLhaus hosts files, provides O(1) domain lookup, refreshes every 24h

Three blocklist categories (toggleable via settings):
- `dns_block_ads` — advertising domains
- `dns_block_malware` — malware/phishing domains
- `dns_block_surveillance` — tracking/surveillance domains

Stats written to state files every 60s: `dns_queries_total`, `dns_cache_hits`, `dns_blocked_total`.

### HTTP CONNECT Proxy (`api/services/http_proxy.py`)

RFC 7231 CONNECT tunnel on `:8888` (default). Routes non-Docker clients through the VPN:

1. Client sends `CONNECT host:port HTTP/1.1`
2. Optional basic auth validation
3. Proxy opens upstream connection through VPN tunnel
4. Returns `HTTP/1.1 200 Connection Established`
5. Bidirectional byte relay until either side closes

### SOCKS5 Proxy (`api/services/socks_proxy.py`)

RFC 1928 SOCKS5 on `:1080` (default):

1. Method negotiation (no auth or username/password)
2. Authentication (RFC 1929, if credentials configured)
3. CONNECT request with address type (IPv4, domain, IPv6)
4. Bidirectional relay

### Shadowsocks AEAD (`api/services/shadowsocks.py`)

Encrypted proxy on `:8388` (default). Supports `aes-256-gcm` and `chacha20-ietf-poly1305`:

- **Key derivation:** EVP_BytesToKey (MD5) → HKDF-SHA1 with "ss-subkey" info label
- **AEADCipher:** Stateful encryptor with nonce counter (12-byte, little-endian, incremented per chunk)
- **Protocol:** Salt (16 bytes) + encrypted length (2 bytes + 16-byte tag) + encrypted payload (N bytes + 16-byte tag)
- **Relay:** Decrypt client→target, encrypt target→client, concurrent bidirectional tasks

### MQTT Service (`api/services/mqtt.py`)

Home Assistant integration via MQTT discovery:

**Auto-discovery entities:**
- Binary sensors: VPN connectivity, Killswitch shield, Health
- Sensors: Public IP, Country, City, VPN State, RX/TX bytes, Active Config
- Buttons: VPN Restart/Rotate/Disconnect, qBt Restart/Pause/Resume
- Switch: Killswitch toggle

**Command handling:** Subscribes to `{prefix}/command`, maps commands to action functions:
- `vpn_restart`, `vpn_disconnect`, `vpn_rotate`
- `killswitch_enable`, `killswitch_disable`
- `qbt_restart`, `qbt_pause`, `qbt_resume`

Commands execute via `asyncio.run_coroutine_threadsafe()` (MQTT runs in a background thread, bridged to the async FastAPI event loop).

### Port Forwarding

**PIA** (`api/services/port_forward.py`):
1. `GET /getSignature?token=<token>` — returns base64 payload + signature with assigned port
2. `GET /bindPort?payload=&signature=` — keep-alive every 15 minutes
3. Port written to state, hook script fired

**Proton** (`api/services/natpmp.py`):
- Raw UDP to gateway:5351 (RFC 6886)
- 12-byte request → 16-byte response with external port
- Refreshed every 45 seconds (60s lifetime)

### Notifications (`api/services/notifications.py`)

Webhook dispatch on VPN events:
- **Discord:** Embed JSON format
- **Slack:** `{text: ...}` payload
- **Gotify:** `POST /message?token=<token>` with priority (8 for vpn_down, 4 for others)
- **Generic:** Full event JSON payload

Non-blocking — errors logged but never raised.

---

## 15. React Frontend

### Stack

React 19, TypeScript 5.6, Vite 6, Tailwind CSS 4 (OKLCH design tokens).

No state management library — purely React hooks (`useState`, `useMemo`, custom `usePoll` and `useSSE`).

### Component Tree

```
App.tsx
 ├── Login               (username/password form)
 └── Dashboard
      ├── VPNStatus       (state, IP, location, transfer stats, controls)
      ├── HealthCard       (per-service health, watchdog state)
      ├── ProviderHealthCard (API latency, cache age, account expiry)
      ├── ConfigManager    (multi-config radio selector)
      ├── QBTStatus        (speeds, torrent counts)
      ├── SystemInfo       (versions, uptimes)
      ├── ConnectionHistory (event timeline, collapsible)
      ├── ServerBrowser    (modal: filterable server table, connect action)
      ├── SettingsPanel    (modal: 16 collapsible groups, hot-reload indicators)
      └── SetupWizard      (5-step first-boot flow)
```

### Data Flow

```
useSSE() ──→ invalidateCache() ──→ increment sseRefresh signal
                                        │
usePoll(fetcher, interval, sseRefresh) ──┘
  │
  └── fetch → 5s GET cache → dedup inflight → response
```

- SSE is the real-time path (instant UI updates on VPN events)
- 10s poll is the safety net (catches anything SSE misses)
- `usePoll` is visibility-aware — pauses when the tab is hidden

### Settings Panel

16 collapsible field groups covering all 120+ configurable fields:

| Group | Example Fields |
|-------|----------------|
| VPN | vpn_enabled, vpn_type, vpn_provider, vpn_country, killswitch_enabled |
| Authentication | admin_user, admin_pass, auth_proxy_header |
| DNS | dns_enabled, dns_upstream, dns_block_ads/malware/surveillance |
| Watchdog | health_check_interval, handshake_stale_seconds, reconnect_threshold |
| MQTT | mqtt_enabled, mqtt_broker, mqtt_port, mqtt_topic_prefix |
| Shadowsocks | shadowsocks_enabled, shadowsocks_port, shadowsocks_password |

Field types: text, password, number, toggle switch. Each field shows its environment variable name and an indicator: lightning bolt for hot-reload, refresh icon for requires-restart.

### Design System

Dark theme with OKLCH color tokens:
- **Primary:** Amber (tunnel highlight)
- **Accent:** Cyan (data/info)
- **Status:** Green (up), Red (down), Yellow (warning), Gray (disabled)
- **Surfaces:** 4 elevation levels (10%–25% lightness)
- **Typography:** System sans-serif, monospace for values (Cascadia Code / Fira Code)

---

## 16. SSE Real-Time Architecture

### Server Side (`api/routes/events.py`)

```python
_clients: list[asyncio.Queue] = []

def broadcast(event: str, data: dict):
    """Push event to all connected SSE clients. Non-blocking."""
    message = {"event": event, "data": data, "timestamp": utcnow()}
    for queue in _clients:
        try:
            queue.put_nowait(message)  # Never awaits — safe from any context
        except asyncio.QueueFull:
            pass  # Slow client drops events (queue size 50)
```

The SSE endpoint (`GET /events`) is an async generator that yields from the client's queue with a 30-second keepalive timeout.

### Client Side (`ui/src/lib/use-sse.ts`)

```typescript
useSSE(onEvent: () => void): void
```

- Connects to `/api/v1/events` via `EventSource`
- Listens to: `vpn_status`, `vpn_state`, `watchdog_recovered`, `watchdog_reconnecting`, `watchdog_failover`, `watchdog_degraded`, `watchdog_cooldown`
- On any event: invalidates API cache (5s TTL), increments `sseRefresh` signal
- Exponential backoff reconnect: 2s → 30s max

### Event Flow

```
Watchdog detects VPN drop
  → broadcast("watchdog_degraded", {failures: 2, threshold: 3})
    → SSE queue per client
      → EventSource receives event
        → invalidateCache("/api/v1/vpn/status", "/api/v1/health")
          → sseRefresh++ triggers usePoll re-fetch
            → UI re-renders with fresh data
```

---

## 17. Testing & Quality Gates

### Test Suite: 734 Tests

28 test files covering every layer:

**Architecture Guardrails (`test_dry.py`):**
- `TestNoRawHttpx` — all HTTP clients must use `http_client()` from constants
- `TestNoHardcodedSubprocessTimeouts` — all timeouts use `SUBPROCESS_TIMEOUT_*` constants
- `TestNoHardcodedStateStrings` — routes use enums (`VpnState.UP`, not `"up"`)
- `TestNoHardcodedPaths` — filesystem paths from constants
- `TestNoHardcodedPortDefaults` — port defaults from constants
- `TestSettingsAlignment` — CONFIGURABLE_FIELDS ↔ SettingsUpdate ↔ Config stay in sync
- `TestNoHardcodedScriptPaths` — script paths use `SCRIPT_INIT_VPN`, `SCRIPT_KILLSWITCH`
- `TestNoHardcodedWgRuntimePaths` — `/etc/wireguard/` paths use `WG_RUNTIME_*`

**s6 Service Graph (`test_s6_service_graph.py`):**
- Pure filesystem validation (no s6 binaries needed)
- Validates all dependencies.d and contents.d references resolve to real services
- Catches dangling references after renames (e.g., `init-wireguard` → `init-vpn`)
- `S6_BUILTINS = {"base"}`, `S6_BUNDLES = {"user"}`

**Provider Parametrized Tests (`test_providers.py`):**
- `@pytest.mark.parametrize("provider_id", PROVIDER_IDS)` — all 25 providers tested:
  - Meta completeness (id, display_name, description, setup_type, credentials)
  - Secret credentials use password field_type
  - Filter capabilities valid
  - Interface compliance (VPNProvider methods)

**Smart Selection (`test_smart_selection.py`):**
- Prefers low load, higher speed
- Excludes current server, falls back if only option
- Picks from top tier only when scores differ
- Unknown load (0) treated as 50

**Rotation Diversity (`test_rotate_diversity.py`):**
- Random country selection (excluding current)
- Country/city filter compliance

**Reconnect Sync (`test_reconnect_sync.py`):**
- Config synced to `/etc/wireguard/` before every `wg-quick up`
- Sync happens before, not after
- No sync for OpenVPN (daemon reads config directly)

### Test Patterns

- **Fixtures:** Per-module `@pytest.fixture(autouse=True)` with `tmp_path` for StateManager
- **Mocking:** `MagicMock`/`AsyncMock` for providers, services, subprocesses
- **TestClient:** FastAPI's TestClient for API endpoint testing
- **No global conftest:** Each module is self-contained

---

## 18. CI/CD Pipeline

### 5-Job Pipeline

```
lint ──────┐
            ├──→ build ──→ scan ──→ smoke
test ──────┘
```

**lint** (8 tools):
1. **Ruff** — Python linting (`ruff check api/`)
2. **Bandit** — Security analysis (`bandit -r api/ -lll -q`, high severity)
3. **mypy** — Type checking with pydantic plugin (`mypy api/`)
4. **ShellCheck** — Bash linting for all s6 scripts
5. **pip-audit** — Python dependency CVE scanning
6. **Hadolint** — Dockerfile best practices (threshold: warning)
7. **npm audit** — JavaScript dependency vulnerabilities (threshold: high)
8. (ShellCheck is tool 4, not 8 — 7 tools total, but ShellCheck covers multiple scripts)

**test** — `pytest tests/ -q --tb=short` (734 tests)

**build** — Multi-arch Docker build (amd64, arm64, arm/v7) with GHA cache, pushed to `ghcr.io`. Cosign keyless signing via Sigstore OIDC — every image has cryptographic provenance.

**scan** — Trivy container image scan for CRITICAL/HIGH CVEs (exit-code 1 = fail).

**smoke** — Deploy container with `VPN_ENABLED=false`, `QBT_ENABLED=false`, verify:
- `/api/v1/health` — all expected keys present, `api=running`
- `/api/v1/system` — version field exists
- `/` — UI served as static files

### Supply Chain Security

Every non-PR image is signed with cosign (keyless, Sigstore OIDC):

```bash
cosign verify \
  --certificate-identity-regexp="github.com/jasondostal/tunnelvision" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  ghcr.io/jasondostal/tunnelvision:latest
```

No keys to manage. The signature proves: this image was built by this GitHub Actions workflow, from this repository, at this commit.

---

## 19. Security Model

### Defense in Depth

1. **Firewall-first boot:** nftables DROP rules applied BEFORE VPN handshake
2. **IPv6 total block:** Separate table at priority -1, all hooks, all chains
3. **Default DROP policy:** Every allowed path is an explicit rule
4. **VPN endpoint pinning:** Killswitch only allows traffic to the specific VPN server IP:port
5. **Route isolation:** LAN traffic routes through Docker bridge, not VPN tunnel
6. **Config file permissions:** `0o600` on all WireGuard/OpenVPN configs
7. **Secret masking:** Settings API returns `"********"` for secret fields
8. **Docker secrets:** `{ENV}_SECRETFILE` pattern for Kubernetes/Swarm secret injection
9. **Credential validation:** Keys validated (base64, 32 bytes) before saving to disk
10. **Signed images:** Cosign keyless signing with Sigstore OIDC provenance

### Auth Layers

- Proxy header bypass (trusted reverse proxy)
- API key (programmatic access)
- Session cookie (7-day, browser)
- Auth middleware exempts setup and auth endpoints only

### What's NOT Encrypted at Rest

- `/config/tunnelvision.yml` contains credentials in plaintext YAML
- WireGuard private keys are stored in plaintext in `wg0.conf`
- This is standard for Docker containers — the security boundary is the container filesystem

---

## 20. Appendix: File Map

### Python Backend

```
api/
├── __init__.py              # __version__
├── main.py                  # FastAPI app, lifespan, middleware, router mounting
├── config.py                # Frozen Config dataclass from env vars
├── constants.py             # ALL paths, ports, timeouts, enums, state strings
├── models.py                # Pydantic response models
├── auth.py                  # Session store, auth check logic
├── routes/
│   ├── auth.py              # Login/logout/me
│   ├── health.py            # /health
│   ├── system.py            # /system
│   ├── vpn.py               # /vpn/status, /vpn/history, /vpn/ip
│   ├── qbt.py               # /qbt/status
│   ├── connect.py           # /vpn/connect, /vpn/rotate, /vpn/reconnect
│   ├── control.py           # /vpn/disconnect, /killswitch/*, /qbt/*
│   ├── provider.py          # /vpn/servers, /vpn/provider-health, /vpn/account
│   ├── setup.py             # /setup/* (wizard)
│   ├── settings.py          # /settings GET/PUT
│   ├── config.py            # /config (safe subset)
│   ├── speedtest.py         # /vpn/speedtest
│   ├── backup.py            # /backup, /restore
│   ├── events.py            # /events (SSE)
│   └── metrics.py           # /metrics (Prometheus)
├── services/
│   ├── state.py             # StateManager — /var/run/tunnelvision/* accessors
│   ├── settings.py          # CONFIGURABLE_FIELDS, load/save YAML
│   ├── watchdog.py          # Self-healing state machine
│   ├── dns.py               # DNS server (DoT, blocklists, cache)
│   ├── http_proxy.py        # HTTP CONNECT proxy
│   ├── socks_proxy.py       # SOCKS5 proxy
│   ├── shadowsocks.py       # Shadowsocks AEAD proxy
│   ├── mqtt.py              # MQTT + HA discovery
│   ├── port_forward.py      # PIA port forwarding
│   ├── natpmp.py            # Proton NAT-PMP port forwarding
│   ├── notifications.py     # Webhook dispatch
│   ├── vpn.py               # Provider discovery & registry
│   ├── history.py           # Connection event logging
│   ├── hooks.py             # Port change hook scripts
│   ├── speed_test.py        # Throughput measurement
│   └── providers/
│       ├── base.py          # VPNProvider base, ProviderMeta, ServerInfo, PeerConfig
│       ├── custom.py         # BYO config
│       ├── gluetun.py        # Sidecar mode
│       ├── mullvad.py        # Mullvad
│       ├── ivpn.py           # IVPN
│       ├── pia.py            # PIA (ephemeral keys, port forwarding)
│       ├── proton.py         # Proton (NAT-PMP, feature bitmask)
│       ├── nordvpn.py        # NordVPN
│       ├── windscribe.py     # Windscribe
│       ├── airvpn.py         # AirVPN
│       ├── surfshark.py      # Surfshark
│       ├── expressvpn.py     # ExpressVPN
│       ├── ipvanish.py       # IPVanish
│       ├── torguard.py       # TorGuard
│       ├── privatevpn.py     # PrivateVPN
│       ├── perfectprivacy.py # Perfect Privacy (OVPN-only)
│       ├── cyberghost.py     # CyberGhost (OVPN-only)
│       ├── privado.py        # Privado
│       ├── purevpn.py        # PureVPN
│       ├── vpnsecure.py      # VPN Secure (OVPN-only)
│       ├── vpnunlimited.py   # VPN Unlimited
│       ├── vyprvpn.py        # VyprVPN (OVPN-only)
│       ├── fastestvpn.py     # FastestVPN
│       ├── hidemyass.py      # HideMyAss (OVPN-only)
│       ├── slickvpn.py       # SlickVPN
│       └── giganews.py       # Giganews (OVPN-only)
```

### Frontend

```
ui/
├── package.json             # React 19 + Vite 6 + Tailwind 4
├── vite.config.ts           # Dev proxy to :8081, @/ alias
├── tsconfig.json
└── src/
    ├── main.tsx             # Entry point
    ├── App.tsx              # Root component + Dashboard
    ├── index.css            # OKLCH design tokens
    ├── lib/
    │   ├── api.ts           # Fetch client with 5s cache + dedup
    │   ├── types.ts         # TypeScript interfaces
    │   ├── utils.ts         # humanBytes, humanSpeed, humanDuration
    │   ├── use-poll.ts      # Visibility-aware polling hook
    │   └── use-sse.ts       # EventSource + reconnect hook
    └── components/
        ├── vpn-status.tsx
        ├── health-card.tsx
        ├── qbt-status.tsx
        ├── system-info.tsx
        ├── connection-history.tsx
        ├── provider-health-card.tsx
        ├── config-manager.tsx
        ├── server-browser.tsx
        ├── setup-wizard.tsx
        ├── settings-panel.tsx
        ├── login.tsx
        ├── status-badge.tsx
        └── logo.tsx
```

### Infrastructure

```
rootfs/etc/s6-overlay/
├── scripts/
│   ├── init-environment.sh
│   ├── init-firewall-pre.sh
│   ├── init-vpn.sh
│   ├── init-killswitch.sh
│   └── healthcheck.sh
└── s6-rc.d/
    ├── init-environment/    (oneshot, depends: base)
    ├── init-firewall-pre/   (oneshot, depends: base, init-environment)
    ├── init-vpn/            (oneshot, depends: base, init-environment, init-firewall-pre)
    ├── init-killswitch/     (oneshot, depends: base, init-vpn)
    ├── svc-api/             (longrun, depends: base, init-killswitch)
    ├── svc-dns/             (longrun, depends: base, init-killswitch)
    ├── svc-healthcheck/     (longrun, depends: base, init-vpn)
    ├── svc-qbittorrent/     (longrun, depends: base, init-killswitch)
    └── user/                (bundle, contains all services)

.github/workflows/
└── build.yml               # lint → test → build+sign → scan → smoke

tests/                       # 28 test files, 734 tests
Dockerfile                   # 3-stage multi-arch build
mypy.ini                     # Pydantic plugin config
.hadolint.yaml               # DL3029, DL3018 ignored
```

### Runtime State Files

```
/var/run/tunnelvision/
├── vpn_state                # "up", "down", "setup_required", "error"
├── vpn_type                 # "wireguard", "openvpn"
├── vpn_interface            # "wg0", "tun0"
├── vpn_ip                   # Tunnel IP (10.x.x.x)
├── vpn_endpoint             # Server IP:port
├── vpn_started_at           # ISO 8601 timestamp
├── vpn_server_hostname      # Selected server name
├── wg_implementation        # "kernel", "userspace"
├── public_ip                # Container's public IP
├── country, city            # Geolocation
├── organization             # ISP name
├── rx_bytes, tx_bytes       # WireGuard transfer stats
├── last_handshake           # Unix timestamp
├── killswitch_state         # "active", "disabled"
├── setup_required           # "true", "false"
├── healthy                  # "true", "false"
├── watchdog_state           # "monitoring", "degraded", etc.
├── forwarded_port           # Port number (PIA/Proton)
├── default_gateway          # Docker bridge gateway IP
├── default_interface        # Docker bridge interface
├── dns_queries_total        # DNS stat
├── dns_cache_hits           # DNS stat
├── dns_blocked_total        # DNS stat
└── openvpn.log, openvpn.pid # OpenVPN daemon files

/config/
├── tunnelvision.yml         # Persistent settings (YAML)
├── connection-history.json  # Event log
├── wireguard/
│   └── wg0.conf             # Active WireGuard config (0600)
├── openvpn/
│   ├── provider.ovpn        # Active OpenVPN config (0600)
│   └── credentials.txt      # OpenVPN auth (0600)
└── qBittorrent/             # qBt config directory
```

---

*This document covers TunnelVision v3.5.0. For the latest changes, see CHANGELOG.md.*
