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
    retries = 3

    async with aiohttp.ClientSession() as session:
        while True:
            url = f"{API_URL}?offset={offset}&limit={limit}"

            for attempt in range(1, retries + 1):
                try:
                    async with session.get(url, timeout=30) as response:
                        if response.status != 200:
                            logger.error(f"HOLDERS_FETCH_BAD_STATUS status={response.status} offset={offset}")
                            if attempt == retries:
                                return holders
                            await asyncio.sleep(attempt)
                            continue

                        data = await response.json()
                        page = data.get("holders") or data.get("result") or data.get("items") or []

                        if not page:
                            logger.info(f"HOLDERS_FETCH_DONE total={len(holders)} offset={offset}")
                            return holders

                        normalized = []
                        for row in page:
                            wallet = row.get("wallet") or row.get("address") or row.get("owner")
                            packs = row.get("packs") or row.get("count") or row.get("packsCount") or 0
                            if wallet:
                                normalized.append({"wallet": wallet, "packs": packs})

                        holders.extend(normalized)
                        logger.info(f"HOLDERS_FETCH_PAGE offset={offset} page_size={len(page)} total={len(holders)}")

                        if len(page) < limit:
                            logger.info(f"HOLDERS_FETCH_LAST_PAGE total={len(holders)}")
                            return holders

                        offset += limit
                        await asyncio.sleep(0.1)
                        break
                except Exception as e:
                    logger.error(f"HOLDERS_FETCH_EXCEPTION offset={offset} attempt={attempt} err={e}")
                    if attempt == retries:
                        return holders
                    await asyncio.sleep(attempt)

    return holders

async def daily_sync_task(bot):
    """Background task to sync holders from Stickers Tools API daily."""
    logger.info("Starting daily sync task")
    while True:
        try:
            logger.info("Fetching holders from Stickers Tools API...")
            holders = await fetch_holders()

            if holders:
                logger.info(f"Successfully fetched {len(holders)} holders. Saving to cache...")
                # Save to settings table for leaderboard display
                await db.update_setting("cached_holders", json.dumps(holders))
                LeaderboardService.invalidate_cache()

                # Also save snapshot for history
                await db.save_snapshot(holders)
                logger.info("Holders saved successfully.")
            else:
                logger.warning("No holders fetched. Skipping update.")

        except Exception as e:
            logger.error(f"Error in daily_sync_task: {e}", exc_info=True)

        # Sleep for 24 hours
        logger.info("Daily sync task sleeping for 24 hours.")
        await asyncio.sleep(24 * 3600)
