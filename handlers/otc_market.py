import os
import html
import re
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode, ChatType
from database import db
from utils import safe_bot_edit_text, safe_answer, safe_edit_text, strip_custom_emojis, is_holder
import logging

logger = logging.getLogger(__name__)

router = Router()

class OTCMarket(StatesGroup):
    SELECT_TYPE = State()
    ENTER_ITEM = State()
    ENTER_PRICE = State()
    ENTER_NAME_ONLY = State()
    PREVIEW = State()

@router.callback_query(F.data == "otc_market")
async def start_otc_market(callback: types.CallbackQuery, state: FSMContext):
    if not await is_holder(callback.from_user.id):
        await callback.answer("❌ OTC not available", show_alert=True)
        return
    await callback.answer()
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.button(text="WTS", callback_data="otc_type_WTS")
    builder.button(text="WTB", callback_data="otc_type_WTB")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 1)

    text = (
        "<tg-emoji emoji-id=\"5258204546391351475\">💰</tg-emoji> <b>OTC Market</b>\n\n"
        "<blockquote>Select the type of trade:</blockquote>"
    )

    msg = await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(OTCMarket.SELECT_TYPE)

@router.callback_query(F.data == "otc_back_to_type")
async def otc_back_to_type(callback: types.CallbackQuery, state: FSMContext):
    await start_otc_market(callback, state)

@router.callback_query(OTCMarket.SELECT_TYPE, F.data.startswith("otc_type_"))
async def select_trade_type(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    trade_type = callback.data.split("_")[-1]
    await state.update_data(trade_type=trade_type)

    builder = InlineKeyboardBuilder()
    builder.button(text="No-link", callback_data="otc_no_link", icon_custom_emoji_id="5258362429389152256")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1)

    text = (
        "<tg-emoji emoji-id=\"5257965174979042426\">📝</tg-emoji> <b>Item Details</b>\n\n"
        "<blockquote>Please send the name of the item and a link to it.\n\n"
        "Example: Rare NFT https://t.me/nft_link</blockquote>"
    )

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(OTCMarket.ENTER_ITEM)

