"""DNS Service — built-in DNS server with DoT, caching, and ad-blocking.

Runs as a separate process under s6 supervision. Provides:
- DNS-over-TLS upstream resolution (dnspython)
- Response caching with TTL awareness (cachetools)
- Blocklist filtering (StevenBlack hosts, URLhaus, custom)
- Stats written to StateManager for API/metrics
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

from api.constants import (
    DNS_BLOCKLIST_REFRESH,
    DNS_CACHE_SIZE,
    DNS_STATS_INTERVAL,
    STATE_DIR,
    TIMEOUT_DOWNLOAD,
    TIMEOUT_QUICK,
    ServiceState,
    http_client,
)

logger = logging.getLogger(__name__)

# Blocklist URLs by category
BLOCKLIST_URLS = {
    "ads": "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
    "malware": "https://urlhaus.abuse.ch/downloads/hostfile/",
    "surveillance": "https://raw.githubusercontent.com/crazy-max/WindowsSpyBlocker/master/data/hosts/spy.txt",
}


class DNSCache:
    """TTL-aware LRU DNS response cache."""

    def __init__(self, maxsize: int = DNS_CACHE_SIZE):
        self._cache: dict[str, tuple[bytes, float]] = {}
        self._maxsize = maxsize

    def get(self, key: str) -> Optional[bytes]:
        """Get cached response if not expired."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        data, expiry = entry
        if time.time() > expiry:
            del self._cache[key]
            return None
        return data

    def put(self, key: str, data: bytes, ttl: int) -> None:
        """Cache response with TTL."""
        if ttl <= 0:
            return
        # Evict oldest if full
        if len(self._cache) >= self._maxsize:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = (data, time.time() + ttl)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class BlocklistManager:
    """Downloads and manages DNS blocklists in hosts-file format."""

    def __init__(self, refresh_interval: int = DNS_BLOCKLIST_REFRESH):
        self._blocked: set[str] = set()
        self._last_refresh: float = 0
        self._refresh_interval = refresh_interval

    @property
    def blocked_count(self) -> int:
        return len(self._blocked)

    def is_blocked(self, domain: str) -> bool:
        """Check if domain is in any active blocklist."""
        return domain.lower() in self._blocked

    async def refresh(self, categories: list[str], custom_url: str = "") -> None:
        """Download and parse blocklists for enabled categories."""
        new_blocked: set[str] = set()

        for category in categories:
            url = BLOCKLIST_URLS.get(category)
            if not url:
                continue
            try:
                async with http_client(timeout=TIMEOUT_DOWNLOAD) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    new_blocked.update(self._parse_hosts(resp.text))
                    logger.info(f"DNS blocklist '{category}': {len(new_blocked)} domains")
            except Exception as e:
                logger.warning(f"DNS blocklist '{category}' failed: {e}")

        if custom_url:
            try:
                async with http_client(timeout=TIMEOUT_DOWNLOAD) as client:
                    resp = await client.get(custom_url)
                    resp.raise_for_status()
                    new_blocked.update(self._parse_hosts(resp.text))
                    logger.info(f"DNS custom blocklist: {len(new_blocked)} total domains")
            except Exception as e:
                logger.warning(f"DNS custom blocklist failed: {e}")

        self._blocked = new_blocked
        self._last_refresh = time.time()

    @staticmethod
    def _parse_hosts(text: str) -> set[str]:
        """Parse hosts-file format into set of blocked domains."""
        domains: set[str] = set()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                # hosts format: 0.0.0.0 domain.com or 127.0.0.1 domain.com
                domain = parts[1].lower()
                if domain != "localhost" and "." in domain:
                    domains.add(domain)
        return domains

    def needs_refresh(self) -> bool:
        return time.time() - self._last_refresh > self._refresh_interval


class DNSResolver:
    """Upstream DNS resolution via DoT or plain UDP."""

    def __init__(self, upstreams: list[str], use_dot: bool = True):
        self.upstreams = upstreams
        self.use_dot = use_dot

    async def resolve(self, query_data: bytes) -> Optional[bytes]:
        """Send DNS query to upstream and return response."""
        try:
            import dns.message
            import dns.query
            import dns.rdatatype

            query = dns.message.from_wire(query_data)

            for upstream in self.upstreams:
                try:
                    if self.use_dot:
                        response = dns.query.tls(query, upstream, timeout=TIMEOUT_QUICK, port=853)
                    else:
                        response = dns.query.udp(query, upstream, timeout=TIMEOUT_QUICK)
                    return response.to_wire()
                except Exception:
                    continue

            return None
        except Exception as e:
            logger.error(f"DNS resolve error: {e}")
            return None


def _extract_domain(data: bytes) -> str:
    """Extract queried domain name from raw DNS query."""
    try:
        # Skip header (12 bytes), parse QNAME
        offset = 12
        labels = []
        while offset < len(data):
            length = data[offset]
            if length == 0:
                break
            offset += 1
            labels.append(data[offset:offset + length].decode("ascii", errors="replace"))
            offset += length
        return ".".join(labels).lower()
    except Exception:
        return ""


def _extract_ttl(data: bytes) -> int:
    """Extract minimum TTL from DNS response."""
    try:
        import dns.message
        msg = dns.message.from_wire(data)
        min_ttl = 300  # default 5 min
        for rrset in msg.answer:
            if rrset.ttl < min_ttl:
                min_ttl = rrset.ttl
        return max(min_ttl, 30)  # floor at 30s
    except Exception:
        return 300


