"""Provider-specific endpoints — connection verification, server metadata, account info."""

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from api.services.vpn import get_provider

router = APIRouter()


def _read_state(path: str, default: str = "") -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except FileNotFoundError:
        return default


@router.get("/vpn/check")
async def vpn_connection_check(request: Request):
    """Verify VPN connection via provider API.

    For Mullvad: confirms exit IP is a Mullvad server, checks blacklist status.
    For custom: returns public IP via generic check services.
    """
    provider = get_provider(request.app.state.config.vpn_provider)
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
    provider = get_provider(request.app.state.config.vpn_provider)
    endpoint = _read_state("/var/run/tunnelvision/vpn_endpoint")

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
    provider = get_provider(request.app.state.config.vpn_provider)
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
):
    """List available VPN servers.

    For Mullvad: full server list with metadata (hostname, location, speed, owned status).
    For custom: returns empty list.
    """
    provider = get_provider(request.app.state.config.vpn_provider)
    servers = await provider.list_servers(country=country, city=city)

    return {
        "provider": provider.name,
        "count": len(servers),
        "servers": [
            {
                "hostname": s.hostname,
                "country": s.country,
                "country_code": s.country_code,
                "city": s.city,
                "owned": s.owned,
                "speed_gbps": s.speed_gbps,
                "fqdn": s.fqdn,
            }
            for s in servers
        ],
    }
