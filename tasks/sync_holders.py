import asyncio
import logging
import aiohttp
import json
from database import db
from loader import bot, ADMIN_IDS
from services.leaderboard import LeaderboardService

logger = logging.getLogger(__name__)

API_URL = "https://stickers.tools/api/v1/launching/packs/0:81abce045d81dc32c42aebc27b1ad6898bb4f89306231d2b58031908a4c267c7/holders"

async def fetch_holders():
    holders = []
    offset = 0
    limit = 100
    retries = 5

    async with aiohttp.ClientSession() as session:
        while True:
            url = f"{API_URL}?offset={offset}&limit={limit}"
            data = None
            page = []

            for attempt in range(1, retries + 1):
                try:
                    async with session.get(url, timeout=30) as response:
                        if response.status != 200:
                            if attempt == retries:
                                return holders
                            await asyncio.sleep(attempt)
                            continue

                        data = await response.json()
                        if isinstance(data, list):
                            page = data
                        elif isinstance(data, dict):
                            page = (
                                data.get("holders")
                                or data.get("result")
                                or data.get("items")
                                or data.get("data")
                                or []
                            )
                        else:
                            page = []
                        break
                except (asyncio.TimeoutError, aiohttp.ClientError, json.JSONDecodeError):
                    if attempt == retries:
                        return holders
                    await asyncio.sleep(attempt)

            for row in page:
                wallet = row.get("wallet") or row.get("address") or row.get("owner")
                packs = row.get("packs") or row.get("packsCount") or row.get("count") or row.get("balance") or 0
                if wallet:
                    holders.append({"wallet": wallet, "packs": packs})

            has_more = data.get("hasMore") if isinstance(data, dict) else None
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
                logger.info(f"Holders synchronized: {len(holders)}")
            else:
                logger.warning("No holders fetched. Skipping update.")

        except Exception as e:
            logger.error(f"Error in daily_sync_task: {e}", exc_info=True)
        except asyncio.CancelledError:
            break

        # Sleep for 24 hours
        await asyncio.sleep(24 * 3600)