def _build_nxdomain(query_data: bytes) -> bytes:
    """Build NXDOMAIN response for blocked domains."""
    try:
        # Copy query header, set QR bit and RCODE=3 (NXDOMAIN)
        response = bytearray(query_data)
        if len(response) < 12:
            return bytes(response)
        # Set QR=1 (response), RD=1, RA=1, RCODE=3
        response[2] = 0x81  # QR=1, Opcode=0, AA=0, TC=0, RD=1
        response[3] = 0x83  # RA=1, Z=0, RCODE=3 (NXDOMAIN)
        # Zero answer, authority, additional counts
        response[6:12] = b'\x00\x00\x00\x00\x00\x00'
        return bytes(response)
    except Exception:
        return query_data


class DNSProtocol(asyncio.DatagramProtocol):
    """UDP DNS server protocol handler."""

    def __init__(self, server: "DNSServer"):
        self.server = server
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:  # type: ignore[override]
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        asyncio.ensure_future(self._handle(data, addr))

    async def _handle(self, data: bytes, addr: tuple[str, int]) -> None:
        response = await self.server.handle_query(data)
        if response and self.transport:
            self.transport.sendto(response, addr)


class DNSServer:
    """Main DNS server — asyncio UDP listener with cache, blocklist, and upstream resolution."""

    def __init__(self, bind: str = "0.0.0.0", port: int = 53):
        self.bind = bind
        self.port = port
        self.cache = DNSCache()
        self.blocklist = BlocklistManager()
        self.resolver: DNSResolver | None = None
        self._queries_total = 0
        self._cache_hits = 0
        self._blocked_total = 0
        self._running = False

    async def handle_query(self, data: bytes) -> Optional[bytes]:
        """Process a DNS query: blocklist → cache → upstream → cache → respond."""
        self._queries_total += 1
        domain = _extract_domain(data)

        # Check blocklist
        if domain and self.blocklist.is_blocked(domain):
            self._blocked_total += 1
            return _build_nxdomain(data)

        # Check cache
        cache_key = domain
        cached = self.cache.get(cache_key)
        if cached is not None:
            self._cache_hits += 1
            # Rewrite transaction ID to match query
            response = bytearray(cached)
            response[0:2] = data[0:2]
            return bytes(response)

        # Upstream resolution
        if self.resolver:
            resolved = await self.resolver.resolve(data)
            if resolved:
                ttl = _extract_ttl(resolved)
                self.cache.put(cache_key, resolved, ttl)
                return resolved

        return _build_nxdomain(data)

    def write_stats(self, state_dir: Path = STATE_DIR) -> None:
        """Write DNS stats to state files for API/metrics."""
        try:
            state_dir.mkdir(parents=True, exist_ok=True)
            (state_dir / "dns_queries_total").write_text(str(self._queries_total))
            (state_dir / "dns_cache_hits").write_text(str(self._cache_hits))
            (state_dir / "dns_blocked_total").write_text(str(self._blocked_total))
            (state_dir / "dns_state").write_text(ServiceState.RUNNING if self._running else ServiceState.STOPPED)
        except Exception:
            pass

    async def run(self) -> None:
        """Start DNS server and blocklist refresh loop."""
        # Load config from environment
        upstreams = os.getenv("DNS_UPSTREAM", "1.1.1.1,1.0.0.1").split(",")
        upstreams = [u.strip() for u in upstreams if u.strip()]
        use_dot = os.getenv("DNS_DOT_ENABLED", "true").lower() == "true"
        cache_enabled = os.getenv("DNS_CACHE_ENABLED", "true").lower() == "true"

        self.resolver = DNSResolver(upstreams, use_dot)

        if not cache_enabled:
            self.cache = DNSCache(maxsize=0)

        logger.info(f"DNS server starting on {self.bind}:{self.port}")
        logger.info(f"Upstreams: {upstreams}, DoT: {use_dot}, Cache: {cache_enabled}")

        # Initial blocklist load
        await self._refresh_blocklists()

        # Start UDP listener
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: DNSProtocol(self),
            local_addr=(self.bind, self.port),
        )

        self._running = True
        self.write_stats()
        logger.info(f"DNS server listening on {self.bind}:{self.port}")

        try:
            # Periodic blocklist refresh and stats write
            while True:
                await asyncio.sleep(DNS_STATS_INTERVAL)
                self.write_stats()
                if self.blocklist.needs_refresh():
                    await self._refresh_blocklists()
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False
            transport.close()
            self.write_stats()

    async def _refresh_blocklists(self) -> None:
        """Refresh blocklists based on current settings."""
        import os
        from api.services.settings import load_settings

        try:
            settings = load_settings()
        except Exception:
            settings = {}

        categories = []
        if settings.get("dns_block_ads", os.getenv("DNS_BLOCK_ADS", "false")).lower() == "true":
            categories.append("ads")
        if settings.get("dns_block_malware", os.getenv("DNS_BLOCK_MALWARE", "false")).lower() == "true":
            categories.append("malware")
        if settings.get("dns_block_surveillance", os.getenv("DNS_BLOCK_SURVEILLANCE", "false")).lower() == "true":
            categories.append("surveillance")

        custom_url = settings.get("dns_custom_blocklist_url", os.getenv("DNS_CUSTOM_BLOCKLIST_URL", ""))

        # Update refresh interval from settings (hot-reloadable)
        refresh_str = settings.get(
            "dns_blocklist_refresh_interval",
            os.getenv("DNS_BLOCKLIST_REFRESH_INTERVAL", str(DNS_BLOCKLIST_REFRESH)),
        )
        try:
            self.blocklist._refresh_interval = int(refresh_str)
        except (ValueError, TypeError):
            pass

        if categories or custom_url:
            await self.blocklist.refresh(categories, custom_url)
            logger.info(f"DNS blocklist refreshed: {self.blocklist.blocked_count} domains blocked")


def main():
    """Entry point for s6 service."""
    logging.basicConfig(level=logging.INFO, format="[dns] %(message)s")
    server = DNSServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
