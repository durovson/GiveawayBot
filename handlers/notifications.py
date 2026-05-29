from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode, ChatType
from typing import Optional, List, Dict
import logging
import re
import html
from datetime import datetime, timedelta

from database import db
from utils import is_any_admin, safe_answer, safe_edit_text, safe_bot_edit_text, safe_bot_send_message

logger = logging.getLogger(__name__)
router = Router()

class NotificationStates(StatesGroup):
    WAITING_FOR_TITLE = State()
    WAITING_FOR_TEXT = State()
    WAITING_FOR_URL = State()
    WAITING_FOR_INTERVAL = State()
    CUSTOM_INTERVAL = State()
    SELECTING_CHATS = State()
    CONFIRMATION = State()

def get_notification_nav_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Back", callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2)
    return builder.as_markup()

def get_interval_keyboard():
    builder = InlineKeyboardBuilder()
    intervals = [1, 2, 3]
    for h in intervals:
        builder.button(text=f"{h}h", callback_data=f"notif_int_{h}")
    builder.button(text="Custom", callback_data="notif_int_custom", icon_custom_emoji_id="5274008024585871702")
    builder.button(text="Back", callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(3, 2, 2)
    return builder.as_markup()

def get_edit_notification_keyboard(is_active: bool):
    builder = InlineKeyboardBuilder()
    builder.button(text="Edit Title", callback_data="notif_edit_title", icon_custom_emoji_id="5778299625370817409")
    builder.button(text="Edit Text", callback_data="notif_edit_text", icon_custom_emoji_id="5891105528356018797")
    builder.button(text="Change Button", callback_data="notif_edit_url", icon_custom_emoji_id="5258185631355378853")
    builder.button(text="Interval", callback_data="notif_edit_interval", icon_custom_emoji_id="5850317551090800862")
    builder.button(text="Select Chats", callback_data="notif_edit_chats", icon_custom_emoji_id="5258486128742244085")

    toggle_text = "OFF" if is_active else "ON"
    builder.button(text=f"Turn {toggle_text}", callback_data="notif_toggle", icon_custom_emoji_id="5258073068852485953")

    builder.button(text="Save & Exit", callback_data="notif_save", icon_custom_emoji_id="5260726538302660868", style="success")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 1, 1, 1, 1)
    return builder.as_markup()

def format_notification_preview(title: str, text: str) -> str:
    safe_title = html.escape(title or "...")
    safe_text = html.escape(text or "...")
    return (
        f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ / {safe_title} /\n"
        f"┋\n"
        f"┣{safe_text}\n"
        f"┋\n"
        f"┗┅┅┅/ #NOTAPES /"
    )

