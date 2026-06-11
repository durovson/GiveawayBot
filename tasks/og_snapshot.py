import logging
import os
import asyncio
import loader
from database import db

logger = logging.getLogger(__name__)

async def create_og_snapshot_once():
    """
    Creates a snapshot of OG holders (users in OTC chat) exactly once.
    Only users already registered in the bot are candidates.
    """
    try:
        # 1. Check if snapshot already exists
        count = await db.get_og_snapshot_count()
        if count > 0:
            logger.info("OG snapshot already exists (%s users), skipping", count)
            return

        logger.info("Starting OG snapshot creation...")

        # 2. Get all registered users
        users = await db.get_all_registered_users()
        if not users:
            logger.info("No registered users found for OG snapshot")
            return

        # 3. Check membership in OTC chat
        otc_chat_id = os.getenv("OTC_CHAT_ID")
        if not otc_chat_id:
            logger.error("OTC_CHAT_ID not set in environment, cannot create OG snapshot")
            return

        og_ids = []
        for user in users:
            telegram_id = user.get("telegram_id")
            if not telegram_id:
                continue

            try:
                member = await loader.bot.get_chat_member(otc_chat_id, telegram_id)
                if member.status in ["member", "administrator", "creator"]:
                    og_ids.append(telegram_id)

                # Avoid flood limits
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.debug("Could not get chat member status for %s: %s", telegram_id, e)

        # 4. Save snapshot
        if og_ids:
            await db.save_og_snapshot(og_ids)
            logger.info("OG snapshot created. Users=%s", len(og_ids))
        else:
            logger.info("No OG holders identified among %s users", len(users))

    except Exception as e:
        logger.error("Error creating OG snapshot: %s", e, exc_info=True)
