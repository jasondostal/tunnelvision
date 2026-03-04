# Roadmap

What's coming. No promises on timelines — this is built for the love of blinkenlights.

## Next

- [ ] **Provider wave 3** — Privado, PureVPN, VPNSecure, VPN Unlimited, VyprVPN, FastestVPN, HideMyAss, SlickVPN, Giganews

## Future

- [ ] Smart server selection — lowest load, nearest geo, preferred region sticky, failover-aware
- [ ] Full OpenVPN parity — connect pipeline, server browser, setup wizard for OVPN-only providers
- [ ] Multi-architecture builds — armv6, armv7, i686, ppc64le
- [ ] Provider health dashboard — per-provider API reachability, cache freshness, account expiry
- [ ] Config export/import — encrypted archive for migration
- [ ] Per-torrent VPN binding (pause individual torrents on VPN drop)
- [ ] Bandwidth scheduling (speed limits by time of day)
- [ ] HACS default store listing (pending review)
- [ ] Native Homepage widget type (not customapi)
- [ ] WireGuard key generation in setup wizard (no copy-paste needed)
- [ ] Tailscale exit node support
- [ ] IPv6 tunnel support (when providers catch up)

## Done

- [x] Provider wave 2 — IPVanish, TorGuard, PrivateVPN, Perfect Privacy, CyberGhost (v2.9.0)
- [x] Provider wave 1 — NordVPN (full rotation), Windscribe, AirVPN, Surfshark, ExpressVPN (v2.8.0)
- [x] Infrastructure hardening — firewall-first boot, userspace WireGuard fallback (wireguard-go), port forward hooks, server auto-updater, richer server filters (v2.7.0)
- [x] Provider framework refactor — metadata protocol, unified connect pipeline, auto-discovery, metadata-driven config, parametrized tests (v2.6.0)
- [x] Docker Secrets support — `_SECRETFILE` env vars for all secret fields (v2.5.0)
- [x] Firewall granularity — VPN input ports, outbound subnet bypass, custom nftables rules (v2.5.0)
- [x] Built-in DNS — DoT upstream, caching, ad/malware/surveillance blocking (v2.5.0)
- [x] ProtonVPN provider — native integration with NAT-PMP port forwarding (v2.5.0)
- [x] HTTP CONNECT proxy — route non-Docker clients through VPN (v2.5.0)
- [x] SOCKS5 proxy — with optional Shadowsocks AEAD encryption (v2.5.0)
- [x] Setup wizard — provider-specific flows for Mullvad, IVPN, PIA, Gluetun with server picker (v2.4.0)
- [x] Connection history UI — dashboard card with event timeline (v2.4.0)
- [x] Server browser — modal with country filter, search, connect-to-server (v2.4.0)
- [x] Multi-config management — switch VPN configs from dashboard (v2.4.0)
- [x] Self-healing VPN — auto-reconnect watchdog, multi-config failover, settings hot-reload (v2.3.0)
- [x] Architecture cleanup — StateManager, Config consolidation, MQTT dispatch (v2.2.0)
- [x] SSE real-time events + HACS SSE push (v2.1.0)
- [x] Gluetun sidecar mode (v2.0.0)
- [x] IVPN provider integration (v1.1.0)
- [x] PIA provider integration (v1.1.0)
- [x] Port forwarding — PIA (v1.1.0)
- [x] Reconnect endpoint + server rotation (v1.2.0)
- [x] Notification webhooks — Discord, Slack, Gotify (v1.2.0)
- [x] Speed test endpoint (v1.2.0)
- [x] Config backup/restore API (v1.2.0)
- [x] Connection history log (v1.2.0)
- [x] Grafana dashboard template (v1.2.0)
- [x] One-liner install script (v1.2.0)
- [x] HEALTHCHECK in Dockerfile (v1.0.0)
- [x] Auth system — local login + proxy bypass (v1.0.0)
- [x] Settings panel + persistent YAML config (v1.0.0)
- [x] Homepage widget with configurable fields (v1.0.0)
- [x] HACS integration (tunnelvision-ha v0.1.0)

## Contributing

Ideas? Issues? PRs welcome. If you use a VPN provider we don't have a provider integration for, open an issue with the provider's API docs and we'll look at it.
