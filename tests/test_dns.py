"""Tests for DNS service (Phase 3).

Tests cache, blocklist parsing, domain extraction, NXDOMAIN building,
and query handling flow.
"""

import asyncio
import time
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from api.services.dns import (
    DNSCache,
    BlocklistManager,
    DNSServer,
    _extract_domain,
    _build_nxdomain,
)


class TestDNSCache:
    """Tests for TTL-aware LRU cache."""

    def test_put_and_get(self):
        cache = DNSCache()
        cache.put("example.com", b"response_data", ttl=60)
        assert cache.get("example.com") == b"response_data"

    def test_get_returns_none_for_missing(self):
        cache = DNSCache()
        assert cache.get("missing.com") is None

    def test_ttl_expiry(self):
        cache = DNSCache()
        cache.put("example.com", b"data", ttl=1)
        assert cache.get("example.com") == b"data"
        # Simulate expiry
        cache._cache["example.com"] = (b"data", time.time() - 1)
        assert cache.get("example.com") is None

    def test_zero_ttl_not_cached(self):
        cache = DNSCache()
        cache.put("example.com", b"data", ttl=0)
        assert cache.get("example.com") is None

    def test_negative_ttl_not_cached(self):
        cache = DNSCache()
        cache.put("example.com", b"data", ttl=-5)
        assert cache.get("example.com") is None

    def test_eviction_on_full(self):
        cache = DNSCache(maxsize=2)
        cache.put("a.com", b"a", ttl=60)
        cache.put("b.com", b"b", ttl=60)
        cache.put("c.com", b"c", ttl=60)
        # Oldest (a.com) should be evicted
        assert cache.get("a.com") is None
        assert cache.get("b.com") == b"b"
        assert cache.get("c.com") == b"c"

    def test_clear(self):
        cache = DNSCache()
        cache.put("example.com", b"data", ttl=60)
        cache.clear()
        assert cache.size == 0
        assert cache.get("example.com") is None

    def test_size(self):
        cache = DNSCache()
        assert cache.size == 0
        cache.put("a.com", b"a", ttl=60)
        cache.put("b.com", b"b", ttl=60)
        assert cache.size == 2


class TestBlocklistManager:
    """Tests for blocklist parsing and matching."""

    def test_parse_hosts_format(self):
        text = """# comment
0.0.0.0 ads.example.com
127.0.0.1 tracker.evil.com
# another comment
0.0.0.0 malware.bad.org
"""
        result = BlocklistManager._parse_hosts(text)
        assert "ads.example.com" in result
        assert "tracker.evil.com" in result
        assert "malware.bad.org" in result
        assert "localhost" not in result

    def test_parse_ignores_comments_and_empty(self):
        text = """# this is a comment

# another comment
"""
        result = BlocklistManager._parse_hosts(text)
        assert len(result) == 0

    def test_parse_ignores_localhost(self):
        text = "127.0.0.1 localhost\n0.0.0.0 localhost.localdomain\n"
        result = BlocklistManager._parse_hosts(text)
        assert "localhost" not in result

    def test_is_blocked(self):
        mgr = BlocklistManager()
        mgr._blocked = {"ads.example.com", "evil.tracker.com"}
        assert mgr.is_blocked("ads.example.com")
        assert mgr.is_blocked("ADS.EXAMPLE.COM")  # case insensitive
        assert not mgr.is_blocked("safe.example.com")

    def test_blocked_count(self):
        mgr = BlocklistManager()
        mgr._blocked = {"a.com", "b.com", "c.com"}
        assert mgr.blocked_count == 3

    def test_needs_refresh(self):
        mgr = BlocklistManager()
        assert mgr.needs_refresh()  # Never refreshed
        mgr._last_refresh = time.time()
        assert not mgr.needs_refresh()  # Just refreshed
        mgr._last_refresh = time.time() - 90000  # Over 24h ago
        assert mgr.needs_refresh()


