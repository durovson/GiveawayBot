import asyncio
import logging
import aiohttp
from database import db
from loader import bot, ADMIN_IDS
from services.leaderboard import LeaderboardService
from utils import normalize_to_raw
import json

logger = logging.getLogger(__name__)

API_URL = "https://stickers.tools/api/v1/launching/packs/0:81abce045d81dc32c42aebc27b1ad6898bb4f89306231d2b58031908a4c267c7/holders"

async def fetch_holders():
    holders = []
    offset = 0
    limit = 30
    retries = 5

    total = 0
    total_held = 0
    has_more = False

    async with aiohttp.ClientSession() as session:
        while True:
            url = f"{API_URL}?offset={offset}&limit={limit}"
            payload = {}
            page = []

            for attempt in range(1, retries + 1):
                try:
                    async with session.get(url, timeout=30) as response:
                        if response.status != 200:
                            if attempt == retries:
                                return {"holders": holders, "total": 0, "totalHeld": 0, "hasMore": False}
                            await asyncio.sleep(attempt)
                            continue

                        response_json = await response.json()
                        payload = response_json.get("data", {}) if isinstance(response_json, dict) else {}
                        page = payload.get("holders", []) if isinstance(payload, dict) else []
                        has_more = payload.get("hasMore", False) if isinstance(payload, dict) else False
                        total = payload.get("total", 0) if isinstance(payload, dict) else 0
                        total_held = payload.get("totalHeld", 0) if isinstance(payload, dict) else 0

                        logger.info("HOLDERS_TOTAL=%s", total)
                        logger.info("HOLDERS_RECEIVED=%s", len(page))

                        break
                except (asyncio.TimeoutError, aiohttp.ClientError, json.JSONDecodeError):
                    if attempt == retries:
                        return {"holders": holders, "total": 0, "totalHeld": 0, "hasMore": False}
                    await asyncio.sleep(attempt)

            valid = []
            for item in page:
                if not isinstance(item, dict):
                    continue
                addr = item.get("addr")
                if not addr:
                    continue
                try:
                    valid.append({
                        "wallet": normalize_to_raw(addr),
                        "packs": item.get("count", 0),
                        "rank": item.get("rank")
                    })
                except Exception:
                    continue
            logger.info("HOLDERS_VALID=%s", len(valid))
            holders.extend(valid)

            if has_more is False:
                break
            if len(page) < limit:
                break
            offset += limit
            await asyncio.sleep(0.1)

    cached = {
        "holders": holders,
        "total": total,
        "totalHeld": total_held,
        "hasMore": has_more,
    }

    return cached

async def daily_sync_task(bot):
    """Background task to sync holders from Stickers Tools API daily."""
    logger.info("Starting daily sync task")
    while True:
        try:
            cached = await fetch_holders()
            holders = cached.get("holders", []) if isinstance(cached, dict) else []

            if holders:
                try:
                    await db.save_snapshot(holders)
                    await db.cleanup_old_snapshots(days=14)
                except Exception:
                    logger.exception("Snapshot save failed")

                LeaderboardService.invalidate_cache()
                logger.info("Holders snapshot updated")
            else:
                logger.warning("Holders API returned empty dataset. Skipping update.")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in daily_sync_task: {e}", exc_info=True)

        # Sleep for 24 hours
        await asyncio.sleep(24 * 3600)
