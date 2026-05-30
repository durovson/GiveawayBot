from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
import html

from database import db
from services.leaderboard import LeaderboardService
from utils import safe_edit_text, normalize_wallet, short_wallet

router = Router()

async def show_game_menu(message: types.Message | types.CallbackQuery, state: FSMContext):
    text = (
        "┏┅⋐[ ◍ _◍ ]っ┅<tg-emoji emoji-id=\"5258508428212445001\">🎮</tg-emoji>┅ / <b>GAME MENU</b> /\n"
        "┋\n"
        "┣ Ready to play?\n"
        "┋\n"
        "┣ [<tg-emoji emoji-id=\"5258330865674494479\">🍑</tg-emoji>] HIGHSCORE: View Leaderboard\n"
        "┣ [<tg-emoji emoji-id=\"5258204546391351475\">💰</tg-emoji>] LOGIN: Connect Ton Wallet\n"
        "┣ [<tg-emoji emoji-id=\"5258391025281408576\">📈</tg-emoji>] BUY Stickers: Boost your Power\n"
        "┋\n"
        "┗┅┅┅/ <b>Select an option</b> /"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Leaderboard", callback_data="leaderboard", icon_custom_emoji_id="5258330865674494479")
    builder.button(text="Wallet", callback_data="wallet_menu", icon_custom_emoji_id="5258204546391351475")
    builder.button(text="Stickers", url="https://t.me/sticker_bot/?startapp=lid_019e1cac-1e8b-7073-bbad-54f1a29d3544", icon_custom_emoji_id="5258391025281408576")
    builder.button(text="Main Menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 2, 1)

    if isinstance(message, types.CallbackQuery):
        await message.answer()
        await safe_edit_text(message, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "game_menu")
async def game_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await show_game_menu(callback, state)

@router.callback_query(F.data == "leaderboard")
async def leaderboard_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id

    top = await LeaderboardService.get_top(limit=10)
    holders = await LeaderboardService._load_holders()

    linked_wallets = await db.get_all_linked_wallets()
    wallet_to_user = {
        normalize_wallet(w['wallet_address']): w['telegram_id']
        for w in linked_wallets if w.get('wallet_address')
    }

    lines = []
    for i, h in enumerate(top, 1):
        addr = h.get('wallet') or h.get('address') or h.get('owner')
        if not addr:
            continue
        addr_norm = normalize_wallet(addr)
        tg_id = wallet_to_user.get(addr_norm)

        display_name = short_wallet(addr)

        if tg_id:
            try:
                user = await callback.bot.get_chat(tg_id)
                display_name = f"@{user.username}" if user.username else user.full_name
            except:
                pass

        packs = h.get('packs', 0)
        lines.append(f"┋ {i}. {html.escape(display_name)} — {packs} packs")

    user_wallet = await db.get_user_wallet(user_id)
    user_pos_line = ""

    if user_wallet:
        user_wallet_norm = normalize_wallet(user_wallet)
        pos = None
        for idx, h in enumerate(holders, 1):
            curr_addr = h.get('wallet') or h.get('address') or h.get('owner')
            if curr_addr and normalize_wallet(curr_addr) == user_wallet_norm:
                pos = idx
                break

        friendly_wallet = short_wallet(user_wallet)

        if pos:
            user_h = holders[pos-1]
            packs = user_h.get('packsCount', user_h.get('packs', 0))
            user_pos_line = f"┋ {pos}. {friendly_wallet} (You) — {packs} packs"
        else:
            user_pos_line = f"┋ —. {friendly_wallet} (You) — 0 packs"

    if not lines:
        text = (
            "┏┅<tg-emoji emoji-id=\"5258508428212445001\">🎮</tg-emoji>┅ / <b>LEADERBOARD</b> /\n"
            "┋\n"
            "┣ No holder statistics available yet.\n"
            "┣ Blockchain sync in progress.\n"
            "┋\n"
            "┗┅┅┅/ Wating... /"
        )
    else:
        text = (
            "┏┅<tg-emoji emoji-id=\"5258508428212445001\">🎮</tg-emoji>┅ / <b>LEADERBOARD</b> /\n"
            "┋\n"
            "┣ Global holders ranking. \n"
            "┣ Data is synchronized in real-time.\n"
            "┋\n"
            + "\n".join(lines) + "\n"
            "┋ ┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
            + (user_pos_line if user_pos_line else "┋ Wallet not linked\n┋") + "\n"
            "┗┅┅┅/ <b>Select an option</b> /"
        )

    builder = InlineKeyboardBuilder()
    builder.button(text="Back", callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
