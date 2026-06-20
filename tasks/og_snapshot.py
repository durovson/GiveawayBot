import logging
import os
import asyncio
from datetime import datetime
from database import db
from services.points_service import PointsService

logger = logging.getLogger(__name__)

async def backfill_og_rewards():
    """
    Identifies users in the users table who are in the OG snapshot
    but haven't been awarded the bonus yet, and awards it.
    """
    try:
        og_ids = await db.get_og_holder_ids()
        if not og_ids:
            logger.info("No OG holders found in snapshot, nothing to backfill")
            return

        now = datetime.now()
        backfilled_count = 0

        for user_id in og_ids:
            # We only care about users registered in our 'users' table
            user = await db.get_user_by_telegram_id(user_id)
            if not user:
                continue

            # Award bonus if not yet awarded OR if og_bonus_amount is 0
            if not user.get("og_bonus_awarded_at") or not user.get("og_bonus_amount"):
                success = await db.update_user_fields(
                    user_id,
                    og_bonus_awarded_at=now.isoformat(),
                    og_bonus_amount=50
                )
                if success:
                    # Recalculate points (PointsService now uses is_og_holder which is True)
                    await PointsService.recalculate_points(user_id)
                    backfilled_count += 1
                else:
                    logger.error(f"Failed to award OG bonus to {user_id}")

        if backfilled_count > 0:
            logger.info("OG Bonus backfill complete. Awarded to %s users.", backfilled_count)
        else:
            logger.info("OG Bonus backfill: No new users to award.")

    except Exception as e:
        logger.error("Error during OG rewards backfill: %s", e, exc_info=True)

async def create_og_snapshot_once():
    """
    Creates a snapshot of OG holders (users in OTC chat) exactly once.
    All users known to the bot (users, participants, etc.) are candidates.
    """
    try:
        # Import loader here to avoid circular dependencies or startup issues in non-bot contexts
        import loader

        # 1. Check if snapshot already exists
        count = await db.get_og_snapshot_count()
        if count > 0:
            logger.info("OG snapshot already exists (%s users), skipping creation. Running backfill...", count)
            await backfill_og_rewards()
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

            # 5. Run backfill
            await backfill_og_rewards()
        else:
            logger.info("No OG holders identified among %s users", len(user_ids))

    except Exception as e:
        logger.error("Error creating OG snapshot: %s", e, exc_info=True)
