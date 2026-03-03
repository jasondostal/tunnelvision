"""Connection history — track VPN state changes, rotations, reconnects."""

import json
from datetime import datetime, timezone
from pathlib import Path

HISTORY_FILE = Path("/config/connection-history.json")
MAX_ENTRIES = 500


def _load() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            return []
    return []


def _save(entries: list[dict]):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(entries[-MAX_ENTRIES:], indent=2))


def log_event(event: str, details: dict | None = None):
    """Log a connection event."""
    entries = _load()
    entries.append({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **(details or {}),
    })
    _save(entries)


def get_history(limit: int = 50) -> list[dict]:
    """Get recent connection history."""
    entries = _load()
    return list(reversed(entries[-limit:]))
