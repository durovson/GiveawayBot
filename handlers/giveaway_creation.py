from aiogram import Router, types, F, Bot
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode, ChatType
from typing import Optional, List
import logging
import re
import pytz
import html
from datetime import datetime, timedelta, time

from database import db
from utils import is_admin, safe_answer, safe_edit_text, safe_bot_edit_text, safe_bot_send_message, strip_custom_emojis

logger = logging.getLogger(__name__)
router = Router()

GIF_ID = "CgACAgIAAxkBAAEbt3NpqAn2obJdHyFVZbi_JOspLX96KAAC7pQAAkCBQEk_A-aRj7qxNToE"

class GiveawayCreation(StatesGroup):
    SELECT_CHAT = State()
    ENTER_NAME = State()
    SELECT_GIVEAWAY_KIND = State()
    ENTER_CHANNELS = State()
    WAITING_FOR_BOT_ADMIN = State()
    WAITING_FOR_ACCESS_TYPE = State()
    WAITING_FOR_WHITELIST = State()
    SELECT_TYPE = State()
    SELECT_MODE_VALUE = State()
    CUSTOM_MODE_VALUE = State()
    SELECT_WINNERS_COUNT = State()
    CUSTOM_WINNERS_COUNT = State()
    ENTER_PRIZES = State()
    CONFIRMATION = State()
    EDIT_PARAMS = State()

def get_giveaway_kind_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Fast (No channels)", callback_data="kind_fast", icon_custom_emoji_id="5323761960829862762")
    builder.button(text="Partner (Required channels)", callback_data="kind_partner", icon_custom_emoji_id="5258486128742244085")
    builder.button(text="Back", callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 1, 2)
    return builder.as_markup()

def get_nav_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Back", callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2)
    return builder.as_markup()

def get_recheck_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="I added!", callback_data="recheck_admin", icon_custom_emoji_id="5260726538302660868")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)
    return builder.as_markup()

async def verify_all_channels(bot: Bot, channels_list: List[str]):
    for channel in channels_list:
        try:
            chat = await bot.get_chat(channel)
            member = await bot.get_chat_member(chat_id=chat.id, user_id=bot.id)
            if member.status not in ['administrator', 'creator']:
                return False, channel.replace('@', '')
        except Exception:
            return False, channel.replace('@', '')
    return True, None

def get_type_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Certain time", callback_data="type_timed", icon_custom_emoji_id="5850317551090800862")
    builder.button(text="By participants", callback_data="type_limited", icon_custom_emoji_id="6032594876506312598")
    builder.button(text="Back", callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 1, 2)
    return builder.as_markup()

def get_mode_keyboard(gtype):
    builder = InlineKeyboardBuilder()
    if gtype == "timed":
        builder.button(text="12:00", style="success", callback_data="val_12:00")
        builder.button(text="15:00", style="success", callback_data="val_15:00")
        builder.button(text="18:00", style="success", callback_data="val_18:00")
        builder.button(text="21:00", style="success", callback_data="val_21:00")
    else:
        builder.button(text="1", style="success", callback_data="val_1")
        builder.button(text="3", style="success", callback_data="val_3")
        builder.button(text="5", style="success", callback_data="val_5")
        builder.button(text="10", style="success", callback_data="val_10")
    builder.button(text="Your own option", callback_data="val_custom", icon_custom_emoji_id="5274008024585871702")
    builder.button(text="Back", callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 1, 2)
    return builder.as_markup()

