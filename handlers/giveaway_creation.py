import os
import html
import re
import secrets
import pytz
from datetime import datetime
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode, ChatType
from database import db
from utils import safe_bot_edit_text, safe_answer, safe_edit_text, strip_custom_emojis, get_message_link
import logging
from services.localization import get_locale, get_locale_by_lang

logger = logging.getLogger(__name__)

router = Router()

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

async def get_giveaway_kind_keyboard(texts):
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["fast_btn"], callback_data="kind_fast", icon_custom_emoji_id="5323761960829862762")
    builder.button(text=texts["partner_btn"], callback_data="kind_partner", icon_custom_emoji_id="5258486128742244085")
    builder.button(text=texts["back_btn"], callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)
    return builder.as_markup()

async def get_nav_keyboard(texts):
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["back_btn"], callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2)
    return builder.as_markup()

async def get_recheck_keyboard(texts):
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["i_added_btn"], callback_data="recheck_admin", icon_custom_emoji_id="5260726538302660868")
    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)
    return builder.as_markup()

async def get_type_keyboard(texts):
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["timed_btn"], callback_data="type_timed", icon_custom_emoji_id="5850317551090800862")
    builder.button(text=texts["limited_btn"], callback_data="type_limited", icon_custom_emoji_id="6032594876506312598")
    builder.button(text=texts["back_btn"], callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2)
    return builder.as_markup()

async def get_mode_keyboard(gtype, texts):
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

    builder.button(text=texts["custom_option_btn"], callback_data="val_custom", icon_custom_emoji_id="5274008024585871702")
    builder.button(text=texts["back_btn"], callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 1, 2)
    return builder.as_markup()

async def get_winners_keyboard(texts):
    builder = InlineKeyboardBuilder()
    for i in [1, 3, 5, 10]:
        builder.button(text=str(i), callback_data=f"win_{i}")
    builder.button(text=texts["custom_option_btn"], callback_data="win_custom", icon_custom_emoji_id="5274008024585871702")
    builder.button(text=texts["back_btn"], callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 1, 2)
    return builder.as_markup()

async def get_prizes_keyboard(prizes, texts):
    builder = InlineKeyboardBuilder()
    if prizes:
        builder.button(text=texts["confirm_prizes_btn"], callback_data="confirm_prizes", icon_custom_emoji_id="5260726538302660868", style="success")
    builder.button(text=texts["back_btn"], callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 2)
    return builder.as_markup()

async def get_access_type_keyboard(texts):
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["access_all_btn"], callback_data="access_all", icon_custom_emoji_id="5258486128742244085")
    builder.button(text=texts["access_whitelist_btn"], callback_data="access_whitelist", icon_custom_emoji_id="5258476306152038031")
    builder.button(text=texts["back_btn"], callback_data="back", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 1, 2)
    return builder.as_markup()

async def get_edit_params_keyboard(texts):
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["edit_name_btn"], callback_data="edit_title", icon_custom_emoji_id="5778299625370817409")
    builder.button(text=texts["edit_channels_btn"], callback_data="edit_channels", icon_custom_emoji_id="5258185631355378853")
    builder.button(text=texts["edit_type_btn"], callback_data="edit_type", icon_custom_emoji_id="5258185631355378853")
    builder.button(text=texts["edit_mode_btn"], callback_data="edit_mode", icon_custom_emoji_id="5850317551090800862")
    builder.button(text=texts["edit_winners_btn"], callback_data="edit_winners", icon_custom_emoji_id="5805553606635559688")
    builder.button(text=texts["edit_prizes_btn"], callback_data="edit_prizes", icon_custom_emoji_id="5891105528356018797")
    builder.button(text=texts["confirm_btn"], callback_data="confirm_giveaway", icon_custom_emoji_id="5258073068852485953", style="success")
    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()

