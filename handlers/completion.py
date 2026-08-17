import random
import asyncio
import html
import logging
import secrets
import pytz
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any

from aiogram import Bot, types
from aiogram.enums import ParseMode, ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import db
from utils import strip_custom_emojis
from services.localization import get_locale, get_locale_by_lang
from config import PRIMARY_ADMIN_ID

logger = logging.getLogger(__name__)

ADMIN_ID = PRIMARY_ADMIN_ID

async def complete_giveaway(giveaway_id: int, bot: Bot):
    claimed = False
    completed = False
    try:
        giveaway = await db.get_giveaway(giveaway_id)
        if not giveaway or giveaway["status"] != "active":
            return

        # Only one worker/callback may complete a giveaway.
        claimed = await db.claim_giveaway_completion(giveaway_id)
        if not claimed:
            return

        participants = await db.get_participants(giveaway_id)
        safe_title = html.escape(giveaway["title"])

        # Public results strictly in English as requested
        en_texts = get_locale_by_lang("en") # Public results forced to English

        if not participants:
            results_text = en_texts["giveaway_no_participants_results"].format(title=safe_title)
        else:
            winners_count_target = min(len(participants), giveaway["winners_count"])
            if winners_count_target <= 0:
                results_text = en_texts["giveaway_no_participants_results"].format(title=safe_title)
                winners = []
                prizes = []
            else:
                # Weighted selection
                remaining = participants.copy()
                winners = []

                while len(winners) < winners_count_target and remaining:
                    winner = random.SystemRandom().choices(
                        population=remaining,
                        weights=[p.get("tickets_used", 1) or 1 for p in remaining],
                        k=1
                    )[0]
                    winners.append(winner)
                    remaining = [p for p in remaining if p["user_id"] != winner["user_id"]]

                prizes = giveaway["prizes"]
            winners_prizes = [[] for _ in range(len(winners))]

            for idx, prize in enumerate(prizes):
                w_idx = idx % len(winners)
                winners_prizes[w_idx].append(prize)

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
                winners_list_str += f"┋ {mention} — {html.escape(prizes_str)}\n"

            if winners_to_save:
                await db.save_winners(giveaway_id, winners_to_save)

                results_text = en_texts["giveaway_winners_results"].format(
                    title=safe_title,
                    winners_list=winners_list_str
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

                await bot.send_message(
                    chat_id=msg["chat_id"],
                    text=final_results_text,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to update or send message in chat {msg['chat_id']}: {e}")

        if messages:
            await asyncio.gather(*(update_msg(m) for m in messages))

        # Personal notifications can remain in user's language
        creator_id = giveaway["creator_id"]
        creator_texts = await get_locale(creator_id)
        notify_text = creator_texts["giveaway_finished_notify"].format(title=safe_title)

        recipients = {giveaway["creator_id"], ADMIN_ID}
        for r_id in recipients:
            try:
                await bot.send_message(r_id, notify_text, parse_mode=ParseMode.HTML)
            except Exception:
                pass

        completed = True

    except Exception as e:
        logger.error(f"Error in complete_giveaway for {giveaway_id}: {e}")
    finally:
        if claimed:
            if completed:
                await db.finish_giveaway(giveaway_id)
            else:
                # Allow the background worker to retry after a transient failure.
                await db.update_giveaway_status(giveaway_id, "active")

async def check_timed_giveaways(bot: Bot):
    while True:
        try:
            now = datetime.now(pytz.UTC) 
            expired_giveaways = await db.get_expired_giveaways(now)
            
            for giveaway in expired_giveaways:
                logger.info(f"Завершение розыгрыша {giveaway['id']}")
                await complete_giveaway(giveaway['id'], bot)
        except Exception as e:
            logger.error(f"Error in check_timed_giveaways: {e}")
        await asyncio.sleep(30)

async def check_periodic_notifications(bot: Bot):
    while True:
        try:
            now = datetime.now(pytz.UTC)
            active_notifications = await db.get_active_notifications()

            try:
                for notif in active_notifications:
                    try:
                        chat_id = notif.get("chat_id")
                        if chat_id:
                            last_sent = notif.get("last_sent")
                            interval = notif.get("interval_minutes", 60)

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

                            if now >= next_send_time:
                                title = notif.get("title", "Ad")
                                text = notif.get("text", "")

                                # Сохраняем оригинальную бизнес-логику сборки сообщения
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

                                # Сборка markup кнопок (оригинальная бизнес-логика сохранена на 100%)
                                builder = InlineKeyboardBuilder()
                                c_btns = notif.get('custom_buttons', [])
                                if isinstance(c_btns, str):
                                    try: c_btns = json.loads(c_btns)
                                    except: c_btns = []
                                if c_btns:
                                    for b in c_btns:
                                        builder.button(text=b['text'], url=b['url'])
                                elif notif.get("button_url"):
                                    builder.button(text=notif.get("button_text", "OPEN"), url=notif["button_url"])
                                builder.adjust(1)
                                reply_markup = builder.as_markup() if (c_btns or notif.get("button_url")) else None

                                # --- МОДЕРНИЗИРОВАННЫЙ БЛОК ОТПРАВКИ И УДАЛЕНИЯ С ЗАЩИТОЙ ---
                                try:
                                    # 1. Попытка удалить предыдущее сообщение, если его ID есть в БД
                                    old_message_id = notif.get("last_message_id")
                                    if old_message_id and int(old_message_id) > 0:
                                        try:
                                            await bot.delete_message(chat_id=chat_id, message_id=int(old_message_id))
                                            logger.info(f"🗑️ Старое сообщение {old_message_id} успешно удалено из чата {chat_id}")
                                        except Exception as del_err:
                                            # Игнорируем ошибку (если сообщение старше 48 часов или удалено вручную)
                                            logger.warning(f"⚠️ Не удалось удалить старое сообщение {old_message_id}: {del_err}")

                                    # 2. Отправка нового сообщения
                                    new_msg = await bot.send_message(
                                        chat_id=chat_id,
                                        text=ad_text,
                                        reply_markup=reply_markup,
                                        parse_mode=ParseMode.HTML
                                    )

                                    # 3. Фиксация нового сообщения и времени в Supabase
                                    await db.update_notification_stats(
                                        notif["id"],
                                        last_sent=now,
                                        last_message_id=new_msg.message_id
                                    )

                                except Exception as tg_err:
                                    logger.error(f"❌ Ошибка отправки сообщения в Telegram (ID уведомления: {notif.get('id')}): {tg_err}")
                                    # Анти-спам заглушка на случай падения отправки
                                    await db.update_notification_stats(
                                        notif["id"],
                                        last_sent=now,
                                        last_message_id=0
                                    )
                    except Exception as inner_loop_err:
                        logger.error(f"❌ Ошибка при обработке уведомления {notif.get('id')}: {inner_loop_err}")

            except Exception as e:
                logger.error(f"Error in check_periodic_notifications loop: {e}")

        except Exception as e:
            logger.error(f"Error in check_periodic_notifications: {e}")

        await asyncio.sleep(60)