def get_winners_keyboard():
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.button(text=str(i), callback_data=f"win_{i}")
    builder.button(text="Your own option", callback_data="win_custom", icon_custom_emoji_id="5274008024585871702")
    builder.button(text="Back", callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(5, 1, 2)
    return builder.as_markup()

def get_prizes_keyboard(prizes):
    builder = InlineKeyboardBuilder()
    if prizes:
        builder.button(text="Confirm prizes", callback_data="confirm_prizes", icon_custom_emoji_id="5260726538302660868", style="success")
    builder.button(text="Back", callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 2)
    return builder.as_markup()

def get_access_type_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Public", callback_data="access_all", icon_custom_emoji_id="5258486128742244085")
    builder.button(text="Whitelist (Users/IDs)", callback_data="access_whitelist", icon_custom_emoji_id="5258476306152038031")
    builder.button(text="Back", callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 1, 2)
    return builder.as_markup()

def get_edit_params_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Name", callback_data="edit_title", icon_custom_emoji_id="5778299625370817409")
    builder.button(text="Channels", callback_data="edit_channels", icon_custom_emoji_id="5258185631355378853")
    builder.button(text="Type", callback_data="edit_type", icon_custom_emoji_id="5258185631355378853")
    builder.button(text="Mode", callback_data="edit_mode", icon_custom_emoji_id="5850317551090800862")
    builder.button(text="Winners", callback_data="edit_winners", icon_custom_emoji_id="5805553606635559688")
    builder.button(text="Prizes", callback_data="edit_prizes", icon_custom_emoji_id="5891105528356018797")
    builder.button(text="Confirm", callback_data="confirm_giveaway", icon_custom_emoji_id="5258073068852485953", style="success")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()

def get_message_link(chat, message_id: int) -> str:
    if chat.username:
        return f"https://t.me/{chat.username}/{message_id}"
    else:
        chat_id_str = str(chat.id)
        if chat_id_str.startswith("-100"):
            chat_id_str = chat_id_str[4:]
        return f"https://t.me/c/{chat_id_str}/{message_id}"

@router.callback_query(F.data.startswith("chat_"), GiveawayCreation.SELECT_CHAT)
async def select_chat(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    chat_id = int(callback.data.split("_")[1])
    await state.update_data(
        chat_id=chat_id,
        prizes=[],
        mandatory_channels=[],
        is_editing=False
    )
    await safe_edit_text(callback,
        "┏┅<tg-emoji emoji-id=\"5258254475386167466\">🖼</tg-emoji>┅ / <b>Event Name</b> /\n"
        "┋\n"
        "┣ Come up with a name for your giveaway!\n"
        "┋\n"
        "┗┅┅┅/ <b>Enter a name:</b> /",
        reply_markup=get_nav_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.ENTER_NAME)

@router.message(GiveawayCreation.ENTER_NAME)
async def enter_name(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(title=message.text)
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')
    if data.get("return_to_confirm"):
        await state.update_data(return_to_confirm=False)
        await state.set_state(GiveawayCreation.CONFIRMATION)
        await show_edit_params(message, state, bot)
        return

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            "┏┅<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji>┅ / <b>Giveaway Type</b> /\n"
            "┋\n"
            "┣ What type of giveaway is yours?\n"
            "┋\n"
            "┗┅┅┅/ Select type: /",
            reply_markup=get_giveaway_kind_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_GIVEAWAY_KIND)

@router.callback_query(F.data.startswith("kind_"))
async def process_giveaway_kind(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    if callback.data == "kind_fast":
        await state.update_data(mandatory_channels=[])
        await ask_access_type(callback.message, state, bot)
    elif callback.data == "kind_partner":
        await safe_edit_text(callback,
            "┏┅<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji>┅ / <b>Mandatory Channels</b> /\n"
            "┋\n"
            "┣ Enter the @usernames of the channels users must\n"
            "┣ subscribe to, separated by spaces or commas.\n"
            "┋\n"
            "┗┅┅┅/ <b>Enter channels:</b> /",
            reply_markup=get_nav_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.ENTER_CHANNELS)

@router.message(GiveawayCreation.ENTER_CHANNELS)
async def enter_channels(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except Exception:
        pass

    channels = re.split(r'[,\s]+', message.text.strip())
    channels = [c if c.startswith('@') else f'@{c}' for c in channels if c]
    await state.update_data(mandatory_channels=channels)

    success, failed_channel = await verify_all_channels(bot, channels)
    if not success:
        await state.update_data(failing_channel=failed_channel)
        data = await state.get_data()
        last_msg_id = data.get('last_msg_id')
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            f"<b>The bot hasn't been added to @{failed_channel} yet. Please make sure it has administrator status.</b>",
            reply_markup=get_recheck_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.WAITING_FOR_BOT_ADMIN)
        return

    data = await state.get_data()
    if data.get("return_to_confirm"):
        await state.update_data(return_to_confirm=False)
        await state.set_state(GiveawayCreation.CONFIRMATION)
        await show_edit_params(message, state, bot)
        return

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await ask_access_type(message, state, bot)

@router.callback_query(F.data == "recheck_admin", GiveawayCreation.WAITING_FOR_BOT_ADMIN)
async def recheck_admin(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    channels = data.get('mandatory_channels', [])

    success, failed_channel = await verify_all_channels(bot, channels)
    if not success:
        await callback.answer(f"Verification failed for @{failed_channel}", show_alert=True)
        await safe_edit_text(callback,
            f"<b>The bot hasn't been added to @{failed_channel} yet. Please make sure it has administrator status.</b>",
            reply_markup=get_recheck_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    await callback.answer("✅ All channels verified!")
    data = await state.get_data()
    if data.get("return_to_confirm"):
        await state.update_data(return_to_confirm=False)
        await state.set_state(GiveawayCreation.CONFIRMATION)
        await show_edit_params(callback, state, bot)
        return

    if data.get('is_editing'):
        await show_edit_params(callback.message, state, bot)
    else:
        await ask_access_type(callback.message, state, bot)

async def ask_access_type(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')
    await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
        "┏┅<tg-emoji emoji-id=\"5258476306152038031\">🔒</tg-emoji>┅ / <b>Access Type</b> /\n"
        "┋\n"
        "┣ Who can participate in the giveaway?\n"
        "┋\n"
        "┗┅┅┅/ Action prompt:</b> /",
        reply_markup=get_access_type_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.WAITING_FOR_ACCESS_TYPE)

@router.callback_query(GiveawayCreation.WAITING_FOR_ACCESS_TYPE)
async def process_access_choice(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if callback.data == "access_all":
        await state.update_data(allowed_users=None)
        await callback.answer("✅ Giveaway is now Public.")
        data = await state.get_data()
        if data.get("return_to_confirm"):
            await state.update_data(return_to_confirm=False)
            await state.set_state(GiveawayCreation.CONFIRMATION)
            await show_edit_params(callback, state, bot)
            return
        await safe_edit_text(callback,
            "┏┅<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji>┅ / <b>Draw Type</b> /\n"
            "┋\n"
            "┣ Select the format of the drawing\n"
            "┋\n"
            "┗┅┅┅/ <b>Select type:</b> /",
            reply_markup=get_type_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_TYPE)
    elif callback.data == "access_whitelist":
        await safe_edit_text(callback,
            "┏┅<tg-emoji emoji-id=\"5258476306152038031\">🔒</tg-emoji>>┅ / <b>Whitelist</b> /\n"
            "┋\n"
            "┣ Send the list of @usernames or User IDs.\n"
            "┣ Example: @user1, 12345678, @user2\n"
            "┋\n"
            "┗┅┅┅/ <b>Action prompt:</b> /",
            reply_markup=get_nav_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.WAITING_FOR_WHITELIST)
    await callback.answer()

@router.message(GiveawayCreation.WAITING_FOR_WHITELIST)
async def process_whitelist(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except Exception:
        pass

    raw_list = re.split(r'[,\s]+', message.text.strip())
    processed_list = [item.strip().lower() for item in raw_list if item.strip()]

    await state.update_data(allowed_users=processed_list)

    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')
    await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
        f"✅ Whitelist saved: {len(processed_list)} entries."
        "┏┅<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji>┅ / <b>Draw Type</b> /\n"
        "┋\n"
        "┣ Select the format of the drawing.\n"
        "┋\n"
        "┗┅┅┅/ <b>Select type:</b> /",
        reply_markup=get_type_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.SELECT_TYPE)

@router.callback_query(F.data.startswith("type_"))
async def select_type(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()
    old_gtype = data.get('gtype')
    gtype = callback.data.split("_")[1]
    await state.update_data(gtype=gtype)

    if data.get("return_to_confirm") and old_gtype == gtype:
        await state.update_data(return_to_confirm=False)
        await state.set_state(GiveawayCreation.CONFIRMATION)
        await show_edit_params(callback, state, bot)
        return

    if gtype == "timed":
        text = (
            "┏┅<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji>┅ / <b>End Time</b> /\n"
            "┋\n"
            "┣ Specify the date and time when the winners will be announced (MSK)\n"
            "┋\n"
            "┗┅┅┅/ <b>Select or enter time (DD.MM.YYYY HH:MM):</b> /"
        )
    else:
        text = (
            "┏┅<tg-emoji emoji-id=\"5258073068852485953\">✈️</tg-emoji>┅ / <b>Participants Limit</b> /\n"
            "┋\n"
            "┣ Select the number of participants to complete.\n"
            "┋\n"
            "┗┅┅┅/ <b>Select limit:</b> /"
        )
    await safe_edit_text(callback, text, reply_markup=get_mode_keyboard(gtype), parse_mode=ParseMode.HTML)
    await state.set_state(GiveawayCreation.SELECT_MODE_VALUE)

@router.callback_query(F.data.startswith("val_"), GiveawayCreation.SELECT_MODE_VALUE)
async def select_mode_value(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    val = callback.data.split("_")[1]
    if val == "custom":
        data = await state.get_data()
        prompt = "Enter the time in DD.MM.YYYY HH:MM format" if data['gtype'] == "timed" else "enter the number of participants as a number"
        await safe_edit_text(callback,
            f"<b>Enter your value:</b>\n\n"
            f"<blockquote>{prompt}</blockquote>",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.CUSTOM_MODE_VALUE)
    else:
        await state.update_data(mode_value=val)
        data = await state.get_data()
        if data.get("return_to_confirm"):
            await state.update_data(return_to_confirm=False)
            await state.set_state(GiveawayCreation.CONFIRMATION)
            await show_edit_params(callback, state, bot)
            return
        if data.get('is_editing'):
            await show_edit_params(callback, state, bot)
        else:
            await safe_edit_text(callback,
                "┏┅<tg-emoji emoji-id=\"5274159185959872191\">👑</tg-emoji>┅ / <b>Winners</b> /\n"
                "┋\n"
                "┣ Select the number of prize places\n"
                "┋\n"
                "┗┅┅┅/ <b>Select quantity:</b> /",
                reply_markup=get_winners_keyboard(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(GiveawayCreation.SELECT_WINNERS_COUNT)

@router.message(GiveawayCreation.CUSTOM_MODE_VALUE)
async def enter_custom_mode_value(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except Exception:
        pass

    await state.update_data(mode_value=message.text)
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')
    if data.get("return_to_confirm"):
        await state.update_data(return_to_confirm=False)
        await state.set_state(GiveawayCreation.CONFIRMATION)
        await show_edit_params(message, state, bot)
        return

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            "<tg-emoji emoji-id=\"5274159185959872191\">👑</tg-emoji> <b>Winners</b>\n\n"
            "<blockquote>Select the number of prize places</blockquote>\n\n"
            "<b>Select quantity:</b>",
            reply_markup=get_winners_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_WINNERS_COUNT)

@router.callback_query(F.data.startswith("win_"), GiveawayCreation.SELECT_WINNERS_COUNT)
async def select_winners_count(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    val = callback.data.split("_")[1]
    if val == "custom":
        await safe_edit_text(callback,
            "<b>Enter the number of winners:</b>",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.CUSTOM_WINNERS_COUNT)
    else:
        await state.update_data(winners_count=int(val))
        data = await state.get_data()
        if data.get("return_to_confirm"):
            await state.update_data(return_to_confirm=False)
            await state.set_state(GiveawayCreation.CONFIRMATION)
            await show_edit_params(callback, state, bot)
            return
        if data.get('is_editing'):
            await show_edit_params(callback, state, bot)
        else:
            await safe_edit_text(callback,
                "<tg-emoji emoji-id=\"5891105528356018797\">💎</tg-emoji> <b>Prizes</b>\n\n"
                "<blockquote>Enter the names of the prizes for the participants. If desired, you can remove a prize from the list by entering it again.</blockquote>\n\n"
                "<b>To add multiple prizes, send them to the bot one by one in separate messages:</b>",
                reply_markup=get_prizes_keyboard([]),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(GiveawayCreation.ENTER_PRIZES)

@router.message(GiveawayCreation.CUSTOM_WINNERS_COUNT)
async def enter_custom_winners_count(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except Exception:
        pass

    if not message.text.isdigit():
        data = await state.get_data()
        await safe_bot_send_message(bot, message.chat.id, "❌ Please enter a number.", reply_to_message_id=data.get('last_msg_id'))
        return

    await state.update_data(winners_count=int(message.text))
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')
    if data.get("return_to_confirm"):
        await state.update_data(return_to_confirm=False)
        await state.set_state(GiveawayCreation.CONFIRMATION)
        await show_edit_params(message, state, bot)
        return

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            "<tg-emoji emoji-id=\"5891105528356018797\">💎</tg-emoji> <b>Prizes</b>\n\n"
            "<blockquote>Enter the names of the prizes for the participants. If desired, you can remove a prize from the list by entering it again.</blockquote>\n\n"
            "<b>To add multiple prizes, send them to the bot one by one in separate messages:</b>",
            reply_markup=get_prizes_keyboard([]),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.ENTER_PRIZES)

@router.message(GiveawayCreation.ENTER_PRIZES)
async def enter_prizes(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    prizes = data.get("prizes", [])
    new_prize = message.text.strip()

    if new_prize in prizes:
        prizes.remove(new_prize)
    else:
        prizes.append(new_prize)

    await state.update_data(prizes=prizes)
    last_msg_id = data.get("last_msg_id")

    prizes_text = "\n".join([f"• {p}" for p in prizes]) if prizes else "None"
    await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
        f"<tg-emoji emoji-id=\"5891105528356018797\">💎</tg-emoji> <b>Prizes</b>\n\n"
        f"<b>Current list:</b>\n{prizes_text}\n\n"
        "<blockquote>Enter the names of the prizes. Entering an existing prize will remove it.</blockquote>",
        reply_markup=get_prizes_keyboard(prizes),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data == "confirm_prizes", GiveawayCreation.ENTER_PRIZES)
async def confirm_prizes(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await state.set_state(GiveawayCreation.CONFIRMATION)
    await state.update_data(return_to_confirm=False)
    await show_edit_params(callback, state, bot)

async def show_edit_params(event, state: FSMContext, bot: Bot):
    data = await state.get_data()
    
    title = html.escape(str(data.get("title", "Not specified")))
    gkind = "Partner" if data.get("mandatory_channels") else "Fast"
    
    raw_channels = data.get("mandatory_channels", [])
    channels = ", ".join([html.escape(str(c)) for c in raw_channels]) or "None"
    
    gtype = "Certain time" if data.get("gtype") == "timed" else "By participants"
    mode_val = html.escape(str(data.get("mode_value", "Not specified")))
    winners = html.escape(str(data.get("winners_count", "Not specified")))
    
    raw_prizes = data.get("prizes", [])
    prizes = ", ".join([html.escape(str(p)) for p in raw_prizes]) or "None"

    text = (
        f"<tg-emoji emoji-id=\"5258096772776991776\">⚙️</tg-emoji> <b>Giveaway Parameters</b>\n\n"
        f"<blockquote><b>Name:</b> {title}\n"
        f"<b>Kind:</b> {gkind}\n"
        f"<b>Channels:</b> {channels}\n"
        f"<b>Type:</b> {gtype}\n"
        f"<b>Mode:</b> {mode_val}\n"
        f"<b>Winners:</b> {winners}\n"
        f"<b>Prizes:</b> {prizes}</blockquote>\n\n"
        f"<b>Select a parameter to edit or launch the giveaway:</b>"
    )

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event, text, reply_markup=get_edit_params_keyboard(), parse_mode=ParseMode.HTML)
    else:
        await safe_bot_edit_text(bot, event.chat.id, data.get("last_msg_id"), text, reply_markup=get_edit_params_keyboard(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "edit_title", StateFilter(GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS))
async def edit_title(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True, return_to_confirm=True)
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5258254475386167466\">🖼</tg-emoji> <b>Edit Name</b>\n\n"
        "<blockquote>Enter a new name for your giveaway</blockquote>",
        reply_markup=get_nav_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.ENTER_NAME)

@router.callback_query(F.data == "edit_channels", StateFilter(GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS))
async def edit_channels(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True, return_to_confirm=True)
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji> <b>Mandatory channels</b>\n\n"
        "<blockquote>Enter the @usernames of the channels, separated by spaces or commas.</blockquote>",
        reply_markup=get_nav_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.ENTER_CHANNELS)

@router.callback_query(F.data == "edit_type", StateFilter(GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS))
async def edit_type(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True, return_to_confirm=True)
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji> <b>Giveaway type</b>\n\n"
        "<blockquote>Select the format of the giveaway</blockquote>",
        reply_markup=get_type_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.SELECT_TYPE)

@router.callback_query(F.data == "edit_mode", StateFilter(GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS))
async def edit_mode(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True, return_to_confirm=True)
    data = await state.get_data()
    gtype = data.get('gtype')
    if gtype == "timed":
        text = (
            "<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji> <b>End time</b>\n\n"
            "<blockquote>Specify the date and time at which the bot will determine the winners (Moscow time)</blockquote>\n\n"
            "<b>Select or enter time (DD.MM.YYYY HH:MM):</b>"
        )
    else:
        text = (
            "<tg-emoji emoji-id=\"5258073068852485953\">✈️</tg-emoji> <b>Participants limit</b>\n\n"
            "<blockquote>Select the number of participants to complete</blockquote>\n\n"
            "<b>Select limit:</b>"
        )
    await safe_edit_text(callback, text, reply_markup=get_mode_keyboard(gtype), parse_mode=ParseMode.HTML)
    await state.set_state(GiveawayCreation.SELECT_MODE_VALUE)

@router.callback_query(F.data == "edit_winners", StateFilter(GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS))
async def edit_winners(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True, return_to_confirm=True)
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5274159185959872191\">👑</tg-emoji> <b>Winners</b>\n\n"
        "<blockquote>Select the number of prize places</blockquote>\n\n"
        "<b>Select quantity:</b>",
        reply_markup=get_winners_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.SELECT_WINNERS_COUNT)

@router.callback_query(F.data == "edit_prizes", StateFilter(GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS))
async def edit_prizes(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True, return_to_confirm=True)
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5891105528356018797\">💎</tg-emoji> <b>Prizes</b>\n\n"
        "<blockquote>Enter the names of the prizes for the participants.</blockquote>",
        reply_markup=get_prizes_keyboard([]),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.ENTER_PRIZES)

def parse_exact_time(time_str: str) -> datetime:
    moscow_tz = pytz.timezone('Europe/Moscow')
    try:
        local_dt = datetime.strptime(time_str, "%d.%m.%Y %H:%M")
        local_dt = moscow_tz.localize(local_dt)
    except ValueError:
        now_moscow = datetime.now(moscow_tz)
        try:
            h, m = map(int, time_str.split(':'))
            local_dt = moscow_tz.localize(datetime.combine(now_moscow.date(), time(h, m)))
            if local_dt <= now_moscow:
                local_dt += timedelta(days=1)
        except Exception:
            raise ValueError("Invalid time format. Use DD.MM.YYYY HH:MM or HH:MM")
    return local_dt.astimezone(pytz.UTC)

async def get_giveaway_post_data(giveaway: dict):
    safe_title = html.escape(giveaway['title'])
    safe_prizes_list = [html.escape(p) for p in giveaway['prizes']]
    safe_prizes = ", ".join(safe_prizes_list)

    if giveaway['mode'] == "timed":
        end_at_dt = datetime.fromisoformat(giveaway['end_at'].replace('Z', '+00:00'))
        moscow_dt = end_at_dt.astimezone(pytz.timezone("Europe/Moscow"))
        end_time_str = moscow_dt.strftime("%d.%m.%Y %H:%M")
    else:
        end_time_str = f"{giveaway['value']} чел."

    conditions_text = "┋<tg-emoji emoji-id=\"5208683423144649892\">😎</tg-emoji> <b>HOW TO ENTER:</b>\n"
    if giveaway.get('mandatory_channels'):
        for idx, channel in enumerate(giveaway['mandatory_channels'], start=1):
            conditions_text += f"┋{idx}. Subscribe to {html.escape(channel)}\n"
        conditions_text += f"┋{len(giveaway['mandatory_channels'])+1}. Click the button below.\n"
    else:
        conditions_text += "┋1. Click the button below.\n"

    post_text = (
        f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ <b>/ {safe_title} /</b>\n"
        f"┋\n"
        f"┣<tg-emoji emoji-id=\"5208616782432084452\">🔥</tg-emoji> <b>WINNERS:</b> {giveaway['winners_count']}\n"
        f"┋\n"
        f"┣<tg-emoji emoji-id=\"5273741156792951269\">🤓</tg-emoji> <b>PRIZES:</b> - {safe_prizes}\n"
        f"┋\n"
        f"{conditions_text}"
        f"┋\n"
        f"┣<tg-emoji emoji-id=\"5274248753207863828\">😈</tg-emoji> <b>ENDS:</b> {end_time_str}\n"
        f"┋\n"
        f"┣<b>GIVEAWAY</b>\n"
        f"┣<b>[ HUMANS.. NOT APES ]</b>\n"
        f"┗┅┅┅/ #NOTAPES /"
    )

    db_gif = await db.get_setting("main_gif")
    gif_to_send = db_gif or GIF_ID

    return post_text, gif_to_send

@router.callback_query(F.data == "confirm_giveaway", StateFilter(GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS))
async def process_confirm_giveaway(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()
    end_at = None
    try:
        if data['gtype'] == "timed":
            end_at = parse_exact_time(data['mode_value'])
    except Exception as e:
        await callback.answer(f"❌ Error parsing time: {e}", show_alert=True)
        return

    # Update to active if already exists or will be created as active
    giveaway = await db.create_giveaway(
        creator_id=callback.from_user.id,
        chat_id=data['chat_id'],
        title=data['title'],
        mode=data['gtype'],
        value=data['mode_value'],
        winners_count=data['winners_count'],
        prizes=data['prizes'],
        end_at=end_at,
        mandatory_channels=data.get('mandatory_channels', []),
        allowed_users=data.get('allowed_users')
    )
    await db.update_giveaway_status(giveaway["id"], "active")

    post_text, gif_to_send = await get_giveaway_post_data(giveaway)

    target_chat = await bot.get_chat(data['chat_id'])
    if target_chat.type == ChatType.CHANNEL:
        post_text = strip_custom_emojis(post_text)

    builder = InlineKeyboardBuilder()
    builder.button(text="START", callback_data=f"join_{giveaway['id']}", icon_custom_emoji_id="5260726538302660868", style="success")

    try:
        try:
            msg = await bot.send_animation(
                chat_id=data['chat_id'],
                animation=gif_to_send,
                caption=post_text,
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            msg = await bot.send_message(
                chat_id=data['chat_id'],
                text=post_text,
                reply_markup=builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
        await db.add_giveaway_message(giveaway['id'], data['chat_id'], msg.message_id)

        try:
            await bot.pin_chat_message(chat_id=data['chat_id'], message_id=msg.message_id)
        except Exception as pin_err:
            logger.error(f"Failed to pin message: {pin_err}")

        success_builder = InlineKeyboardBuilder()
        success_builder.button(text="Make announcement", callback_data=f"make_announcement_{giveaway['id']}", icon_custom_emoji_id="5260268501515377807")
        success_builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
        success_builder.adjust(1)
        await safe_edit_text(callback,
            "<tg-emoji emoji-id=\"5258501105293205250\">👏</tg-emoji> <b>The giveaway has been successfully launched!</b>",
            reply_markup=success_builder.as_markup(),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await safe_edit_text(callback, f"<tg-emoji emoji-id=\"5273876254989246882\">🤬</tg-emoji> Error sending message to group: {e}")

    await state.clear()

async def is_bot_admin(chat_id: int, bot: Bot) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, bot.id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

@router.callback_query(F.data.startswith("make_announcement_"))
async def make_announcement_select_chat(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    giveaway_id = int(callback.data.split("_")[-1])

    chats = await db.get_tracked_groups()
    builder = InlineKeyboardBuilder()

    count = 0
    for chat in chats:
        if await is_bot_admin(chat['chat_id'], bot):
            builder.button(text=chat['title'], callback_data=f"ann_to_{giveaway_id}_{chat['chat_id']}")
            count += 1

    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    text = "<b>Select a chat for the announcement:</b>" if count > 0 else "<b>There are no chats available for announcement.</b>"

    await safe_edit_text(callback,
        text,
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data.startswith("ann_to_"))
async def execute_announcement(callback: types.CallbackQuery, bot: Bot):
    await callback.answer()
    parts = callback.data.split("_")
    giveaway_id = int(parts[2])
    target_chat_id = int(parts[3])

    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway:
        await callback.message.answer("<tg-emoji emoji-id=\"5273876254989246882\">🤬</tg-emoji> Giveaway not found.", parse_mode=ParseMode.HTML)
        return

    target_chat = await bot.get_chat(target_chat_id)
    is_channel = target_chat.type == ChatType.CHANNEL

    post_text, gif_to_send = await get_giveaway_post_data(giveaway)

    if is_channel:
        post_text = strip_custom_emojis(post_text)

    join_builder = InlineKeyboardBuilder()

    if target_chat_id != giveaway['chat_id']:
        orig_chat = await bot.get_chat(giveaway['chat_id'])
        msgs = await db.get_giveaway_messages(giveaway_id)
        orig_msg_id = next((m['message_id'] for m in msgs if m['chat_id'] == giveaway['chat_id']), None)

        if orig_msg_id:
            link = get_message_link(orig_chat, orig_msg_id)
            join_builder.button(text="JOIN", url=link)
        else:
            join_builder.button(text="START", callback_data=f"join_{giveaway_id}", icon_custom_emoji_id="5260726538302660868", style="success")
    else:
        join_builder.button(text="START", callback_data=f"join_{giveaway_id}", icon_custom_emoji_id="5260726538302660868", style="success")

    try:
        try:
            ann_msg = await bot.send_animation(
                chat_id=target_chat_id,
                animation=gif_to_send,
                caption=post_text,
                reply_markup=join_builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            ann_msg = await bot.send_message(
                chat_id=target_chat_id,
                text=post_text,
                reply_markup=join_builder.as_markup(),
                parse_mode=ParseMode.HTML
            )
        await db.add_giveaway_message(giveaway_id, target_chat_id, ann_msg.message_id)
        await callback.message.answer("<tg-emoji emoji-id=\"5258501105293205250\">👏</tg-emoji> The announcement has been successfully published", parse_mode=ParseMode.HTML)
    except Exception as e:
        await callback.message.answer(f"<tg-emoji emoji-id=\"5273876254989246882\">🤬</tg-emoji> Error sending announcement: {e}", parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "back")
async def process_back(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()

    if current_state == GiveawayCreation.SELECT_CHAT:
         from handlers.main_menu import back_to_main_menu
         await back_to_main_menu(callback, state)

    elif current_state == GiveawayCreation.ENTER_NAME:
        # Back to SELECT_CHAT
        from handlers.main_menu import create_giveaway_handler
        await create_giveaway_handler(callback, state)

    elif current_state == GiveawayCreation.SELECT_GIVEAWAY_KIND:
        # Back to ENTER_NAME
        await edit_title(callback, state)

    elif current_state == GiveawayCreation.ENTER_CHANNELS:
        # Back to SELECT_GIVEAWAY_KIND
        data = await state.get_data()
        last_msg_id = data.get('last_msg_id')
        await safe_bot_edit_text(bot, callback.message.chat.id, last_msg_id,
            '<tg-emoji emoji-id="5258185631355378853">⭐️</tg-emoji> <b>Giveaway Kind</b>\n\n'
            '<blockquote>Select the kind of giveaway:</blockquote>',
            reply_markup=get_giveaway_kind_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_GIVEAWAY_KIND)

    elif current_state == GiveawayCreation.WAITING_FOR_BOT_ADMIN:
        # Back to ENTER_CHANNELS
        await safe_edit_text(callback,
            '<tg-emoji emoji-id="5258185631355378853">⭐️</tg-emoji> <b>Mandatory channels</b>\n\n'
            '<blockquote>Enter the @usernames of the channels users must subscribe to, separated by spaces or commas.</blockquote>\n\n'
            '<b>Enter channels:</b>',
            reply_markup=get_nav_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.ENTER_CHANNELS)

    elif current_state == GiveawayCreation.WAITING_FOR_ACCESS_TYPE:
        # Возврат к вводу каналов
        data = await state.get_data()
        if data.get('mandatory_channels'):
            await safe_edit_text(callback,
                '<tg-emoji emoji-id="5258185631355378853">⭐️</tg-emoji> <b>Mandatory channels</b>\n\n'
                '<blockquote>Enter the @usernames of the channels users must subscribe to, separated by spaces or commas.</blockquote>\n\n'
                '<b>Enter channels:</b>',
                reply_markup=get_nav_keyboard(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(GiveawayCreation.ENTER_CHANNELS)
        else:
            # If no channels (Fast kind), back to kind selection
            last_msg_id = data.get('last_msg_id')
            await safe_bot_edit_text(bot, callback.message.chat.id, last_msg_id,
                '<tg-emoji emoji-id="5258185631355378853">⭐️</tg-emoji> <b>Giveaway Kind</b>\n\n'
                '<blockquote>Select the kind of giveaway:</blockquote>',
                reply_markup=get_giveaway_kind_keyboard(),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(GiveawayCreation.SELECT_GIVEAWAY_KIND)

    elif current_state in [GiveawayCreation.WAITING_FOR_WHITELIST, GiveawayCreation.SELECT_TYPE]:
        # Back to WAITING_FOR_ACCESS_TYPE
        await ask_access_type(callback.message, state, bot)

    elif current_state in [GiveawayCreation.SELECT_MODE_VALUE, GiveawayCreation.CUSTOM_MODE_VALUE]:
        # Back to SELECT_TYPE
        await safe_edit_text(callback,
            '<tg-emoji emoji-id="5258185631355378853">⭐️</tg-emoji> <b>Draw type</b>\n\n'
            '<blockquote>Select the format of the drawing</blockquote>\n\n'
            '<b>Select type:</b>',
            reply_markup=get_type_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_TYPE)

    elif current_state in [GiveawayCreation.SELECT_WINNERS_COUNT, GiveawayCreation.CUSTOM_WINNERS_COUNT]:
        # Back to SELECT_MODE_VALUE
        gtype = data.get("gtype")
        text = (
            '<tg-emoji emoji-id="5850317551090800862">⏳</tg-emoji> <b>End time</b>\n\n'
            '<blockquote>Specify the date and time at which the bot will determine the winners (Moscow time)</blockquote>\n\n'
            '<b>Select or enter time (DD.MM.YYYY HH:MM):</b>'
        ) if gtype == "timed" else (
            '<tg-emoji emoji-id="6032594876506312598">👥</tg-emoji> <b>Participants</b>\n\n'
            '<blockquote>Specify the number of participants upon reaching which the drawing will take place</blockquote>\n\n'
            '<b>Select or enter quantity:</b>'
        )
        await safe_edit_text(callback, text, reply_markup=get_mode_keyboard(gtype), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.SELECT_MODE_VALUE)

    elif current_state == GiveawayCreation.ENTER_PRIZES:
        # Back to SELECT_WINNERS_COUNT
        await edit_winners(callback, state)

    elif current_state in [GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS]:
        # Возвращаемся обратно на шаг ввода призов
        text = (
            "<tg-emoji emoji-id="6032644646587338669">🎁</tg-emoji> <b>Prizes</b>\n\n"
            "<blockquote>Specify the prizes for the giveaway. Each prize on a new line.</blockquote>\n\n"
            "<b>Enter prizes text:</b>"
        )
        await safe_edit_text(callback, text, reply_markup=get_nav_keyboard(), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.ENTER_PRIZES)
    else:
        # Fallback to main menu
        from handlers.main_menu import back_to_main_menu
        await back_to_main_menu(callback, state)
