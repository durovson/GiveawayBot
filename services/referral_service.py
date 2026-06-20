import secrets
import string
import logging
from database import db
from datetime import datetime
from services.points_service import PointsService

logger = logging.getLogger(__name__)

class ReferralService:
    ALPHABET = string.ascii_uppercase + string.digits

    @classmethod
    def generate_ref_code(cls):
        """Generates a 6-character alphanumeric referral code."""
        return ''.join(secrets.choice(cls.ALPHABET) for _ in range(6))

    @classmethod
    async def get_or_create_ref_code(cls, user_id: int):
        """Retrieves an existing ref_code or generates a new one if missing."""
        user = await db.get_user_by_telegram_id(user_id)
        if user and user.get("ref_code"):
            return user["ref_code"]

        # Generate a unique code
        while True:
            code = cls.generate_ref_code()
            existing = await db.get_user_by_ref_code(code)
            if not existing:
                break

        await db.update_user_fields(user_id, ref_code=code)
        return code

    @classmethod
    async def process_start_param(cls, user_id: int, start_param: str):
        """Processes the 'ref_' start parameter for new users."""
        if not start_param or not start_param.startswith("ref_"):
            return

        ref_code = start_param.replace("ref_", "")

        # 1. Check if user already has a referrer
        user = await db.get_user_by_telegram_id(user_id)
        if user and user.get("referrer_id"):
            logger.info(f"User {user_id} already has a referrer: {user['referrer_id']}")
            return

        # 2. Find the owner of the ref_code
        referrer = await db.get_user_by_ref_code(ref_code)
        if not referrer:
            logger.warning(f"Invalid referral code: {ref_code}")
            return

        referrer_id = referrer["telegram_id"]

        # Anti-abuse: cannot refer self
        if referrer_id == user_id:
            logger.warning(f"User {user_id} tried to refer themselves.")
            return

        # 3. Register the referral
        await db.update_user_fields(user_id, referrer_id=referrer_id)
        await db.create_referral(referrer_id=referrer_id, referred_id=user_id)

        logger.info(f"User {user_id} referred by {referrer_id}")

    @classmethod
    async def activate_referral(cls, referred_id: int):
        """
        Activates a referral:
        - Updates user status to 'active'
        - Increments active_referrals for referrer
        - Recalculates points for referrer
        """
        user = await db.get_user_by_telegram_id(referred_id)
        if not user or user.get("referral_status") == "active":
            return

        referrer_id = user.get("referrer_id")
        if not referrer_id:
            return

        now = datetime.now()

        # 1. Update referred user status
        await db.update_user_fields(
            referred_id,
            referral_status="active",
            referral_validated_at=now.isoformat()
        )
        await db.update_referral_status(referred_id, status="active", activated_at=now)

        # 2. Increment active referrals for referrer in points table
        referrer_points = await db.get_points(referrer_id)
        current_active = referrer_points.get("active_referrals", 0) if referrer_points else 0

        await db.upsert_points(
            referrer_id,
            active_referrals=current_active + 1
        )

        # 3. Recalculate RP for referrer
        await PointsService.recalculate_points(referrer_id)

        logger.info(f"Referral activated: {referred_id} (referred by {referrer_id})")
