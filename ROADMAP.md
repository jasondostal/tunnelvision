# Roadmap

What's coming. No promises on timelines — this is built for the love of blinkenlights.

## v1.1 — Polish

- [ ] Grafana dashboard template (pre-built JSON)
- [ ] One-liner install script (`curl | bash` generates docker-compose)
- [ ] HEALTHCHECK instruction in Dockerfile (VPN connectivity test)
- [ ] Auto-reconnect watchdog (rotate server on sustained health failure)
- [ ] Notification webhooks (Discord, Slack, Gotify) on VPN disconnect

## v1.2 — Provider Enrichment

- [ ] ProtonVPN provider integration (server list, connection check)
- [ ] IVPN provider integration
- [ ] Port forwarding support (Mullvad, PIA)
- [ ] Server browser in dashboard UI (map view, filter by country/city)
- [ ] Speed test endpoint (measure tunnel throughput)

## v1.3 — Config & Management

- [ ] Config backup/restore API (export/import container settings)
- [ ] Per-torrent VPN binding (pause individual torrents on VPN drop)
- [ ] Bandwidth scheduling (speed limits by time of day)
- [ ] Connection history log (track server rotations, disconnects, reconnects)
- [ ] Multi-config management (switch between VPN configs from UI)

## Future

- [ ] HACS store listing (pending review)
- [ ] Native Homepage widget type (not customapi)
- [ ] WireGuard key generation in setup wizard (no copy-paste needed)
- [ ] Tailscale exit node support
- [ ] IPv6 tunnel support (when providers catch up)

## Contributing

Ideas? Issues? PRs welcome. If you use a VPN provider we don't have a provider integration for, open an issue with the provider's API docs and we'll look at it.
