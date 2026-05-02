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
    SELECT_TYPE = State()
    SELECT_MODE_VALUE = State()
    CUSTOM_MODE_VALUE = State()
    SELECT_WINNERS_COUNT = State()
    CUSTOM_WINNERS_COUNT = State()
    ENTER_PRIZES = State()
    CONFIRMATION = State()
    EDIT_PARAMS = State()

def get_type_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Certain time", callback_data="type_timed", icon_custom_emoji_id="5850317551090800862")
    builder.button(text="By participants", callback_data="type_limited", icon_custom_emoji_id="6032594876506312598")
    builder.adjust(2)
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
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

def get_winners_keyboard():
    builder = InlineKeyboardBuilder()
    for i in range(1, 6):
        builder.button(text=str(i), callback_data=f"win_{i}")
    builder.button(text="Your own option", callback_data="win_custom", icon_custom_emoji_id="5274008024585871702")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(5, 1, 1)
    return builder.as_markup()

def get_prizes_keyboard(prizes):
    builder = InlineKeyboardBuilder()
    if prizes:
        builder.button(text="Confirm prizes", callback_data="confirm_prizes", icon_custom_emoji_id="5260726538302660868", style="success")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)
    return builder.as_markup()

def get_edit_params_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Name", callback_data="edit_title", icon_custom_emoji_id="5778299625370817409")
    builder.button(text="Type", callback_data="edit_type", icon_custom_emoji_id="5258185631355378853")
    builder.button(text="Mode", callback_data="edit_mode", icon_custom_emoji_id="5850317551090800862")
    builder.button(text="Winners", callback_data="edit_winners", icon_custom_emoji_id="5805553606635559688")
    builder.button(text="Prizes", callback_data="edit_prizes", icon_custom_emoji_id="5891105528356018797")
    builder.button(text="Launch", callback_data="finalize_giveaway", icon_custom_emoji_id="5258073068852485953", style="success")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 1, 1, 1)
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
    await state.update_data(chat_id=chat_id)
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5258254475386167466\">🖼</tg-emoji> <b>Event name</b>\n\n"
        "<blockquote>Come up with a name for your giveaway</blockquote>\n\n"
        "Enter a name:",
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
            "<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji> <b>Draw type</b>\n\n"
            "<blockquote>Select the format of the drawing</blockquote>\n\n"
            "Select type:",
            reply_markup=get_type_keyboard(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_TYPE)

