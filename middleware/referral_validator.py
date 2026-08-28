import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from datetime import datetime, timedelta
import pytz

from database import db
from services.referral_service import ReferralService
from services.points_service import PointsService

logger = logging.getLogger(__name__)

class ReferralValidatorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        user_id = user.id

        try:
            user_data = await db.get_user_by_telegram_id(user_id)
            data["user_data"] = user_data

            if user_data:
                # FIX #4 — Auto Update Names
                if user_data.get("username") != user.username or user_data.get("first_name") != user.first_name:
                    await PointsService.update_username(user_id, user.username, user.first_name)
                    logger.debug(f"User {user_id} profile synced")

                # Referral Activation Logic
                if (
                    user_data.get("referrer_id")
                    and user_data.get("wallet_connected_at")
                    and user_data.get("referral_status") != "active"
                ):
                    wallet_connected_at = user_data["wallet_connected_at"]

                    # Handle string or datetime
                    if isinstance(wallet_connected_at, str):
                        wallet_connected_at = datetime.fromisoformat(wallet_connected_at.replace("Z", "+00:00"))

                    # Use UTC for comparison
                    now = datetime.now(pytz.UTC)
                    if wallet_connected_at.tzinfo is None:
                        wallet_connected_at = pytz.UTC.localize(wallet_connected_at)

                    if now - wallet_connected_at >= timedelta(hours=24):
                        # Activate referral
                        await ReferralService.activate_referral(user_id)
                        logger.info(f"Referral for user {user_id} activated via middleware activity check.")

        except Exception as e:
            logger.error(f"Error in ReferralValidatorMiddleware: {e}")

        return await handler(event, data)
