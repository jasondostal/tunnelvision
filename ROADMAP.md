# Roadmap

What's coming. No promises on timelines — this is built for the love of blinkenlights.

## v1.2 — Polish & Hardening

- [ ] Grafana dashboard template (pre-built JSON)
- [ ] One-liner install script (`curl | bash` generates docker-compose)
- [ ] HEALTHCHECK instruction in Dockerfile (VPN connectivity test)
- [ ] Auto-reconnect watchdog (rotate server on sustained health failure)
- [ ] Notification webhooks (Discord, Slack, Gotify) on VPN disconnect
- [ ] Server browser in dashboard UI (filter by country/city, show load)
- [ ] Speed test endpoint (measure tunnel throughput)

## v1.3 — Config & Management

- [ ] Config backup/restore API (export/import container settings)
- [ ] Per-torrent VPN binding (pause individual torrents on VPN drop)
- [ ] Bandwidth scheduling (speed limits by time of day)
- [ ] Connection history log (track server rotations, disconnects, reconnects)
- [ ] Multi-config management (switch between VPN configs from UI)

## Future

- [ ] HACS default store listing (pending review)
- [ ] Native Homepage widget type (not customapi)
- [ ] WireGuard key generation in setup wizard (no copy-paste needed)
- [ ] Tailscale exit node support
- [ ] IPv6 tunnel support (when providers catch up)
- [ ] Additional providers as APIs become available (ProtonVPN API is currently deprecated)

## Done

- [x] ~~IVPN provider integration~~ (v1.1.0)
- [x] ~~PIA provider integration~~ (v1.1.0)
- [x] ~~Port forwarding support~~ (v1.1.0 — PIA)
- [x] ~~Auth system (local login + proxy bypass)~~ (v1.0.0)
- [x] ~~Settings panel + persistent YAML config~~ (v1.0.0)
- [x] ~~Homepage widget with configurable fields~~ (v1.0.0)
- [x] ~~HACS integration~~ (tunnelvision-ha v0.1.0)

## Contributing

Ideas? Issues? PRs welcome. If you use a VPN provider we don't have a provider integration for, open an issue with the provider's API docs and we'll look at it.
