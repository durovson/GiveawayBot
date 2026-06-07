import logging
import loader
from database import db
from datetime import datetime

logger = logging.getLogger(__name__)

class PointsService:
    @staticmethod
    async def recalculate_points(user_id: int):
        """
        Recalculates and updates total points for a user based on the formula:
        RP = (packs * 10) + (active_referrals * 5) + holder_bonus + referral_income
        """
        try:
            # 1. Get current data from points table
            points_data = await db.get_points(user_id)
            if not points_data:
                # If no record in points table, ensure user exists and init points
                await db.ensure_user_exists(user_id)
                points_data = {
                    "user_id": user_id,
                    "packs": 0,
                    "active_referrals": 0,
                    "holder_bonus": 0,
                    "referral_income": 0,
                    "is_holder": False
                }

            # 2. Extract values
            packs = points_data.get("packs", 0)
            active_referrals = points_data.get("active_referrals", 0)
            holder_bonus = points_data.get("holder_bonus", 0)
            referral_income = points_data.get("referral_income", 0)

            # 3. Calculate RP
            total_points = (packs * 10) + (active_referrals * 5) + holder_bonus + referral_income

            # 4. Update the points table (only point-related data)
            await db.upsert_points(
                user_id=user_id,
                total_points=total_points
            )

            logger.info(f"RP recalculated for user {user_id}: {total_points}")
            return total_points

        except Exception as e:
            logger.error(f"Error recalculating points for user {user_id}: {e}")
            return None

    @staticmethod
    async def update_username(user_id: int, username: str, first_name: str):
        """Updates user profile info strictly in the users table."""
        # Update users table - this is the source of truth for user names
        await db.update_user_fields(
            user_id,
            username=username,
            first_name=first_name
        )
