"""Authentication — single-user local auth + reverse proxy bypass."""

import ipaddress
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter()

# In-memory session store — single container, single process, this is fine
_sessions: dict[str, dict] = {}

SESSION_COOKIE = "tv_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days
MAX_SESSIONS = 100


class LoginRequest(BaseModel):
    username: str
    password: str


def _is_trusted_proxy(client_ip: str, trusted_ips_str: str) -> bool:
    """Return True if client_ip matches any entry in the trusted proxy list (IPs or CIDRs)."""
    try:
        client = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in trusted_ips_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            if client in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            pass
    return False


def check_proxy_auth_config(auth_proxy_header: str, trusted_proxy_ips: str) -> bool:
    """Return True if proxy auth is securely configured (both header and trusted IPs set).

    Called at startup to detect misconfiguration early.
    """
    return bool(auth_proxy_header and trusted_proxy_ips)


def _check_proxy_header(request: Request) -> str | None:
    """Check if a trusted reverse proxy sent the configured auth header.

    Security model:
    - If TRUSTED_PROXY_IPS is configured: only accept the header from those IPs/CIDRs.
      Requests from any other source have the header ignored regardless of its value.
    - If TRUSTED_PROXY_IPS is NOT configured: accept from any source (backward compat)
      but startup emits a warning. This is insecure — any LAN client can forge the header.
    """
    config = getattr(request.app.state, "config", None)
    if not config or not config.auth_proxy_header:
        return None

    header_value = request.headers.get(config.auth_proxy_header)
    if not header_value:
        return None

    if not config.trusted_proxy_ips:
        log.warning(
            "Proxy header '%s' ignored — TRUSTED_PROXY_IPS not configured (fail-closed)",
            config.auth_proxy_header,
        )
        return None

    client_ip = request.client.host if request.client else ""
    if not _is_trusted_proxy(client_ip, config.trusted_proxy_ips):
        log.debug(
            "Proxy header '%s' ignored — source %s not in TRUSTED_PROXY_IPS",
            config.auth_proxy_header, client_ip,
        )
        return None

    return header_value


def _check_session(request: Request) -> str | None:
    """Check if request has a valid session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token and token in _sessions:
        session = _sessions[token]
        if session["expires"] > datetime.now(timezone.utc).timestamp():
            return session["user"]
        del _sessions[token]
    return None


def check_auth(request: Request) -> str | None:
    """Check all auth methods. Returns username or None."""
    config = getattr(request.app.state, "config", None)
    if not config or not config.login_required:
        return "anonymous"

    # 1. Proxy header (trusted reverse proxy)
    proxy_user = _check_proxy_header(request)
    if proxy_user:
        return proxy_user

    # 2. API key (programmatic access)
    if config.api_key and secrets.compare_digest(request.headers.get("X-API-Key", ""), config.api_key):
        return "api"

    # 3. Session cookie (local login)
    session_user = _check_session(request)
    if session_user:
        return session_user

    return None


@router.post("/auth/login")
async def login(body: LoginRequest, request: Request):
    """Login with username and password. Returns a session cookie."""
    config = request.app.state.config

    if not config.login_required:
        return {"user": "anonymous", "message": "Auth not configured"}

    if body.username != config.admin_user or body.password != config.admin_pass:
        return JSONResponse(status_code=401, content={"detail": "Invalid credentials"})

    # Clean up expired sessions and enforce max count
    now = datetime.now(timezone.utc).timestamp()
    expired = [k for k, v in _sessions.items() if v["expires"] <= now]
    for k in expired:
        del _sessions[k]
    if len(_sessions) >= MAX_SESSIONS:
        return JSONResponse(status_code=429, content={"detail": "Too many active sessions"})

    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "user": body.username,
        "expires": now + SESSION_MAX_AGE,
    }

    response = JSONResponse(content={"user": body.username})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=bool(config.auth_proxy_header),
        path="/",
    )
    return response


@router.post("/auth/logout")
async def logout(request: Request):
    """Clear session cookie."""
    token = request.cookies.get(SESSION_COOKIE)
    if token and token in _sessions:
        del _sessions[token]

    response = JSONResponse(content={"message": "Logged out"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/auth/me")
async def auth_me(request: Request):
    """Check current auth status. Returns user or 401."""
    user = check_auth(request)
    config = request.app.state.config

    if user is None:
        return JSONResponse(status_code=401, content={
            "authenticated": False,
            "login_required": config.login_required,
        })

    return {
        "authenticated": True,
        "user": user,
        "login_required": config.login_required,
    }
