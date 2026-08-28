import os
import html
import re
from decimal import Decimal, InvalidOperation
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode, ChatType
from database import db
from utils import safe_bot_edit_text, safe_edit_text, strip_custom_emojis, is_holder
import logging
from services.localization import get_locale_by_lang
from services.offer_cooldown import OfferCooldown
from utils import bot_deep_link

logger = logging.getLogger(__name__)

router = Router()

class OTCMarket(StatesGroup):
    SELECT_TYPE = State()
    ENTER_ITEM = State()
    ENTER_PRICE = State()
    ENTER_NAME_ONLY = State()
    PREVIEW = State()
    OFFER_AMOUNT = State()

@router.callback_query(F.data == "otc_market")
async def start_otc_market(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    user_id = callback.from_user.id

    # Parallelize check with something or just use the is_holder result if it was passed?
    # In this case, we just keep it simple but ensure we use gather if possible.
    # Actually, the task said: "Dont call holder-check twice inside one menu opening"

    if not await is_holder(user_id):
        await callback.answer(texts["otc_not_available"], show_alert=True)
        return
    await callback.answer()
    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["otc_wts_btn"], callback_data="otc_type_WTS")
    builder.button(text=texts["otc_wtb_btn"], callback_data="otc_type_WTB")
    builder.button(text=texts["otc_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 1)

    text = texts["otc_title"]

    msg = await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(OTCMarket.SELECT_TYPE)

@router.callback_query(F.data == "otc_back_to_type")
async def otc_back_to_type(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await start_otc_market(callback, state, texts)

@router.callback_query(OTCMarket.SELECT_TYPE, F.data.startswith("otc_type_"))
async def select_trade_type(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    # texts from middleware
    trade_type = callback.data.split("_")[-1]
    await state.update_data(trade_type=trade_type)

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["otc_no_link_btn"], callback_data="otc_no_link", icon_custom_emoji_id="5258362429389152256")
    builder.button(text=texts["otc_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 1)

    text = texts["otc_item_details_title"]

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    await state.set_state(OTCMarket.ENTER_ITEM)

@router.callback_query(F.data == "otc_no_link")
async def otc_no_link_selected(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    # texts from middleware

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["otc_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")

    text = texts["otc_item_name_title"]
    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    await state.set_state(OTCMarket.ENTER_NAME_ONLY)

@router.message(OTCMarket.ENTER_NAME_ONLY, F.text)
async def enter_name_only(message: types.Message, state: FSMContext, bot: Bot, texts: dict):
    data = await state.get_data()
    last_msg_id = data.get("last_msg_id")

    try:
        await message.delete()
    except Exception:
        pass

    item_name = message.text.strip()
    await state.update_data(item_name=item_name, url=None)
    await show_price_input(bot, message.chat.id, last_msg_id, state, texts)

@router.message(OTCMarket.ENTER_ITEM, F.text)
async def enter_item_details(message: types.Message, state: FSMContext, bot: Bot, texts: dict):
    data = await state.get_data()
    last_msg_id = data.get("last_msg_id")

    try:
        await message.delete()
    except Exception:
        pass

    text = message.text.strip()
    url_match = re.search(r'(https?://\S+)', text)

    if url_match:
        url = url_match.group(1)
        item_name = text.replace(url, "").strip()
        if not item_name:
            item_name = "Item"
    else:
        item_name = text
        url = None

    await state.update_data(item_name=item_name, url=url)
    await show_price_input(bot, message.chat.id, last_msg_id, state, texts)

async def show_price_input(bot: Bot, chat_id: int, last_msg_id: int, state: FSMContext, texts: dict):
    # texts from middleware
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["otc_skip_offer_btn"], callback_data="otc_price_skip", icon_custom_emoji_id="5260687681733533075")
    builder.button(text=texts["otc_back_btn"], callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["otc_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 2)

    price_text = texts["otc_price_title"]

    await safe_bot_edit_text(bot, chat_id, last_msg_id, price_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    await state.set_state(OTCMarket.ENTER_PRICE)

@router.callback_query(OTCMarket.ENTER_PRICE, F.data == "otc_price_skip")
async def otc_price_skipped(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    await state.update_data(price_text=None, is_offer=True)
    await show_otc_preview(callback, state, bot, texts)

@router.message(OTCMarket.ENTER_PRICE, F.text)
async def enter_price(message: types.Message, state: FSMContext, bot: Bot, texts: dict):
    try:
        await message.delete()
    except Exception:
        pass

    text = message.text.strip()
    if text.replace(".", "", 1).isdigit():
        price = f"{text} GRAM"
    else:
        price = text

    await state.update_data(price_text=price, is_offer=False)
    await show_otc_preview(message, state, bot, texts)

async def finalize_otc_publication(event, state: FSMContext, bot: Bot, texts: dict):
    user_id = event.from_user.id
    # texts from middleware
    en_texts = get_locale_by_lang("en") # Public messages strictly in English
    data = await state.get_data()
    trade_type = data.get("trade_type")
    item_name = html.escape(data.get("item_name"))
    url = data.get("url")
    last_msg_id = data.get("last_msg_id")

    price_text = data.get("price_text")
    is_offer = data.get("is_offer")
    display_price = en_texts["otc_offer"] if is_offer else price_text

    item_display = f"<a href=\"{url}\">{item_name}</a>" if url else f"<b>{item_name}</b>"

    if is_offer:
        post_text = (
            f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅/ {html.escape(str(trade_type))} /\n"
            "┋\n"
            f"┣ <b>{en_texts['otc_item']}:</b> {item_display}\n"
            "┋\n"
            f"┣ <b>{en_texts['otc_offer']}</b>\n"
            "┋\n"
            "┗┅ / #NOTAPES /"
        )
    else:
        post_text = (
            f"┏<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅/ {html.escape(str(trade_type))} /\n"
            "┋\n"
            f"┣ <b>{en_texts['otc_item']}:</b> {item_display}\n"
            "┋\n"
            f"┣ <b>{en_texts['otc_price']}:</b> {html.escape(str(display_price))}\n"
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

    await db.ensure_user_exists(user_id)
    listing = await db.create_otc_listing({
        "seller_id": user_id, "trade_type": trade_type,
        "item_name": data.get("item_name"), "item_url": url,
        "price_text": price_text, "status": "draft",
    })
    if not listing:
        await event.answer(texts["otc_publish_error"])
        return
    builder = InlineKeyboardBuilder()
    builder.button(text=en_texts["otc_make_offer_btn"], url=await bot_deep_link(f"offer_{listing['id']}"),
                   icon_custom_emoji_id="5260687681733533075", style="success")
    builder.button(text=en_texts["otc_profile_btn"], url=f"tg://user?id={user_id}",
                   icon_custom_emoji_id="5260535596941582167")
    builder.adjust(2)

    try:
        target_chat = await bot.get_chat(otc_chat_id)
        if target_chat.type == ChatType.CHANNEL:
            post_text = strip_custom_emojis(post_text)
    except Exception as e:
        logger.warning(f"Could not get chat info for {otc_chat_id}: {e}")

    send_kwargs = {
        "chat_id": otc_chat_id,
        "reply_markup": builder.as_markup(),
        "parse_mode": ParseMode.HTML
    }

    if otc_topic_id:
        send_kwargs["message_thread_id"] = int(otc_topic_id)

    try:
        sent = await bot.send_message(text=post_text, **send_kwargs)
        await db.update_otc_listing(listing["id"], {
            "chat_id": sent.chat.id, "message_id": sent.message_id, "status": "active",
        })
        success_builder = InlineKeyboardBuilder()
        success_builder.button(text=texts["otc_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531")

        success_text = texts["otc_post_success"]

        if isinstance(event, types.CallbackQuery):
            await safe_edit_text(event.message, success_text, reply_markup=success_builder.as_markup(), parse_mode=ParseMode.HTML)
        else:
            await safe_bot_edit_text(bot, event.chat.id, last_msg_id, success_text, reply_markup=success_builder.as_markup(), parse_mode=ParseMode.HTML)

    except Exception as e:
        await db.update_otc_listing(listing["id"], {"status": "deleted"})
        logger.error(f"OTC Publication error: {e}")
        error_text = f"❌ Error sending to channel: {e}"
        if isinstance(event, types.CallbackQuery):
            await event.message.answer(error_text)
        else:
            await event.answer(error_text)

    await state.clear()

async def show_otc_preview(event, state: FSMContext, bot: Bot, texts: dict):
    # texts from middleware
    en_texts = get_locale_by_lang("en") # Previews of public posts use English terms for the post part
    data = await state.get_data()
    trade_type = data.get("trade_type")
    item_name = html.escape(data.get("item_name"))
    url = data.get("url")
    price_text = data.get("price_text")
    is_offer = data.get("is_offer")
    last_msg_id = data.get("last_msg_id")

    display_price = en_texts["otc_offer"] if is_offer else price_text
    item_display = f"<a href=\"{url}\">{item_name}</a>" if url else f"<b>{item_name}</b>"

    if is_offer:
        post_text = (
            f"<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅/ {html.escape(str(trade_type))} /\n"
            "┋\n"
            f"┣ <b>{en_texts['otc_item']}:</b> {item_display}\n"
            "┋\n"
            f"┣ <b>{en_texts['otc_offer']}</b>\n"
            "┋\n"
            "┣┅ / #NOTAPES /"
        )
    else:
        post_text = (
            f"<tg-emoji emoji-id=\"5273867703709361006\">👿</tg-emoji>┅/ {html.escape(str(trade_type))} /\n"
            "┋\n"
            f"┣ <b>{en_texts['otc_item']}:</b> {item_display}\n"
            "┋\n"
            f"┣ <b>{en_texts['otc_price']}:</b> {html.escape(str(display_price))}\n"
            "┋\n"
            "┣┅ / #NOTAPES /"
        )

    preview_text = texts["otc_preview_title"].format(
        post_text=post_text,
        preview=post_text
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["otc_edit_item_btn"], callback_data="otc_edit_item", icon_custom_emoji_id="5257965174979042426")
    builder.button(text=texts["otc_edit_price_btn"], callback_data="otc_edit_price", icon_custom_emoji_id="5258204546391351475")
    builder.button(text=texts["otc_confirm_post_btn"], callback_data="otc_confirm_post", icon_custom_emoji_id="5260416304224936047", style="success")
    builder.button(text=texts["otc_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 1, 1)

    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event.message, preview_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    else:
        await safe_bot_edit_text(bot, event.chat.id, last_msg_id, preview_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

    await state.set_state(OTCMarket.PREVIEW)


@router.callback_query(OTCMarket.PREVIEW, F.data == "otc_edit_item")
async def otc_edit_item(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    # texts from middleware
    data = await state.get_data()
    url = data.get("url")

    if url:
        builder = InlineKeyboardBuilder()
        builder.button(text=texts["otc_no_link_btn"], callback_data="otc_no_link", icon_custom_emoji_id="5258362429389152256")
        builder.button(text=texts["otc_back_btn"], callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
        builder.button(text=texts["otc_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
        builder.adjust(1, 2)

        text = texts["otc_item_details_title"]
        await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        await state.set_state(OTCMarket.ENTER_ITEM)
    else:
        builder = InlineKeyboardBuilder()
        builder.button(text=texts["otc_back_btn"], callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
        builder.button(text=texts["otc_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
        builder.adjust(2)

        text = texts["otc_item_name_title"]
        await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
        await state.set_state(OTCMarket.ENTER_NAME_ONLY)


@router.callback_query(OTCMarket.PREVIEW, F.data == "otc_edit_price")
async def otc_edit_price(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    # texts from middleware

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["otc_skip_offer_btn"], callback_data="otc_price_skip", icon_custom_emoji_id="5260687681733533075")
    builder.button(text=texts["otc_back_btn"], callback_data="otc_back_to_type", icon_custom_emoji_id="5260687119092817530")
    builder.button(text=texts["otc_main_menu_btn"], callback_data="main_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(1, 2)

    price_text = texts["otc_price_title"]

    await safe_edit_text(callback, price_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    await state.set_state(OTCMarket.ENTER_PRICE)


@router.callback_query(OTCMarket.PREVIEW, F.data == "otc_confirm_post")
async def otc_confirm_post(callback: types.CallbackQuery, state: FSMContext, bot: Bot, texts: dict):
    await callback.answer()
    await finalize_otc_publication(callback, state, bot, texts)


async def start_offer_from_link(event: types.Message | types.CallbackQuery, listing_id: int,
                                state: FSMContext, texts: dict):
    blocked = {int(x) for x in os.getenv("OTC_OFFER_BLOCKED_USER_IDS", "").split(",") if x.strip().isdigit()}
    if event.from_user.id in blocked:
        await event.answer(texts["otc_offer_blocked"])
        return
    listing = await db.get_otc_listing(listing_id)
    if not listing or listing.get("status") != "active":
        await event.answer(texts["otc_offer_unavailable"])
        return
    if listing["seller_id"] == event.from_user.id:
        await event.answer(texts["otc_offer_own"])
        return
    remaining = OfferCooldown.remaining(event.from_user.id, listing_id)
    if remaining:
        await event.answer(texts["otc_offer_cooldown"].format(seconds=remaining))
        return
    await state.set_state(OTCMarket.OFFER_AMOUNT)
    await state.update_data(offer_listing_id=listing_id)
    text = texts["otc_offer_amount_prompt"].format(item=html.escape(listing["item_name"]))
    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event, text, parse_mode=ParseMode.HTML, state=state)
    else:
        await event.answer(text, parse_mode=ParseMode.HTML)


@router.message(OTCMarket.OFFER_AMOUNT, F.text)
async def submit_offer(message: types.Message, state: FSMContext, bot: Bot, texts: dict):
    data = await state.get_data()
    listing_id = int(data.get("offer_listing_id", 0))
    listing = await db.get_otc_listing(listing_id)
    if not listing or listing.get("status") != "active" or listing["seller_id"] == message.from_user.id:
        await message.answer(texts["otc_offer_unavailable"])
        await state.clear()
        return
    remaining = OfferCooldown.remaining(message.from_user.id, listing_id)
    if remaining:
        await message.answer(texts["otc_offer_cooldown"].format(seconds=remaining))
        return
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0 or amount.as_tuple().exponent < -9:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer(texts["otc_offer_invalid"])
        return
    await db.ensure_user_exists(message.from_user.id)
    offer = await db.create_otc_offer({
        "listing_id": listing_id, "buyer_id": message.from_user.id,
        "seller_id": listing["seller_id"], "amount_ton": str(amount),
    })
    if not offer:
        await message.answer(texts["otc_offer_error"])
        return
    OfferCooldown.mark(message.from_user.id, listing_id)
    seller_keyboard = InlineKeyboardBuilder()
    seller_keyboard.button(text=texts["otc_offer_accept_btn"], callback_data=f"offer_accept_{offer['id']}", style="success")
    seller_keyboard.button(text=texts["otc_offer_decline_btn"], callback_data=f"offer_decline_{offer['id']}", style="danger")
    seller_keyboard.button(text=texts["otc_profile_btn"], url=f"tg://user?id={message.from_user.id}")
    seller_keyboard.adjust(2, 1)
    await bot.send_message(listing["seller_id"], texts["otc_offer_seller_notice"].format(
        amount=amount, item=html.escape(listing["item_name"]),
        buyer=html.escape("@" + (message.from_user.username or str(message.from_user.id))),
    ), reply_markup=seller_keyboard.as_markup(), parse_mode=ParseMode.HTML)
    await message.answer(texts["otc_offer_sent"].format(amount=amount), parse_mode=ParseMode.HTML)
    await state.clear()


@router.callback_query(F.data.regexp(r"^offer_(accept|decline)_\d+$"))
async def respond_offer(callback: types.CallbackQuery, bot: Bot, texts: dict):
    parts = callback.data.split("_")
    status = "accepted" if parts[1] == "accept" else "declined"
    result = await db.respond_otc_offer(int(parts[2]), callback.from_user.id, status)
    if not result.get("ok"):
        await callback.answer(texts["otc_offer_unavailable"], show_alert=True)
        return
    await callback.answer(texts[f"otc_offer_{status}"], show_alert=True)
    try:
        lang = await db.get_user_language(result["buyer_id"])
        buyer_texts = get_locale_by_lang(lang)
        buyer_keyboard = InlineKeyboardBuilder()
        buyer_keyboard.button(text=buyer_texts["otc_profile_btn"],
                              url=f"tg://user?id={result['seller_id']}")
        await bot.send_message(result["buyer_id"], buyer_texts["otc_offer_buyer_result"].format(
            status=buyer_texts[f"otc_offer_status_{status}"], amount=result["amount_ton"]),
            reply_markup=buyer_keyboard.as_markup(), parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("Could not notify OTC offer buyer")
