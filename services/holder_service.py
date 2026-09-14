import logging
import os

import loader
from config import HOLDER_CHAT_ID
from database import db
from services.points_service import PointsService

logger = logging.getLogger(__name__)

class HolderService:
    @staticmethod
    async def award_holder_join_bonus(user_id: int) -> bool:
        """Claim and apply the shared one-time 50 RP holders bonus."""
        awarded = await db.claim_holder_join_bonus(user_id)
        if not awarded:
            return False

        await db.upsert_points(user_id, is_holder=True)
        await PointsService.recalculate_points(user_id)
        logger.info("User %s received the holders-chat bonus", user_id)
        return True

    @staticmethod
    async def verify_holder_status(user_id: int):
        """
        Verifies if a user is a member of the holders chat.
        If membership is confirmed, atomically claims the shared holder bonus.
        """
        otc_chat_id = os.environ.get("OTC_CHAT_ID", str(HOLDER_CHAT_ID))

        try:
            member = await loader.bot.get_chat_member(otc_chat_id, user_id)
            is_member = member.status in ["member", "administrator", "creator"]

            if is_member:
                await HolderService.award_holder_join_bonus(user_id)
                return True

            return False

        except Exception as e:
            logger.error(f"Error verifying holder status for user {user_id}: {e}")
            return False
