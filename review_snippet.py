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
    builder.adjust(1)
    return builder.as_markup()

def get_nav_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Back", callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2)
    return builder.as_markup()

def get_recheck_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ I added!", callback_data="recheck_admin")
    builder.button(text="❌ Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
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
    builder.adjust(2, 2)
    return builder.as_markup()

def get_mode_keyboard(gtype):
    builder = InlineKeyboardBuilder()
    if gtype == "timed":
        builder.button(text="12:00", style="success", callback_data="val_12:00")
        builder.button(text="15:00", style="success", callback_data="val_15:00")
        builder.button(text="18:00", style="success", callback_data="val_18:00")
        builder.button(text="21:00", style="success", callback_data="val_21:00")
    else:
        builder.button(text="10", style="success", callback_data="val_10")
        builder.button(text="25", style="success", callback_data="val_25")
        builder.button(text="50", style="success", callback_data="val_50")
        builder.button(text="100", style="success", callback_data="val_100")
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
    builder.adjust(2, 2)
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
        "<tg-emoji emoji-id=\"5258254475386167466\">🖼</tg-emoji> <b>Event name</b>\n\n"
        "<blockquote>Come up with a name for your giveaway</blockquote>\n\n"
        "<b>Enter a name:</b>",
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

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            "<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji> <b>Giveaway Kind</b>\n\n"
            "<blockquote>Select the kind of giveaway:</blockquote>",
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
            "<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji> <b>Mandatory channels</b>\n\n"
            "<blockquote>Enter the @usernames of the channels users must subscribe to, separated by spaces or commas.</blockquote>\n\n"
            "<b>Enter channels:</b>",
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
            f"The bot hasn't been added to @{failed_channel} yet. Please make sure it has administrator status.",
            reply_markup=get_recheck_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.WAITING_FOR_BOT_ADMIN)
        return

    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')

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
            f"The bot hasn't been added to @{failed_channel} yet. Please make sure it has administrator status.",
            reply_markup=get_recheck_keyboard(),
            parse_mode=ParseMode.HTML
        )
        return

    await callback.answer("✅ All channels verified!")
    if data.get('is_editing'):
        await show_edit_params(callback.message, state, bot)
    else:
        await ask_access_type(callback.message, state, bot)

async def ask_access_type(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')
    await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
        "<tg-emoji emoji-id=\"5258476306152038031\">🔒</tg-emoji> <b>Access type</b>\n\n"
        "<blockquote>Who can participate in the giveaway?</blockquote>\n\n"
        "<b>Action prompt:</b>",
        reply_markup=get_access_type_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.WAITING_FOR_ACCESS_TYPE)

@router.callback_query(GiveawayCreation.WAITING_FOR_ACCESS_TYPE)
async def process_access_choice(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    if callback.data == "access_all":
        await state.update_data(allowed_users=None)
        await callback.answer("✅ Giveaway is now Public.")
        await safe_edit_text(callback,
            "<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji> <b>Draw type</b>\n\n"
            "<blockquote>Select the format of the drawing</blockquote>\n\n"
            "<b>Select type:</b>",
            reply_markup=get_type_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_TYPE)
    elif callback.data == "access_whitelist":
        await safe_edit_text(callback,
            "<tg-emoji emoji-id=\"5258476306152038031\">🔒</tg-emoji> <b>Whitelist</b>\n\n"
            "<blockquote>Send the list of @usernames or User IDs.\n"
            "Example: @user1, 12345678, @user2</blockquote>\n\n"
            "<b>Action prompt:</b>",
            reply_markup=get_nav_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.WAITING_FOR_WHITELIST)
    await callback.answer()

@router.message(GiveawayCreation.WAITING_FOR_WHITELIST)
async def process_whitelist(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
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

    chats = await db.get_tracked_chats()
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
            join_builder.button(text="Join the chat", url=link)
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
        # If in confirmation/edit, back to ENTER_PRIZES
        await edit_prizes(callback, state)

    else:
        # Fallback to main menu
        from handlers.main_menu import back_to_main_menu
        await back_to_main_menu(callback, state)
