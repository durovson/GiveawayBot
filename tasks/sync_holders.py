import asyncio
import logging
import aiohttp
import json
from database import db
from loader import bot, ADMIN_IDS

logger = logging.getLogger(__name__)

API_URL = "https://stickers.tools/api/v1/launching/packs/0:81abce045d81dc32c42aebc27b1ad6898bb4f89306231d2b58031908a4c267c7/holders"

async def fetch_holders():
    holders = []
    offset = 0
    limit = 30

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(f"{API_URL}?offset={offset}&limit={limit}", timeout=15) as response:
                    if response.status != 200:
                        logger.error(f"Error fetching holders: {response.status}")
                        break
                        
                    data = await response.json()
                    
                    current_holders = data.get("holders", data.get("result", []))
                    has_more = data.get("hasMore", data.get("has_more", False))
                    
                    if not current_holders:
                        logger.info(f"Pagination finished. Total holders collected: {len(holders)}")
                        break
                    
                    holders.extend(current_holders)
                    
                    logger.info(f"Collected {len(current_holders)} holders at offset {offset}")

                    if not has_more:
                        logger.info(f"Reached the last page (hasMore is False). Total holders collected: {len(holders)}")
                        break
                        
                    offset += len(current_holders)
                    
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Exception fetching holders at offset {offset}: {e}")
                break
                
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

                # Also save snapshot for history
                await db.save_snapshot({"data": holders})
                logger.info("Holders saved successfully.")
            else:
                logger.warning("No holders fetched. Skipping update.")

        except Exception as e:
            logger.error(f"Error in daily_sync_task: {e}", exc_info=True)

        # Sleep for 24 hours
        logger.info("Daily sync task sleeping for 24 hours.")
        await asyncio.sleep(24 * 3600)
