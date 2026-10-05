import html
import logging

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from database import db
from utils import safe_bot_edit_text, safe_edit_text

logger = logging.getLogger(__name__)
router = Router()

BOT_BROADCAST_CHAT_ID = 0


class NotificationStates(StatesGroup):
    SELECT_CHAT = State()
    ENTER_TITLE = State()
    ENTER_TEXT = State()
    ENTER_BUTTONS = State()
    ENTER_INTERVAL = State()
    ENTER_CUSTOM_INTERVAL = State()
    PREVIEW = State()


async def get_notification_nav_keyboard(user_id: int, texts: dict):
    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts["notif_back_btn"],
        callback_data="notif_back",
        icon_custom_emoji_id="5260687119092817530",
    )
    builder.button(
        text=texts["notif_main_menu_btn"],
        callback_data="main_menu",
        icon_custom_emoji_id="6042137469204303531",
        style="danger",
    )
    builder.adjust(1)
    return builder.as_markup()


def get_interval_keyboard(texts: dict):
    builder = InlineKeyboardBuilder()
    builder.button(text="3H", callback_data="interval_180")
    builder.button(text="8H", callback_data="interval_480")
    builder.button(text="12H", callback_data="interval_720")
    builder.button(text=texts["notif_custom_btn"], callback_data="interval_custom")
    builder.button(text=texts["notif_back_btn"], callback_data="notif_back")
    builder.adjust(3, 1, 1)
    return builder.as_markup()


