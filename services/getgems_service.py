import os
import time

import aiohttp

import loader

COLLECTION_ADDRESS = "EQDwLDJcRXegHyvvRHXouGrUODuF0eagnWzLvUMUSTw8tv3Y"

GETGEMS_API_KEY = os.getenv("GETGEMS_API_KEY")

API_URL = (
    f"https://api.getgems.io/public-api/v1/collection/stats/"
    f"{COLLECTION_ADDRESS}"
)

_stats_cache = None
_stats_cache_at = 0.0
CACHE_TTL_SECONDS = 60


def format_floor(value):
    try:
        return f"{int(float(value))}"
    except Exception:
        return "0"


def format_volume(value):
    try:
        value = float(value)

        if value >= 1000:
            return f"{value / 1000:.1f}K"

        return f"{value:.0f}"

    except Exception:
        return "0"


async def get_collection_stats():
    global _stats_cache, _stats_cache_at
    now = time.monotonic()
    if _stats_cache and now - _stats_cache_at < CACHE_TTL_SECONDS:
        return _stats_cache.copy()

    headers = {
        "accept": "application/json"
    }
    if GETGEMS_API_KEY:
        headers["Authorization"] = GETGEMS_API_KEY

    try:
        session = loader.http_session
        owns_session = session is None or session.closed
        if owns_session:
            session = aiohttp.ClientSession()
        try:
            async with session.get(
                API_URL,
                headers=headers,
                timeout=10
            ) as response:

                data = await response.json()

                stats = data["response"]

                result = {
                    "floor": format_floor(
                        stats["floorPrice"]
                    ),
                    "volume": format_volume(
                        stats["totalVolumeSold"]
                    )
                }
                _stats_cache = result
                _stats_cache_at = now
                return result.copy()
        finally:
            if owns_session:
                await session.close()

    except Exception:
        if _stats_cache:
            return _stats_cache.copy()
        return {
            "floor": "?",
            "volume": "?"
        }
