import asyncio
import logging
import aiohttp
import json
from database import db
from loader import bot, ADMIN_IDS
from services.leaderboard import LeaderboardService
from utils import normalize_to_raw

logger = logging.getLogger(__name__)

API_URL = "https://stickers.tools/api/v1/launching/packs/0:81abce045d81dc32c42aebc27b1ad6898bb4f89306231d2b58031908a4c267c7/holders"

async def fetch_holders():
    def extract_wallet(item):
        if isinstance(item, dict):
            return item.get("wallet") or item.get("holder") or item.get("address") or item.get("owner")
        return None

    def extract_packs(item):
        if isinstance(item, dict):
            return item.get("packs") or item.get("packsCount") or item.get("count") or item.get("balance") or 0
        return 0

    holders = []
    offset = 0
    limit = 100
    retries = 5

    def extract_page(payload):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("holders", "items", "data"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    async with aiohttp.ClientSession() as session:
        while True:
            url = f"{API_URL}?offset={offset}&limit={limit}"
            payload = None
            page = []

            for attempt in range(1, retries + 1):
                try:
                    async with session.get(url, timeout=30) as response:
                        if response.status != 200:
                            if attempt == retries:
                                return holders
                            await asyncio.sleep(attempt)
                            continue

                        payload = await response.json()
                        page = extract_page(payload)

                        total_value = payload.get("total") if isinstance(payload, dict) else None
                        if isinstance(total_value, int):
                            logger.info("HOLDERS_RESPONSE_TYPE=%s HOLDERS_TOTAL=%s", type(payload).__name__, total_value)
                        else:
                            logger.info("HOLDERS_RESPONSE_TYPE=%s", type(payload).__name__)

                        break
                except (asyncio.TimeoutError, aiohttp.ClientError, json.JSONDecodeError):
                    if attempt == retries:
                        return holders
                    await asyncio.sleep(attempt)

            valid_count = 0
            for row in page:
                if not isinstance(row, dict):
                    continue
                wallet = extract_wallet(row)
                if not wallet:
                    continue
                try:
                    normalized = normalize_to_raw(wallet)
                except Exception:
                    continue
                packs = int(extract_packs(row) or 0)
                valid_count += 1
                holders.append({"wallet": normalized, "packs": packs})
            logger.info("HOLDERS_VALID=%s", valid_count)

            has_more = payload.get("hasMore") if isinstance(payload, dict) else None
            if has_more is False:
                break
            if len(page) < limit:
                break
            offset += limit
            await asyncio.sleep(0.1)

    return holders

async def daily_sync_task(bot):
    """Background task to sync holders from Stickers Tools API daily."""
    logger.info("Starting daily sync task")
    while True:
        try:
            holders = await fetch_holders()

            if holders:
                await db.update_setting("cached_holders", json.dumps(holders))
                LeaderboardService.invalidate_cache()
                await db.save_snapshot(holders)
                logger.info("HOLDERS_FETCH_DONE total=%s", len(holders))
            else:
                logger.warning("Holders API returned empty dataset. Skipping update.")

        except Exception as e:
            logger.error(f"Error in daily_sync_task: {e}", exc_info=True)
        except asyncio.CancelledError:
            break

        # Sleep for 24 hours
        await asyncio.sleep(24 * 3600)
