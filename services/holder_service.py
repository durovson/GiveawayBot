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
        If verified for the first time, awards the OG bonus (tracked via og_bonus_awarded_at).
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
                    is_og = await db.is_og_holder(user_id)

                    # Update user verification status
                    update_fields = {"holder_verified_at": now.isoformat()}
                    if is_og:
                        update_fields["og_bonus_awarded_at"] = now.isoformat()

                    success = await db.update_user_fields(user_id, **update_fields)
                    if not success:
                        logger.error(f"Failed to update user fields for {user_id}")
                        return False

                    # Mark as holder in points table
                    await db.upsert_points(
                        user_id,
                        is_holder=True
                    )

                    # Recalculate RP
                    await PointsService.recalculate_points(user_id)
                    logger.info(f"User {user_id} verified as holder for the first time. OG: {is_og}")

                return True

            return False

        except Exception as e:
            logger.error(f"Error verifying holder status for user {user_id}: {e}")
            return False
