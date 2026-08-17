from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import logging
import html

from database import db
from utils import safe_edit_text
from services.localization import get_locale

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "history_created")
async def history_created(callback: types.CallbackQuery, texts: dict):
    user_id = callback.from_user.id
    # texts from middleware
    await callback.answer()
    giveaways = await db.get_user_created_giveaways(user_id)

    builder = InlineKeyboardBuilder()

    if not giveaways:
        text = texts["giveaway_history_title"].format(content=texts["giveaway_no_giveaways"])
    else:
        # Sort by id descending and take 5
        giveaways.sort(key=lambda x: x.get('id', 0), reverse=True)
        top_giveaways = giveaways[:5]

        blocks = []

        for g in top_giveaways:
            status = texts["giveaway_not_completed"] if g['status'] == 'active' else texts["giveaway_completed"]
            title = html.escape(g.get('title') or 'Untitled')

            # Start entry content
            entry = f"<tg-emoji emoji-id=\"5258254475386167466\">🖼</tg-emoji> <b>{texts['giveaway_event_label']}:</b> {title}\n"
            entry += f"<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji> <b>{texts['giveaway_status_label']}:</b> {status}"

            if g['status'] == 'active':
                builder.button(text=texts["giveaway_announcement_btn"].format(title=title), callback_data=f"make_announcement_{g['id']}", icon_custom_emoji_id="5260268501515377807")

            # If completed, add winners list on new lines
            if g['status'] != 'active':
                winners = await db.get_giveaway_winners(g['id'])
                if winners:
                    entry += f"\n\n<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji> <b>{texts['giveaway_winners']}:</b>"
                    for w in winners:
                        w_name = html.escape(w.get('username') or f"ID:{w.get('user_id')}")
                        w_prize = html.escape(w.get('prize', 'Prize'))
                        entry += f"\n@{w_name} — {w_prize}"

            # Wrap each giveaway in its own blockquote
            blocks.append(f"<blockquote>{entry.strip()}</blockquote>")

        # Combine all parts
        text = texts["giveaway_history_title"].format(content="\n".join(blocks))

    builder.button(text=texts["giveaway_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)
    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("join_"))
async def join_giveaway(callback: types.CallbackQuery, texts: dict):
    giveaway_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    # texts from middleware
    # Если у пользователя есть юзернейм, приводим его к нижнему регистру.
    # Если юзернейма нет (используется full_name), оставляем как есть.
    username = callback.from_user.username or callback.from_user.full_name
    if callback.from_user.username:
        username = username.lower()

    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway:
        await callback.answer(texts["giveaway_removed"], show_alert=True)
        return
    if giveaway['status'] != 'active':
        await callback.answer(texts["giveaway_finished"], show_alert=True)
        return

    if callback.from_user.username and callback.from_user.username.lower() == "klassikaone":
        await callback.answer(texts["giveaway_participation_prohibited_admin"], show_alert=True)
        return

    whitelist = giveaway.get('allowed_users')
    if whitelist:
        user_id_str = str(user_id)
        current_username = f"@{callback.from_user.username}".lower() if callback.from_user.username else None

        is_allowed = (user_id_str in whitelist) or (current_username and current_username in whitelist)

        if not is_allowed:
            await callback.answer(
                texts["giveaway_not_whitelisted"],
                show_alert=True
            )
            return

    # Check mandatory channel subscriptions
    unsubscribed_from = []
    if giveaway.get('mandatory_channels'):
        for channel in giveaway['mandatory_channels']:
            try:
                member = await callback.bot.get_chat_member(chat_id=channel, user_id=user_id)
                if member.status in ['left', 'kicked', 'restricted']:
                    unsubscribed_from.append(channel)
            except Exception as e:
                logger.error(f"Error checking subscription for {channel}: {e}")
                # We can choose to skip or block if check fails. Usually better to block to be safe.
                # unsubscribed_from.append(channel)

    if unsubscribed_from:
        # Note: We keep channel IDs as is, but could potentially try to get titles
        channels_str = ", ".join(unsubscribed_from)
        await callback.answer(f"{texts['giveaway_not_subscribed']} ({channels_str})", show_alert=True)
        return

    # Participant creation and ticket consumption are one database transaction.
    join_result = await db.join_giveaway_atomic(giveaway_id, user_id, username)
    if join_result.get("ok"):
        consumed_tickets = join_result.get("bonus_tickets_consumed", 0)
        if consumed_tickets > 0:
            await callback.answer(
                texts["lucky_tickets_applied"].format(tickets=consumed_tickets),
                show_alert=True,
            )
        else:
            await callback.answer(texts["giveaway_success_join"], show_alert=True)
        if giveaway['mode'] == 'limited':
            participants = await db.get_participants(giveaway_id)
            try:
                limit = int(giveaway['value'])
                if len(participants) >= limit:
                    from handlers.completion import complete_giveaway
                    await complete_giveaway(giveaway_id, callback.bot)
            except ValueError:
                pass
    elif join_result.get("error") == "ALREADY_JOINED":
        await callback.answer(texts["giveaway_already_joined"], show_alert=True)
    elif join_result.get("error") in {"GIVEAWAY_NOT_FOUND", "GIVEAWAY_NOT_ACTIVE"}:
        await callback.answer(texts["giveaway_finished"], show_alert=True)
    else:
        logger.error("Atomic join failed for giveaway %s: %s", giveaway_id, join_result)
        await callback.answer(texts.get("error_occurred", "Error"), show_alert=True)