async def _render_from_message(message: types.Message, state: FSMContext, bot: Bot, text: str, keyboard):
    data = await state.get_data()
    last_msg_id = data.get("last_msg_id")
    if last_msg_id:
        msg = await safe_bot_edit_text(
            bot,
            message.chat.id,
            last_msg_id,
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
        )
        if msg:
            await state.update_data(last_msg_id=msg.message_id)
        return
    msg = await message.answer(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    await state.update_data(last_msg_id=msg.message_id)


async def _target_label(chat_id: int | None, texts: dict) -> str:
    if chat_id == BOT_BROADCAST_CHAT_ID:
        return texts["notif_target_bot"]
    if chat_id is None:
        return texts["notif_target_not_selected"]
    try:
        chats = await db.get_tracked_groups()
        row = next((item for item in chats if int(item["chat_id"]) == int(chat_id)), None)
        if row:
            return html.escape(str(row.get("title") or chat_id))
    except Exception:
        pass
    return str(chat_id)


@router.callback_query(F.data == "manage_notifications")
async def start_notification_management(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(texts["access_denied"], show_alert=True)
        return

    await callback.answer()
    await state.clear()
    notifications = await db.get_notifications()

    builder = InlineKeyboardBuilder()
    for notification in notifications:
        status = "✅" if notification.get("is_active") else "⏸"
        title = str(notification.get("title") or f"#{notification['id']}")
        builder.button(
            text=f"{status} {title}",
            callback_data=f"notif_view_{notification['id']}",
        )

    builder.button(
        text=texts["notif_add_new_btn"],
        callback_data="notif_add",
        icon_custom_emoji_id="5258260149037965799",
    )
    builder.button(
        text=texts["notif_main_menu_btn"],
        callback_data="main_menu",
        icon_custom_emoji_id="6042137469204303531",
        style="danger",
    )
    builder.adjust(1)

    text = texts["notif_mgmt_title"]
    if not notifications:
        text += "\n\n" + texts["notif_no_notifs"]
    await safe_edit_text(
        callback,
        text,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )


@router.callback_query(F.data == "notif_add")
async def add_new_notification(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(texts["access_denied"], show_alert=True)
        return

    await callback.answer()
    await state.clear()
    await state.update_data(is_active=True, is_editing=False)
    await safe_edit_text(
        callback,
        texts["notif_enter_title"],
        reply_markup=await get_notification_nav_keyboard(callback.from_user.id, texts),
        parse_mode=ParseMode.HTML,
        state=state,
    )
    await state.set_state(NotificationStates.ENTER_TITLE)


@router.callback_query(F.data.startswith("notif_view_"))
async def view_notification(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict
):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(texts["access_denied"], show_alert=True)
        return

    await callback.answer()
    notif_id = int(callback.data.rsplit("_", 1)[1])
    notifications = await db.get_notifications()
    notification = next(
        (item for item in notifications if int(item["id"]) == notif_id), None
    )
    if not notification:
        await callback.answer(texts["notif_not_found"], show_alert=True)
        return

    await state.clear()
    await state.update_data(
        id=notification["id"],
        title=notification.get("title") or "",
        text=notification.get("text") or "",
        custom_buttons=notification.get("custom_buttons") or [],
        interval_minutes=notification.get("interval_minutes") or 60,
        chat_id=notification.get("chat_id"),
        is_active=bool(notification.get("is_active")),
        is_editing=False,
        last_msg_id=callback.message.message_id if callback.message else None,
    )
    await show_notification_preview(callback, state, bot, texts)


@router.message(NotificationStates.ENTER_TITLE, F.text)
async def process_title(
    message: types.Message, state: FSMContext, bot: Bot, texts: dict
):
    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(title=message.text.strip())
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await show_notification_preview(message, state, bot, texts)
        return

    await _render_from_message(
        message,
        state,
        bot,
        texts["notif_enter_text"],
        await get_notification_nav_keyboard(message.from_user.id, texts),
    )
    await state.set_state(NotificationStates.ENTER_TEXT)


@router.message(NotificationStates.ENTER_TEXT, F.text)
async def process_text(
    message: types.Message, state: FSMContext, bot: Bot, texts: dict
):
    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(text=message.text.strip())
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await show_notification_preview(message, state, bot, texts)
    else:
        await show_btn_input_screen(message, state, bot, texts)


async def show_btn_input_screen(event, state: FSMContext, bot: Bot, texts: dict):
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["notif_skip_btn"], callback_data="notif_skip_btns")
    builder.button(text=texts["notif_back_btn"], callback_data="notif_back")
    builder.button(
        text=texts["notif_main_menu_btn"],
        callback_data="main_menu",
        style="danger",
    )
    builder.adjust(1)

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(
            event,
            texts["notif_enter_buttons"],
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML,
            state=state,
        )
    else:
        await _render_from_message(
            event, state, bot, texts["notif_enter_buttons"], builder.as_markup()
        )
    await state.set_state(NotificationStates.ENTER_BUTTONS)


@router.message(NotificationStates.ENTER_BUTTONS, F.text)
async def process_buttons(
    message: types.Message, state: FSMContext, bot: Bot, texts: dict
):
    try:
        await message.delete()
    except Exception:
        pass

    raw_text = message.text.strip()
    if raw_text.lower() in {"skip", "пропустить", "-"}:
        buttons = []
    else:
        buttons = []
        for line in raw_text.splitlines():
            if " - " not in line:
                continue
            label, url = line.split(" - ", 1)
            label = label.strip()
            url = url.strip()
            if label and url.startswith(("https://", "http://", "tg://")):
                buttons.append({"text": label, "url": url})
        if not buttons:
            await _render_from_message(
                message,
                state,
                bot,
                texts["notif_invalid_buttons"],
                await get_notification_nav_keyboard(message.from_user.id, texts),
            )
            return

    await state.update_data(custom_buttons=buttons)
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await show_notification_preview(message, state, bot, texts)
    else:
        await show_interval_selector(message, state, bot, texts)


@router.callback_query(
    NotificationStates.ENTER_BUTTONS, F.data == "notif_skip_btns"
)
async def skip_buttons(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict
):
    await callback.answer()
    await state.update_data(custom_buttons=[])
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await show_notification_preview(callback, state, bot, texts)
    else:
        await show_interval_selector(callback, state, bot, texts)


async def show_interval_selector(event, state: FSMContext, bot: Bot, texts: dict):
    keyboard = get_interval_keyboard(texts)
    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(
            event,
            texts["notif_enter_interval"],
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            state=state,
        )
    else:
        await _render_from_message(
            event, state, bot, texts["notif_enter_interval"], keyboard
        )
    await state.set_state(NotificationStates.ENTER_INTERVAL)


@router.callback_query(
    NotificationStates.ENTER_INTERVAL, F.data.startswith("interval_")
)
async def process_interval(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict
):
    await callback.answer()
    value = callback.data.rsplit("_", 1)[1]

    if value == "custom":
        await safe_edit_text(
            callback,
            texts["notif_custom_interval_title"],
            reply_markup=await get_notification_nav_keyboard(callback.from_user.id, texts),
            parse_mode=ParseMode.HTML,
            state=state,
        )
        await state.set_state(NotificationStates.ENTER_CUSTOM_INTERVAL)
        return

    await state.update_data(interval_minutes=float(value))
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await show_notification_preview(callback, state, bot, texts)
    else:
        await show_chat_selector(callback, state, bot, texts)


@router.message(NotificationStates.ENTER_CUSTOM_INTERVAL, F.text)
async def process_custom_interval(
    message: types.Message, state: FSMContext, bot: Bot, texts: dict
):
    try:
        await message.delete()
    except Exception:
        pass

    try:
        value = int(message.text)
        if not 15 <= value <= 1440:
            raise ValueError
    except (TypeError, ValueError):
        await _render_from_message(
            message,
            state,
            bot,
            texts["notif_invalid_interval"],
            await get_notification_nav_keyboard(message.from_user.id, texts),
        )
        return

    await state.update_data(interval_minutes=float(value))
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await show_notification_preview(message, state, bot, texts)
    else:
        await show_chat_selector(message, state, bot, texts)


async def show_chat_selector(event, state: FSMContext, bot: Bot, texts: dict):
    chats = await db.get_tracked_groups()
    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts["notif_bot_users_btn"],
        callback_data=f"notif_chat_sel_{BOT_BROADCAST_CHAT_ID}",
        style="success",
    )
    for chat in chats:
        builder.button(
            text=str(chat.get("title") or chat["chat_id"]),
            callback_data=f"notif_chat_sel_{chat['chat_id']}",
        )
    builder.button(
        text=texts["notif_back_btn"],
        callback_data="notif_back",
        icon_custom_emoji_id="5260687119092817530",
    )
    builder.button(
        text=texts["notif_main_menu_btn"],
        callback_data="main_menu",
        icon_custom_emoji_id="6042137469204303531",
        style="danger",
    )
    builder.adjust(1)

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(
            event,
            texts["notif_select_chat_title"],
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML,
            state=state,
        )
    else:
        await _render_from_message(
            event, state, bot, texts["notif_select_chat_title"], builder.as_markup()
        )
    await state.set_state(NotificationStates.SELECT_CHAT)


@router.callback_query(
    NotificationStates.SELECT_CHAT, F.data.startswith("notif_chat_sel_")
)
async def process_notif_chat(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict
):
    await callback.answer()
    chat_id = int(callback.data.rsplit("_", 1)[1])
    await state.update_data(chat_id=chat_id)
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
    await show_notification_preview(callback, state, bot, texts)


async def show_notification_preview(event, state: FSMContext, bot: Bot, texts: dict):
    data = await state.get_data()
    title = str(data.get("title") or "")
    message_text = str(data.get("text") or "")
    interval = data.get("interval_minutes")
    is_active = bool(data.get("is_active", True))
    target = await _target_label(data.get("chat_id"), texts)

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["notif_edit_title_btn"], callback_data="notif_edit_title")
    builder.button(text=texts["notif_edit_text_btn"], callback_data="notif_edit_text")
    builder.button(
        text=texts["notif_edit_buttons_btn"], callback_data="notif_edit_btns"
    )
    builder.button(
        text=texts["notif_edit_interval_btn"], callback_data="notif_edit_interval"
    )
    builder.button(text=texts["notif_edit_chat_btn"], callback_data="notif_edit_chat")
    status_label = texts["notif_active"] if is_active else texts["notif_paused"]
    builder.button(
        text=texts["notif_toggle_status_btn"].format(STATUS=status_label),
        callback_data="notif_toggle_status",
    )
    builder.button(
        text=texts["notif_save_btn"],
        callback_data="notif_confirm_save",
        style="success",
    )
    builder.button(
        text=texts["notif_back_to_list_btn"],
        callback_data="manage_notifications",
    )
    builder.button(
        text=texts["notif_main_menu_btn"],
        callback_data="main_menu",
        style="danger",
    )
    builder.adjust(2, 2, 2, 1, 1, 1)

    preview_text = (
        texts["notif_preview_header"]
        + f"┣ <b>{texts['notif_title_label']}:</b> {html.escape(title)}\n"
        + f"┣ <b>{texts['notif_text_label']}:</b> {html.escape(message_text)}\n"
        + f"┣ <b>{texts['notif_target_label']}:</b> {target}\n"
        + f"┣ <b>{texts['notif_interval_label']}:</b> {interval} min\n"
        + f"┣ <b>{texts['notif_status_label']}:</b> {html.escape(status_label)}\n"
        + texts["notif_preview_footer"]
    )

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(
            event,
            preview_text,
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML,
            state=state,
        )
    else:
        await _render_from_message(
            event, state, bot, preview_text, builder.as_markup()
        )
    await state.set_state(NotificationStates.PREVIEW)


