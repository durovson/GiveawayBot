import asyncio
import random
import logging
import pytz
import html
from datetime import datetime
from aiogram import Bot
from aiogram.enums import ParseMode

from database import db

logger = logging.getLogger(__name__)

ADMIN_ID = 734720997
GIF_ID = "CgACAgIAAxkBAAEbt3NpqAn2obJdHyFVZbi_JOspLX96KAAC7pQAAkCBQEk_A-aRj7qxNToE"

async def is_user_active(bot: Bot, user_id: int) -> bool:
    try:
        await bot.get_chat(user_id)
        return True
    except Exception:
        return False

async def complete_giveaway(giveaway_id: int, bot: Bot):
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway or giveaway['status'] != 'active':
        return

    try:
        participants = await db.get_participants(giveaway_id)
        safe_title = html.escape(giveaway.get("title", "Без названия"))

        # --- Strict Subscription Verification ---
        verified_participants = []
        mandatory_channels = giveaway.get('mandatory_channels', [])

        for p in participants:
            is_subscribed = True
            for channel_id in mandatory_channels:
                try:
                    member = await bot.get_chat_member(chat_id=channel_id, user_id=p['user_id'])
                    if member.status in ['left', 'kicked', 'restricted']:
                        is_subscribed = False
                        break
                except Exception as e:
                    # If bot is not admin or channel not found, we skip check for THIS specific channel
                    # but technically we should still consider them subscribed to others.
                    # Per instructions: "If a bot is not an admin in a channel, it logs the error instead of crashing."
                    logger.warning(f"Could not verify subscription for user {p['user_id']} in channel {channel_id}: {e}")
                    continue

            if is_subscribed:
                verified_participants.append(p)
            else:
                # Remove "cheaters" from DB to keep it clean
                await db.remove_participant(giveaway_id, p['user_id'])

        participants = verified_participants
        # --- End Verification ---

        if not participants:
            results_text = (
                f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ <b>/ {safe_title} /</b>\n"
                f"┋<tg-emoji emoji-id=\"5422626434331990897\">🤩</tg-emoji> <b>GAME OVER!</b>\n"
                f"┋\n"
                f"┋ <b>Unfortunately, there were no humans...</b>\n"
                f"┋\n"
                f"┣<b>GIVEAWAY</b>\n"
                f"┣[ HUMANS.. NOT APES ]\n"
                f"┗┅┅┅/ #NOTAPES /"
            )
        else:
            random.shuffle(participants)
            winners = []
            winners_count_target = min(len(participants), giveaway['winners_count'])

            # Pick winners from verified participants who are also active
            for p in participants:
                if len(winners) >= winners_count_target:
                    break

                if await is_user_active(bot, p['user_id']):
                    winners.append(p)

            # If not enough active users, fill with the rest of verified participants
            if len(winners) < winners_count_target:
                current_winner_ids = [w['user_id'] for w in winners]
                for p in participants:
                    if len(winners) >= winners_count_target:
                        break
                    if p['user_id'] not in current_winner_ids:
                        winners.append(p)

            prizes = giveaway['prizes']
            winners_prizes = [[] for _ in range(len(winners))]

            # Distribute prizes (triangular fill logic)
            if winners:
                prize_idx = 0
                limit = len(winners)
                while prize_idx < len(prizes):
                    for i in range(limit):
                        if prize_idx < len(prizes):
                            winners_prizes[i].append(prizes[prize_idx])
                            prize_idx += 1
                        else:
                            break
                    limit -= 1
                    if limit <= 0:
                        limit = len(winners)

            winners_to_save = []
            for i, winner in enumerate(winners):
                winners_to_save.append({
                    "user_id": winner['user_id'],
                    "username": winner['username'],
                    "prize": ", ".join(winners_prizes[i])
                })

            # Save winners before sending message to ensure state is consistent
            await db.save_winners(giveaway_id, winners_to_save)

            winners_list_str = ""
            for i, winner in enumerate(winners):
                safe_prizes = ", ".join([html.escape(p) for p in winners_prizes[i]])
                raw_username = winner.get("username") or f"ID:{winner['user_id']}"
                safe_username = html.escape(raw_username)
                if raw_username and not raw_username.startswith("ID:"):
                    mention = f"<b>@{safe_username}</b>"
                else:
                    mention = f"<b><a href=\"tg://user?id={winner['user_id']}\">{safe_username}</a></b>"
                winners_list_str += f"┋<tg-emoji emoji-id=\"5274159185959872191\">👑</tg-emoji> {mention} — {safe_prizes}\n"

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
                # 1. Try to edit caption (for animations)
                try:
                    await bot.edit_message_caption(
                        chat_id=msg['chat_id'],
                        message_id=msg['message_id'],
                        caption=results_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=None
                    )
                    return
                except Exception:
                    pass

                # 2. Try to edit text (for plain messages)
                try:
                    await bot.edit_message_text(
                        chat_id=msg['chat_id'],
                        message_id=msg['message_id'],
                        text=results_text,
                        parse_mode=ParseMode.HTML,
                        reply_markup=None
                    )
                    return
                except Exception:
                    pass

                # 3. Fallback: send NEW message if editing failed
                await bot.send_message(
                    chat_id=msg['chat_id'],
                    text=results_text,
                    parse_mode=ParseMode.HTML
                )
            except Exception as e:
                logger.error(f"Failed to update or send message in chat {msg['chat_id']}: {e}")

        if messages:
            await asyncio.gather(*(update_msg(m) for m in messages))

        # Notify creator and whitelisted admin
        notify_text = (
            f"<tg-emoji emoji-id=\"5258096772776991776\">⚙️</tg-emoji> <b>Розыгрыш «{safe_title}» завершен!</b>\n\n"
            f"Результаты опубликованы в группе."
        )
        recipients = {giveaway['creator_id'], ADMIN_ID}
        for r_id in recipients:
            try:
                await bot.send_message(r_id, notify_text, parse_mode=ParseMode.HTML)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error in complete_giveaway for {giveaway_id}: {e}")
    finally:
        # Guarantee status update
        await db.finish_giveaway(giveaway_id)

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
    from datetime import timedelta
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    while True:
        try:
            now = datetime.now(pytz.UTC)
            active_notifications = await db.get_active_notifications()

            for notif in active_notifications:
                try:
                    last_sent = notif.get('last_sent')
                    interval_hours = notif['interval_hours']

                    if last_sent is None:
                        # For new notifications, send immediately
                        last_sent_dt = now - timedelta(hours=interval_hours)
                    else:
                        if isinstance(last_sent, str):
                            last_sent_dt = datetime.fromisoformat(last_sent)
                        else:
                            last_sent_dt = last_sent

                        # Convert to UTC if it's naive or in another timezone
                        if last_sent_dt.tzinfo is None:
                            last_sent_dt = pytz.UTC.localize(last_sent_dt)
                        else:
                            last_sent_dt = last_sent_dt.astimezone(pytz.UTC)

                    next_send_time = last_sent_dt + timedelta(hours=interval_hours)
                    delete_threshold = next_send_time - timedelta(minutes=2)

                    chat_id = notif['chat_id']
                    last_message_id = notif.get('last_message_id')

                    # 1. Delete step 2 minutes before start
                    if now >= delete_threshold and now < next_send_time and last_message_id is not None:
                        try:
                            await bot.delete_message(chat_id=chat_id, message_id=last_message_id)
                        except TelegramBadRequest as e:
                            logger.error(f"Failed to delete old ad message: {e}")
                        finally:
                            await db.update_notification_last_msg(notif['id'], None)

                    # 2. New message sending stage
                    if now >= next_send_time:
                        title = notif['title']
                        text = notif['text']

                        ad_text = (
                            f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ / {html.escape(title)} /\n"
                            f"┋\n"
                            f"┣{html.escape(text)}\n"
                            f"┋\n"
                            f"┗┅┅┅/ #NOTAPES /"
                        )

                        builder = InlineKeyboardBuilder()
                        if notif.get('button_url'):
                            builder.button(text=notif.get('button_text', 'OPEN'), url=notif['button_url'])

                        new_msg = await bot.send_message(
                            chat_id=chat_id,
                            text=ad_text,
                            reply_markup=builder.as_markup() if notif.get('button_url') else None,
                            parse_mode=ParseMode.HTML
                        )

                        await db.update_notification_stats(
                            notif['id'],
                            last_sent=now,
                            last_message_id=new_msg.message_id
                        )
                except Exception as e:
                    logger.error(f"Error processing notification {notif.get('id')}: {e}")

        except Exception as e:
            logger.error(f"Error in check_periodic_notifications: {e}")

        await asyncio.sleep(60) # Check every minute
