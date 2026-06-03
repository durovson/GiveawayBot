import os
import logging
from datetime import datetime, timedelta
from aiogram import Router, types, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
import html

from database import db
from services.leaderboard import LeaderboardService
from utils import safe_edit_text, normalize_wallet, short_wallet
from services.localization import get_locale

logger = logging.getLogger(__name__)
router = Router()

async def show_game_menu(message: types.Message | types.CallbackQuery, state: FSMContext):
    user_id = message.from_user.id
    texts = await get_locale(user_id)

    text = texts["game_menu_title"]

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["game_leaderboard_btn"], callback_data="leaderboard", icon_custom_emoji_id="5258330865674494479")
    builder.button(text=texts["game_wallet_btn"], callback_data="wallet_menu", icon_custom_emoji_id="5258204546391351475")
    builder.button(text=texts["game_stickers_btn"], url="https://t.me/sticker_bot/?startapp=lid_019e1cac-1e8b-7073-bbad-54f1a29d3544", icon_custom_emoji_id="5258391025281408576")
    builder.button(text=texts["holders_chat_btn"], callback_data="holders_chat", icon_custom_emoji_id="5258486128742244085")
    builder.button(text=texts["game_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 2, 1, 1)

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
    texts = await get_locale(user_id)

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

        packs = h.get('packsCount', h.get('packs', 0))
        lines.append(f"┋ {i}. {html.escape(display_name)} — {packs} {texts['game_packs']}")

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
            user_pos_line = f"┋ {pos}. {friendly_wallet} ({texts['game_you']}) — {packs} {texts['game_packs']}"
        else:
            user_pos_line = f"┋ —. {friendly_wallet} ({texts['game_you']}) — 0 {texts['game_packs']}"

    if not lines:
        text = texts["game_leaderboard_waiting"]
    else:
        text = texts["game_leaderboard_title"].format(
            lines="\n".join(lines),
            user_pos=user_pos_line if user_pos_line else texts["game_wallet_not_linked"]
        )

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "holders_chat")
async def holders_chat_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    texts = await get_locale(user_id)

    # Reusing existing packs calculation logic from LeaderboardService
    # LeaderboardService.get_wallet returns {"rank": idx, "wallet": candidate, "packs": packs}
    wallet_info = await LeaderboardService.get_rank(user_id)
    packs = wallet_info["packs"] if wallet_info else 0

    text = texts["holders_chat_title"].format(packs=packs)

    builder = InlineKeyboardBuilder()
    if packs >= 10:
        builder.button(text=texts["holders_chat_join_btn"], callback_data="join_holders_chat", icon_custom_emoji_id="5256143829672672750")

    builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "join_holders_chat")
async def join_holders_chat_handler(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)

    # 0. Get Chat ID
    otc_chat_id = os.environ.get("OTC_CHAT_ID")
    if not otc_chat_id:
        logger.error("OTC_CHAT_ID not set")
        await callback.answer(texts["holders_chat_error"], show_alert=True)
        return

    # 1. Check if user is already a member
    try:
        member = await bot.get_chat_member(otc_chat_id, user_id)
        if member.status in ["member", "administrator", "creator"]:
            await callback.answer(texts["holders_chat_already_member"], show_alert=True)
            return
    except Exception:
        # If bot cannot check membership, proceed anyway as access is controlled by invite issuance
        pass

    # 2. Verify packs again
    wallet_info = await LeaderboardService.get_rank(user_id)
    packs = wallet_info["packs"] if wallet_info else 0

    if packs < 10:
        await callback.answer(texts.get("holders_chat_error", "Error"), show_alert=True)
        return

    # 3. Anti-spam check (24h)
    last_invite = await db.get_last_holder_invite(user_id)
    if last_invite:
        created_at = last_invite["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))

        if datetime.now(created_at.tzinfo) - created_at < timedelta(hours=24):
            await callback.answer(texts["holders_chat_already_invited"], show_alert=True)
            return

    # 4. Generate invite link
    try:
        # Create one-time invite link valid for 24h
        expire_date = datetime.now() + timedelta(hours=24)
        invite = await bot.create_chat_invite_link(
            chat_id=otc_chat_id,
            member_limit=1,
            expire_date=expire_date,
            creates_join_request=False
        )

        # 5. Save to database
        await db.save_holder_invite(
            telegram_id=user_id,
            username=callback.from_user.username,
            packs=packs
        )

        # 6. Show success UI
        success_text = texts["holders_chat_join_success"]

        builder = InlineKeyboardBuilder()
        builder.button(text=texts["holders_chat_open_btn"], url=invite.invite_link, icon_custom_emoji_id="5316727448644103237")
        builder.button(text=texts["game_back_btn"], callback_data="holders_chat", icon_custom_emoji_id="5877629862306385808")
        builder.adjust(1)

        await safe_edit_text(callback, success_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
        await callback.answer()

    except Exception as e:
        logger.error(f"Error creating invite link: {e}")
        await callback.answer(texts["holders_chat_error"], show_alert=True)
