import html
import re
import json
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from database import db
from utils import safe_edit_text, safe_bot_edit_text, strip_custom_emojis
from services.localization import get_locale
import logging

logger = logging.getLogger(__name__)

router = Router()

class NotificationStates(StatesGroup):
    SELECT_CHAT = State()
    ENTER_TITLE = State()
    ENTER_TEXT = State()
    ENTER_BUTTONS = State()
    ENTER_INTERVAL = State()
    ENTER_CUSTOM_INTERVAL = State()
    PREVIEW = State()

async def get_notification_nav_keyboard(user_id: int, texts: dict):
    # texts from middleware
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["notif_back_btn"], callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["notif_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)
    return builder.as_markup()

def get_interval_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="3H", callback_data="interval_180")
    builder.button(text="8H", callback_data="interval_480")
    builder.button(text="12H", callback_data="interval_720")
    builder.button(text="CUSTOM", callback_data="interval_custom")
    builder.button(text="BACK", callback_data="notif_back")
    builder.adjust(3, 1, 1)
    return builder.as_markup()

@router.callback_query(F.data == "manage_notifications")
async def start_notification_management(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    user_id = callback.from_user.id
    # texts from middleware
    await state.clear()

    notifications = await db.get_notifications()

    builder = InlineKeyboardBuilder()
    for n in notifications:
        status = "✅" if n['is_active'] else "⏸"
        builder.button(text=f"{status} {n['title']}", callback_data=f"notif_view_{n['id']}")

    builder.button(text=texts["notif_add_new_btn"], callback_data="notif_add", icon_custom_emoji_id="5258260149037965799")
    builder.button(text=texts["notif_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    text = texts["notif_mgmt_title"]
    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "notif_add")
async def add_new_notification(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    user_id = callback.from_user.id
    # texts from middleware
    text = texts["notif_enter_title"]
    await safe_edit_text(callback, text, reply_markup=await get_notification_nav_keyboard(user_id, texts), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(NotificationStates.ENTER_TITLE)

@router.callback_query(F.data.startswith("notif_view_"))
async def view_notification(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    notif_id = int(callback.data.split("_")[-1])
    notifs = await db.get_notifications()
    notif = next((n for n in notifs if n['id'] == notif_id), None)
    if not notif: return

    await state.update_data(
        id=notif['id'],
        title=notif['title'],
        text=notif['text'],
        custom_buttons=notif.get('custom_buttons', []),
        interval_minutes=notif['interval_minutes'],
        chat_id=notif['chat_id'],
        is_active=notif['is_active']
    )
    await show_notification_preview(callback, state, bot, texts)

@router.message(NotificationStates.ENTER_TITLE, F.text)
async def process_title(message: types.Message, state: FSMContext, bot: Bot, texts: dict):
    user_id = message.from_user.id
    # texts from middleware
    try: await message.delete()
    except: pass

    await state.update_data(title=message.text)
    data = await state.get_data()
    if data.get('is_editing'):
        await show_notification_preview(message, state, bot, texts)
    else:
        text = texts["notif_enter_text"]
        msg = await safe_bot_edit_text(bot, message.chat.id, data['last_msg_id'], text, reply_markup=await get_notification_nav_keyboard(user_id, texts), parse_mode=ParseMode.HTML)
        if msg: await state.update_data(last_msg_id=msg.message_id)
        await state.set_state(NotificationStates.ENTER_TEXT)

@router.message(NotificationStates.ENTER_TEXT, F.text)
async def process_text(message: types.Message, state: FSMContext, bot: Bot, texts: dict):
    try: await message.delete()
    except: pass
    await state.update_data(text=message.text)
    data = await state.get_data()
    if data.get('is_editing'):
        await show_notification_preview(message, state, bot, texts)
    else:
        await show_btn_input_screen(message, state, bot, texts)

async def show_btn_input_screen(event, state: FSMContext, bot: Bot, texts: dict):
    user_id = event.from_user.id if isinstance(event, types.CallbackQuery) else event.chat.id
    # texts from middleware
    text = texts["notif_enter_buttons"]

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["notif_skip_btn"], callback_data="notif_skip_btns")
    builder.button(text=texts["notif_back_btn"], callback_data="notif_back")
    builder.button(text=texts["notif_main_menu_btn"], callback_data="main_menu", style="danger")
    builder.adjust(1)

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event.message, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        data = await state.get_data()
        msg = await safe_bot_edit_text(bot, event.chat.id, data['last_msg_id'], text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        if msg: await state.update_data(last_msg_id=msg.message_id)

    await state.set_state(NotificationStates.ENTER_BUTTONS)

@router.message(NotificationStates.ENTER_BUTTONS, F.text)
async def process_buttons(message: types.Message, state: FSMContext, bot: Bot, texts: dict):
    try: await message.delete()
    except: pass

    raw_text = message.text.strip()
    if raw_text.lower() == "skip":
        await state.update_data(custom_buttons=[])
    else:
        buttons = []
        lines = raw_text.split('\n')
        for line in lines:
            if ' - ' in line:
                label, url = line.split(' - ', 1)
                buttons.append({"text": label.strip(), "url": url.strip()})
        await state.update_data(custom_buttons=buttons)

    data = await state.get_data()
    if data.get('is_editing'):
        await show_notification_preview(message, state, bot, texts)
    else:
        await show_interval_selector(message, state, bot, texts)

@router.callback_query(NotificationStates.ENTER_BUTTONS, F.data == "notif_skip_btns")
async def skip_buttons(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    await state.update_data(custom_buttons=[])
    data = await state.get_data()
    if data.get('is_editing'):
        await show_notification_preview(callback, state, bot, texts)
    else:
        await show_interval_selector(callback, state, bot, texts)

async def show_interval_selector(event, state: FSMContext, bot: Bot, texts: dict):
    user_id = event.from_user.id if isinstance(event, types.CallbackQuery) else event.chat.id
    # texts from middleware
    text = texts["notif_enter_interval"]

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event.message, text, reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML, state=state)
    else:
        data = await state.get_data()
        msg = await safe_bot_edit_text(bot, event.chat.id, data['last_msg_id'], text, reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML)
        if msg: await state.update_data(last_msg_id=msg.message_id)

    await state.set_state(NotificationStates.ENTER_INTERVAL)

@router.callback_query(NotificationStates.ENTER_INTERVAL, F.data.startswith("interval_"))
async def process_interval(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    val = callback.data.split("_")[-1]

    if val == "custom":
        user_id = callback.from_user.id
        # texts from middleware
        text = texts["notif_custom_interval_title"]
        await safe_edit_text(callback, text, reply_markup=await get_notification_nav_keyboard(user_id, texts), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.ENTER_CUSTOM_INTERVAL)
    else:
        await state.update_data(interval_minutes=float(val))
        data = await state.get_data()
        if data.get('is_editing'):
            await show_notification_preview(callback, state, bot, texts)
        else:
            await show_chat_selector(callback, state, bot, texts)

@router.message(NotificationStates.ENTER_CUSTOM_INTERVAL, F.text)
async def process_custom_interval(message: types.Message, state: FSMContext, bot: Bot, texts: dict):
    user_id = message.from_user.id
    # texts from middleware
    try: await message.delete()
    except: pass

    data = await state.get_data()
    try:
        val = int(message.text)
        if not (15 <= val <= 1440):
            raise ValueError("Out of range")

        await state.update_data(interval_minutes=float(val))
        if data.get('is_editing'):
            await show_notification_preview(message, state, bot, texts)
        else:
            await show_chat_selector(message, state, bot, texts)
    except ValueError:
        text = texts["notif_invalid_interval"]
        msg = await safe_bot_edit_text(bot, message.chat.id, data['last_msg_id'], text, reply_markup=await get_notification_nav_keyboard(user_id, texts), parse_mode=ParseMode.HTML)
        if msg: await state.update_data(last_msg_id=msg.message_id)

async def show_chat_selector(event, state: FSMContext, bot: Bot, texts: dict):
    user_id = event.from_user.id if isinstance(event, types.CallbackQuery) else event.chat.id
    # texts from middleware
    chats = await db.get_tracked_groups()
    builder = InlineKeyboardBuilder()
    for chat in chats:
        builder.button(text=chat['title'], callback_data=f"notif_chat_sel_{chat['chat_id']}")

    builder.button(text=texts["notif_back_btn"], callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["notif_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    text = texts["notif_select_chat_title"]

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event.message, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        data = await state.get_data()
        msg = await safe_bot_edit_text(bot, event.chat.id, data['last_msg_id'], text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        if msg: await state.update_data(last_msg_id=msg.message_id)

    await state.set_state(NotificationStates.SELECT_CHAT)

@router.callback_query(F.data.startswith("notif_chat_sel_"), NotificationStates.SELECT_CHAT)
async def process_notif_chat(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    chat_id = int(callback.data.split("_")[-1])
    await state.update_data(chat_id=chat_id)
    await show_notification_preview(callback, state, bot, texts)

async def show_notification_preview(event, state: FSMContext, bot: Bot, texts: dict):
    user_id = event.from_user.id if isinstance(event, types.CallbackQuery) else event.chat.id
    # texts from middleware
    data = await state.get_data()
    title = data.get('title')
    text = data.get('text')
    interval = data.get('interval_minutes')
    is_active = data.get('is_active', True)

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["notif_edit_title_btn"], callback_data="notif_edit_title")
    builder.button(text=texts["notif_edit_text_btn"], callback_data="notif_edit_text")
    builder.button(text=texts["notif_edit_buttons_btn"], callback_data="notif_edit_btns")
    builder.button(text=texts["notif_edit_interval_btn"], callback_data="notif_edit_interval")
    builder.button(text=texts["notif_edit_chat_btn"], callback_data="notif_edit_chat")

    status_label = texts["notif_active"] if is_active else texts["notif_paused"]
    builder.button(text=texts["notif_toggle_status_btn"].format(status=status_label), callback_data="notif_toggle_status")

    builder.button(text=texts["notif_save_btn"], callback_data="notif_confirm_save", style="success")
    builder.button(text=texts["notif_main_menu_btn"], callback_data="main_menu", style="danger")
    builder.adjust(2, 2, 2, 1, 1)

    preview_text = texts["notif_preview_header"] +         f"┣ <b>Title:</b> {html.escape(title)}\n" +         f"┣ <b>Text:</b> {html.escape(text)}\n" +         f"┣ <b>Interval:</b> {interval} min\n" +         texts["notif_preview_footer"]

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event.message, preview_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    else:
        msg = await safe_bot_edit_text(bot, event.chat.id, data['last_msg_id'], preview_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        if msg: await state.update_data(last_msg_id=msg.message_id)

    await state.set_state(NotificationStates.PREVIEW)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_title")
async def edit_title(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    user_id = callback.from_user.id
    # texts from middleware
    await state.update_data(is_editing=True)
    await safe_edit_text(callback, texts["notif_enter_title"], reply_markup=await get_notification_nav_keyboard(user_id, texts), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(NotificationStates.ENTER_TITLE)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_text")
async def edit_text(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    user_id = callback.from_user.id
    # texts from middleware
    await state.update_data(is_editing=True)
    await safe_edit_text(callback, texts["notif_enter_text"], reply_markup=await get_notification_nav_keyboard(user_id, texts), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(NotificationStates.ENTER_TEXT)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_btns")
async def edit_btns(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    await state.update_data(is_editing=True)
    await show_btn_input_screen(callback, state, bot, texts)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_interval")
async def edit_interval(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    user_id = callback.from_user.id
    # texts from middleware
    await state.update_data(is_editing=True)
    await safe_edit_text(callback, texts["notif_enter_interval"], reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(NotificationStates.ENTER_INTERVAL)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_chat")
async def edit_chat(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    await state.update_data(is_editing=True)
    await show_chat_selector(callback, state, bot, texts)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_toggle_status")
async def toggle_status(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(is_active=not data.get('is_active', True))
    await show_notification_preview(callback, state, bot, texts)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_confirm_save")
async def confirm_save(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    user_id = callback.from_user.id
    # texts from middleware
    data = await state.get_data()
    title = data.get('title')
    text = data.get('text')
    interval = data.get('interval_minutes')
    chat_id = data.get('chat_id')

    if not all([title, text, interval, chat_id]):
        await callback.answer(texts["notif_fill_all_fields"], show_alert=True)
        return

    await callback.answer()

    notif_data = {
        "title": title,
        "text": text,
        "custom_buttons": data.get('custom_buttons', []),
        "interval_minutes": interval,
        "chat_id": chat_id,
        "is_active": data.get('is_active', True)
    }
    if data.get('id'):
        notif_data['id'] = data['id']

    await db.upsert_notification(notif_data)

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["notif_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531")

    await safe_edit_text(callback, texts["notif_save_success"], reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    await state.clear()

@router.callback_query(F.data == "notif_back")
async def handle_notif_back(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()
    is_editing = data.get('is_editing')

    if is_editing or current_state == NotificationStates.PREVIEW.state:
        await state.update_data(is_editing=False)
        await show_notification_preview(callback, state, bot, texts)
        return

    if current_state == NotificationStates.ENTER_TITLE.state:
        await start_notification_management(callback, state, texts)
    elif current_state == NotificationStates.ENTER_TEXT.state:
        await add_new_notification(callback, state, texts)
    elif current_state == NotificationStates.ENTER_BUTTONS.state:
        user_id = callback.from_user.id
        # texts from middleware
        await safe_edit_text(callback, texts["notif_enter_text"], reply_markup=await get_notification_nav_keyboard(user_id, texts), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.ENTER_TEXT)
    elif current_state == NotificationStates.ENTER_INTERVAL.state:
        await show_btn_input_screen(callback, state, bot, texts)
    elif current_state == NotificationStates.ENTER_CUSTOM_INTERVAL.state:
        await show_interval_selector(callback, state, bot, texts)
    elif current_state == NotificationStates.SELECT_CHAT.state:
        await show_interval_selector(callback, state, bot, texts)
    else:
        await start_notification_management(callback, state, texts)
