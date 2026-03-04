"""Provider-specific endpoints — connection verification, server metadata, account info."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from api.constants import PROVIDER_CACHE_TTL, http_client
from api.services.providers.base import ServerFilter
from api.services.vpn import get_provider

router = APIRouter()


@router.get("/vpn/check")
async def vpn_connection_check(request: Request):
    """Verify VPN connection via provider API.

    For Mullvad: confirms exit IP is a Mullvad server, checks blacklist status.
    For custom: returns public IP via generic check services.
    """
    config = request.app.state.config
    provider = get_provider(config.vpn_provider, config)
    check = await provider.check_connection()

    return {
        "provider": provider.name,
        "ip": check.ip,
        "country": check.country,
        "city": check.city,
        "is_vpn_ip": check.is_vpn_ip,
        "blacklisted": check.blacklisted,
        "blacklist_results": check.blacklist_results,
        "organization": check.organization,
        "checked_at": check.checked_at,
    }


@router.get("/vpn/server")
async def vpn_server_info(request: Request):
    """Get metadata about the VPN server we're connected to.

    For Mullvad: hostname, country, city, hosting provider, owned status, speed.
    For custom: returns null (no server metadata available).
    """
    config = request.app.state.config
    provider = get_provider(config.vpn_provider, config)
    endpoint = request.app.state.state.vpn_endpoint

    # Extract IP from endpoint (format: "IP:PORT")
    endpoint_ip = endpoint.split(":")[0] if ":" in endpoint else endpoint

    server = await provider.get_server_info(endpoint_ip)

    if server is None:
        return {
            "provider": provider.name,
            "available": False,
            "message": f"Server metadata not available for provider '{provider.name}'",
        }

    return {
        "provider": provider.name,
        "available": True,
        "hostname": server.hostname,
        "country": server.country,
        "country_code": server.country_code,
        "city": server.city,
        "city_code": server.city_code,
        "hosting_provider": server.provider,
        "owned": server.owned,
        "speed_gbps": server.speed_gbps,
        "server_type": server.server_type,
        "fqdn": server.fqdn,
    }


@router.get("/vpn/account")
async def vpn_account_info(request: Request):
    """Check VPN account status.

    For Mullvad: account expiry date and days remaining.
    Requires MULLVAD_ACCOUNT environment variable.
    For custom: returns null (no account check available).
    """
    config = request.app.state.config
    provider = get_provider(config.vpn_provider, config)
    account = await provider.get_account_info()

    if account is None:
        return {
            "provider": provider.name,
            "available": False,
            "message": f"Account info not available for provider '{provider.name}'",
        }

    return {
        "provider": provider.name,
        "available": True,
        "active": account.active,
        "expires_at": account.expires_at,
        "days_remaining": account.days_remaining,
    }


@router.get("/vpn/servers")
async def vpn_server_list(
    request: Request,
    country: str | None = Query(None, description="Filter by country name or code"),
    city: str | None = Query(None, description="Filter by city name or code"),
    owned_only: bool | None = Query(None, description="Only servers owned by the provider"),
    p2p: bool | None = Query(None, description="P2P / torrenting capability"),
    streaming: bool | None = Query(None, description="Streaming-optimized servers"),
    port_forward: bool | None = Query(None, description="Port forwarding capable"),
    secure_core: bool | None = Query(None, description="Secure core / double-hop"),
    multihop: bool | None = Query(None, description="Multi-hop routing"),
    max_load: int | None = Query(None, description="Maximum server load percentage (0-100)"),
):
    """List available VPN servers with optional filtering.

    Supported filters vary by provider — see filter_capabilities in /vpn/providers.
    For custom/paste providers: returns empty list.
    """
    config = request.app.state.config
    provider = get_provider(config.vpn_provider, config)
    server_filter = ServerFilter(
        country=country, city=city, owned_only=owned_only, p2p=p2p,
        streaming=streaming, port_forward=port_forward, secure_core=secure_core,
        multihop=multihop, max_load=max_load,
    )
    servers = await provider.list_servers(filter=server_filter)

    return {
        "provider": provider.name,
        "count": len(servers),
        "servers": [
            {
                "hostname": s.hostname,
                "country": s.country,
                "country_code": s.country_code,
                "city": s.city,
                "city_code": s.city_code,
                "owned": s.owned,
                "speed_gbps": s.speed_gbps,
                "load": s.load,
                "fqdn": s.fqdn,
                "port_forward": s.port_forward,
                "p2p": s.p2p,
                "streaming": s.streaming,
                "secure_core": s.secure_core,
                "multihop": s.multihop,
            }
            for s in servers
        ],
    }


@router.get("/vpn/provider-health")
async def provider_health(request: Request):
    """Provider observability — API reachability, server cache freshness, account expiry.

    Returns live signal about the active provider's health:
    - api_reachable: whether the provider's API endpoint responds (null for PASTE providers)
    - api_latency_ms: round-trip time to the API (null if not applicable / unreachable)
    - server_count: number of servers in the in-memory cache (null if never fetched)
    - cache_age_seconds: seconds since the server list was last refreshed
    - cache_fresh: whether the cache is within the TTL window (1 hour)
    - account: expiry data where the provider supports account checks
    """
    config = request.app.state.config
    provider = get_provider(config.vpn_provider, config)

    # API reachability ping
    api_reachable: bool | None = None
    api_latency_ms: int | None = None
    ping_url = provider.HEALTH_PING_URL
    if ping_url:
        t0 = time.monotonic()
        try:
            async with http_client() as client:
                await client.head(ping_url, timeout=3.0)
            api_reachable = True
            api_latency_ms = round((time.monotonic() - t0) * 1000)
        except Exception:
            api_reachable = False

    # Server cache metadata (read directly from in-memory singleton)
    server_count: int | None = len(provider._server_cache) if provider._server_cache is not None else None
    cache_age_seconds: int | None = None
    cache_fresh: bool | None = None
    if provider._cache_time is not None:
        cache_age_seconds = int((datetime.now(timezone.utc) - provider._cache_time).total_seconds())
        cache_fresh = cache_age_seconds < PROVIDER_CACHE_TTL

    # Account info — only for providers that support it
    account_payload: dict = {"available": False}
    if provider.meta.supports_account_check:
        account = await provider.get_account_info()
        if account is not None:
            account_payload = {
                "available": True,
                "active": account.active,
                "expires_at": account.expires_at.isoformat() if account.expires_at else None,
                "days_remaining": account.days_remaining,
            }

    return {
        "provider_id": provider.meta.id,
        "provider_name": provider.meta.display_name,
        "supports_account_check": provider.meta.supports_account_check,
        "api_reachable": api_reachable,
        "api_latency_ms": api_latency_ms,
        "server_count": server_count,
        "cache_age_seconds": cache_age_seconds,
        "cache_fresh": cache_fresh,
        "account": account_payload,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
