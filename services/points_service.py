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

                # Try to get username and display_name from user record or Telegram
                username = user.get("username")
                first_name = user.get("first_name")

                if not username or not first_name:
                    try:
                        tg_user = await loader.bot.get_chat(user_id)
                        username = tg_user.username
                        first_name = tg_user.first_name
                    except Exception:
                        pass

                if username:
                    display_name = f"@{username}"
                elif first_name:
                    display_name = first_name
                else:
                    display_name = f"User {user_id}"

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
        """Updates username and display_name in users and points tables."""
        if username:
            display = f"@{username}"
        elif first_name:
            display = first_name
        else:
            display = f"User {user_id}"

        # Update users table
        await db.update_user_fields(
            user_id,
            username=username,
            first_name=first_name
        )

        # Update points table
        await db.upsert_points(
            user_id=user_id,
            username=username,
            display_name=display
        )
