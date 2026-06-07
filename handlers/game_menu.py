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
from services.referral_service import ReferralService
from services.points_service import PointsService
from services.holder_service import HolderService
from utils import safe_edit_text, normalize_wallet, short_wallet
from services.localization import get_locale

logger = logging.getLogger(__name__)
router = Router()

async def show_game_menu(message: types.Message | types.CallbackQuery, state: FSMContext):
    user_id = message.from_user.id
    texts = await get_locale(user_id)

    # Get user points info
    points_data = await db.get_points(user_id)
    if not points_data:
        # Initialize if not present
        await PointsService.recalculate_points(user_id)
        points_data = await db.get_points(user_id)

    rp = points_data.get("total_points", 0) if points_data else 0

    # Get total invited (from referrals table)
    try:
        response = await db.client.table("referrals").select("id", count="exact").eq("referrer_id", user_id).execute()
        refs = response.count if response.count is not None else 0
    except:
        refs = 0

    text = texts["game_menu_title"].format(rp=rp, refs=refs)

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["highscore_btn"], callback_data="leaderboard", icon_custom_emoji_id="5258508428212445001")
    builder.button(text=texts["referral_btn"], callback_data="referral_menu", icon_custom_emoji_id="6032594876506312598")
    builder.button(text=texts["holders_btn"], callback_data="holders_chat", icon_custom_emoji_id="5260687681733533075")
    builder.button(text=texts["login_btn"], callback_data="wallet_menu", icon_custom_emoji_id="5316612764427367709")
    builder.button(text=texts["boost_btn"], url="https://t.me/sticker_bot/?startapp=lid_019e1cac-1e8b-7073-bbad-54f1a29d3544", icon_custom_emoji_id="5258212268742549391")
    builder.button(text=texts["game_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    if isinstance(message, types.CallbackQuery):
        await message.answer()
        await safe_edit_text(message, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        await message.answer(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "game_menu")
async def game_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await show_game_menu(callback, state)

@router.callback_query(F.data == "referral_menu")
async def referral_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)

    ref_code = await ReferralService.get_or_create_ref_code(user_id)
    bot_user = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_user.username}?start=ref_{ref_code}"

    # Get stats
    points_data = await db.get_points(user_id)
    active_refs = points_data.get("active_referrals", 0) if points_data else 0

    try:
        response = await db.client.table("referrals").select("id", count="exact").eq("referrer_id", user_id).execute()
        total_invited = response.count if response.count is not None else 0
    except:
        total_invited = 0

    text = texts["referral_menu_title"].format(
        ref_link=f"<code>{ref_link}</code>",
        invited=total_invited,
        active=active_refs
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    await callback.answer()

@router.callback_query(F.data == "leaderboard")
async def leaderboard_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    texts = await get_locale(user_id)

    # Use points table for leaderboard
    top_points = await db.get_leaderboard(limit=10)

    lines = []
    for i, p in enumerate(top_points, 1):
        display_name = html.escape(p.get("display_name") or str(p.get("user_id", "Unknown")))
        rp = p.get("total_points", 0)
        packs = p.get("packs", 0)
        active_refs = p.get("active_referrals", 0)
        lines.append(f"┋ {i}. {display_name} — {rp} RP ({packs}/{active_refs})")

    user_points = await db.get_points(user_id)
    user_pos_line = ""

    if user_points:
        try:
            rank_res = await db.client.rpc("get_user_rank", {"user_id_param": user_id}).execute()
            rank = rank_res.data if rank_res.data else "—"
        except:
            rank = "—"

        display_name = html.escape(user_points.get("display_name") or "You")
        rp = user_points.get("total_points", 0)
        packs = user_points.get("packs", 0)
        active_refs = user_points.get("active_referrals", 0)
        user_pos_line = f"┋ {rank}. {display_name} — {rp} RP ({packs}/{active_refs})"

    text = texts["game_leaderboard_title"].format(
        lines='\n'.join(lines),
        user_pos=user_pos_line
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

    # Verify holder status via HolderService
    await HolderService.verify_holder_status(user_id)

    # Get packs from points table
    points_data = await db.get_points(user_id)
    packs = points_data.get("packs", 0) if points_data else 0

    text = texts["holders_chat_title"].format(packs=packs)

    builder = InlineKeyboardBuilder()
    builder.button(text="ACCESS CHAT", callback_data="check_holders_chat_access")
    builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "check_holders_chat_access")
async def check_holders_chat_access(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)

    # Get packs from points table
    points_data = await db.get_points(user_id)
    packs = points_data.get("packs", 0) if points_data else 0

    if packs < 10:
        await callback.answer(texts["need_packs_msg"], show_alert=True)
        return

    # Access granted
    await callback.answer(texts["access_granted_msg"], show_alert=True)

    # Replace button with actual join link
    otc_chat_id = os.environ.get("OTC_CHAT_ID")
    try:
        expire_date = datetime.now() + timedelta(hours=24)
        invite = await bot.create_chat_invite_link(
            chat_id=otc_chat_id,
            member_limit=1,
            expire_date=expire_date,
            creates_join_request=False
        )

        # Save to database
        await db.save_holder_invite(
            telegram_id=user_id,
            username=callback.from_user.username,
            packs=packs
        )

        builder = InlineKeyboardBuilder()
        builder.button(text="JOIN CHAT", url=invite.invite_link)
        builder.button(text=texts["game_back_btn"], callback_data="game_menu", icon_custom_emoji_id="5877629862306385808")
        builder.adjust(1)

        await safe_edit_text(callback, texts["holders_chat_join_success"], reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

    except Exception as e:
        logger.error(f"Error creating invite link: {e}")
        await callback.answer(texts["holders_chat_error"], show_alert=True)

@router.callback_query(F.data == "join_holders_chat")
async def join_holders_chat_handler(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await check_holders_chat_access(callback, state, bot)
