import asyncio
import html
import json
import logging
from datetime import datetime, timedelta

import pytz
from aiogram import Bot
from aiogram.enums import ChatType, ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import db
from utils import strip_custom_emojis

logger = logging.getLogger(__name__)

BOT_BROADCAST_CHAT_ID = 0
BROADCAST_BATCH_SIZE = 20
BROADCAST_BATCH_DELAY = 1.0


def _build_markup(notification: dict):
    builder = InlineKeyboardBuilder()
    has_buttons = False
    buttons = notification.get("custom_buttons") or []
    if isinstance(buttons, str):
        try:
            buttons = json.loads(buttons)
        except (TypeError, ValueError, json.JSONDecodeError):
            buttons = []

    for button in buttons:
        if not isinstance(button, dict):
            continue
        label = str(button.get("text") or "").strip()
        url = str(button.get("url") or "").strip()
        if label and url:
            builder.button(text=label, url=url)
            has_buttons = True

    if not buttons and notification.get("button_url"):
        builder.button(
            text=notification.get("button_text", "OPEN"),
            url=notification["button_url"],
        )
        has_buttons = True

    builder.adjust(1)
    return builder.as_markup() if has_buttons else None


def _build_text(notification: dict) -> str:
    return (
        f'┏<tg-emoji emoji-id="5273867703709361006">👿</tg-emoji>┅ / '
        f'{html.escape(str(notification.get("title") or "Ad"))} /\n'
        "┋\n"
        f'┣{html.escape(str(notification.get("text") or ""))}\n'
        "┋\n"
        "┗┅┅┅/ #NOTAPES /"
    )


async def _all_bot_user_ids() -> list[int]:
    if not db.client:
        return []

    result: list[int] = []
    offset = 0
    page_size = 1000
    while True:
        response = await (
            db.client.table("users")
            .select("telegram_id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = response.data or []
        for row in rows:
            try:
                result.append(int(row["telegram_id"]))
            except (KeyError, TypeError, ValueError):
                continue
        if len(rows) < page_size:
            break
        offset += page_size
    return result


async def _broadcast_to_bot_users(
    bot: Bot, text: str, reply_markup, notification_id: int
) -> tuple[int, int]:
    user_ids = await _all_bot_user_ids()
    sent = 0
    failed = 0

    async def send_one(user_id: int) -> bool:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )
            return True
        except Exception as exc:
            logger.debug(
                "Notification %s bot broadcast skipped user %s: %s",
                notification_id,
                user_id,
                exc,
            )
            return False

    for start in range(0, len(user_ids), BROADCAST_BATCH_SIZE):
        batch = user_ids[start : start + BROADCAST_BATCH_SIZE]
        results = await asyncio.gather(
            *(send_one(user_id) for user_id in batch),
            return_exceptions=False,
        )
        sent += sum(1 for ok in results if ok)
        failed += sum(1 for ok in results if not ok)
        if start + BROADCAST_BATCH_SIZE < len(user_ids):
            await asyncio.sleep(BROADCAST_BATCH_DELAY)

    logger.info(
        "Notification %s broadcast complete: %s sent, %s failed",
        notification_id,
        sent,
        failed,
    )
    return sent, failed


async def _send_to_chat(
    bot: Bot, notification: dict, text: str, reply_markup
) -> int:
    chat_id = int(notification["chat_id"])

    try:
        target_chat = await bot.get_chat(chat_id)
        if target_chat.type == ChatType.CHANNEL:
            text = strip_custom_emojis(text)
    except Exception:
        pass

    old_message_id = notification.get("last_message_id")
    if old_message_id and int(old_message_id) > 0:
        try:
            await bot.delete_message(
                chat_id=chat_id,
                message_id=int(old_message_id),
            )
        except Exception as exc:
            logger.warning(
                "Could not delete previous notification %s in chat %s: %s",
                old_message_id,
                chat_id,
                exc,
            )

    message = await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML,
    )
    return message.message_id


def _last_sent_at(notification: dict, now: datetime) -> datetime:
    last_sent = notification.get("last_sent")
    interval = float(notification.get("interval_minutes") or 60)

    if last_sent is None:
        return now - timedelta(minutes=interval)

    if isinstance(last_sent, str):
        parsed = datetime.fromisoformat(last_sent.replace("Z", "+00:00"))
    else:
        parsed = last_sent

    if parsed.tzinfo is None:
        parsed = pytz.UTC.localize(parsed)
    else:
        parsed = parsed.astimezone(pytz.UTC)
    return parsed


async def _process_notification(bot: Bot, notification: dict, now: datetime):
    notification_id = int(notification["id"])
    interval = float(notification.get("interval_minutes") or 60)
    if now < _last_sent_at(notification, now) + timedelta(minutes=interval):
        return

    text = _build_text(notification)
    reply_markup = _build_markup(notification)
    chat_id = notification.get("chat_id")

    try:
        if chat_id == BOT_BROADCAST_CHAT_ID:
            await _broadcast_to_bot_users(
                bot,
                text,
                reply_markup,
                notification_id,
            )
            last_message_id = 0
        elif chat_id is not None:
            last_message_id = await _send_to_chat(
                bot,
                notification,
                text,
                reply_markup,
            )
        else:
            logger.warning(
                "Notification %s has no target and was skipped",
                notification_id,
            )
            return

        await db.update_notification_stats(
            notification_id,
            last_sent=now,
            last_message_id=last_message_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to send notification %s: %s",
            notification_id,
            exc,
        )
        await db.update_notification_stats(
            notification_id,
            last_sent=now,
            last_message_id=0,
        )


async def check_periodic_notifications(bot: Bot):
    while True:
        try:
            now = datetime.now(pytz.UTC)
            active_notifications = await db.get_active_notifications()
            for notification in active_notifications:
                try:
                    await _process_notification(bot, notification, now)
                except Exception:
                    logger.exception(
                        "Unhandled error while processing notification %s",
                        notification.get("id"),
                    )
        except Exception:
            logger.exception("Periodic notification loop failed")

        await asyncio.sleep(60)
