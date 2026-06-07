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
                # If no record in points table, initialize with basic info from users table
                user = await db.get_user_by_telegram_id(user_id)
                if not user:
                    logger.error(f"Cannot recalculate points: User {user_id} not found in database")
                    return

                # Try to get username and display_name from Telegram
                username = None
                display_name = str(user_id)
                try:
                    tg_user = await loader.bot.get_chat(user_id)
                    username = tg_user.username
                    if tg_user.username:
                        display_name = f"@{tg_user.username}"
                    elif tg_user.first_name:
                        display_name = tg_user.first_name
                except Exception:
                    pass

                points_data = {
                    "user_id": user_id,
                    "username": username,
                    "display_name": display_name,
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

            # 4. Update the points table
            await db.upsert_points(
                user_id=user_id,
                total_points=total_points,
                username=points_data.get("username"),
                display_name=points_data.get("display_name")
            )

            logger.info(f"RP recalculated for user {user_id}: {total_points}")
            return total_points

        except Exception as e:
            logger.error(f"Error recalculating points for user {user_id}: {e}")
            return None

    @staticmethod
    async def update_username(user_id: int, username: str, first_name: str):
        """Updates username and display_name in the points table."""
        if username:
            display = f"@{username}"
        elif first_name:
            display = first_name
        else:
            display = str(user_id)

        await db.upsert_points(
            user_id=user_id,
            username=username,
            display_name=display
        )
