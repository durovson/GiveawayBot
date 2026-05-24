import html
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from database import db
from utils import is_admin, is_any_admin, safe_answer, safe_edit_text, is_holder

router = Router()

HOLDERS_CHAT_ID = -1001944951957

MAIN_MENU_TEXT = (
    "<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji><b>NOTAPES | MAIN ECOSYSTEM</b><tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>\n\n"
    "<blockquote>Welcome to the official ecosystem hub. Explore the game sector, manage systems, or contact support. All nodes are active.</blockquote>\n\n"
    "<b>Select a section from the navigation grid below:</b>"
)

async def get_main_menu_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    # Задача 1: Нативный вызов кастомных премиум эмодзи
    builder.button(text='GAME ZONE', callback_data="game_main", icon_custom_emoji_id="5258508428212445001")
    
    is_user_holder = await is_holder(user_id)
    if is_user_holder:
        builder.button(text='SYSTEM', callback_data="system_submenu", icon_custom_emoji_id="5258096772776991776")
    
    builder.button(text='SUPPORT', url="https://t.me/ton_geist", icon_custom_emoji_id="5258020476977946656")

    if is_user_holder:
        builder.adjust(1, 1, 1)
    else:
        builder.adjust(1, 1)

    return builder.as_markup()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await safe_answer(
        message, MAIN_MENU_TEXT,
        reply_markup=await get_main_menu_keyboard(message.from_user.id),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await safe_edit_text(
        callback, MAIN_MENU_TEXT,
        reply_markup=await get_main_menu_keyboard(callback.from_user.id),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data == "system_submenu")
async def open_system_submenu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    is_user_admin = await is_admin(HOLDERS_CHAT_ID, user_id)
    builder = InlineKeyboardBuilder()

    if not is_user_admin:
        builder.button(text="OTC Market", callback_data="otc_market")
    else:
        builder.button(text="Giveaway", callback_data="create_giveaway")
        builder.button(text="History", callback_data="history_created")
        builder.button(text="OTC Market", callback_data="otc_market")
        builder.button(text="Notifications", callback_data="manage_notifications")
        if user_id == 786080766:
            builder.button(text="Update GIF", callback_data="admin_update_gif")

    builder.button(text='Back to Main Menu', callback_data="main_menu", icon_custom_emoji_id="5257963315258204021")
    builder.adjust(2 if is_user_admin else 1)

    system_text = (
        "┏┅<tg-emoji emoji-id=\"5258096772776991776\">⚙️</tg-emoji>┅ <b>/ SYSTEM CORE /</b>\n"
        "┋\n"
        "┣ <blockquote>Authorized executive dashboard. Legacy operational privileges and holder infrastructure subroutines are fully online.</blockquote>\n"
        "┋\n"
        "┗┅┅┅/ #NOTAPES /"
    )
    await safe_edit_text(callback, system_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