class TestDomainExtraction:
    """Tests for _extract_domain()."""

    def test_extract_simple_domain(self):
        # Build a minimal DNS query for "example.com"
        # Header (12 bytes) + QNAME + QTYPE + QCLASS
        header = b'\x00\x01'  # ID
        header += b'\x01\x00'  # Flags (RD=1)
        header += b'\x00\x01'  # QDCOUNT=1
        header += b'\x00\x00\x00\x00\x00\x00'  # AN/NS/AR = 0

        # QNAME: 7example3com0
        qname = b'\x07example\x03com\x00'
        qtype = b'\x00\x01'  # A
        qclass = b'\x00\x01'  # IN

        data = header + qname + qtype + qclass
        assert _extract_domain(data) == "example.com"

    def test_extract_subdomain(self):
        header = b'\x00\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
        qname = b'\x03www\x07example\x03com\x00'
        data = header + qname + b'\x00\x01\x00\x01'
        assert _extract_domain(data) == "www.example.com"

    def test_extract_from_empty_returns_empty(self):
        assert _extract_domain(b"") == ""
        assert _extract_domain(b"\x00" * 12) == ""


class TestNXDOMAIN:
    """Tests for NXDOMAIN response building."""

    def test_nxdomain_preserves_query_id(self):
        query = bytearray(b'\xAB\xCD')  # Transaction ID
        query += b'\x01\x00'  # Flags
        query += b'\x00\x01\x00\x00\x00\x00\x00\x00'  # Counts
        query += b'\x07example\x03com\x00\x00\x01\x00\x01'  # Question

        response = _build_nxdomain(bytes(query))
        assert response[0:2] == b'\xAB\xCD'  # Same transaction ID

    def test_nxdomain_sets_rcode_3(self):
        query = b'\x00\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
        query += b'\x07example\x03com\x00\x00\x01\x00\x01'
        response = _build_nxdomain(query)
        # RCODE is in lower 4 bits of byte 3
        assert (response[3] & 0x0F) == 3


class TestDNSServer:
    """Tests for DNS server query handling."""

    @pytest.fixture
    def server(self):
        return DNSServer()

    @pytest.mark.asyncio
    async def test_blocked_domain_returns_nxdomain(self, server):
        server.blocklist._blocked = {"blocked.example.com"}

        # Build query for blocked.example.com
        header = b'\x00\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
        qname = b'\x07blocked\x07example\x03com\x00'
        query = header + qname + b'\x00\x01\x00\x01'

        response = await server.handle_query(query)
        assert response is not None
        assert (response[3] & 0x0F) == 3  # NXDOMAIN
        assert server._blocked_total == 1

    @pytest.mark.asyncio
    async def test_cached_response_returned(self, server):
        # Pre-populate cache
        domain = "cached.example.com"
        cached_response = b'\x00\x01\x81\x80' + b'\x00' * 100
        server.cache.put(domain, cached_response, ttl=60)

        # Build query
        header = b'\x00\x02\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
        qname = b'\x06cached\x07example\x03com\x00'
        query = header + qname + b'\x00\x01\x00\x01'

        response = await server.handle_query(query)
        assert response is not None
        # Transaction ID should be from query (0x0002), not cached (0x0001)
        assert response[0:2] == b'\x00\x02'
        assert server._cache_hits == 1

    @pytest.mark.asyncio
    async def test_stats_increment(self, server):
        server.blocklist._blocked = {"blocked.com"}

        header = b'\x00\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
        qname = b'\x07blocked\x03com\x00'
        query = header + qname + b'\x00\x01\x00\x01'

        await server.handle_query(query)
        assert server._queries_total == 1
        assert server._blocked_total == 1

    def test_write_stats(self, server, tmp_path):
        server._queries_total = 100
        server._cache_hits = 42
        server._blocked_total = 15
        server._running = True

        server.write_stats(tmp_path)

        assert (tmp_path / "dns_queries_total").read_text() == "100"
        assert (tmp_path / "dns_cache_hits").read_text() == "42"
        assert (tmp_path / "dns_blocked_total").read_text() == "15"
        assert (tmp_path / "dns_state").read_text() == "running"

    def test_settings_registered(self):
        from api.services.settings import CONFIGURABLE_FIELDS

        dns_fields = [k for k in CONFIGURABLE_FIELDS if k.startswith("dns_")]
        assert len(dns_fields) == 9
