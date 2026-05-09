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

        if not participants:
            results_text = (
                f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ <b>/ {safe_title} /</b>\n"
                f"┋<tg-emoji emoji-id=\"5422626434331990897\">🤩</tg-emoji> <b>GAME OVER!</b>\n"
                f"┋\n"
                f"┋ <b>Unfortunately, there were no apes...</b>\n"
                f"┋\n"
                f"┣<b>GIVEAWAY</b>\n"
                f"┣[ HUMANS.. NOT APES ]\n"
                f"┗┅┅┅/ #NOTAPES /"
            )
        else:
            random.shuffle(participants)
            winners = []
            winners_count_target = min(len(participants), giveaway['winners_count'])

            # Try to find active users first
            for p in participants:
                if len(winners) >= winners_count_target:
                    break
                # Проверка подписок перед выдачей приза
                is_subscribed = True
                if giveaway.get('mandatory_channels'):
                    for channel in giveaway['mandatory_channels']:
                        try:
                            member = await bot.get_chat_member(chat_id=channel, user_id=p['user_id'])
                            if member.status in ['left', 'kicked', 'restricted']:
                                is_subscribed = False
                                break
                        except Exception:
                            is_subscribed = False
                            break

                if is_subscribed and await is_user_active(bot, p['user_id']):
                    winners.append(p)

            # If not enough active users, fill with the rest
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
