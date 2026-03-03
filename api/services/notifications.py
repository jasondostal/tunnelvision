"""Notification service — webhooks for VPN state changes.

Supports Discord, Slack, Gotify, and generic webhooks.
Fires on VPN disconnect, reconnect, and port forwarding changes.
"""

import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


async def notify(event: str, message: str, details: dict | None = None):
    """Send notification to all configured webhooks."""
    webhook_url = os.getenv("NOTIFY_WEBHOOK_URL", "")
    gotify_url = os.getenv("NOTIFY_GOTIFY_URL", "")
    gotify_token = os.getenv("NOTIFY_GOTIFY_TOKEN", "")

    if not webhook_url and not gotify_url:
        return

    payload = {
        "event": event,
        "message": message,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Discord / Slack webhook (auto-detect by URL)
        if webhook_url:
            try:
                if "discord.com" in webhook_url:
                    await client.post(webhook_url, json={
                        "embeds": [{
                            "title": f"TunnelVision — {event}",
                            "description": message,
                            "color": 0xE8A838 if event != "vpn_down" else 0xFF4444,
                            "timestamp": payload["timestamp"],
                        }]
                    })
                elif "hooks.slack.com" in webhook_url:
                    await client.post(webhook_url, json={
                        "text": f"*TunnelVision — {event}*\n{message}",
                    })
                else:
                    # Generic webhook — POST full payload
                    await client.post(webhook_url, json=payload)
            except Exception as e:
                logger.warning(f"Webhook notification failed: {e}")

        # Gotify
        if gotify_url and gotify_token:
            try:
                await client.post(
                    f"{gotify_url.rstrip('/')}/message",
                    params={"token": gotify_token},
                    json={
                        "title": f"TunnelVision — {event}",
                        "message": message,
                        "priority": 8 if event == "vpn_down" else 4,
                    },
                )
            except Exception as e:
                logger.warning(f"Gotify notification failed: {e}")
