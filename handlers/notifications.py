from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode, ChatType
from typing import Optional, List, Dict, Any
import logging
import re
import html
import os
from datetime import datetime, timedelta

from database import db
from utils import is_any_admin, safe_answer, safe_edit_text, safe_bot_edit_text, safe_bot_send_message

logger = logging.getLogger(__name__)
router = Router()

class NotificationStates(StatesGroup):
    WAITING_FOR_TITLE = State()
    WAITING_FOR_TEXT = State()
    WAITING_FOR_BUTTONS = State()
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
    intervals = [60, 120, 180, 360, 720]
    for m in intervals:
        hours, minutes = divmod(m, 60)
        label = f"{hours}h {minutes}m" if hours and minutes else (f"{hours}h" if hours else f"{minutes}m")
        builder.button(text=label, callback_data=f"notif_int_{m}")
    builder.button(text="Custom", callback_data="notif_int_custom", icon_custom_emoji_id="5274008024585871702")
    builder.button(text="Back", callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(3, 2, 2)
    return builder.as_markup()

def get_edit_notification_keyboard(is_active: bool):
    builder = InlineKeyboardBuilder()
    builder.button(text="Edit Title", callback_data="notif_edit_title", icon_custom_emoji_id="5778299625370817409")
    builder.button(text="Edit Text", callback_data="notif_edit_text", icon_custom_emoji_id="5891105528356018797")
    builder.button(text="Manage Buttons", callback_data="notif_edit_buttons", icon_custom_emoji_id="5258185631355378853")
    builder.button(text="Interval", callback_data="notif_edit_interval", icon_custom_emoji_id="5850317551090800862")
    builder.button(text="Select Chats", callback_data="notif_edit_chats", icon_custom_emoji_id="5258486128742244085")

    toggle_text = "OFF" if is_active else "ON"
    builder.button(text=f"Turn {toggle_text}", callback_data="notif_toggle", icon_custom_emoji_id="5258073068852485953")

    builder.button(text="Save & Exit", callback_data="notif_save", icon_custom_emoji_id="5260726538302660868", style="success")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 1, 1, 1, 1)
    return builder.as_markup()

def format_notification_preview(title: str, text: str, custom_buttons: List[Dict] = None) -> str:
    safe_title = html.escape(title or "...")
    safe_text = html.escape(text or "...")

    btn_info = ""
    if custom_buttons:
        btn_info = "\n┋\n┋ <b>Buttons:</b>\n"
        for btn in custom_buttons:
            btn_info += f"┋ — {html.escape(btn['text'])} ({btn['url']})\n"

    return (
        f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ / {safe_title} /\n"
        f"┋\n"
        f"┣{safe_text}"
        f"{btn_info}"
        f"┋\n"
        f"┗┅┅┅/ #NOTAPES /"
    )

async def show_notification_params(message_or_cb, state: FSMContext, bot: Bot):
    data = await state.get_data()
    preview = format_notification_preview(data.get('title'), data.get('text'), data.get('custom_buttons', []))

    interval = data.get('interval_minutes', 0)
    is_active = data.get('is_active', True)
    chat_id = data.get('chat_id')
    chat_title = "None"
    if chat_id:
        chats = await db.get_tracked_groups()
        target_chat = next((c for c in chats if c['chat_id'] == chat_id), None)
        if target_chat:
            chat_title = target_chat['title']

    status_text = (
        f"<b>Notification Parameters:</b>\n\n"
        f"<blockquote>"
        f"<b>Interval:</b> {format_interval(interval)}\n"
        f"<b>Chat:</b> {chat_title}\n"
        f"<b>Status:</b> {'Active' if is_active else 'Inactive'}"
        f"</blockquote>\n\n"
        f"<b>Preview:</b>\n\n"
        f"{status_text_preview_helper(preview)}"
    )

    reply_markup = get_edit_notification_keyboard(is_active)

    if isinstance(message_or_cb, types.CallbackQuery):
        await safe_edit_text(message_or_cb, status_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, state=state)
    else:
        last_msg_id = data.get('last_msg_id')
        await safe_bot_edit_text(bot, message_or_cb.chat.id, last_msg_id, status_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML, state=state)

def status_text_preview_helper(preview: str) -> str:
    return preview

