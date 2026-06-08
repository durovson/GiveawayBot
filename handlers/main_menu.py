import asyncio
from aiogram import Router, types, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
import html
import logging
from datetime import datetime

from database import db
from handlers.giveaway_creation import GiveawayCreation
from utils import is_admin, is_any_admin, safe_answer, safe_edit_text, is_holder
from services.localization import get_locale
from services.referral_service import ReferralService
from services.points_service import PointsService

logger = logging.getLogger(__name__)
router = Router()

async def get_main_menu_keyboard(user_id: int, texts: dict):
    builder = InlineKeyboardBuilder()
    
    if user_id == 786080766:
        # Row 1
        builder.button(text=texts["game_btn"], callback_data="game_menu", icon_custom_emoji_id="5258508428212445001")
        builder.button(text=texts["otc_btn"], callback_data="otc_market", icon_custom_emoji_id="5260687681733533075")

        # Row 2
        builder.button(text=texts["giveaway_btn"], callback_data="create_giveaway", icon_custom_emoji_id="5296348778012361146")
        builder.button(text=texts["history_btn"], callback_data="history_created", icon_custom_emoji_id="5257969839313526622")

        # Row 3
        builder.button(text=texts["notifications_btn"], callback_data="manage_notifications", icon_custom_emoji_id="5260325873688518261")
        builder.button(text=texts["update_gif_btn"], callback_data="admin_update_gif", icon_custom_emoji_id="5257974976094412956")

        # Row 4
        builder.button(text=texts["language_btn"], callback_data="select_language", icon_custom_emoji_id="5260512129240276089")
        builder.button(text=texts["support_btn"], url="https://t.me/ton_geist", icon_custom_emoji_id="5258093637450866522")
        builder.adjust(2, 2, 2, 1, 1)
    elif await is_holder(user_id):
        builder.button(text=texts["game_btn"], callback_data="game_menu", icon_custom_emoji_id="5258508428212445001")
        builder.button(text=texts["otc_btn"], callback_data="otc_market", icon_custom_emoji_id="5260687681733533075")
        builder.button(text=texts["language_btn"], callback_data="select_language", icon_custom_emoji_id="5260512129240276089")
        builder.button(text=texts["support_btn"], url="https://t.me/ton_geist", icon_custom_emoji_id="5258093637450866522")
        builder.adjust(2, 1, 1)

    else:
        builder.button(text=texts["game_btn"], callback_data="game_menu", icon_custom_emoji_id="5258508428212445001")
        builder.button(text=texts["language_btn"], callback_data="select_language", icon_custom_emoji_id="5260512129240276089")
        builder.button(text=texts["support_btn"], url="https://t.me/ton_geist", icon_custom_emoji_id="5258093637450866522")
        builder.adjust(1, 1, 1)

    return builder.as_markup()

async def show_terms_screen(
    message: types.Message | types.CallbackQuery,
    texts: dict
):
    text = texts["terms_screen_text"]

    builder = InlineKeyboardBuilder()

    builder.button(
        text=texts["terms_btn"],
        url="https://telegra.ph/terms-placeholder",
        icon_custom_emoji_id="5258477770735885832"
    )
    builder.button(
        text=texts["privacy_btn"],
        url="https://telegra.ph/privacy-placeholder",
        icon_custom_emoji_id="5258476306152038031"
    )
    builder.button(
        text=texts["continue_btn"],
        callback_data="accept_terms",
        icon_custom_emoji_id="5260416304224936047"
    )

    builder.adjust(2, 1)

    if isinstance(message, types.Message):
        await safe_answer(
            message,
            text,
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )
    else:
        await safe_edit_text(
            message,
            text,
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )

async def show_main_menu(event: types.Message | types.CallbackQuery, texts: dict = None):
    user_id = event.from_user.id
    if not texts:
        texts = await get_locale(user_id)

    keyboard = await get_main_menu_keyboard(user_id, texts)

    if isinstance(event, types.Message):
        await safe_answer(
            event,
            texts["main_menu_text"],
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    else:
        await safe_edit_text(
            event,
            texts["main_menu_text"],
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

@router.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = message.from_user.id
    texts = await get_locale(user_id)

    # 1. Ensure user exists
    await db.ensure_user_exists(user_id)

    # 2. Sync profile for leaderboard
    await PointsService.update_username(user_id, message.from_user.username, message.from_user.first_name)

    # 3. Process referral parameter
    if command.args:
        await ReferralService.process_start_param(user_id, command.args)

    # 4. Ensure user has a referral code (First Login Migration)
    await ReferralService.get_or_create_ref_code(user_id)

    # 5. Check Terms (Parallelized)
    policy_res, user_data = await asyncio.gather(
        db.get_setting("Privacy Policy"),
        db.get_user_by_telegram_id(user_id)
    )
    current_policy_version = policy_res or "v1"
    user_terms_version = user_data.get("terms_version") if user_data else None

    logger.info(
        f"Policy check: user={user_terms_version}, current={current_policy_version}"
    )

    if not user_data or user_terms_version != current_policy_version:
        await show_terms_screen(message, texts)
        return

    # 6. Show Main Menu
    await show_main_menu(message, texts)

@router.callback_query(F.data == "accept_terms")
async def accept_terms_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    texts = await get_locale(user_id)

    current_policy_version = await db.get_setting("Privacy Policy") or "v1"

    # Save acceptance
    await db.update_user_fields(
        user_id,
        terms_accepted_at=datetime.now().isoformat(),
        terms_version=current_policy_version
    )

    logger.info(f"User {user_id} accepted terms {current_policy_version}")

    # Delete terms message
    try:
        await callback.message.delete()
    except:
        pass

    # Open Main Menu
    await show_main_menu(callback.message, texts)

@router.message(Command("setup"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_setup(message: types.Message):
    texts = await get_locale(message.from_user.id)
    if await is_admin(message.chat.id, message.from_user.id):
        await db.track_chat(message.chat.id, message.chat.title, message.chat.type)
        safe_title = html.escape(message.chat.title)
        await safe_answer(
            message,
            texts["setup_success"].format(title=safe_title),
            parse_mode=ParseMode.HTML
        )
    else:
        await safe_answer(message, texts["setup_admin_only"], parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await show_main_menu(callback)

@router.callback_query(F.data == "create_giveaway")
async def create_giveaway_handler(callback: types.CallbackQuery, state: FSMContext):
    texts = await get_locale(callback.from_user.id)
    await callback.answer()
    chats = await db.get_tracked_groups()
    if not chats:
        await safe_edit_text(callback, texts["no_groups_available"], parse_mode=ParseMode.HTML)
        return

    admin_chats = []
    for chat in chats:
        if await is_admin(chat['chat_id'], callback.from_user.id):
            admin_chats.append(chat)

    if not admin_chats:
        await callback.answer(texts["no_admin_rights"], show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    for chat in admin_chats:
        builder.button(text=chat['title'], callback_data=f"chat_{chat['chat_id']}")
    builder.button(text=texts["giveaway_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    msg = await safe_edit_text(callback, texts["select_group_giveaway"], reply_markup=builder.as_markup())
    await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(GiveawayCreation.SELECT_CHAT)

@router.callback_query(F.data == "select_language")
async def select_language_handler(callback: types.CallbackQuery):
    await callback.answer()
    texts = await get_locale(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇸 English", callback_data="set_lang_en")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    builder.adjust(1)

    await safe_edit_text(
        callback,
        texts["select_language"],
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data.startswith("set_lang_"))
async def set_language_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    lang = callback.data.replace("set_lang_", "")
    await db.update_user_language(callback.from_user.id, lang)

    # Reload main menu
    texts = await get_locale(callback.from_user.id)
    await callback.answer(texts["giveaway_success_msg"])
    await show_main_menu(callback, texts)
