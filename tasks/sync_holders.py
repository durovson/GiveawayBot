import asyncio
import logging
import aiohttp
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
                    
                    if not current_holders:
                        logger.info(f"Pagination finished. Total holders collected: {len(holders)}")
                        break
                    
                    holders.extend(current_holders)
                    
                    if len(current_holders) < limit:
                        logger.info(f"Reached the last page. Total holders collected: {len(holders)}")
                        break
                        
                    offset += limit
                    
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Exception fetching holders at offset {offset}: {e}")
                break
                
    return holders
