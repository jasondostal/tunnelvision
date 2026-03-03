"""TunnelVision REST API — the visibility layer."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api import __version__
from api.config import load_config
from api.routes import auth, health, vpn, qbt, system, config as config_routes, provider, setup, connect, metrics, control, settings, speedtest, backup, events


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    from api.services.mqtt import get_mqtt_service

    app.state.config = load_config()
    app.state.started_at = time.time()

    # Start MQTT if configured
    mqtt_svc = get_mqtt_service()
    mqtt_svc.start()

    yield

    # Shutdown
    mqtt_svc.stop()


app = FastAPI(
    title="TunnelVision",
    description="All-in-one qBittorrent + WireGuard VPN + API",
    version=__version__,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS — allow dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Auth middleware — layered: proxy header → API key → session cookie
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Authentication: local login, proxy header bypass, or API key."""
    from api.routes.auth import check_auth

    config = getattr(request.app.state, "config", None)
    if not config:
        return await call_next(request)

    path = request.url.path

    # Always open: auth endpoints, setup, docs, metrics, static assets
    open_paths = ("/api/v1/auth/", "/api/v1/setup/", "/api/docs", "/api/redoc", "/api/openapi.json", "/metrics")
    if any(path.startswith(p) for p in open_paths) or not path.startswith("/api/"):
        return await call_next(request)

    # Check API key first (programmatic access — Homepage, HACS, Prometheus)
    if config.api_key and request.headers.get("X-API-Key") == config.api_key:
        return await call_next(request)

    # If API key is required and not provided, reject
    if config.api_auth_required and not request.headers.get("X-API-Key"):
        # Fall through to session/proxy check if login is also configured
        if not config.login_required:
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid API key"})

    # Check login auth (proxy header, session cookie)
    if config.login_required:
        user = check_auth(request)
        if user is None:
            return JSONResponse(status_code=401, content={"detail": "Authentication required"})

    return await call_next(request)


# Mount API routes
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(vpn.router, prefix="/api/v1", tags=["vpn"])
app.include_router(qbt.router, prefix="/api/v1", tags=["qbittorrent"])
app.include_router(system.router, prefix="/api/v1", tags=["system"])
app.include_router(config_routes.router, prefix="/api/v1", tags=["config"])
app.include_router(provider.router, prefix="/api/v1", tags=["provider"])
app.include_router(setup.router, prefix="/api/v1", tags=["setup"])
app.include_router(connect.router, prefix="/api/v1", tags=["connect"])
app.include_router(control.router, prefix="/api/v1", tags=["control"])
app.include_router(settings.router, prefix="/api/v1", tags=["settings"])
app.include_router(speedtest.router, prefix="/api/v1", tags=["speedtest"])
app.include_router(backup.router, prefix="/api/v1", tags=["backup"])
app.include_router(events.router, prefix="/api/v1", tags=["events"])
app.include_router(metrics.router, tags=["metrics"])  # /metrics at root, no /api/v1 prefix

# Mount UI static files (if built)
try:
    app.mount("/", StaticFiles(directory="/app/ui/dist", html=True), name="ui")
except Exception:
    pass  # UI not built yet — API-only mode


@app.get("/api")
async def api_root():
    """API root — version and available endpoints."""
    return {
        "name": "TunnelVision",
        "version": __version__,
        "endpoints": {
            "health": "/api/v1/health",
            "vpn_status": "/api/v1/vpn/status",
            "vpn_ip": "/api/v1/vpn/ip",
            "vpn_check": "/api/v1/vpn/check",
            "vpn_server": "/api/v1/vpn/server",
            "vpn_account": "/api/v1/vpn/account",
            "vpn_servers": "/api/v1/vpn/servers",
            "vpn_connect": "/api/v1/vpn/connect",
            "vpn_rotate": "/api/v1/vpn/rotate",
            "vpn_reconnect": "/api/v1/vpn/reconnect",
            "vpn_configs": "/api/v1/vpn/configs",
            "qbt_status": "/api/v1/qbt/status",
            "system": "/api/v1/system",
            "config": "/api/v1/config",
            "metrics": "/metrics",
            "docs": "/api/docs",
        },
    }
