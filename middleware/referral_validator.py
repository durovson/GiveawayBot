import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
import pytz

from database import db
from services.localization import get_locale_by_lang
from services.referral_service import ReferralService
from services.points_service import PointsService

logger = logging.getLogger(__name__)


_GIVEAWAY_REQUIRED_STATE = {
    "recheck_admin": "WAITING_FOR_BOT_ADMIN",
    "access_all": "WAITING_FOR_ACCESS_TYPE",
    "access_whitelist": "WAITING_FOR_ACCESS_TYPE",
    "confirm_prizes": "ENTER_PRIZES",
    "confirm_giveaway": "CONFIRMATION",
}

_GIVEAWAY_PREFIX_STATES = (
    ("chat_", "SELECT_CHAT"),
    ("kind_", "SELECT_GIVEAWAY_KIND"),
    ("type_", "SELECT_TYPE"),
    ("val_", "SELECT_MODE_VALUE"),
    ("win_", "SELECT_WINNERS_COUNT"),
    ("edit_", "CONFIRMATION"),
)

_GIVEAWAY_REQUIRED_FIELDS = {
    "kind_": ("chat_id", "title"),
    "recheck_admin": ("chat_id", "title", "kind", "mandatory_channels"),
    "access_all": ("chat_id", "title", "kind"),
    "access_whitelist": ("chat_id", "title", "kind"),
    "type_": ("chat_id", "title", "kind"),
    "val_": ("chat_id", "title", "kind", "gtype"),
    "win_": ("chat_id", "title", "kind", "gtype", "mode_value"),
    "confirm_prizes": (
        "chat_id",
        "title",
        "kind",
        "gtype",
        "mode_value",
        "winners_count",
        "prizes",
    ),
    "edit_": (
        "chat_id",
        "title",
        "kind",
        "gtype",
        "mode_value",
        "winners_count",
        "prizes",
    ),
    "confirm_giveaway": (
        "chat_id",
        "title",
        "kind",
        "gtype",
        "mode_value",
        "winners_count",
        "prizes",
    ),
}


def _giveaway_expected_state(callback_data: str | None) -> str | None:
    if not callback_data:
        return None
    expected = _GIVEAWAY_REQUIRED_STATE.get(callback_data)
    if expected:
        return expected
    for prefix, state_name in _GIVEAWAY_PREFIX_STATES:
        if callback_data.startswith(prefix):
            return state_name
    return None


def _giveaway_required_fields(callback_data: str) -> tuple[str, ...]:
    exact = _GIVEAWAY_REQUIRED_FIELDS.get(callback_data)
    if exact is not None:
        return exact
    for prefix, fields in _GIVEAWAY_REQUIRED_FIELDS.items():
        if prefix.endswith("_") and callback_data.startswith(prefix):
            return fields
    return ()


def _state_name(state_value: str | None) -> str | None:
    if not state_value:
        return None
    return state_value.rsplit(":", 1)[-1]


async def _expire_giveaway_session(
    callback: CallbackQuery,
    state,
    user_data: dict | None,
    missing_fields: tuple[str, ...] = (),
) -> None:
    if state:
        try:
            await state.clear()
        except Exception:
            logger.exception("Failed to clear stale giveaway FSM state")

    lang = (user_data or {}).get("language") or "en"
    texts = get_locale_by_lang(lang)

    if lang == "ru":
        screen_text = (
            "⚠️ <b>СЕССИЯ СОЗДАНИЯ РОЗЫГРЫША ИСТЕКЛА</b>\n\n"
            "Бот был перезапущен, поэтому незавершённые данные создания "
            "розыгрыша больше недоступны. Начните создание заново."
        )
        alert_text = "Сессия устарела после перезапуска бота. Начните создание заново."
    else:
        screen_text = (
            "⚠️ <b>GIVEAWAY SETUP SESSION EXPIRED</b>\n\n"
            "The bot was restarted, so the unfinished giveaway setup data "
            "is no longer available. Start creating the giveaway again."
        )
        alert_text = "The setup session expired after a bot restart. Start again."

    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts.get("giveaway_btn", "🎟 GIVEAWAY"),
        callback_data="create_giveaway",
        style="success",
    )
    builder.button(
        text=texts.get("giveaway_main_menu_btn", "MAIN MENU"),
        callback_data="main_menu",
        style="danger",
    )
    builder.adjust(1)

    try:
        await callback.answer(alert_text, show_alert=True)
    except Exception:
        pass

    message = callback.message
    if message:
        try:
            await message.edit_text(
                screen_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML",
            )
        except Exception:
            try:
                await message.answer(
                    screen_text,
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML",
                )
            except Exception:
                logger.exception("Failed to show expired giveaway-session screen")

    logger.warning(
        "Rejected stale/incomplete giveaway callback user_id=%s callback=%s missing=%s",
        callback.from_user.id,
        callback.data,
        ",".join(missing_fields) if missing_fields else "-",
    )


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

            # Giveaway creation currently uses MemoryStorage. Any Render restart
            # invalidates an unfinished FSM session, but Telegram leaves the old
            # inline keyboard on screen. Reject those stale callbacks instead of
            # letting them reconstruct a partial draft and crash with KeyError.
            if isinstance(event, CallbackQuery):
                expected_state = _giveaway_expected_state(event.data)
                if expected_state:
                    fsm_state = data.get("state")
                    current_state = await fsm_state.get_state() if fsm_state else None
                    draft = await fsm_state.get_data() if fsm_state else {}
                    required_fields = _giveaway_required_fields(event.data or "")
                    missing_fields = tuple(
                        key for key in required_fields if key not in draft
                    )

                    if (
                        _state_name(current_state) != expected_state
                        or missing_fields
                    ):
                        await _expire_giveaway_session(
                            event,
                            fsm_state,
                            user_data,
                            missing_fields,
                        )
                        return None

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
