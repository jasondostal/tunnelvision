"""Server list auto-updater — proactively refreshes provider server caches.

Runs as a background task. Ensures server lists stay current without
requiring a user request to trigger a stale-cache refresh.

Only refreshes providers that have live instances (i.e. the active provider
has been used at least once) and support server lists.
"""

import asyncio
import logging

from api.constants import PROVIDER_CACHE_TTL

logger = logging.getLogger(__name__)


class ServerListUpdater:
    """Background task that refreshes provider server list caches on a schedule."""

    def __init__(self, config=None):
        self._config = config
        self._task: asyncio.Task | None = None

    @property
    def _interval(self) -> int:
        if self._config:
            return self._config.server_list_update_interval
        return PROVIDER_CACHE_TTL

    @property
    def _enabled(self) -> bool:
        if self._config:
            return self._config.server_list_auto_update
        return True

    def start(self):
        if not self._enabled:
            logger.info("Server list auto-updater disabled")
            return
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._run())
        logger.info(f"Server list auto-updater started (interval={self._interval}s)")

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()

    @property
    def active(self) -> bool:
        return self._task is not None and not self._task.done()

    async def _run(self):
        try:
            # Initial delay — let the app settle before first refresh
            await asyncio.sleep(self._interval)
            while True:
                await self._refresh_all()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            logger.info("Server list auto-updater stopped")

    async def _refresh_all(self):
        from api.services.vpn import get_server_list_providers, refresh_provider_server_list

        providers = get_server_list_providers()
        for name in providers:
            count = await refresh_provider_server_list(name)
            if count:
                logger.info(f"Server list refreshed: {name} ({count} servers)")


# Singleton
_updater: ServerListUpdater | None = None


def get_server_list_updater(config=None) -> ServerListUpdater:
    global _updater
    if _updater is None:
        _updater = ServerListUpdater(config=config)
    return _updater
