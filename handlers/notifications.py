import re
import html
import logging
from typing import Optional, List, Dict

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram import Bot

from database import db
from utils import safe_edit_text, safe_bot_edit_text, is_any_admin

logger = logging.getLogger(__name__)

router = Router()

class NotificationStates(StatesGroup):
    ENTER_TITLE = State()
    ENTER_TEXT = State()
    ENTER_BUTTONS = State()
    ENTER_INTERVAL = State()
    ENTER_CUSTOM_INTERVAL = State()
    SELECT_CHAT = State()
    PREVIEW = State()

def get_notification_nav_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Back", callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main Menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2)
    return builder.as_markup()

def get_interval_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="3 hours", callback_data="notif_int_180")
    builder.button(text="6 hours", callback_data="notif_int_360")
    builder.button(text="8 hours", callback_data="notif_int_480")
    builder.button(text="Custom", callback_data="notif_int_custom", icon_custom_emoji_id="5258204546391351475")
    builder.button(text="Back", callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main Menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(3, 1, 2)
    return builder.as_markup()

def format_notification_preview(title: str, text: str, buttons: List[Dict]) -> str:
    post_text = (
        f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅/ {html.escape(title or '...')} /\n"
        "┋\n"
        f"┣ {html.escape(text or '...')}\n"
        "┋\n"
    )
    for b in buttons:
        post_text += f"┣ [ {html.escape(b['text'])} - {html.escape(b['url'])} ]\n"
    post_text += "┗┅ / #NOTAPES /"
    return post_text

async def show_notification_preview(event, state: FSMContext, bot: Bot):
    data = await state.get_data()
    title = data.get("title", "...")
    text = data.get("text", "...")
    interval = data.get("interval_minutes", 60)
    chat_id = data.get("chat_id")
    is_active = data.get("is_active", True)
    last_msg_id = data.get("last_msg_id")

    chat_title = "None"
    if chat_id:
        chats = await db.get_tracked_groups()
        target_chat = next((c for c in chats if c['chat_id'] == chat_id), None)
        if target_chat:
            chat_title = target_chat['title']

    buttons = data.get("custom_buttons", [])
    post_text = format_notification_preview(title, text, buttons)

    preview_text = (
        "┏┅<tg-emoji emoji-id=\"5258254475386167466\">🖼️</tg-emoji>┅ / <b>Preview & Settings</b> /\n"
        "┋\n"
        f"┣ <b>Interval:</b> {int(interval)}m\n"
        f"┣ <b>Target Chat:</b> {html.escape(chat_title)}\n"
        f"┣ <b>Status:</b> {'Active' if is_active else 'Inactive'}\n"
        "┋\n"
        f"┣ {post_text}\n"
        "┋\n"
        "┗┅┅┅/ <b>Confirm or edit your notification:</b> /"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Title", callback_data="notif_edit_title", icon_custom_emoji_id="5778299625370817409")
    builder.button(text="Text", callback_data="notif_edit_text", icon_custom_emoji_id="5891105528356018797")
    builder.button(text="Buttons", callback_data="notif_edit_btns", icon_custom_emoji_id="5258185631355378853")
    builder.button(text="Interval", callback_data="notif_edit_interval", icon_custom_emoji_id="5850317551090800862")
    builder.button(text="Chat", callback_data="notif_edit_chat", icon_custom_emoji_id="5258486128742244085")

    toggle_text = "Turn OFF" if is_active else "Turn ON"
    builder.button(text=toggle_text, callback_data="notif_toggle_status", icon_custom_emoji_id="5258073068852485953")

    builder.button(text="Confirm & Save", callback_data="notif_confirm_save", icon_custom_emoji_id="5260726538302660868", style="success")
    builder.button(text="Main Menu", callback_data="main_menu", icon_custom_emoji_id="5260342697075416641", style="danger")
    builder.adjust(2, 2, 2, 1, 1)

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event.message, preview_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        msg = await safe_bot_edit_text(bot, event.chat.id, last_msg_id, preview_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        if msg:
            await state.update_data(last_msg_id=msg.message_id)

    await state.set_state(NotificationStates.PREVIEW)

@router.callback_query(F.data == "manage_notifications")
async def start_notification_management(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if not await is_any_admin(callback.from_user.id):
        await callback.answer("❌ Access denied", show_alert=True)
        return

    notifications = await db.get_notifications()
    builder = InlineKeyboardBuilder()

    for n in notifications:
        status = "✅" if n['is_active'] else "❌"
        builder.button(text=f"{status} {n['title']}", callback_data=f"notif_view_{n['id']}")

    builder.button(text="Add New", callback_data="notif_add_new", icon_custom_emoji_id="5260416304224936047")
    builder.button(text="Main Menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    text = "┏┅<tg-emoji emoji-id=\"5260268501515377807\">📣</tg-emoji>┅ / <b>Notification Management</b> /\n┋\n┗┅┅┅/ <b>Configure periodic ads for your groups.</b> /"
    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    # Don't state.clear() immediately if we want to preserve last_msg_id from previous menu,
    # but start_notification_management is usually called from main menu where last_msg_id might not be set in state yet.
    # Let's preserve last_msg_id if it exists.
    data = await state.get_data()
    last_id = data.get('last_msg_id')
    await state.clear()
    if last_id:
        await state.update_data(last_msg_id=last_id)

@router.callback_query(F.data == "notif_add_new")
async def add_new_notification(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(last_msg_id=callback.message.message_id, is_active=True, custom_buttons=[], interval_minutes=60, is_editing=False)

    text = (
        "┏┅<tg-emoji emoji-id=\"5778299625370817409\">📝</tg-emoji>┅ / <b>Notification Title</b> /\n"
        "┋\n"
        "┗┅┅┅/ <b>Enter a short title for this notification (internal).</b> /"
    )
    await safe_edit_text(callback, text, reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(NotificationStates.ENTER_TITLE)

@router.callback_query(F.data.startswith("notif_view_"))
async def edit_existing_notification(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    notif_id = int(callback.data.split("_")[-1])
    notifs = await db.get_notifications()
    notif = next((n for n in notifs if n['id'] == notif_id), None)

    if notif:
        await state.update_data(
            id=notif['id'],
            title=notif['title'],
            text=notif['text'],
            custom_buttons=notif.get('custom_buttons', []),
            interval_minutes=notif['interval_minutes'],
            chat_id=notif['chat_id'],
            is_active=notif['is_active'],
            last_msg_id=callback.message.message_id,
            is_editing=False
        )
        await show_notification_preview(callback, state, bot)

@router.message(NotificationStates.ENTER_TITLE, F.text)
async def process_notif_title(message: types.Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    await state.update_data(title=message.text)
    data = await state.get_data()

    if data.get('is_editing'):
        await show_notification_preview(message, state, bot)
    else:
        text = (
            "┏┅<tg-emoji emoji-id=\"5891105528356018797\">💬</tg-emoji>┅ / <b>Notification Text</b> /\n"
            "┋\n"
            "┗┅┅┅/ <b>Enter the main text of the message.</b> /"
        )
        msg = await safe_bot_edit_text(bot, message.chat.id, data['last_msg_id'], text, reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML)
        if msg:
            await state.update_data(last_msg_id=msg.message_id)
        await state.set_state(NotificationStates.ENTER_TEXT)

@router.message(NotificationStates.ENTER_TEXT, F.text)
async def process_notif_text(message: types.Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    await state.update_data(text=message.text)
    data = await state.get_data()

    if data.get('is_editing'):
        await show_notification_preview(message, state, bot)
    else:
        await show_btn_input_screen(message, state, bot)

async def show_btn_input_screen(event, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')
    btns = data.get('custom_buttons', [])
    preview = format_notification_preview(data.get('title'), data.get('text'), btns)

    builder = InlineKeyboardBuilder()
    builder.button(text="Clear Buttons", callback_data="notif_btns_clear", icon_custom_emoji_id="5260687681733533075")
    builder.button(text="Done / Next", callback_data="notif_btns_done", icon_custom_emoji_id="5260726538302660868", style="success")
    builder.adjust(1)

    text = (
        f"┏┅<tg-emoji emoji-id=\"5258185631355378853\">🔗</tg-emoji>┅ / <b>Notification Buttons</b> /\n"
        f"┋\n"
        f"┣ Send the button name and a link in any format.\n"
        f"┣ Example: <i>My Channel @channel</i> or <i>Click here t.me/link</i>\n"
        f"┋ You can send multiple buttons one by one.\n"
        f"┋\n"
        f"┗┅┅┅/ <b>Preview:</b> /\n\n{preview}"
    )

    chat_id = event.chat.id if isinstance(event, types.Message) else event.message.chat.id
    msg = await safe_bot_edit_text(bot, chat_id, last_msg_id, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    if msg:
        await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(NotificationStates.ENTER_BUTTONS)

@router.message(NotificationStates.ENTER_BUTTONS, F.text)
async def enter_notif_buttons(message: types.Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    data = await state.get_data()
    text = message.text

    # Extract URL or @username
    url_match = re.search(r"(https?://\S+|t\.me/\S+|@\S+)", text)
    if url_match:
        raw_url = url_match.group(0)
        # Normalize URL
        if raw_url.startswith("@"):
            url = f"https://t.me/{raw_url[1:]}"
        elif raw_url.startswith("t.me/"):
            url = f"https://{raw_url}"
        elif not raw_url.startswith("http"):
            url = f"https://{raw_url}"
        else:
            url = raw_url

        # The rest of the text is the button name
        name = text.replace(raw_url, "").strip(" -|:\n")
        if not name:
            name = "Open Link"

        btns = data.get('custom_buttons', [])
        btns.append({"text": name, "url": url})
        await state.update_data(custom_buttons=btns)

    await show_btn_input_screen(message, state, bot)

@router.callback_query(NotificationStates.ENTER_BUTTONS, F.data == "notif_btns_clear")
async def notif_btns_clear(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer("Cleared")
    await state.update_data(custom_buttons=[])
    await show_btn_input_screen(callback, state, bot)

@router.callback_query(NotificationStates.ENTER_BUTTONS, F.data == "notif_btns_done")
async def notif_btns_done(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()

    if data.get('is_editing'):
        await show_notification_preview(callback, state, bot)
    else:
        text = (
            "┏┅<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji>┅ / <b>Sending Interval</b> /\n"
            "┋\n"
            "┗┅┅┅/ Select how often the notification should be sent. /"
        )
        await safe_edit_text(callback, text, reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.ENTER_INTERVAL)

@router.callback_query(F.data.startswith("notif_int_"), NotificationStates.ENTER_INTERVAL)
async def process_notif_interval(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    val = callback.data.split("_")[-1]

    if val == "custom":
        text = (
            "┏┅<tg-emoji emoji-id=\"5258204546391351475\">⏳</tg-emoji>┅ / <b>Custom Interval</b> /\n"
            "┋\n"
            "┗┅┅┅/ <b>Enter interval in minutes (min 15, max 1440):</b> /"
        )
        await safe_edit_text(callback, text, reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.ENTER_CUSTOM_INTERVAL)
    else:
        await state.update_data(interval_minutes=float(val))
        data = await state.get_data()
        if data.get('is_editing'):
            await show_notification_preview(callback, state, bot)
        else:
            await show_chat_selector(callback, state, bot)

@router.message(NotificationStates.ENTER_CUSTOM_INTERVAL, F.text)
async def process_custom_interval(message: types.Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    data = await state.get_data()
    try:
        val = int(message.text)
        if not (15 <= val <= 1440):
            raise ValueError("Out of range")

        await state.update_data(interval_minutes=float(val))
        data = await state.get_data()
        if data.get('is_editing'):
            await show_notification_preview(message, state, bot)
        else:
            await show_chat_selector(message, state, bot)
    except ValueError:
        text = (
            "┏┅<tg-emoji emoji-id=\"5258204546391351475\">⏳</tg-emoji>┅ / <b>Custom Interval</b> /\n"
            "┋\n"
            "┣ <b>Invalid number.</b>\n"
            "┋ Please enter a number between 15 and 1440.\n"
            "┋\n"
            "┗┅┅┅/ <b>Enter interval in minutes:</b> /"
        )
        msg = await safe_bot_edit_text(bot, message.chat.id, data['last_msg_id'], text, reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML)
        if msg:
            await state.update_data(last_msg_id=msg.message_id)

async def show_chat_selector(event, state: FSMContext, bot: Bot):
    chats = await db.get_tracked_groups()
    builder = InlineKeyboardBuilder()
    for chat in chats:
        builder.button(text=chat['title'], callback_data=f"notif_chat_sel_{chat['chat_id']}")

    builder.button(text="Back", callback_data="notif_back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    text = (
        "┏┅<tg-emoji emoji-id=\"5258486128742244085\">🤝</tg-emoji>┅ / <b>Select Target Chat</b> /\n"
        "┋\n"
        "┗┅┅┅/ Select the group where the ad will be posted. /"
    )

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event.message, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        data = await state.get_data()
        msg = await safe_bot_edit_text(bot, event.chat.id, data['last_msg_id'], text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        if msg:
            await state.update_data(last_msg_id=msg.message_id)

    await state.set_state(NotificationStates.SELECT_CHAT)

@router.callback_query(F.data.startswith("notif_chat_sel_"), NotificationStates.SELECT_CHAT)
async def process_notif_chat(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    chat_id = int(callback.data.split("_")[-1])
    await state.update_data(chat_id=chat_id)
    await show_notification_preview(callback, state, bot)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_title")
async def edit_title(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True)
    text = (
        "┏┅<tg-emoji emoji-id=\"5778299625370817409\">📝</tg-emoji>┅ / <b>Edit Title</b> /\n"
        "┋\n"
        "┗┅┅┅/ <b>Enter a new title for this notification.</b> /"
    )
    await safe_edit_text(callback, text, reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(NotificationStates.ENTER_TITLE)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_text")
async def edit_text(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True)
    text = (
        "┏┅<tg-emoji emoji-id=\"5891105528356018797\">💬</tg-emoji>┅ / <b>Edit Text</b> /\n"
        "┋\n"
        "┗┅┅┅/ <b>Enter the new main text.</b> /"
    )
    await safe_edit_text(callback, text, reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(NotificationStates.ENTER_TEXT)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_btns")
async def edit_btns(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await state.update_data(is_editing=True)
    await show_btn_input_screen(callback, state, bot)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_interval")
async def edit_interval(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True)
    text = (
        "┏┅<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji>┅ / <b>Edit Interval</b> /\n"
        "┋\n"
        "┗┅┅┅/ <b>Select a new sending interval.</b> /"
    )
    await safe_edit_text(callback, text, reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(NotificationStates.ENTER_INTERVAL)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_chat")
async def edit_chat(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await state.update_data(is_editing=True)
    await show_chat_selector(callback, state, bot)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_toggle_status")
async def toggle_status(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()
    await state.update_data(is_active=not data.get('is_active', True))
    await show_notification_preview(callback, state, bot)

@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_confirm_save")
async def confirm_save(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    try: await callback.answer()
    except: pass

    data = await state.get_data()
    title = data.get('title')
    text = data.get('text')
    interval = data.get('interval_minutes')
    chat_id = data.get('chat_id')

    if not all([title, text, interval, chat_id]):
        await callback.answer("❌ Please fill all fields before saving!", show_alert=True)
        return

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

    success_text = (
        "┏<tg-emoji emoji-id=\"5260726538302660868\">✅</tg-emoji>┅ / <b>Notification saved successfully!</b> /\n"
        "┋\n"
        "┗┅┅┅/ <b>Your advertisement schedule has been updated and is now active.</b> /"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Main Menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531")

    await safe_edit_text(callback, success_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    await state.clear()

@router.callback_query(F.data == "notif_back")
async def handle_notif_back(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()
    is_editing = data.get('is_editing')

    if is_editing or current_state == NotificationStates.PREVIEW:
        await state.update_data(is_editing=False)
        await show_notification_preview(callback, state, bot)
        return

    if current_state == NotificationStates.ENTER_TITLE:
        await start_notification_management(callback, state)
    elif current_state == NotificationStates.ENTER_TEXT:
        await add_new_notification(callback, state)
    elif current_state == NotificationStates.ENTER_BUTTONS:
        # Back to text
        text = (
            "┏┅<tg-emoji emoji-id=\"5891105528356018797\">💬</tg-emoji>┅ / <b>Notification Text</b> /\n"
            "┋\n"
            "┗┅┅┅/ <b>Enter the main text of the message.</b> /"
        )
        await safe_edit_text(callback, text, reply_markup=get_notification_nav_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.ENTER_TEXT)
    elif current_state == NotificationStates.ENTER_INTERVAL:
        await show_btn_input_screen(callback, state, bot)
    elif current_state == NotificationStates.ENTER_CUSTOM_INTERVAL:
        text = (
            "┏┅<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji>┅ / <b>Sending Interval</b> /\n"
            "┋\n"
            "┗┅┅┅/ Select how often the notification should be sent. /"
        )
        await safe_edit_text(callback, text, reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.ENTER_INTERVAL)
    elif current_state == NotificationStates.SELECT_CHAT:
        text = (
            "┏┅<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji>┅ / <b>Sending Interval</b> /\n"
            "┋\n"
            "┗┅┅┅/ Select how often the notification should be sent. /"
        )
        await safe_edit_text(callback, text, reply_markup=get_interval_keyboard(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(NotificationStates.ENTER_INTERVAL)
    else:
        await start_notification_management(callback, state)