def format_interval(interval_minutes: int) -> str:
    h, m = divmod(int(interval_minutes), 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"

@router.callback_query(F.data == "manage_notifications")
async def start_notification_management(callback: types.CallbackQuery, state: FSMContext):
    if not await is_any_admin(callback.from_user.id):
        await callback.answer("Access denied", show_alert=True)
        return

    await callback.answer()

    notifs = await db.get_notifications()
    builder = InlineKeyboardBuilder()
    for n in notifs:
        builder.button(text=n['title'], callback_data=f"notif_sel_{n['id']}")

    builder.button(text="Create New", callback_data="notif_new", icon_custom_emoji_id="5258252276362909477")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    await safe_edit_text(callback, "<b>Notification Management</b>", reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "notif_new")
async def create_notif_title(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    msg = await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5258252276362909477\">➕</tg-emoji> <b>Notification Title</b>\n\n"
        "<blockquote>Enter the internal title for this notification (visible only to you).</blockquote>\n\n"
        "<b>Enter title:</b>",
        reply_markup=get_notification_nav_keyboard(),
        parse_mode=ParseMode.HTML, state=state)
    if msg: await state.update_data(last_msg_id=msg.message_id, custom_buttons=[])
    await state.set_state(NotificationStates.WAITING_FOR_TITLE)

@router.callback_query(F.data.startswith("notif_sel_"))
async def select_notif_to_manage(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    notif_id = int(callback.data.split("_")[-1])
    notifs = await db.get_notifications()
    notif = next((n for n in notifs if n['id'] == notif_id), None)
    if not notif: return

    await state.clear()

    custom_buttons = notif.get('custom_buttons')
    if not custom_buttons and notif.get('button_url'):
        custom_buttons = [{"text": notif.get('button_text') or "OPEN", "url": notif['button_url']}]
    elif not custom_buttons:
        custom_buttons = []

    await state.update_data(
        id=notif['id'],
        title=notif['title'],
        text=notif['text'],
        custom_buttons=custom_buttons,
        interval_minutes=notif['interval_minutes'],
        chat_id=notif['chat_id'],
        is_active=notif['is_active'],
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
            "<tg-emoji emoji-id=\"5891105528356018797\">📝</tg-emoji> <b>Notification Text</b>\n\n"
            "<blockquote>Enter the main text of the notification.</blockquote>\n\n"
            "<b>Enter text:</b>",
            reply_markup=get_notification_nav_keyboard(),
            parse_mode=ParseMode.HTML, state=state)
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
        await show_add_button_prompt(message, state, bot)

async def show_add_button_prompt(message_or_cb, state: FSMContext, bot: Bot, error_msg: str = ""):
    data = await state.get_data()
    buttons = data.get('custom_buttons', [])

    text = (
        f"<tg-emoji emoji-id=\"5257965174979042426\">📝</tg-emoji> <b>Notification Buttons</b> ({len(buttons)} added)\n\n"
        "<blockquote>Please send the text for the button and its link.\n\n"
        "Example: Visit Website https://example.com</blockquote>"
    )

    if error_msg:
        text = f"{error_msg}\n\n{text}"

    builder = InlineKeyboardBuilder()
    if buttons:
        builder.button(text="Done / Skip", callback_data="notif_buttons_done", icon_custom_emoji_id="5260416304224936047")
    else:
        builder.button(text="Skip", callback_data="notif_buttons_done", icon_custom_emoji_id="5260687681733533075")

    builder.button(text="Back", callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    if isinstance(message_or_cb, types.CallbackQuery):
        await safe_edit_text(message_or_cb, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        await safe_bot_edit_text(bot, message_or_cb.chat.id, data['last_msg_id'], text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

    await state.set_state(NotificationStates.WAITING_FOR_BUTTONS)

@router.message(NotificationStates.WAITING_FOR_BUTTONS)
async def process_button_input(message: types.Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    text = message.text
    url_match = re.search(r"(https?://\S+|t\.me/\S+)", text)

    if not url_match:
        await show_add_button_prompt(message, state, bot, error_msg="❌ <b>Invalid Input:</b> No link found.")
        return

    url = url_match.group(0)
    if url.startswith("t.me/"):
        url = "https://" + url

    button_title = text.replace(url_match.group(0), "").strip()
    if not button_title:
        button_title = "OPEN"

    data = await state.get_data()
    buttons = data.get('custom_buttons', [])
    buttons.append({"text": button_title, "url": url})

    await state.update_data(custom_buttons=buttons)
    await show_add_button_prompt(message, state, bot)

@router.callback_query(F.data == "notif_buttons_done", NotificationStates.WAITING_FOR_BUTTONS)
async def finish_buttons(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()

    if data.get('is_editing'):
        await show_notification_params(callback, state, bot)
        await state.set_state(NotificationStates.CONFIRMATION)
    else:
        await safe_edit_text(callback,
            "<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji> <b>Sending Interval</b>\n\n"
            "<blockquote>Select how often the notification should be sent.</blockquote>",
            reply_markup=get_interval_keyboard(),
            parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.WAITING_FOR_INTERVAL)

@router.callback_query(F.data.startswith("notif_int_"), NotificationStates.WAITING_FOR_INTERVAL)
async def select_notif_interval(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    val = callback.data.split("_")[-1]

    if val == "custom":
        await safe_edit_text(callback,
            "<b>Enter interval in minutes (min 15, max 720):</b>",
            reply_markup=get_notification_nav_keyboard(),
            parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.CUSTOM_INTERVAL)
    else:
        await state.update_data(interval_minutes=int(val))
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
        if not (15 <= val <= 720):
            raise ValueError("Out of range")

        await state.update_data(interval_minutes=float(val))
        data = await state.get_data()

        if data.get('is_editing'):
            await show_notification_params(message, state, bot)
            await state.set_state(NotificationStates.CONFIRMATION)
        else:
            await show_chat_selection(message, state, bot)
    except ValueError:
        await safe_bot_edit_text(bot, message.chat.id, data['last_msg_id'],
            "❌ Invalid number. Please enter a number between 15 and 720.\n\n"
            "<b>Enter interval in minutes (min 15, max 720):</b>",
            reply_markup=get_notification_nav_keyboard(),
            parse_mode=ParseMode.HTML, state=state)

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
        await safe_edit_text(message_or_cb, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        data = await state.get_data()
        await safe_bot_edit_text(bot, message_or_cb.chat.id, data['last_msg_id'], text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

    await state.set_state(NotificationStates.SELECTING_CHATS)

@router.callback_query(F.data.startswith("notif_chat_"), NotificationStates.SELECTING_CHATS)
async def select_notif_chat(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Сбой отправки callback.answer (игнорируем): {e}")

    chat_id = int(callback.data.split("_")[-1])
    await state.update_data(chat_id=chat_id)
    await show_notification_params(callback, state, bot)
    await state.set_state(NotificationStates.CONFIRMATION)

@router.callback_query(F.data == "notif_save", NotificationStates.CONFIRMATION)
async def save_notification(callback: types.CallbackQuery, state: FSMContext):
    # 1. Сразу гасим часики на кнопке и изолируем сетевую ошибку Telegram
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Сбой отправки callback.answer (игнорируем): {e}")

    data = await state.get_data()
    if not data.get('chat_id') or not data.get('title') or not data.get('text') or not data.get('interval_minutes'):
        await callback.message.answer("❌ Please fill all fields")
        return

    notif_data = {
        "title": data['title'],
        "text": data['text'],
        "custom_buttons": data.get('custom_buttons', []),
        "interval_minutes": data['interval_minutes'],
        "chat_id": data['chat_id'],
        "is_active": data.get('is_active', True)
    }

    # Still keep legacy fields for now just in case, but custom_buttons is primary
    if data.get('custom_buttons'):
        notif_data['button_url'] = data['custom_buttons'][0]['url']
        notif_data['button_text'] = data['custom_buttons'][0]['text']

    if data.get('id'):
        notif_data['id'] = data['id']

    try:
        # 3. Логика записи в БД Supabase (убедись, что этот блок выполняется независимо)
        await (db.update_notification(data['id'], notif_data) if data.get('id') else db.create_notification(notif_data))

        # 4. Уведомляем пользователя об успешном создании
        await callback.message.answer("✅ Saved successfully")
        await state.clear()
        await start_notification_management(callback, state)

    except Exception as db_error:
        logger.error(f"Ошибка при записи уведомления в Supabase: {db_error}")
        await callback.message.answer("❌ Не удалось сохранить уведомление в базу данных. Попробуйте еще раз.")

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

    await state.update_data(is_editing=True)

    if field == "title":
        await safe_edit_text(callback, "<b>Enter new title:</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.WAITING_FOR_TITLE)
    elif field == "text":
        await safe_edit_text(callback, "<b>Enter new text:</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.WAITING_FOR_TEXT)
    elif field == "buttons":
        await state.update_data(custom_buttons=[]) # Reset buttons when editing for simplicity, or we could add management
        await show_add_button_prompt(callback, state, bot)
    elif field == "interval":
        await safe_edit_text(callback, "<b>Select new interval:</b>", reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML, state=state)
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
        await safe_edit_text(callback, "<b>Notification Title</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.WAITING_FOR_TITLE)
    elif current_state == NotificationStates.WAITING_FOR_BUTTONS:
        await safe_edit_text(callback, "<b>Notification Text</b>", reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.WAITING_FOR_TEXT)
    elif current_state == NotificationStates.WAITING_FOR_INTERVAL:
        await show_add_button_prompt(callback, state, bot)
    elif current_state == NotificationStates.CUSTOM_INTERVAL:
        await safe_edit_text(callback, "<b>Select interval:</b>", reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.WAITING_FOR_INTERVAL)
    elif current_state == NotificationStates.SELECTING_CHATS:
        await safe_edit_text(callback, "<b>Select interval:</b>", reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.WAITING_FOR_INTERVAL)
    elif current_state == NotificationStates.CONFIRMATION:
        await start_notification_management(callback, state)
    else:
        await start_notification_management(callback, state)
