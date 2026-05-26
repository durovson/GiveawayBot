import asyncio
import logging
import html
import os
import secrets
import pytz
from datetime import datetime, timedelta
from typing import List, Dict, Any

from aiogram import Bot, types
from aiogram.enums import ParseMode, ChatType
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

from database import db
from utils import strip_custom_emojis
from loader import ADMIN_IDS

logger = logging.getLogger(__name__)

# Use the first admin from loader as the primary notification recipient
ADMIN_ID = ADMIN_IDS[0]

async def complete_giveaway(giveaway_id: int, bot: Bot):
    try:
        # Atomic status update to prevent race conditions
        started = await db.try_start_giveaway_completion(giveaway_id)
        if not started:
            return

        giveaway = await db.get_giveaway(giveaway_id)
        if not giveaway:
            return

        participants = await db.get_participants(giveaway_id)
        safe_title = html.escape(giveaway["title"])

        if not participants:
            results_text = (
                f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ <b>/ {safe_title} /</b>\n"
                f"┋\n"
                f"┋ <b>Unfortunately, there were no humans...</b>\n"
                f"┋\n"
                f"┣<b>GIVEAWAY</b>\n"
                f"┣[ HUMANS.. NOT APES ]\n"
                f"┗┅┅┅/ #NOTAPES /"
            )
        else:
            # 4. Cryptographically strong shuffling
            secrets.SystemRandom().shuffle(participants)

            # Determine target winners count
            winners_count_target = min(len(participants), giveaway["winners_count"])

            # Winners are the first N participants
            winners = participants[:winners_count_target]

            # 5. Distribute prizes among selected winners
            prizes = giveaway["prizes"]
            winners_prizes = [[] for _ in range(len(winners))]

            # Distribute prizes cyclically
            for idx, prize in enumerate(prizes):
                w_idx = idx % len(winners)
                winners_prizes[w_idx].append(prize)

            # Prepare data for saving to DB and display
            winners_to_save = []
            winners_list_str = ""
            for idx, w in enumerate(winners):
                allocated_prizes = winners_prizes[idx]
                prizes_str = ", ".join(allocated_prizes)
                winners_to_save.append({
                    "giveaway_id": giveaway_id,
                    "user_id": w["user_id"],
                    "username": w["username"],
                    "prize": prizes_str
                })

                raw_username = w.get("username") or f"ID:{w['user_id']}"
                safe_username = html.escape(raw_username)
                if raw_username and not raw_username.startswith("ID:"):
                    mention = f"<b>@{safe_username}</b>"
                else:
                    mention = f"<b><a href=\"tg://user?id={w['user_id']}\">{safe_username}</a></b>"
                winners_list_str += f"┋<tg-emoji emoji-id=\"5274159185959872191\">👑</tg-emoji> {mention} — {html.escape(prizes_str)}\n"

            # Save winners
            await db.save_winners(giveaway_id, winners_to_save)

            results_text = (
                f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ <b>/ {safe_title} /</b>\n"
                f"┋<tg-emoji emoji-id=\"5422626434331990897\">🤩</tg-emoji> <b>GAME OVER!</b>\n"
                f"┋\n"
                f"{winners_list_str}"
                f"┋\n"
                f"┣<b>GIVEAWAY</b>\n"
                f"┣[ HUMANS.. NOT APES ]\n"
                f"┗┅┅┅/ #NOTAPES /"
            )

        messages = await db.get_giveaway_messages(giveaway_id)

        async def update_msg(msg):
            try:
                final_results_text = results_text
                try:
                    target_chat = await bot.get_chat(msg["chat_id"])
                    if target_chat.type == ChatType.CHANNEL:
                        final_results_text = strip_custom_emojis(results_text)
                except Exception:
                    pass

                # 1. Try to edit caption (for animations)
                try:
                    await bot.edit_message_caption(
                        chat_id=msg["chat_id"],
                        message_id=msg["message_id"],
                        caption=final_results_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=None
                    )
                    return
                except Exception:
                    pass

                # 2. Try to edit text (for plain messages)
                try:
                    await bot.edit_message_text(
                        chat_id=msg["chat_id"],
                        message_id=msg["message_id"],
                        text=final_results_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=None
                    )
                    return
                except Exception:
                    pass

                # 3. Fallback: send NEW message
                await bot.send_message(
                    chat_id=msg["chat_id"],
                    text=final_results_text,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to update or send message in chat {msg['chat_id']}: {e}")

        if messages:
            await asyncio.gather(*(update_msg(m) for m in messages))

        # Notify creator and admin
        notify_text = (
            f"<tg-emoji emoji-id=\"5258096772776991776\">⚙️</tg-emoji> <b>Giveaway «{safe_title}» finished!</b>\n\n"
            f"Results published in the group."
        )
        recipients = {giveaway["creator_id"], ADMIN_ID}
        for r_id in recipients:
            try:
                await bot.send_message(r_id, notify_text, parse_mode=ParseMode.HTML)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error in complete_giveaway for {giveaway_id}: {e}")
    finally:
        # Set final status
        await db.finish_giveaway(giveaway_id)

async def check_timed_giveaways(bot: Bot):
    while True:
        try:
            now = datetime.now(pytz.UTC) 
            expired_giveaways = await db.get_expired_giveaways(now)
            
            for giveaway in expired_giveaways:
                logger.info(f"Finishing giveaway {giveaway['id']}")
                await complete_giveaway(giveaway['id'], bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in check_timed_giveaways: {e}")
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise

async def check_periodic_notifications(bot: Bot):
    while True:
        try:
            now = datetime.now(pytz.UTC)
            active_notifications = await db.get_active_notifications()

            for notif in active_notifications:
                try:
                    last_sent = notif.get("last_sent")
                    interval = int(notif["interval_minutes"])

                    if last_sent is None:
                        last_sent_dt = now - timedelta(minutes=interval)
                    else:
                        if isinstance(last_sent, str):
                            last_sent_dt = datetime.fromisoformat(last_sent)
                        else:
                            last_sent_dt = last_sent

                        if last_sent_dt.tzinfo is None:
                            last_sent_dt = pytz.UTC.localize(last_sent_dt)
                        else:
                            last_sent_dt = last_sent_dt.astimezone(pytz.UTC)

                    next_send_time = last_sent_dt + timedelta(minutes=interval)
                    delete_threshold = next_send_time - timedelta(minutes=2)

                    chat_id = notif["chat_id"]
                    last_message_id = notif.get("last_message_id")

                    if now >= next_send_time:
                        title = notif["title"]
                        text = notif["text"]

                        ad_text = (
                            f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ / {html.escape(title)} /\n"
                            f"┋\n"
                            f"┣{html.escape(text)}\n"
                            f"┋\n"
                            f"┗┅┅┅/ #NOTAPES /"
                        )

                        try:
                            target_chat = await bot.get_chat(chat_id)
                            if target_chat.type == ChatType.CHANNEL:
                                ad_text = strip_custom_emojis(ad_text)
                        except Exception:
                            pass

                        builder = InlineKeyboardBuilder()
                        custom_buttons = notif.get("custom_buttons")
                        if custom_buttons:
                            for btn in custom_buttons:
                                builder.button(text=btn["text"], url=btn["url"])
                            builder.adjust(1)
                        elif notif.get("button_url"):
                            builder.button(text=notif.get("button_text", "OPEN"), url=notif["button_url"])

                        new_msg = await bot.send_message(
                            chat_id=chat_id,
                            text=ad_text,
                            reply_markup=builder.as_markup() if (custom_buttons or notif.get("button_url")) else None,
                            parse_mode=ParseMode.HTML
                        )

                        await db.update_notification_stats(
                            notif["id"],
                            last_sent=now,
                            last_message_id=new_msg.message_id if new_msg else None
                        )
                        logger.info("notification sent: id=%s chat_id=%s", notif["id"], chat_id)
                        if last_message_id is not None:
                            try:
                                await bot.delete_message(chat_id=chat_id, message_id=last_message_id)
                                logger.info("notification deleted: id=%s old_message_id=%s", notif["id"], last_message_id)
                            except TelegramBadRequest as e:
                                logger.error(f"Failed to delete old ad message: {e}")
                except Exception as e:
                    logger.error(f"Error processing notification {notif.get('id')}: {e}")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Error in check_periodic_notifications: {e}")
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            raise
