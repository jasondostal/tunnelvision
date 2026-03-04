"""Tests for NAT-PMP port forwarding (Phase 4)."""

import struct

import pytest

from api.services.natpmp import build_request, parse_response, NatPMPService


class TestNatPMPPackets:
    """Tests for NAT-PMP packet construction and parsing."""

    def test_build_request_default(self):
        """Default request: UDP mapping with 60s lifetime."""
        data = build_request()
        assert len(data) == 12
        version, opcode, reserved, internal, external, lifetime = \
            struct.unpack("!BBHHHi", data)
        assert version == 0
        assert opcode == 1  # UDP
        assert reserved == 0
        assert internal == 0
        assert external == 0
        assert lifetime == 60

    def test_build_request_tcp(self):
        data = build_request(opcode=2, internal_port=8080, external_port=0, lifetime=120)
        version, opcode, _, internal, external, lifetime = \
            struct.unpack("!BBHHHi", data)
        assert opcode == 2  # TCP
        assert internal == 8080
        assert lifetime == 120

    def test_parse_response_success(self):
        """Parse a valid NAT-PMP response."""
        # Build response: version=0, opcode=129, result=0, epoch=12345,
        # internal=0, external=51413, lifetime=60
        data = struct.pack("!BBHiHHi", 0, 129, 0, 12345, 0, 51413, 60)
        result = parse_response(data)
        assert result is not None
        assert result["external_port"] == 51413
        assert result["lifetime"] == 60
        assert result["epoch"] == 12345

    def test_parse_response_error(self):
        """Non-zero result code should return None."""
        data = struct.pack("!BBHiHHi", 0, 129, 3, 0, 0, 0, 0)
        result = parse_response(data)
        assert result is None

    def test_parse_response_too_short(self):
        """Short data should return None."""
        result = parse_response(b"\x00\x01")
        assert result is None

    def test_parse_response_empty(self):
        result = parse_response(b"")
        assert result is None


class TestNatPMPService:
    """Tests for NatPMPService lifecycle."""

    def test_initial_state(self):
        svc = NatPMPService()
        assert svc.port is None
        assert svc.active is False

    def test_stop_clears_port(self):
        svc = NatPMPService()
        svc._port = 51413
        svc.stop()
        assert svc.port is None
