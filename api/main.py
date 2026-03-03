"""TunnelVision REST API — the visibility layer."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api import __version__
from api.config import load_config
from api.routes import health, vpn, qbt, system, config as config_routes, provider, setup, connect, metrics


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


# API key middleware (if configured)
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Optional API key authentication."""
    config = getattr(request.app.state, "config", None)
    if config and config.api_auth_required:
        # Skip auth for docs, health, setup, and UI static files
        path = request.url.path
        if path.startswith("/api/") and not path.startswith("/api/v1/setup/") and path not in ("/api/docs", "/api/redoc", "/api/openapi.json", "/metrics"):
            api_key = request.headers.get("X-API-Key", "")
            if api_key != config.api_key:
                return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


# Mount API routes
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(vpn.router, prefix="/api/v1", tags=["vpn"])
app.include_router(qbt.router, prefix="/api/v1", tags=["qbittorrent"])
app.include_router(system.router, prefix="/api/v1", tags=["system"])
app.include_router(config_routes.router, prefix="/api/v1", tags=["config"])
app.include_router(provider.router, prefix="/api/v1", tags=["provider"])
app.include_router(setup.router, prefix="/api/v1", tags=["setup"])
app.include_router(connect.router, prefix="/api/v1", tags=["connect"])
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