@router.callback_query(F.data.startswith("chat_"))
async def process_chat_selection(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    chat_id = int(callback.data.split("_")[1])
    await state.update_data(chat_id=chat_id)
    await safe_edit_text(callback, texts["enter_title"], reply_markup=await get_nav_keyboard(texts), parse_mode=ParseMode.HTML)
    await state.set_state(GiveawayCreation.ENTER_NAME)

@router.message(GiveawayCreation.ENTER_NAME, F.text)
async def process_title_input(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    texts = await get_locale(user_id)
    try: await message.delete()
    except: pass
    await state.update_data(title=message.text)
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            texts["giveaway_title"],
            reply_markup=await get_giveaway_kind_keyboard(texts),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_GIVEAWAY_KIND)

@router.callback_query(F.data.startswith("kind_"))
async def process_kind(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    kind = callback.data.split("_")[1]
    await state.update_data(kind=kind)

    if kind == "partner":
        await safe_edit_text(callback, texts["enter_channels"], reply_markup=await get_nav_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.ENTER_CHANNELS)
    else:
        await state.update_data(mandatory_channels=None)
        await ask_access_type(callback.message, state, bot)

@router.message(GiveawayCreation.ENTER_CHANNELS, F.text)
async def process_channels(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    texts = await get_locale(user_id)
    try: await message.delete()
    except: pass

    raw_text = message.text.strip()
    channels = re.split(r'[,\s]+', raw_text)
    channels = [c.replace("https://t.me/", "@").strip() for c in channels if c.strip()]

    await state.update_data(mandatory_channels=channels)
    await check_bot_admin_in_channels(message, state, bot)

async def check_bot_admin_in_channels(message: types.Message | types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    texts = await get_locale(user_id)
    data = await state.get_data()
    channels = data.get("mandatory_channels", [])
    last_msg_id = data.get('last_msg_id')

    failed_channels = []
    for ch in channels:
        if not await is_bot_admin(ch, bot):
            failed_channels.append(ch)

    if failed_channels:
        failed_str = "\n".join(failed_channels)
        text = texts["bot_not_admin"].format(channels=failed_str)
        if isinstance(message, types.CallbackQuery):
            await safe_edit_text(message, text, reply_markup=await get_recheck_keyboard(texts), parse_mode=ParseMode.HTML)
        else:
            await safe_bot_edit_text(bot, message.chat.id, last_msg_id, text, reply_markup=await get_recheck_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.WAITING_FOR_BOT_ADMIN)
        return

    await callback_answer_wrapper(message, texts["channels_verified_alert"])
    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await ask_access_type(message if isinstance(message, types.Message) else message.message, state, bot)

async def callback_answer_wrapper(event, text):
    if isinstance(event, types.CallbackQuery):
        await event.answer(text)

@router.callback_query(F.data == "recheck_admin")
async def recheck_admin(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await check_bot_admin_in_channels(callback, state, bot)

async def ask_access_type(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.chat.id
    texts = await get_locale(user_id)
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')
    await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
        texts["select_access"],
        reply_markup=await get_access_type_keyboard(texts),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GiveawayCreation.WAITING_FOR_ACCESS_TYPE)

@router.callback_query(GiveawayCreation.WAITING_FOR_ACCESS_TYPE)
async def process_access_choice(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    if callback.data == "access_all":
        await state.update_data(allowed_users=None)
        await callback.answer(texts["giveaway_public_alert"])
        data = await state.get_data()
        if data.get('is_editing'):
            await show_edit_params(callback, state, bot)
        else:
            await safe_edit_text(callback,
                texts["select_type"],
                reply_markup=await get_type_keyboard(texts),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(GiveawayCreation.SELECT_TYPE)
    elif callback.data == "access_whitelist":
        await safe_edit_text(callback,
            texts["enter_whitelist"],
            reply_markup=await get_nav_keyboard(texts),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.WAITING_FOR_WHITELIST)
    await callback.answer()

@router.message(GiveawayCreation.WAITING_FOR_WHITELIST)
async def process_whitelist(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    texts = await get_locale(user_id)
    try: await message.delete()
    except: pass

    raw_list = re.split(r'[,\s]+', message.text.strip())
    processed_list = [item.strip().lower() for item in raw_list if item.strip()]

    await state.update_data(allowed_users=processed_list)

    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            texts["select_type"],
            reply_markup=await get_type_keyboard(texts),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_TYPE)

@router.callback_query(F.data.startswith("type_"))
async def select_type(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    await callback.answer()
    gtype = callback.data.split("_")[1]
    await state.update_data(gtype=gtype)

    if gtype == "timed":
        text = texts["enter_time"]
    else:
        text = texts["enter_participants"]

    await safe_edit_text(callback, text, reply_markup=await get_mode_keyboard(gtype, texts), parse_mode=ParseMode.HTML)
    await state.set_state(GiveawayCreation.SELECT_MODE_VALUE)

@router.callback_query(F.data.startswith("val_"), GiveawayCreation.SELECT_MODE_VALUE)
async def select_mode_value(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    await callback.answer()
    val = callback.data.split("_")[1]
    if val == "custom":
        await safe_edit_text(callback, texts["enter_value_prompt"], parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.CUSTOM_MODE_VALUE)
    else:
        await state.update_data(mode_value=val)
        data = await state.get_data()
        if data.get('is_editing'):
            await show_edit_params(callback, state, bot)
        else:
            await safe_edit_text(callback,
                texts["enter_winners_count"],
                reply_markup=await get_winners_keyboard(texts),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(GiveawayCreation.SELECT_WINNERS_COUNT)

@router.message(GiveawayCreation.CUSTOM_MODE_VALUE)
async def enter_custom_mode_value(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    texts = await get_locale(user_id)
    try: await message.delete()
    except: pass

    await state.update_data(mode_value=message.text)
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            texts["enter_winners_count"],
            reply_markup=await get_winners_keyboard(texts),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.SELECT_WINNERS_COUNT)

@router.callback_query(F.data.startswith("win_"), GiveawayCreation.SELECT_WINNERS_COUNT)
async def select_winners_count(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    await callback.answer()
    val = callback.data.split("_")[1]
    if val == "custom":
        await safe_edit_text(callback, texts["enter_winners_count"], parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.CUSTOM_WINNERS_COUNT)
    else:
        await state.update_data(winners_count=int(val))
        data = await state.get_data()
        if data.get('is_editing'):
            await show_edit_params(callback, state, bot)
        else:
            await safe_edit_text(callback,
                texts["enter_prizes"],
                reply_markup=await get_prizes_keyboard([], texts),
                parse_mode=ParseMode.HTML
            )
            await state.set_state(GiveawayCreation.ENTER_PRIZES)

@router.message(GiveawayCreation.CUSTOM_WINNERS_COUNT)
async def enter_custom_winners_count(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    texts = await get_locale(user_id)
    try: await message.delete()
    except: pass

    if not message.text.isdigit():
        await message.answer(texts["enter_number_error"])
        return

    await state.update_data(winners_count=int(message.text))
    data = await state.get_data()
    last_msg_id = data.get('last_msg_id')

    if data.get('is_editing'):
        await show_edit_params(message, state, bot)
    else:
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id,
            texts["enter_prizes"],
            reply_markup=await get_prizes_keyboard([], texts),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(GiveawayCreation.ENTER_PRIZES)

@router.message(GiveawayCreation.ENTER_PRIZES, F.text)
async def process_prizes(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    texts = await get_locale(user_id)
    try: await message.delete()
    except: pass

    data = await state.get_data()
    prizes = data.get('prizes', [])
    new_prizes = [p.strip() for p in message.text.split('\n') if p.strip()]
    prizes.extend(new_prizes)

    await state.update_data(prizes=prizes)
    last_msg_id = data.get('last_msg_id')

    prizes_list = "\n".join([f"• {p}" for p in prizes])
    text = texts["enter_prizes"] + f"\n\n<b>{texts['current_prizes']}:</b>\n{prizes_list}"

    await safe_bot_edit_text(bot, message.chat.id, last_msg_id, text, reply_markup=await get_prizes_keyboard(prizes, texts), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "confirm_prizes")
async def confirm_prizes(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await show_edit_params(callback, state, bot)

async def show_edit_params(event, state: FSMContext, bot: Bot):
    user_id = event.from_user.id if isinstance(event, types.CallbackQuery) else event.chat.id
    texts = await get_locale(user_id)
    data = await state.get_data()

    preview_text = await generate_preview(data, texts)

    try:
        text = texts["preview_title"].format(preview=preview_text)
    except Exception as e:
        logger.error(f"preview_title = {texts.get('preview_title')}")
        raise

    kb = await get_edit_params_keyboard(texts)

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(
            event,
            text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML
        )
    else:
        await safe_bot_edit_text(
            bot,
            event.chat.id,
            data['last_msg_id'],
            text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML
        )

    await state.set_state(GiveawayCreation.CONFIRMATION)

async def generate_preview(data, texts):
    kind_label = texts["fast_btn"] if data['kind'] == "fast" else texts["partner_btn"]
    type_label = texts["timed_btn"] if data['gtype'] == "timed" else texts["limited_btn"]

    preview = f"<b>{texts['title_label']}:</b> {html.escape(data['title'])}\n"
    preview += f"<b>{texts['kind_label']}:</b> {kind_label}\n"
    if data.get('mandatory_channels'):
        preview += f"<b>{texts['channels_label']}:</b> {', '.join(data['mandatory_channels'])}\n"
    preview += f"<b>{texts['type_label']}:</b> {type_label}\n"
    preview += f"<b>{texts['value_label']}:</b> {data['mode_value']}\n"
    preview += f"<b>{texts['winners_label']}:</b> {data['winners_count']}\n"
    preview += f"<b>{texts['prizes_label']}:</b> {', '.join(data['prizes'])}\n"
    preview += f"<b>{texts['access_label']}:</b> {texts['access_all_btn'] if not data.get('allowed_users') else texts['access_whitelist_btn']}"

    return preview

@router.callback_query(F.data == "confirm_giveaway", GiveawayCreation.CONFIRMATION)
async def finalize_giveaway(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    data = await state.get_data()

    giveaway_id = await db.create_giveaway({
        "creator_id": user_id,
        "chat_id": data['chat_id'],
        "title": data['title'],
        "kind": data['kind'],
        "mandatory_channels": data.get('mandatory_channels'),
        "gtype": data['gtype'],
        "value": data['mode_value'],
        "winners_count": data['winners_count'],
        "prizes": data['prizes'],
        "allowed_users": data.get('allowed_users'),
        "status": "active"
    })

    await callback.answer(texts["giveaway_launched_alert"])

    # Send to group - strictly English
    en_texts = get_locale_by_lang("en")
    post_text, gif_to_send = await get_giveaway_post_data(await db.get_giveaway(giveaway_id), en_texts)

    kb = InlineKeyboardBuilder()
    kb.button(text=en_texts["join_btn"], callback_data=f"join_{giveaway_id}", icon_custom_emoji_id="5260726538302660868", style="success")

    try:
        try:
            msg = await bot.send_animation(chat_id=data['chat_id'], animation=gif_to_send, caption=post_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        except:
            msg = await bot.send_message(chat_id=data['chat_id'], text=post_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)

        await db.add_giveaway_message(giveaway_id, data['chat_id'], msg.message_id)
    except Exception as e:
        logger.error(f"Error sending giveaway to group: {e}")

    # Success message
    success_builder = InlineKeyboardBuilder()
    success_builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    await safe_edit_text(callback, texts["giveaway_launched_success"], reply_markup=success_builder.as_markup(), parse_mode=ParseMode.HTML)
    await state.clear()

async def get_giveaway_post_data(giveaway, texts=None):
    if not texts:
        # Defaults to English for chat publication as requested
        texts = get_locale_by_lang("en")

    title = html.escape(giveaway['title'])
    prizes = ", ".join([html.escape(p) for p in giveaway['prizes']])
    winners = giveaway['winners_count']

    if giveaway['gtype'] == 'timed':
        cond = f"{texts['ends_at']} {giveaway['value']}"
    else:
        cond = f"{texts['ends_when']} {giveaway['value']} {texts['participants_suffix']}"

    channels_text = ""
    if giveaway.get('mandatory_channels'):
        channels_text = f"\n┋ {texts['subscribe_to']}: " + ", ".join(giveaway['mandatory_channels'])

    post_text = (
        f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅ <b>/ {title} /</b>\n"
        f"┋\n"
        f"┣ <b>{texts['prizes']}:</b> {prizes}\n"
        f"┣ <b>{texts['winners']}:</b> {winners}\n"
        f"┣ <b>{texts['condition']}:</b> {cond}"
        f"{channels_text}\n"
        f"┋\n"
        f"┗┅┅┅/ #NOTAPES /"
    )

    gif_id = await db.get_setting("main_gif")
    return post_text, gif_id

async def is_bot_admin(chat_id: int | str, bot: Bot) -> bool:
    try:
        if isinstance(chat_id, str) and not chat_id.startswith("-"):
            # It's a username
            chat = await bot.get_chat(chat_id)
            target_id = chat.id
        else:
            target_id = chat_id

        member = await bot.get_chat_member(target_id, bot.id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

@router.callback_query(F.data.startswith("make_announcement_"))
async def make_announcement_select_chat(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    await callback.answer()
    giveaway_id = int(callback.data.split("_")[-1])

    chats = await db.get_tracked_groups()
    builder = InlineKeyboardBuilder()

    count = 0
    for chat in chats:
        if await is_bot_admin(chat['chat_id'], bot):
            builder.button(text=chat['title'], callback_data=f"ann_to_{giveaway_id}_{chat['chat_id']}")
            count += 1

    builder.button(text=texts["main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    text = texts["select_announcement_chat"] if count > 0 else texts["no_chats_available"]

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("ann_to_"))
async def execute_announcement(callback: types.CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    await callback.answer()
    parts = callback.data.split("_")
    giveaway_id = int(parts[2])
    target_chat_id = int(parts[3])

    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway:
        await callback.message.answer(texts["giveaway_removed"], parse_mode=ParseMode.HTML)
        return

    target_chat = await bot.get_chat(target_chat_id)
    is_channel = target_chat.type == ChatType.CHANNEL

    # Public announcements in English
    en_texts = get_locale_by_lang("en")
    post_text, gif_to_send = await get_giveaway_post_data(giveaway, en_texts)

    if is_channel:
        post_text = strip_custom_emojis(post_text)

    join_builder = InlineKeyboardBuilder()

    if target_chat_id != giveaway['chat_id']:
        orig_chat = await bot.get_chat(giveaway['chat_id'])
        msgs = await db.get_giveaway_messages(giveaway_id)
        orig_msg_id = next((m['message_id'] for m in msgs if m['chat_id'] == giveaway['chat_id']), None)

        if orig_msg_id:
            link = get_message_link(orig_chat, orig_msg_id)
            join_builder.button(text=en_texts["join_btn"], url=link)
        else:
            join_builder.button(text=en_texts["start_btn"], callback_data=f"join_{giveaway_id}", icon_custom_emoji_id="5260726538302660868", style="success")
    else:
        join_builder.button(text=en_texts["start_btn"], callback_data=f"join_{giveaway_id}", icon_custom_emoji_id="5260726538302660868", style="success")

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
        await callback.message.answer(texts["success_msg"], parse_mode=ParseMode.HTML)
    except Exception as e:
        await callback.message.answer(f"{texts['error_msg']}: {e}", parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "back")
async def process_back(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    await callback.answer()
    current_state = await state.get_state()
    data = await state.get_data()

    if current_state == GiveawayCreation.SELECT_CHAT:
         from handlers.main_menu import back_to_main_menu
         await back_to_main_menu(callback, state)
    elif current_state == GiveawayCreation.ENTER_NAME:
        from handlers.main_menu import create_giveaway_handler
        await create_giveaway_handler(callback, state)
    elif current_state == GiveawayCreation.SELECT_GIVEAWAY_KIND:
        await safe_edit_text(callback, texts["enter_title"], reply_markup=await get_nav_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.ENTER_NAME)
    elif current_state == GiveawayCreation.ENTER_CHANNELS:
        await safe_edit_text(callback, texts["giveaway_title"], reply_markup=await get_giveaway_kind_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.SELECT_GIVEAWAY_KIND)
    elif current_state == GiveawayCreation.WAITING_FOR_BOT_ADMIN:
        await safe_edit_text(callback, texts["enter_channels"], reply_markup=await get_nav_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.ENTER_CHANNELS)
    elif current_state == GiveawayCreation.WAITING_FOR_ACCESS_TYPE:
        if data.get('kind') == 'partner':
             await safe_edit_text(callback, texts["enter_channels"], reply_markup=await get_nav_keyboard(texts), parse_mode=ParseMode.HTML)
             await state.set_state(GiveawayCreation.ENTER_CHANNELS)
        else:
             await safe_edit_text(callback, texts["giveaway_title"], reply_markup=await get_giveaway_kind_keyboard(texts), parse_mode=ParseMode.HTML)
             await state.set_state(GiveawayCreation.SELECT_GIVEAWAY_KIND)
    elif current_state in [GiveawayCreation.WAITING_FOR_WHITELIST, GiveawayCreation.SELECT_TYPE]:
        await ask_access_type(callback.message, state, bot)
    elif current_state in [GiveawayCreation.SELECT_MODE_VALUE, GiveawayCreation.CUSTOM_MODE_VALUE]:
        await safe_edit_text(callback, texts["select_type"], reply_markup=await get_type_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.SELECT_TYPE)
    elif current_state in [GiveawayCreation.SELECT_WINNERS_COUNT, GiveawayCreation.CUSTOM_WINNERS_COUNT]:
        gtype = data.get("gtype")
        await safe_edit_text(callback, texts["enter_time"] if gtype == "timed" else texts["enter_participants"], reply_markup=await get_mode_keyboard(gtype, texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.SELECT_MODE_VALUE)
    elif current_state == GiveawayCreation.ENTER_PRIZES:
        await safe_edit_text(callback, texts["enter_winners_count"], reply_markup=await get_winners_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.SELECT_WINNERS_COUNT)
    elif current_state in [GiveawayCreation.CONFIRMATION, GiveawayCreation.EDIT_PARAMS]:
        await safe_edit_text(callback, texts["enter_prizes"], reply_markup=await get_prizes_keyboard(data.get('prizes', []), texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.ENTER_PRIZES)
    else:
        from handlers.main_menu import back_to_main_menu
        await back_to_main_menu(callback, state)

@router.callback_query(GiveawayCreation.CONFIRMATION, F.data.startswith("edit_"))
async def edit_param_handler(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    param = callback.data.replace("edit_", "")
    await state.update_data(is_editing=True)

    if param == "title":
        await safe_edit_text(callback, texts["enter_title"], reply_markup=await get_nav_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.ENTER_NAME)
    elif param == "channels":
        await safe_edit_text(callback, texts["enter_channels"], reply_markup=await get_nav_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.ENTER_CHANNELS)
    elif param == "type":
        await safe_edit_text(callback, texts["select_type"], reply_markup=await get_type_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.SELECT_TYPE)
    elif param == "mode":
        gtype = (await state.get_data()).get('gtype')
        await safe_edit_text(callback, texts["enter_time"] if gtype == "timed" else texts["enter_participants"], reply_markup=await get_mode_keyboard(gtype, texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.SELECT_MODE_VALUE)
    elif param == "winners":
        await safe_edit_text(callback, texts["enter_winners_count"], reply_markup=await get_winners_keyboard(texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.SELECT_WINNERS_COUNT)
    elif param == "prizes":
        await state.update_data(prizes=[]) # Reset prizes to enter again
        await safe_edit_text(callback, texts["enter_prizes"], reply_markup=await get_prizes_keyboard([], texts), parse_mode=ParseMode.HTML)
        await state.set_state(GiveawayCreation.ENTER_PRIZES)
