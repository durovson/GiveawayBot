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
                async with session.get(f"{API_URL}?offset={offset}&limit={limit}") as response:
                    if response.status != 200:
                        logger.error(f"Error fetching holders: {response.status}")
                        break
                    data = await response.json()
                    current_holders = data.get("holders", [])
                    if not current_holders:
                        break
                    holders.extend(current_holders)
                    if not data.get("hasMore", False):
                        break
                    offset += len(current_holders)
            except Exception as e:
                logger.error(f"Exception fetching holders: {e}")
                break
    return holders

async def daily_sync_task(bot):
    while True:
        try:
            logger.info("Starting daily holders sync...")
            holders = await fetch_holders()

            # Save to settings as a cached JSON for leaderboard
            import json
            await db.update_setting("cached_holders", json.dumps(holders))

            # Snapshot check
            total_packs = sum(h.get("packsCount", 0) for h in holders)
            last_total = await db.get_setting("last_total_packs")
            last_total = int(last_total) if last_total else 0

            milestones = [333, 666, 1000]
            for m in milestones:
                if total_packs >= m > last_total:
                    # Trigger Snapshot
                    logger.info(f"Milestone {m} reached! Total packs: {total_packs}")
                    await db.save_snapshot({"milestone": m, "total_packs": total_packs, "holders": holders})

                    # Notify admins
                    linked_wallets = await db.get_all_linked_wallets()
                    wallet_to_user = {w['wallet_address']: w['telegram_id'] for w in linked_wallets}

                    report = f"🔥 <b>Milestone {m} reached!</b>\n\n"
                    for h in holders[:20]: # Top 20 for report
                        addr = h['address']
                        packs = h['packsCount']
                        tg_id = wallet_to_user.get(addr)
                        username = "Unknown"
                        if tg_id:
                            try:
                                user = await bot.get_chat(tg_id)
                                username = f"@{user.username}" if user.username else user.full_name
                            except:
                                username = f"ID:{tg_id}"
                        report += f"• {username} - {packs} packs - {addr[:6]}...{addr[-4:]}\n"

                    for admin_id in ADMIN_IDS:
                        try:
                            await bot.send_message(admin_id, report, parse_mode=ParseMode.HTML)
                        except:
                            pass

            await db.update_setting("last_total_packs", str(total_packs))
            logger.info("Daily sync completed.")

        except Exception as e:
            logger.error(f"Error in daily_sync_task: {e}")

        await asyncio.sleep(24 * 3600) # Wait 24 hours
