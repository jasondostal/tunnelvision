# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in TunnelVision, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please use [GitHub's private vulnerability reporting](https://github.com/jasondostal/tunnelvision/security/advisories/new) to submit your report.

You can expect:
- Acknowledgment within 48 hours
- A fix timeline within 7 days for critical issues
- Credit in the release notes (unless you prefer anonymity)

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest  | Yes       |
| Older   | No        |

## Security Features

TunnelVision includes several security features:

- **Kill switch**: nftables-based firewall blocks all traffic outside the VPN tunnel
- **IPv6 leak protection**: All IPv6 traffic is dropped by default
- **DNS leak protection**: Built-in DNS server with DoT (DNS over TLS)
- **Pre-VPN firewall**: Traffic is locked down before the VPN tunnel is established
- **Supply chain security**: Container images are signed with cosign and include SBOM attestation
- **WireGuard config protection**: Private keys are stored with 0600 permissions
