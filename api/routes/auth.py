"""Authentication — single-user local auth + reverse proxy bypass."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

# In-memory session store — single container, single process, this is fine
_sessions: dict[str, dict] = {}

SESSION_COOKIE = "tv_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days


class LoginRequest(BaseModel):
    username: str
    password: str


def _check_proxy_header(request: Request) -> str | None:
    """Check if reverse proxy sent a trusted auth header."""
    config = getattr(request.app.state, "config", None)
    if config and config.auth_proxy_header:
        return request.headers.get(config.auth_proxy_header)
    return None


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
    if config.api_key and request.headers.get("X-API-Key") == config.api_key:
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

    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "user": body.username,
        "expires": datetime.now(timezone.utc).timestamp() + SESSION_MAX_AGE,
    }

    response = JSONResponse(content={"user": body.username})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
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