@router.callback_query(F.data.startswith("type_"), GiveawayCreation.SELECT_TYPE)
async def select_type(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    gtype = callback.data.split("_")[1]
    await state.update_data(gtype=gtype)

    if gtype == "timed":
        text = (
            "<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji> <b>End time</b>\n\n"
            "<blockquote>Specify the time at which the bot will determine the winners (Moscow time)</blockquote>\n\n"
            "Select or enter time (HH:MM):"
        )
    else:
        text = (
            "<tg-emoji emoji-id=\"5258073068852485953\">✈️</tg-emoji> <b>Participants limit</b>\n\n"
            "<blockquote>Select the number of participants to complete</blockquote>\n\n"
            "Select limit:"
        )
    await safe_edit_text(callback, text, reply_markup=get_mode_keyboard(gtype), parse_mode=ParseMode.HTML)
    await state.set_state(GiveawayCreation.SELECT_MODE_VALUE)

@router.callback_query(F.data.startswith("val_"), GiveawayCreation.SELECT_MODE_VALUE)
async def select_mode_value(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    val = callback.data.split("_")[1]
    if val == "custom":
        await safe_edit_text(callback,
            "<b>Enter your value:</b>\n\n"
            "<blockquote>Enter the time in HH:MM format or the number of participants as a number</blockquote>",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.CUSTOM_MODE_VALUE)
    else:
        await state.update_data(mode_value=val)
        data = await state.get_data()
        if data.get('is_editing'):
            await show_edit_params(callback, state, bot)
        else:
            await safe_edit_text(callback,
                "<tg-emoji emoji-id=\"5274159185959872191\">👑</tg-emoji> <b>Winners</b>\n\n"
                "<blockquote>Select the number of prize places</blockquote>\n\n"
                "Select quantity:",
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

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            "<tg-emoji emoji-id=\"5274159185959872191\">👑</tg-emoji> <b>Winners</b>\n\n"
            "<blockquote>Select the number of prize places</blockquote>\n\n"
            "Select quantity:",
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
            "<b>Enter the number of winners:</b>\n\n"
            "<blockquote>Please indicate the desired number of prize places.</blockquote>",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.CUSTOM_WINNERS_COUNT)
    else:
        await state.update_data(winners_count=int(val))
        data = await state.get_data()
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
            await state.update_data(prizes=[])

@router.message(GiveawayCreation.CUSTOM_WINNERS_COUNT)
async def enter_custom_winners_count(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')

    try:
        count = int(message.text)
        await state.update_data(winners_count=count)
        data = await state.get_data()
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
            await state.update_data(prizes=[])
    except ValueError:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            "<b>Please enter a number.</b>\n\n"
            "<blockquote>Please indicate the desired number of prize places:</blockquote>",
            parse_mode=ParseMode.HTML
        )

@router.message(GiveawayCreation.ENTER_PRIZES)
async def enter_prizes(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except Exception:
        pass

    data = await state.get_data()
    prizes = data.get('prizes', [])
    last_msg_id = data.get('last_msg_id')
    new_prize = message.text

    if new_prize in prizes:
        prizes.remove(new_prize)
        status_msg = f"Prize «{html.escape(new_prize)}» deleted."
    else:
        prizes.append(new_prize)
        status_msg = f"Prize «{html.escape(new_prize)}» added."

    await state.update_data(prizes=prizes)
    prizes_list = "\n".join([f"• {html.escape(p)}" for p in prizes])

    text = (
        f"<tg-emoji emoji-id=\"5891105528356018797\">💎</tg-emoji> <b>Prizes</b>\n\n"
        f"<b>{status_msg}</b>\n\n"
        f"<blockquote><b>Current list:</b>\n"
        f"{prizes_list if prizes else 'Empty'}</blockquote>\n\n"
        f"Enter the next prize or click the button below:"
    )

    await safe_bot_edit_text(bot, message.chat.id, last_msg_id, text,
        reply_markup=get_prizes_keyboard(prizes),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data == "confirm_prizes", GiveawayCreation.ENTER_PRIZES)
async def confirm_prizes(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await show_edit_params(callback, state, bot)

async def show_edit_params(message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    prizes_str = ", ".join(data['prizes'])
    last_msg_id = data.get('last_msg_id')

    text = (
        "<tg-emoji emoji-id=\"5258096772776991776\">⚙️</tg-emoji> <b>Draw parameters</b>\n\n"
        "<blockquote>"
        f"<b>Name:</b> {html.escape(data['title'])}\n"
        f"<b>Type:</b> {'By time' if data['gtype'] == 'timed' else 'By participants'}\n"
        f"<b>Mode:</b> {data['mode_value']}\n"
        f"<b>Winners:</b> {data['winners_count']}\n"
        f"<b>Prizes:</b> {html.escape(prizes_str)}"
        "</blockquote>\n\n"
        "Check the data and click «START»."
    )

    if isinstance(message, types.Message):
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id, text,
            reply_markup=get_edit_params_keyboard(), parse_mode=ParseMode.HTML)
    else:
        await safe_edit_text(message, text,
            reply_markup=get_edit_params_keyboard(), parse_mode=ParseMode.HTML)

    await state.set_state(GiveawayCreation.EDIT_PARAMS)

@router.callback_query(F.data == "edit_title", StateFilter(GiveawayCreation.EDIT_PARAMS))
async def edit_title(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True)
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5258254475386167466\">🖼</tg-emoji> <b>Event name</b>\n\n"
        "<blockquote>Come up with a name for your giveaway</blockquote>\n\n"
        "Enter a name:",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.ENTER_NAME)

@router.callback_query(F.data == "edit_type", StateFilter(GiveawayCreation.EDIT_PARAMS))
async def edit_type(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True)
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5258185631355378853\">⭐️</tg-emoji> <b>Giveaway type</b>\n\n"
        "<blockquote>Select the format of the giveaway</blockquote>\n\n"
        "Select type:",
        reply_markup=get_type_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.SELECT_TYPE)

@router.callback_query(F.data == "edit_mode", StateFilter(GiveawayCreation.EDIT_PARAMS))
async def edit_mode(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True)
    data = await state.get_data()
    gtype = data['gtype']
    if gtype == "timed":
        text = (
            "<tg-emoji emoji-id=\"5850317551090800862\">⏳</tg-emoji> <b>End time</b>\n\n"
            "<blockquote>Specify the time at which the bot will determine the winners (Moscow time)</blockquote>\n\n"
            "Select or enter time (HH:MM):"
        )
    else:
        text = (
            "<tg-emoji emoji-id=\"5258073068852485953\">✈️</tg-emoji> <b>Participants limit</b>\n\n"
            "<blockquote>Select the number of participants to complete</blockquote>\n\n"
            "Select limit:"
        )
    await safe_edit_text(callback, text, reply_markup=get_mode_keyboard(gtype), parse_mode=ParseMode.HTML)
    await state.set_state(GiveawayCreation.SELECT_MODE_VALUE)

@router.callback_query(F.data == "edit_winners", StateFilter(GiveawayCreation.EDIT_PARAMS))
async def edit_winners(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.update_data(is_editing=True)
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5274159185959872191\">👑</tg-emoji> <b>Winners</b>\n\n"
        "<blockquote>Select the number of prize places</blockquote>\n\n"
        "Select quantity:",
        reply_markup=get_winners_keyboard(),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.SELECT_WINNERS_COUNT)

@router.callback_query(F.data == "edit_prizes", StateFilter(GiveawayCreation.EDIT_PARAMS))
async def edit_prizes(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await safe_edit_text(callback,
        "<tg-emoji emoji-id=\"5891105528356018797\">💎</tg-emoji> <b>Prizes</b>\n\n"
        "<blockquote>Enter the names of the prizes for the participants. If desired, you can remove a prize from the list by entering it again.</blockquote>\n\n"
        "<b>To add multiple prizes, send them to the bot one by one in separate messages:</b>",
        reply_markup=get_prizes_keyboard([]),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.ENTER_PRIZES)

def get_next_occurrence(time_str: str) -> datetime:
    moscow_tz = pytz.timezone('Europe/Moscow')
    now_moscow = datetime.now(moscow_tz)
    h, m = map(int, time_str.split(':'))
    target = moscow_tz.localize(datetime.combine(now_moscow.date(), time(h, m)))
    if target <= now_moscow:
        target += timedelta(days=1)
    return target.astimezone(pytz.UTC)

async def get_giveaway_post_data(giveaway: dict):
    safe_title = html.escape(giveaway['title'])
    safe_prizes_list = [html.escape(p) for p in giveaway['prizes']]
    safe_prizes = ", ".join(safe_prizes_list)

    if giveaway['mode'] == "timed":
        end_at_dt = datetime.fromisoformat(giveaway['end_at'].replace('Z', '+00:00'))
        end_time_str = end_at_dt.astimezone(pytz.timezone("Europe/Moscow")).strftime("%H:%M")
    else:
        end_time_str = f"{giveaway['value']} чел."

    post_text = (
        f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ <b>/ {safe_title} /</b>\n"
        f"┋<tg-emoji emoji-id=\"5274248753207863828\">😈</tg-emoji> <b>WIN:</b> {giveaway['winners_count']} - {safe_prizes}\n"
        f"┋\n"
        f"┋<tg-emoji emoji-id=\"5273741156792951269\">🤓</tg-emoji> <b>JOIN:</b> Click the button.\n"
        f"┋\n"
        f"┋<tg-emoji emoji-id=\"5273876254989246882\">🤬</tg-emoji> <b>ENDS:</b> {end_time_str}\n"
        f"┋\n"
        f"┣<b>GIVEAWAY</b>\n"
        f"┣[ HUMANS.. NOT APES ]\n"
        f"┗┅┅┅/ #NOTAPES /"
    )

    db_gif = await db.get_setting("main_gif")
    gif_to_send = db_gif or GIF_ID

    return post_text, gif_to_send

@router.callback_query(F.data == "finalize_giveaway", StateFilter(GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS))
async def finalize_giveaway(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    data = await state.get_data()
    end_at = None
    if data['gtype'] == "timed":
        end_at = get_next_occurrence(data['mode_value'])

    giveaway = await db.create_giveaway(
        creator_id=callback.from_user.id,
        chat_id=data['chat_id'],
        title=data['title'],
        mode=data['gtype'],
        value=data['mode_value'],
        winners_count=data['winners_count'],
        prizes=data['prizes'],
        end_at=end_at
    )

    post_text, gif_to_send = await get_giveaway_post_data(giveaway)

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
