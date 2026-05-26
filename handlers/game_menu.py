from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
import html
import json

from database import db
from services.leaderboard import LeaderboardService
from utils import safe_edit_text, normalize_to_raw, raw_to_user_friendly

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

    top = await LeaderboardService.get_top(limit=10)
    holders = await LeaderboardService._load_holders()

    # 2. Привязываем кошельки к Telegram ID, нормализуя ключи в Raw формат
    linked_wallets = await db.get_all_linked_wallets()
    wallet_to_user = {
        normalize_to_raw(w['wallet_address']): w['telegram_id']
        for w in linked_wallets if w.get('wallet_address')
    }

    lines = []
    for i, h in enumerate(top, 1):
        if not isinstance(h, dict):
            continue
        addr = h.get('wallet') or h.get('address') or h.get('owner')
        if not addr:
            continue
        addr_raw = normalize_to_raw(addr)
        tg_id = wallet_to_user.get(addr_raw)

        # Выводим адреса топ-10 в красивом UQ... формате
        friendly_addr = raw_to_user_friendly(addr)
        display_name = f"{friendly_addr[:6]}...{friendly_addr[-4:]}"

        if tg_id:
            try:
                user = await callback.bot.get_chat(tg_id)
                display_name = f"@{user.username}" if user.username else user.full_name
            except:
                pass

        packs = h.get('packs', h.get('packsCount', 0))
        lines.append(f"┋ {i}. {html.escape(display_name)} — {packs} packs")

    # 3. Поиск позиции текущего пользователя с нормализацией адресов
    user_wallet = await db.get_user_wallet(user_id)
    user_pos_line = ""

    if user_wallet:
        user_wallet_raw = normalize_to_raw(user_wallet)
        # Ищем совпадение в полном списке холдеров
        pos = next(
            (
                i for i, h in enumerate(holders, 1)
                if isinstance(h, dict)
                and (h.get('wallet') or h.get('address') or h.get('owner'))
                and normalize_to_raw((h.get('wallet') or h.get('address') or h.get('owner'))) == user_wallet_raw
            ),
            None,
        )

        friendly_wallet = raw_to_user_friendly(user_wallet)
        short_wallet = f"{friendly_wallet[:6]}...{friendly_wallet[-4:]}"

        if pos:
            user_h = holders[pos-1]
            packs = user_h.get('packsCount', user_h.get('packs', 0))
            user_pos_line = f"┋ {pos}. {short_wallet} (Вы) — {packs} packs"
        else:
            # Если кошелек привязан, но паков 0 (или нет в выгрузке API)
            user_pos_line = f"┋ —. {short_wallet} (Вы) — 0 packs"

    text = (
        "┏┅🍑┅ / PACK HOLDERS LEADERBOARD /\n"
        "┋\n"
        "┣ Global ranking of tokenized collection distribution. \n"
        "┣ Data is synchronized in real-time directly via the Stickers Tools API aggregator.\n"
        "┋\n"
        + "\n".join(lines) + "\n"
        "┋ ┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
        + (user_pos_line if user_pos_line else "┋ Wallet not linked or not found in list\n┋") + "\n"
        "┗┅┅┅/ Live Blockchain Parsing /"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Back", callback_data="game_menu")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