@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_title")
async def edit_title(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    await callback.answer()
    await state.update_data(is_editing=True)
    await safe_edit_text(
        callback,
        texts["notif_enter_title"],
        reply_markup=await get_notification_nav_keyboard(callback.from_user.id, texts),
        parse_mode=ParseMode.HTML,
        state=state,
    )
    await state.set_state(NotificationStates.ENTER_TITLE)


@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_text")
async def edit_text(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    await callback.answer()
    await state.update_data(is_editing=True)
    await safe_edit_text(
        callback,
        texts["notif_enter_text"],
        reply_markup=await get_notification_nav_keyboard(callback.from_user.id, texts),
        parse_mode=ParseMode.HTML,
        state=state,
    )
    await state.set_state(NotificationStates.ENTER_TEXT)


@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_btns")
async def edit_btns(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict
):
    await callback.answer()
    await state.update_data(is_editing=True)
    await show_btn_input_screen(callback, state, bot, texts)


@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_interval")
async def edit_interval(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    await callback.answer()
    await state.update_data(is_editing=True)
    await safe_edit_text(
        callback,
        texts["notif_enter_interval"],
        reply_markup=get_interval_keyboard(texts),
        parse_mode=ParseMode.HTML,
        state=state,
    )
    await state.set_state(NotificationStates.ENTER_INTERVAL)


@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_edit_chat")
async def edit_chat(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict
):
    await callback.answer()
    await state.update_data(is_editing=True)
    await show_chat_selector(callback, state, bot, texts)


@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_toggle_status")
async def toggle_status(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict
):
    data = await state.get_data()
    new_status = not bool(data.get("is_active", True))
    notification_id = data.get("id")

    if notification_id and db.client:
        try:
            await (
                db.client.table("notifications")
                .update({"is_active": new_status})
                .eq("id", notification_id)
                .execute()
            )
        except Exception as exc:
            logger.error("Failed to toggle notification %s: %s", notification_id, exc)
            await callback.answer(texts["notif_toggle_error"], show_alert=True)
            return

    await state.update_data(is_active=new_status)
    await callback.answer(texts["notif_toggle_saved"])
    await show_notification_preview(callback, state, bot, texts)


@router.callback_query(NotificationStates.PREVIEW, F.data == "notif_confirm_save")
async def confirm_save(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict
):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer(texts["access_denied"], show_alert=True)
        return

    data = await state.get_data()
    title = str(data.get("title") or "").strip()
    message_text = str(data.get("text") or "").strip()
    interval = data.get("interval_minutes")
    chat_id = data.get("chat_id")

    if not title or not message_text or not interval or chat_id is None:
        await callback.answer(texts["notif_fill_all_fields"], show_alert=True)
        return

    notif_data = {
        "title": title,
        "text": message_text,
        "custom_buttons": data.get("custom_buttons") or [],
        "interval_minutes": interval,
        "chat_id": int(chat_id),
        "is_active": bool(data.get("is_active", True)),
    }
    if data.get("id"):
        notif_data["id"] = data["id"]

    await db.upsert_notification(notif_data)
    await callback.answer(texts["notif_save_alert"])

    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts["notif_back_to_list_btn"],
        callback_data="manage_notifications",
        style="success",
    )
    builder.button(
        text=texts["notif_main_menu_btn"],
        callback_data="main_menu",
        icon_custom_emoji_id="6042137469204303531",
    )
    builder.adjust(1)
    await safe_edit_text(
        callback,
        texts["notif_save_success"],
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )
    await state.clear()


@router.callback_query(F.data == "notif_back")
async def handle_notif_back(
    callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict
):
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()

    if data.get("is_editing") or current_state == NotificationStates.PREVIEW.state:
        await state.update_data(is_editing=False)
        await show_notification_preview(callback, state, bot, texts)
        return

    if current_state == NotificationStates.ENTER_TITLE.state:
        await start_notification_management(callback, state, texts)
    elif current_state == NotificationStates.ENTER_TEXT.state:
        await add_new_notification(callback, state, texts)
    elif current_state == NotificationStates.ENTER_BUTTONS.state:
        await safe_edit_text(
            callback,
            texts["notif_enter_text"],
            reply_markup=await get_notification_nav_keyboard(callback.from_user.id, texts),
            parse_mode=ParseMode.HTML,
            state=state,
        )
        await state.set_state(NotificationStates.ENTER_TEXT)
    elif current_state in {
        NotificationStates.ENTER_INTERVAL.state,
        NotificationStates.ENTER_CUSTOM_INTERVAL.state,
    }:
        await show_btn_input_screen(callback, state, bot, texts)
    elif current_state == NotificationStates.SELECT_CHAT.state:
        await show_interval_selector(callback, state, bot, texts)
    else:
        await start_notification_management(callback, state, texts)
