from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import logging
import html

from database import db
from utils import safe_edit_text

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "history_created")
async def history_created(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    giveaways = await db.get_user_created_giveaways(user_id)

    builder = InlineKeyboardBuilder()

    if not giveaways:
        text = (
            "<tg-emoji emoji-id=\"5273741156792951269\">🤓</tg-emoji> <b>Created giveaways</b>\n\n"
            "<blockquote>You haven't created any giveaways yet.</blockquote>\n\n"
            "<tg-emoji emoji-id=\"5296348778012361146\">🏷</tg-emoji> Select action:"
        )
    else:
        # Sort by id descending and take 5
        giveaways.sort(key=lambda x: x.get('id', 0), reverse=True)
        top_giveaways = giveaways[:5]

        header = "<tg-emoji emoji-id=\"5273741156792951269\">🤓</tg-emoji> <b>Created giveaways</b>\n\n"
        blocks = []

        for g in top_giveaways:
            status = "Not completed" if g['status'] == 'active' else "Completed"
            title = html.escape(g.get('title') or 'Untitled')

            # Start entry content
            entry = f"<tg-emoji emoji-id=\"5258254475386167466\">🖼</tg-emoji> <b>Event:</b> {title}\n"
            entry += f"<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji> <b>Status:</b> {status}"

            if g['status'] == 'active':
                builder.button(text=f"Announcement: {title}", callback_data=f"make_announcement_{g['id']}", icon_custom_emoji_id="5260268501515377807")

            # If completed, add winners list on new lines
            if g['status'] != 'active':
                winners = await db.get_giveaway_winners(g['id'])
                if winners:
                    entry += f"\n\n<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji> <b>Winners:</b>"
                    for w in winners:
                        w_name = html.escape(w.get('username') or f"ID:{w.get('user_id')}")
                        w_prize = html.escape(w.get('prize', 'Prize'))
                        entry += f"\n@{w_name} — {w_prize}"

            # Wrap each giveaway in its own blockquote
            blocks.append(f"<blockquote>{entry.strip()}</blockquote>")

        # Combine all parts
        text = header + "\n".join(blocks)
        text += "\n\n<tg-emoji emoji-id=\"5296348778012361146\">🏷</tg-emoji> Select action:"

    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)
    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("join_"))
async def join_giveaway(callback: types.CallbackQuery):
    giveaway_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    username = callback.from_user.username or callback.from_user.full_name

    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway:
        await callback.answer("❌ The giveaway has been removed.", show_alert=True)
        return
    if giveaway['status'] != 'active':
        await callback.answer("❌ This event has already ended.", show_alert=True)
        return

    if user_id == giveaway['creator_id']:
        await callback.answer("❌ The creator cannot participate in his own giveaway.", show_alert=True)
        return

    if callback.from_user.username and callback.from_user.username.lower() == "klassikaone":
        await callback.answer("❌ Participation is prohibited, you are the leader.", show_alert=True)
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
        channels_str = ", ".join(unsubscribed_from)
        await callback.answer(f"❌ First subscribe to: {channels_str}", show_alert=True)
        return

    success = await db.add_participant(giveaway_id, user_id, username)
    if success:
        await callback.answer("✅ You are participating!", show_alert=True)
        if giveaway['mode'] == 'limited':
            participants = await db.get_participants(giveaway_id)
            try:
                limit = int(giveaway['value'])
                if len(participants) >= limit:
                    from handlers.completion import complete_giveaway
                    await complete_giveaway(giveaway_id, callback.bot)
            except ValueError:
                pass
    else:
        await callback.answer("ℹ️ You are already participating in this giveaway.", show_alert=True)
