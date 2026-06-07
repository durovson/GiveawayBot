import os
import logging
from datetime import datetime
import loader
from database import db
from services.points_service import PointsService

logger = logging.getLogger(__name__)

class HolderService:
    @staticmethod
    async def verify_holder_status(user_id: int):
        """
        Verifies if a user is a member of the holders chat.
        If verified for the first time, awards the holder bonus.
        """
        otc_chat_id = os.environ.get("OTC_CHAT_ID")
        if not otc_chat_id:
            logger.error("OTC_CHAT_ID is not set in environment variables")
            return False

        try:
            member = await loader.bot.get_chat_member(otc_chat_id, user_id)
            is_member = member.status in ["member", "administrator", "creator"]

            if is_member:
                # Check if already verified
                user = await db.get_user_by_telegram_id(user_id)
                if user and not user.get("holder_verified_at"):
                    # First time verification
                    now = datetime.now()

                    # Update users table
                    await db.update_user_fields(user_id, holder_verified_at=now)

                    # Update points table
                    await db.upsert_points(
                        user_id,
                        is_holder=True,
                        holder_bonus=150
                    )

                    # Recalculate RP
                    await PointsService.recalculate_points(user_id)
                    logger.info(f"User {user_id} verified as holder for the first time. Bonus awarded.")

                return True

            return False

        except Exception as e:
            logger.error(f"Error verifying holder status for user {user_id}: {e}")
            return False