@router.callback_query(F.data == "otc_no_link")
async def otc_no_link_selected(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    builder = InlineKeyboardBuilder()
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")

    text = (
        "<tg-emoji emoji-id=\"5257965174979042426\">📝</tg-emoji> <b>Item Name</b>\n\n"
        "<blockquote>Please send only the name of the item.</blockquote>"
    )
    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(OTCMarket.ENTER_NAME_ONLY)

@router.message(OTCMarket.ENTER_NAME_ONLY, F.text)
async def enter_name_only(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get("last_msg_id")

    try:
        await message.delete()
    except Exception:
        pass

    item_name = message.text.strip()
    await state.update_data(item_name=item_name, url=None)

    if data.get("price_text") or data.get("is_offer"):
        await show_otc_preview(message, state, bot)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="Skip (Offer)", callback_data="otc_price_skip", icon_custom_emoji_id="5260687681733533075")
    builder.button(text="Back", callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 1, 1)

    price_text = (
        "<tg-emoji emoji-id=\"5258204546391351475\">💰</tg-emoji> <b>Price</b>\n\n"
        "<blockquote>Enter the price in TON or click the \"Skip (Offer)\" button.</blockquote>"
    )

    await safe_bot_edit_text(bot, message.chat.id, last_msg_id, price_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(OTCMarket.ENTER_PRICE)

@router.message(OTCMarket.ENTER_ITEM, F.text)
async def enter_item_details(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get("last_msg_id")

    try:
        await message.delete()
    except Exception:
        pass

    text = message.text
    url_match = re.search(r"(https?://\S+|t\.me/\S+)", text)
    if not url_match:
        builder = InlineKeyboardBuilder()
        builder.button(text="No-link", callback_data="otc_no_link", icon_custom_emoji_id="5258362429389152256")
        builder.button(text="Back", callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
        builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
        builder.adjust(1, 1, 1)

        warning_text = (
            "<tg-emoji emoji-id=\"5273876254989246882\">🤬</tg-emoji> <b>Invalid Input</b>\n\n"
            "<blockquote>Please include a valid URL (http:// or https://) in your message or click <b>No-link</b>.</blockquote>"
        )
        await safe_bot_edit_text(bot, message.chat.id, last_msg_id, warning_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
        return

    url = url_match.group(0)
    if url.startswith("t.me/"):
        url = "https://" + url
    item_name = text.replace(url_match.group(0), "").strip()

    if not item_name:
        item_name = "Item"

    await state.update_data(item_name=item_name, url=url)

    if data.get("price_text") or data.get("is_offer"):
        await show_otc_preview(message, state, bot)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="Skip (Offer)", callback_data="otc_price_skip", icon_custom_emoji_id="5260687681733533075")
    builder.button(text="Back", callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 1, 1)

    price_text = (
        "<tg-emoji emoji-id=\"5258204546391351475\">💰</tg-emoji> <b>Price</b>\n\n"
        "<blockquote>Enter the price in TON or click the \"Skip (Offer)\" button.</blockquote>"
    )

    await safe_bot_edit_text(bot, message.chat.id, last_msg_id, price_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(OTCMarket.ENTER_PRICE)

@router.callback_query(OTCMarket.ENTER_PRICE, F.data == "otc_price_skip")
async def otc_price_skipped(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await state.update_data(price_text=None, is_offer=True)
    await show_otc_preview(callback, state, bot)

@router.message(OTCMarket.ENTER_PRICE, F.text)
async def enter_price(message: types.Message, state: FSMContext, bot: Bot):
    try:
        await message.delete()
    except Exception:
        pass

    text = message.text.strip()
    if text.replace(".", "", 1).isdigit():
        price = f"{text} TON"
    else:
        price = text

    await state.update_data(price_text=price, is_offer=False)
    await show_otc_preview(message, state, bot)

async def finalize_otc_publication(event, state: FSMContext, bot: Bot):
    data = await state.get_data()
    trade_type = data.get("trade_type")
    item_name = html.escape(data.get("item_name"))
    url = data.get("url")
    last_msg_id = data.get("last_msg_id")
    user_id = event.from_user.id

    price_text = data.get("price_text")
    is_offer = data.get("is_offer")
    display_price = "Offer" if is_offer else price_text

    item_display = f"<a href=\"{url}\">{item_name}</a>" if url else f"<b>{item_name}</b>"

    # Новый формат сообщения
    if is_offer:
        post_text = (
            f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅/ {html.escape(str(trade_type))} /\n"
            "┋\n"
            f"┣ <b>Item:</b> {item_display}\n"
            "┋\n"
            "┣ <b>Offer</b>\n"
            "┋\n"
            "┗┅ / #NOTAPES /"
        )
    else:
        post_text = (
            f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅/ {html.escape(str(trade_type))} /\n"
            "┋\n"
            f"┣ <b>Item:</b> {item_display}\n"
            "┋\n"
            f"┣ <b>Price:</b> {html.escape(str(display_price))}\n"
            "┋\n"
            "┗┅ / #NOTAPES /"
        )

    otc_chat_id = os.environ.get("OTC_CHAT_ID")
    otc_topic_id = os.environ.get("OTC_TOPIC_ID")

    if not otc_chat_id:
        msg_text = "❌ OTC_CHAT_ID is not set in environment variables."
        if isinstance(event, types.CallbackQuery):
            await event.message.answer(msg_text)
        else:
            await event.answer(msg_text)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="Contact", url=f"tg://user?id={user_id}", icon_custom_emoji_id="5260535596941582167")



    try:
        target_chat = await bot.get_chat(otc_chat_id)
        if target_chat.type == ChatType.CHANNEL:
            post_text = strip_custom_emojis(post_text)
    except Exception as e:
        logger.warning(f"Could not get chat info for {otc_chat_id}: {e}")

    # 1. Подготавливаем базовые параметры, которые общие для всех типов сообщений
    send_kwargs = {
        "chat_id": otc_chat_id,
        "reply_markup": builder.as_markup(),
        "parse_mode": ParseMode.HTML
    }

    # Если указана конкретная тема (Topic), добавляем её ID
    if otc_topic_id:
        send_kwargs["message_thread_id"] = int(otc_topic_id)

    try:
        await bot.send_message(text=post_text, **send_kwargs)
        # Промежуточное сообщение вместо резкого перехода в меню
        success_builder = InlineKeyboardBuilder()
        success_builder.button(text="Back to Menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531")

        success_text = "✅ <b>Post published successfully!</b>\n\n<blockquote>Your order has been sent to the OTC channel.</blockquote>"

        if isinstance(event, types.CallbackQuery):
            await safe_edit_text(event.message, success_text, reply_markup=success_builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
        else:
            await safe_bot_edit_text(bot, event.chat.id, last_msg_id, success_text, reply_markup=success_builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

    except Exception as e:
        logger.error(f"OTC Publication error: {e}")
        error_text = f"❌ Error sending to channel: {e}"
        if isinstance(event, types.CallbackQuery):
            await event.message.answer(error_text)
        else:
            await event.answer(error_text)

    await state.clear()

async def show_otc_preview(event, state: FSMContext, bot: Bot):
    data = await state.get_data()
    trade_type = data.get("trade_type")
    item_name = html.escape(data.get("item_name"))
    url = data.get("url")
    price_text = data.get("price_text")
    is_offer = data.get("is_offer")
    last_msg_id = data.get("last_msg_id")

    display_price = "Offer" if is_offer else price_text
    item_display = f"<a href=\"{url}\">{item_name}</a>" if url else f"<b>{item_name}</b>"

    if is_offer:
        post_text = (
            f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅/ {html.escape(str(trade_type))} /\n"
            "┋\n"
            f"┣ <b>Item:</b> {item_display}\n"
            "┋\n"
            "┣ <b>Offer</b>\n"
            "┋\n"
            "┗┅ / #NOTAPES /"
        )
    else:
        post_text = (
            f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅/ {html.escape(str(trade_type))} /\n"
            "┋\n"
            f"┣ <b>Item:</b> {item_display}\n"
            "┋\n"
            f"┣ <b>Price:</b> {html.escape(str(display_price))}\n"
            "┋\n"
            "┗┅ / #NOTAPES /"
        )

    preview_text = (
        "<b><tg-emoji emoji-id=\"5258254475386167466\">🖼️</tg-emoji> Preview</b>\n\n"
        f"<blockquote>{post_text}</blockquote>\n\n"
        "<b>Confirm or edit your post:</b>"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="Edit Item", callback_data="otc_edit_item", icon_custom_emoji_id="5257965174979042426")
    builder.button(text="Edit Price", callback_data="otc_edit_price", icon_custom_emoji_id="5258204546391351475")
    builder.button(text="Confirm & Post", callback_data="otc_confirm_post", icon_custom_emoji_id="5260416304224936047", style="success")
    builder.button(text="Cancel", callback_data="main_menu", icon_custom_emoji_id="5260342697075416641", style="danger")
    builder.adjust(2, 1, 1)

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event.message, preview_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    else:
        await safe_bot_edit_text(bot, event.chat.id, last_msg_id, preview_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

    await state.set_state(OTCMarket.PREVIEW)


@router.callback_query(OTCMarket.PREVIEW, F.data == "otc_edit_item")
async def otc_edit_item(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    url = data.get("url")

    if url:
        builder = InlineKeyboardBuilder()
        builder.button(text="No-link", callback_data="otc_no_link", icon_custom_emoji_id="5258362429389152256")
        builder.button(text="Back", callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
        builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
        builder.adjust(1, 1, 1)

        text = (
            "<tg-emoji emoji-id=\"5257965174979042426\">📝</tg-emoji> <b>Item Details</b>\n\n"
            "<blockquote>Please send the name of the item and a link to it.\n\n"
            "Example: Rare NFT https://t.me/nft_link</blockquote>"
        )
        await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(OTCMarket.ENTER_ITEM)
    else:
        builder = InlineKeyboardBuilder()
        builder.button(text="Back", callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
        builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
        builder.adjust(1, 1)

        text = (
            "<tg-emoji emoji-id=\"5257965174979042426\">📝</tg-emoji> <b>Item Name</b>\n\n"
            "<blockquote>Please send only the name of the item.</blockquote>"
        )
        await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
        await state.set_state(OTCMarket.ENTER_NAME_ONLY)


@router.callback_query(OTCMarket.PREVIEW, F.data == "otc_edit_price")
async def otc_edit_price(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()

    builder = InlineKeyboardBuilder()
    builder.button(text="Skip (Offer)", callback_data="otc_price_skip", icon_custom_emoji_id="5260687681733533075")
    builder.button(text="Back", callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
    builder.button(text="Main menu", callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 1, 1)

    price_text = (
        "<tg-emoji emoji-id=\"5258204546391351475\">💰</tg-emoji> <b>Price</b>\n\n"
        "<blockquote>Enter the price in TON or click the \"Skip (Offer)\" button.</blockquote>"
    )

    await safe_edit_text(callback, price_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)
    await state.set_state(OTCMarket.ENTER_PRICE)


@router.callback_query(OTCMarket.PREVIEW, F.data == "otc_confirm_post")
async def otc_confirm_post(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    await finalize_otc_publication(callback, state, bot)