async def show_notification_params(message_or_cb, state: FSMContext, bot: Bot):
    data = await state.get_data()
    preview = format_notification_preview(data.get('title'), data.get('text'))

    interval = data.get('interval_hours', 0)
    is_active = data.get('is_active', True)
    chat_id = data.get('chat_id')
    chat_title = "None"
    if chat_id:
        chats = await db.get_tracked_groups()
        target_chat = next((c for c in chats if c['chat_id'] == chat_id), None)
        if target_chat:
            chat_title = target_chat['title']

    status_text = (
        f"┏┅<tg-emoji emoji-id=\"5260268501515377807\">📣</tg-emoji>┅ / <b>Notification Parameters:</b> /\n"
        f"┋\n"
        f"┣ <b>Interval:</b> {int(interval)}m\n"
        f"┣ <b>Chat:</b> {chat_title}\n"
        f"┣ <b>Status:</b> {'Active' if is_active else 'Inactive'}"
        f"┋\n"
        f"┗┅┅┅/ <b>Preview:</b> /\n"
        f"{preview}"
    )

    reply_markup = get_edit_notification_keyboard(is_active)

    if isinstance(message_or_cb, types.CallbackQuery):
        await safe_edit_text(message_or_cb, status_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        last_msg_id = data.get('last_msg_id')
        await safe_bot_edit_text(bot, message_or_cb.chat.id, last_msg_id, status_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "manage_notifications")
async def start_notification_management(callback: types.CallbackQuery, state: FSMContext):
    if not await is_any_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    await callback.answer()

    notifs = await db.get_notifications()
    builder = InlineKeyboardBuilder()
    for n in notifs:
        builder.button(text=n['title'], callback_data=f"notif_select_{n['id']}")

    builder.button(text="Create New", callback_data="notif_create", icon_custom_emoji_id="5258185631355378853")
    builder.button(text="Main Menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    await safe_edit_text(callback, "<b>┏┅<tg-emoji emoji-id=\"5260268501515377807\">📣</tg-emoji>┅ / Notification Management</b> /\n┋\n\n┗┅┅┅/ Select a notification to edit or create a new one. /", reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "notif_create")
async def create_notification(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_data({"is_editing": False, "is_active": True, "last_msg_id": callback.message.message_id})

    await safe_edit_text(callback,
        "┏┅<<tg-emoji emoji-id=\"5258254475386167466\">🖼</tg-emoji>┅ / <b>Notification Title</b> /\n"
        "┋\n"
        "┣ Enter a title for the notification (used in the header).\n"
        "┋\n"
        "┗┅┅┅/ <b>Enter title:</b> /",
        reply_markup=get_notification_nav_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(NotificationStates.WAITING_FOR_TITLE)

@router.callback_query(F.data.startswith("notif_select_"))
async def select_notification(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    notif_id = int(callback.data.split("_")[-1])
    notifs = await db.get_notifications()
    notif = next((n for n in notifs if n['id'] == notif_id), None)

    if notif:
        interval = notif['interval_hours']
        if interval < 15: interval *= 60
        await state.update_data(
            id=notif['id'],
            title=notif['title'],
            text=notif['text'],
            button_url=notif['button_url'],
            button_text=notif.get('button_text', 'OPEN'),
            interval_hours=interval,
            is_active=notif['is_active'],
            chat_id=notif['chat_id'],
            is_editing=True,
            last_msg_id=callback.message.message_id
        )
        await show_notification_params(callback, state, bot)
        await state.set_state(NotificationStates.CONFIRMATION)

@router.message(NotificationStates.WAITING_FOR_TITLE)
async def enter_notif_title(message: types.Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    await state.update_data(title=message.text)
    data = await state.get_data()

    if data.get('is_editing'):
        await show_notification_params(message, state, bot)
        await state.set_state(NotificationStates.CONFIRMATION)
    else:
        await safe_bot_edit_text(bot, message.chat.id, data['last_msg_id'],
            "┏┅<tg-emoji emoji-id=\"5891105528356018797\">📝</tg-emoji>┅ / <b>Notification Text</b> /\n"
            "┋\n"
            "┣ Enter the main text of the notification.\n"
            "┋\n"
            "┗┅┅┅/ <b>Enter text:</b> /",
            reply_markup=get_notification_nav_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(NotificationStates.WAITING_FOR_TEXT)

@router.message(NotificationStates.WAITING_FOR_TEXT)
async def enter_notif_text(message: types.Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    await state.update_data(text=message.text)
    data = await state.get_data()

    if data.get('is_editing'):
        await show_notification_params(message, state, bot)
        await state.set_state(NotificationStates.CONFIRMATION)
    else:
        await safe_bot_edit_text(bot, message.chat.id, data['last_msg_id'],
            "┏┅<tg-emoji emoji-id=\"5258185631355378853\">🔗</tg-emoji>┅ / <b>Button URL</b> /\n"
            "┋\n"
            "┣ Enter the URL for the button. One button allowed.\n"
            "┋\n"
            "┗┅┅┅/ <b>Enter URL (or type /skip):</b> /",
            reply_markup=get_notification_nav_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(NotificationStates.WAITING_FOR_URL)

@router.message(NotificationStates.WAITING_FOR_URL)
async def enter_notif_url(message: types.Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    url = message.text if message.text != "/skip" else None
    await state.update_data(button_url=url)
    data = await state.get_data()

    if data.get('is_editing'):
        await show_notification_params(message, state, bot)
        await state.set_state(NotificationStates.CONFIRMATION)
    else:
        await safe_bot_edit_text(bot, message.chat.id, data['last_msg_id'],
            "┏┅<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji>┅ / <b>Sending Interval</b> /\n"
            "┋\n"
            "┗┅┅┅/ Select how often the notification should be sent. /",
            reply_markup=get_interval_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(NotificationStates.WAITING_FOR_INTERVAL)

@router.callback_query(F.data.startswith("notif_int_"), NotificationStates.WAITING_FOR_INTERVAL)
async def select_notif_interval(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    val = callback.data.split("_")[-1]

    if val == "custom":
        await safe_edit_text(callback,
            "<b>Enter interval in minutes (min 15, max 60):</b>",
            reply_markup=get_notification_nav_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(NotificationStates.CUSTOM_INTERVAL)
    else:
        await state.update_data(interval_hours=float(val) * 60)
        data = await state.get_data()

        if data.get('is_editing'):
            await show_notification_params(callback, state, bot)
            await state.set_state(NotificationStates.CONFIRMATION)
        else:
            await show_chat_selection(callback, state, bot)

@router.message(NotificationStates.CUSTOM_INTERVAL)
async def process_custom_interval(message: types.Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    data = await state.get_data()
    try:
        val = int(message.text)
        if not (15 <= val <= 60):
            raise ValueError("Out of range")

        await state.update_data(interval_hours=float(val))
        data = await state.get_data()

        if data.get('is_editing'):
            await show_notification_params(message, state, bot)
            await state.set_state(NotificationStates.CONFIRMATION)
        else:
            await show_chat_selection(message, state, bot)
    except ValueError:
        await safe_bot_edit_text(bot, message.chat.id, data['last_msg_id'],
            "❌ Invalid number. Please enter a number between 15 and 60.\n\n"
            "<b>Enter interval in minutes (min 15, max 60):</b>",
            reply_markup=get_notification_nav_keyboard(),
            parse_mode=ParseMode.HTML)

async def show_chat_selection(message_or_cb, state: FSMContext, bot: Bot):
    chats = await db.get_tracked_groups()
    builder = InlineKeyboardBuilder()
    for chat in chats:
        builder.button(text=chat['title'], callback_data=f"notif_chat_{chat['chat_id']}")

    builder.button(text="Back", callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    text = "<b>Select Target Group</b>\n\n<blockquote>Select the group where the ad will be posted.</blockquote>"

    if isinstance(message_or_cb, types.CallbackQuery):
        await safe_edit_text(message_or_cb, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    else:
        data = await state.get_data()
        await safe_bot_edit_text(bot, message_or_cb.chat.id, data['last_msg_id'], text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

    await state.set_state(NotificationStates.SELECTING_CHATS)

@router.callback_query(F.data.startswith("notif_chat_"), NotificationStates.SELECTING_CHATS)
async def select_notif_chat(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    chat_id = int(callback.data.split("_")[-1])
    await state.update_data(chat_id=chat_id)
    await show_notification_params(callback, state, bot)
    await state.set_state(NotificationStates.CONFIRMATION)

@router.callback_query(F.data == "notif_save", NotificationStates.CONFIRMATION)
async def save_notification(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get('chat_id') or not data.get('title') or not data.get('text') or not data.get('interval_hours'):
        await callback.answer("❌ Please fill all fields", show_alert=True)
        return

    notif_data = {
        "title": data['title'],
        "text": data['text'],
        "button_url": data.get('button_url'),
        "interval_hours": data['interval_hours'],
        "chat_id": data['chat_id'],
        "is_active": data.get('is_active', True)
    }
    if data.get('id'):
        notif_data['id'] = data['id']

    await db.upsert_notification(notif_data)
    await callback.answer("✅ Saved successfully", show_alert=True)
    await state.clear()
    await start_notification_management(callback, state)

@router.callback_query(F.data == "notif_toggle", NotificationStates.CONFIRMATION)
async def toggle_notification(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(is_active=not data.get('is_active', True))
    await show_notification_params(callback, state, bot)

@router.callback_query(F.data.startswith("notif_edit_"), NotificationStates.CONFIRMATION)
async def edit_notif_field(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    field = callback.data.split("_")[-1]

    if field == "title":
        await safe_edit_text(callback, "<b>Enter new title:</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(NotificationStates.WAITING_FOR_TITLE)
    elif field == "text":
        await safe_edit_text(callback, "<b>Enter new text:</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(NotificationStates.WAITING_FOR_TEXT)
    elif field == "url":
        await safe_edit_text(callback, "<b>Enter new URL (or /skip):</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(NotificationStates.WAITING_FOR_URL)
    elif field == "interval":
        await safe_edit_text(callback, "<b>Select new interval:</b>", reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(NotificationStates.WAITING_FOR_INTERVAL)
    elif field == "chats":
        await show_chat_selection(callback, state, bot)

@router.callback_query(F.data == "notif_back")
async def process_notif_back(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()

    if current_state == NotificationStates.WAITING_FOR_TITLE:
        await start_notification_management(callback, state)
    elif current_state == NotificationStates.WAITING_FOR_TEXT:
        await safe_edit_text(callback, "<b>Notification Title</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(NotificationStates.WAITING_FOR_TITLE)
    elif current_state == NotificationStates.WAITING_FOR_URL:
        await safe_edit_text(callback, "<b>Notification Text</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(NotificationStates.WAITING_FOR_TEXT)
    elif current_state == NotificationStates.WAITING_FOR_INTERVAL:
        await safe_edit_text(callback, "<b>Button URL</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(NotificationStates.WAITING_FOR_URL)
    elif current_state == NotificationStates.CUSTOM_INTERVAL:
        await safe_edit_text(callback, "<b>Select interval:</b>", reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(NotificationStates.WAITING_FOR_INTERVAL)
    elif current_state == NotificationStates.SELECTING_CHATS:
        await safe_edit_text(callback, "<b>Select interval:</b>", reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(NotificationStates.WAITING_FOR_INTERVAL)
    elif current_state == NotificationStates.CONFIRMATION:
        await start_notification_management(callback, state)
    else:
        await start_notification_management(callback, state)
