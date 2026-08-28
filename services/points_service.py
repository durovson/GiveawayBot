import logging

from database import db
from utils import normalize_to_raw

logger = logging.getLogger(__name__)

class PointsService:
    @staticmethod
    async def recalculate_points(user_id: int):
        """
        Recalculates and updates total points for a user based on the new formula:
        RP = ((packs * 10) + (active_referrals * 5) + og_bonus) * multiplier
        """
        try:
            # 1. Get current data from points table and users table
            points_data = await db.get_points(user_id)
            user_data = await db.get_user_by_telegram_id(user_id)

            if not user_data:
                logger.error(f"User {user_id} not found in users table during recalculation")
                return None

            if not points_data:
                await db.ensure_user_exists(user_id)
                points_data = await db.get_points(user_id)
                if not points_data:
                    points_data = {
                        "packs": 0,
                        "active_referrals": 0
                    }

            # 2. Extract base values
            packs = points_data.get("packs", 0)
            active_referrals = points_data.get("active_referrals", 0)

            # 3. OG Bonus (O)
            # OG is determined by membership in og_holders_snapshot
            is_og = await db.is_og_holder(user_id)
            og_bonus = 50 if is_og else 0

            # 4. Retention Multiplier (C)
            multiplier = 1.0
            wallet = user_data.get("wallet_address")

            if wallet:
                try:
                    normalized_wallet = normalize_to_raw(wallet)
                    milestones = await db.get_milestones_data()
                    if milestones:
                        ms_map = {m["milestone"]: m["data"] for m in milestones}

                        def get_bal(ms_data, w):
                            if not ms_data:
                                return None
                            # Snapshot data is a list of {"wallet": "...", "packs": ...}
                            for item in ms_data:
                                if item.get("wallet") == w:
                                    return item.get("packs", 0)
                            return None

                        # Snapshot #3 (1000 sold)
                        if 1000 in ms_map and 666 in ms_map and 333 in ms_map:
                            bal_333 = get_bal(ms_map[333], normalized_wallet)
                            bal_666 = get_bal(ms_map[666], normalized_wallet)
                            bal_1000 = get_bal(ms_map[1000], normalized_wallet)

                            # Rule: continuous retention from 1 to 3
                            if (
                                bal_333 is not None
                                and bal_666 is not None
                                and bal_1000 is not None
                                and bal_333 > 0
                                and bal_666 >= bal_333
                                and bal_1000 >= bal_666
                            ):
                                multiplier = 1.5
                        # Snapshot #2 (666 sold)
                        elif 666 in ms_map and 333 in ms_map:
                            bal_333 = get_bal(ms_map[333], normalized_wallet)
                            bal_666 = get_bal(ms_map[666], normalized_wallet)

                            if (
                                bal_333 is not None
                                and bal_666 is not None
                                and bal_333 > 0
                                and bal_666 >= bal_333
                            ):
                                multiplier = 1.2
                except Exception as ex:
                    logger.error(f"Error calculating retention for user {user_id}: {ex}")

            # External RP (for example verified GRAM deposits) must survive
            # holder/referral recalculation.
            spent_points = points_data.get("spent_points", 0)
            external_points = points_data.get("external_points", 0)
            base_points = (packs * 10) + (active_referrals * 5) + og_bonus
            calculated_points = round(base_points * multiplier)
            total_points = max(0, calculated_points + external_points - spent_points)

            # 6. Update the points table
            await db.upsert_points(
                user_id=user_id,
                holder_bonus=og_bonus,
                total_points=total_points
            )

            logger.info(f"RP recalculated for user {user_id}: {total_points} (C={multiplier}, O={og_bonus})")
            return total_points

        except Exception as e:
            logger.error(f"Error recalculating points for user {user_id}: {e}")
            return None

    @staticmethod
    async def update_username(user_id: int, username: str, first_name: str):
        """Updates user profile info strictly in the users table."""
        await db.update_user_fields(
            user_id,
            username=username,
            first_name=first_name
        )
