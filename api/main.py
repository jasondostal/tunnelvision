"""TunnelVision REST API — the visibility layer."""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api import __version__
from api.config import load_config
from api.routes import health, vpn, qbt, system, config as config_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    app.state.config = load_config()
    app.state.started_at = time.time()
    yield


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
        # Skip auth for docs, health, and UI static files
        path = request.url.path
        if path.startswith("/api/") and path not in ("/api/docs", "/api/redoc", "/api/openapi.json"):
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
            "qbt_status": "/api/v1/qbt/status",
            "system": "/api/v1/system",
            "config": "/api/v1/config",
            "docs": "/api/docs",
        },
    }
