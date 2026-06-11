import logging
import os
import asyncio
from datetime import datetime
import loader
from database import db
from services.points_service import PointsService

logger = logging.getLogger(__name__)

async def create_og_snapshot_once():
    """
    Creates a snapshot of OG holders (users in OTC chat) exactly once.
    All users known to the bot (users, participants, etc.) are candidates.
    """
    try:
        # 1. Check if snapshot already exists
        count = await db.get_og_snapshot_count()
        if count > 0:
            logger.info("OG snapshot already exists (%s users), skipping", count)
            return

        logger.info("Starting OG snapshot creation...")

        # 2. Get all known users
        user_ids = await db.get_all_known_users()
        if not user_ids:
            logger.info("No known users found for OG snapshot")
            return

        # 3. Check membership in OTC chat
        otc_chat_id = os.getenv("OTC_CHAT_ID")
        if not otc_chat_id:
            logger.error("OTC_CHAT_ID not set in environment, cannot create OG snapshot")
            return

        og_ids = []
        for telegram_id in user_ids:
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
            logger.info("OG snapshot saved. Users=%s", len(og_ids))

            # 5. Backfill OG Bonus and Recalculate RP
            now = datetime.now()
            backfilled_count = 0

            for user_id in og_ids:
                user = await db.get_user_by_telegram_id(user_id)
                if not user:
                    continue

                if not user.get("og_bonus_awarded_at"):
                    await db.update_user_fields(
                        user_id,
                        og_bonus_awarded_at=now
                    )
                    await PointsService.recalculate_points(user_id)
                    backfilled_count += 1

            logger.info("OG Bonus backfill complete. Awarded to %s users.", backfilled_count)
        else:
            logger.info("No OG holders identified among %s users", len(user_ids))

    except Exception as e:
        logger.error("Error creating OG snapshot: %s", e, exc_info=True)
