"""Speed test endpoint — measure tunnel throughput."""

import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter()

# Use a well-known CDN file for download speed testing
TEST_URL = "https://speed.cloudflare.com/__down?bytes=10000000"  # 10MB
TEST_BYTES = 10_000_000


class SpeedTestResponse(BaseModel):
    download_mbps: float = Field(description="Download speed in Mbps")
    download_bytes: int = Field(description="Bytes downloaded")
    duration_seconds: float = Field(description="Test duration in seconds")
    test_url: str = ""


@router.post("/vpn/speedtest", response_model=SpeedTestResponse)
async def run_speed_test():
    """Run a quick download speed test through the VPN tunnel.

    Downloads a 10MB test file from Cloudflare and measures throughput.
    Takes ~5-15 seconds depending on connection speed.
    """
    start = time.monotonic()
    total_bytes = 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("GET", TEST_URL) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    total_bytes += len(chunk)
    except Exception:
        pass

    elapsed = time.monotonic() - start
    mbps = (total_bytes * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0

    return SpeedTestResponse(
        download_mbps=round(mbps, 2),
        download_bytes=total_bytes,
        duration_seconds=round(elapsed, 2),
        test_url=TEST_URL,
    )
