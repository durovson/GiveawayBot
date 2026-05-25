from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
import html
import json

from database import db
from utils import safe_edit_text

router = Router()

@router.callback_query(F.data == "game_menu")
async def game_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    text = (
        "┏┅🍑┅ / GAME MENU /\n"
        "┋\n"
        "┣ Welcome to the Game section!\n"
        "┣ Here you can track your position in the leaderboard\n"
        "┣ and manage your TON wallet.\n"
        "┋\n"
        "┗┅┅┅/ Select an option /"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Leaderboard", callback_data="leaderboard", icon_custom_emoji_id="5258185631355378853")
    builder.button(text="Wallet", callback_data="wallet_menu", icon_custom_emoji_id="5258416629745714088")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "leaderboard")
async def leaderboard_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    cached_data = await db.get_setting("cached_holders")
    holders = json.loads(cached_data) if cached_data else []

    linked_wallets = await db.get_all_linked_wallets()
    wallet_to_user = {w['wallet_address']: w['telegram_id'] for w in linked_wallets}

    # Pre-fetch usernames for linked wallets in top 10
    top_10 = holders[:10]

    lines = []
    for i, h in enumerate(top_10, 1):
        addr = h['address']
        packs = h['packsCount']
        tg_id = wallet_to_user.get(addr)

        display_name = f"{addr[:6]}...{addr[-4:]}"
        if tg_id:
            try:
                user = await callback.bot.get_chat(tg_id)
                display_name = f"@{user.username}" if user.username else user.full_name
            except:
                pass

        lines.append(f"┋ {i}. {html.escape(display_name)} — {packs} packs")

    # Find current user position
    user_wallet = await db.get_user_wallet(user_id)
    user_pos_line = ""
    if user_wallet:
        pos = next((i for i, h in enumerate(holders, 1) if h['address'] == user_wallet), None)
        if pos:
            user_h = holders[pos-1]
            user_pos_line = f"┋ {pos}. {user_wallet[:6]}...{user_wallet[-4:]} (Вы) — {user_h['packsCount']} packs"

    text = (
        "┏┅🍑┅ / PACK HOLDERS LEADERBOARD /\n"
        "┋\n"
        "┣ Global ranking of tokenized collection distribution. \n"
        "┣ Data is synchronized in real-time directly via the Stickers Tools API aggregator.\n"
        "┋\n"
        + "\n".join(lines) + "\n"
        "┋ ┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
        + (user_pos_line + "\n" if user_pos_line else "┋ Wallet not linked or not found in list\n") +
        "┋\n"
        "┗┅┅┅/ Live Blockchain Parsing /"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Back", callback_data="game_menu")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
