"""Tests for smart server selection and WireGuard key generation."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes.connect import _select_server
from api.services.providers.base import ServerInfo
from api.services.state import StateManager

client = TestClient(app)


@pytest.fixture(autouse=True)
def _init_app_state(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    app.state.state = StateManager(state_dir=state_dir)


def _server(hostname: str, load: int = 0, speed_gbps: int = 0) -> ServerInfo:
    return ServerInfo(hostname=hostname, load=load, speed_gbps=speed_gbps,
                      country="Switzerland", city="Zurich", public_key="key")


class TestSelectServer:
    def test_prefers_low_load(self):
        # 6 moderate servers + 1 worst — top-5 cutoff should exclude the worst
        servers = [_server(f"mid{i}.example.com", load=40 + i * 5) for i in range(6)]
        servers.append(_server("worst.example.com", load=99))
        results = [_select_server(servers).hostname for _ in range(100)]
        assert "worst.example.com" not in results

    def test_prefers_higher_speed(self):
        # All servers have equal load; 6 slow + 1 fast — fast should always win top-5
        servers = [_server(f"slow{i}.example.com", load=50, speed_gbps=i) for i in range(6)]
        servers.append(_server("fastest.example.com", load=50, speed_gbps=100))
        results = [_select_server(servers).hostname for _ in range(100)]
        assert "slowest.example.com" not in results  # non-existent → vacuously true
        # fastest should be present (it's always in top-5, scoring highest)
        assert "fastest.example.com" in results

    def test_excludes_current_server(self):
        servers = [
            _server("current.example.com", load=5),
            _server("other.example.com", load=80),
        ]
        results = [_select_server(servers, exclude_hostname="current.example.com").hostname
                   for _ in range(20)]
        assert all(h == "other.example.com" for h in results)

    def test_fallback_when_only_option(self):
        servers = [_server("only.example.com", load=5)]
        # Should not raise even when exclude matches only server
        result = _select_server(servers, exclude_hostname="only.example.com")
        assert result.hostname == "only.example.com"

    def test_picks_from_top_5(self):
        servers = [_server(f"s{i}.example.com", load=i * 10) for i in range(20)]
        results = {_select_server(servers).hostname for _ in range(100)}
        # Should only pick from the top 5 (lowest load = s0-s4)
        assert all(h.startswith("s") for h in results)
        assert len(results) <= 5

    def test_no_exclude(self):
        servers = [_server("a.example.com"), _server("b.example.com")]
        result = _select_server(servers)
        assert result.hostname in ("a.example.com", "b.example.com")

    def test_uniform_scores_pick_from_full_pool(self):
        """When all servers have identical scores (e.g. provider exposes no load),
        pick from the entire pool — not the first N alphabetically."""
        # 20 servers, identical load=None (treated as 50) and speed=10 Gbps
        servers = [_server(f"z{i:02d}.example.com", load=0, speed_gbps=10) for i in range(20)]
        results = {_select_server(servers).hostname for _ in range(200)}
        # With uniform scores, all 20 should appear eventually
        assert len(results) > 5, f"Expected >5 distinct servers, got {len(results)}: {results}"

    def test_unknown_load_treated_as_50(self):
        """load=0 (unknown) should be treated as 50, not as best-possible."""
        # 6 unknown-load servers + 1 genuinely low-load server
        # The low-load server should always appear in top-5; the unknown-load ones compete for the other slots
        servers = [_server(f"unknown{i}.example.com", load=0) for i in range(6)]
        servers.append(_server("low.example.com", load=10))
        results = [_select_server(servers).hostname for _ in range(100)]
        # low.example.com (load=10, score≈0.9) beats all unknown (load→50, score≈0.35)
        assert "low.example.com" in results


class TestGenerateKeypair:
    def test_generates_keypair(self):
        mock_genkey = MagicMock(returncode=0, stdout="AAAA+privatekey=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n")
        mock_pubkey = MagicMock(returncode=0, stdout="BBBB+publickey=BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB\n")

        with patch("api.routes.setup.subprocess.run", side_effect=[mock_genkey, mock_pubkey]):
            resp = client.post("/api/v1/setup/generate-keypair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "private_key" in data
        assert "public_key" in data

    def test_handles_wg_not_found(self):
        with patch("api.routes.setup.subprocess.run", side_effect=FileNotFoundError):
            resp = client.post("/api/v1/setup/generate-keypair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "wireguard-tools" in data["error"].lower() or "not found" in data["error"].lower()

    def test_handles_genkey_failure(self):
        mock_fail = MagicMock(returncode=1, stdout="")
        with patch("api.routes.setup.subprocess.run", return_value=mock_fail):
            resp = client.post("/api/v1/setup/generate-keypair")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
