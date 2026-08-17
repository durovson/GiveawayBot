import html
import json
import logging

from aiogram import Bot, F, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from database import db
from services.localization import get_locale_by_lang
from utils import safe_bot_edit_text, safe_edit_text

logger = logging.getLogger(__name__)
router = Router()


class StoreLotCreation(StatesGroup):
    title = State()
    description = State()
    price = State()
    quantity = State()
    image_url = State()
    reward_type = State()
    reward_payload = State()
    per_user_limit = State()
    confirm = State()


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _back_keyboard(texts: dict, callback_data: str = "store_admin"):
    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts["store_back_btn"],
        callback_data=callback_data,
        icon_custom_emoji_id="5877629862306385808",
    )
    return builder.as_markup()


async def _edit_flow_message(message: types.Message, state: FSMContext, text: str, markup):
    data = await state.get_data()
    result = await safe_bot_edit_text(
        message.bot,
        message.chat.id,
        data.get("last_msg_id"),
        text,
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
    )
    if result:
        await state.update_data(last_msg_id=result.message_id)


async def show_store_admin(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["store_admin_create_btn"], callback_data="store_admin_create", style="success")
    builder.button(text=texts["store_admin_lots_btn"], callback_data="store_admin_lots")
    builder.button(text=texts["store_admin_orders_btn"], callback_data="store_admin_orders")
    builder.button(
        text=texts["store_back_btn"],
        callback_data="store_menu",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(1)
    msg = await safe_edit_text(
        callback,
        texts["store_admin_title"],
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )
    if msg:
        await state.update_data(last_msg_id=msg.message_id)


@router.callback_query(F.data == "store_admin")
async def store_admin_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_store_admin(callback, state, texts)


@router.callback_query(F.data == "store_admin_create")
async def create_lot_start(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    await callback.answer()
    await state.clear()
    msg = await safe_edit_text(
        callback,
        texts["store_admin_enter_title"],
        reply_markup=_back_keyboard(texts),
        parse_mode=ParseMode.HTML,
        state=state,
    )
    if msg:
        await state.update_data(last_msg_id=msg.message_id)
    await state.set_state(StoreLotCreation.title)


@router.message(StoreLotCreation.title, F.text)
async def create_lot_title(message: types.Message, state: FSMContext, texts: dict):
    if not _is_admin(message.from_user.id):
        await state.clear()
        return
    title = message.text.strip()[:120]
    try:
        await message.delete()
    except Exception:
        pass
    if not title:
        return
    await state.update_data(title=title)
    await _edit_flow_message(message, state, texts["store_admin_enter_description"], _back_keyboard(texts))
    await state.set_state(StoreLotCreation.description)


@router.message(StoreLotCreation.description, F.text)
async def create_lot_description(message: types.Message, state: FSMContext, texts: dict):
    description = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(description="" if description == "-" else description[:1500])
    await _edit_flow_message(message, state, texts["store_admin_enter_price"], _back_keyboard(texts))
    await state.set_state(StoreLotCreation.price)


@router.message(StoreLotCreation.price, F.text)
async def create_lot_price(message: types.Message, state: FSMContext, texts: dict):
    try:
        value = int(message.text.strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts["store_admin_invalid_number"])
        return
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(price_rp=value)
    await _edit_flow_message(message, state, texts["store_admin_enter_quantity"], _back_keyboard(texts))
    await state.set_state(StoreLotCreation.quantity)


@router.message(StoreLotCreation.quantity, F.text)
async def create_lot_quantity(message: types.Message, state: FSMContext, texts: dict):
    try:
        value = int(message.text.strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts["store_admin_invalid_number"])
        return
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(total_quantity=value)
    await _edit_flow_message(message, state, texts["store_admin_enter_image"], _back_keyboard(texts))
    await state.set_state(StoreLotCreation.image_url)


@router.message(StoreLotCreation.image_url, F.text)
async def create_lot_image(message: types.Message, state: FSMContext, texts: dict):
    image_url = message.text.strip()
    try:
        await message.delete()
    except Exception:
        pass
    if image_url == "-":
        image_url = None
    elif not image_url.startswith(("https://", "http://")):
        await message.answer(texts["store_admin_invalid_url"])
        return
    await state.update_data(image_url=image_url)
    builder = InlineKeyboardBuilder()
    for reward_type, key in (
        ("manual", "store_reward_manual_btn"),
        ("ticket", "store_reward_ticket_btn"),
        ("role", "store_reward_role_btn"),
        ("channel", "store_reward_channel_btn"),
        ("sticker", "store_reward_sticker_btn"),
        ("nft", "store_reward_nft_btn"),
        ("physical", "store_reward_physical_btn"),
        ("custom", "store_reward_custom_btn"),
    ):
        builder.button(text=texts[key], callback_data=f"store_reward_{reward_type}")
    builder.button(text=texts["store_back_btn"], callback_data="store_admin")
    builder.adjust(2)
    await _edit_flow_message(message, state, texts["store_admin_select_reward"], builder.as_markup())
    await state.set_state(StoreLotCreation.reward_type)


@router.callback_query(StoreLotCreation.reward_type, F.data.startswith("store_reward_"))
async def create_lot_reward_type(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    reward_type = callback.data.replace("store_reward_", "")
    await state.update_data(reward_type=reward_type)
    await callback.answer()
    prompt = (
        texts["store_admin_enter_ticket_reward"]
        if reward_type == "ticket"
        else texts["store_admin_enter_reward_payload"]
    )
    await safe_edit_text(
        callback,
        prompt,
        reply_markup=_back_keyboard(texts),
        parse_mode=ParseMode.HTML,
        state=state,
    )
    await state.set_state(StoreLotCreation.reward_payload)


@router.message(StoreLotCreation.reward_payload, F.text)
async def create_lot_reward_payload(message: types.Message, state: FSMContext, texts: dict):
    data = await state.get_data()
    raw = message.text.strip()
    if data.get("reward_type") == "ticket":
        try:
            tickets = int(raw)
            if tickets <= 0:
                raise ValueError
        except ValueError:
            await message.answer(texts["store_admin_invalid_number"])
            return
        payload = {"tickets": tickets}
    else:
        payload = {"instructions": raw[:1000]}
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(reward_payload=payload)
    await _edit_flow_message(message, state, texts["store_admin_enter_limit"], _back_keyboard(texts))
    await state.set_state(StoreLotCreation.per_user_limit)


@router.message(StoreLotCreation.per_user_limit, F.text)
async def create_lot_limit(message: types.Message, state: FSMContext, texts: dict):
    try:
        value = int(message.text.strip())
        if value <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts["store_admin_invalid_number"])
        return
    try:
        await message.delete()
    except Exception:
        pass
    await state.update_data(per_user_limit=value)
    data = await state.get_data()
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["store_admin_publish_btn"], callback_data="store_admin_publish", style="success")
    builder.button(text=texts["store_back_btn"], callback_data="store_admin")
    builder.adjust(1)
    preview = texts["store_admin_preview"].format(
        title=html.escape(data["title"]),
        description=html.escape(data.get("description") or texts["store_no_description"]),
        price=data["price_rp"],
        quantity=data["total_quantity"],
        reward=html.escape(data["reward_type"]),
        limit=value,
    )
    await _edit_flow_message(message, state, preview, builder.as_markup())
    await state.set_state(StoreLotCreation.confirm)


@router.callback_query(StoreLotCreation.confirm, F.data == "store_admin_publish")
async def create_lot_publish(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    data = await state.get_data()
    lot = await db.create_store_lot({
        "title": data["title"],
        "description": data.get("description", ""),
        "price_rp": data["price_rp"],
        "total_quantity": data["total_quantity"],
        "image_url": data.get("image_url"),
        "reward_type": data["reward_type"],
        "reward_payload": data.get("reward_payload", {}),
        "per_user_limit": data["per_user_limit"],
        "status": "active",
        "created_by": callback.from_user.id,
    })
    if not lot:
        await callback.answer(texts["store_admin_create_error"], show_alert=True)
        return
    await callback.answer(texts["store_admin_created_alert"], show_alert=True)
    await show_store_admin(callback, state, texts)


@router.callback_query(F.data == "store_admin_lots")
async def store_admin_lots(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    await callback.answer()
    lots = await db.get_store_lots_admin()
    builder = InlineKeyboardBuilder()
    for lot in lots:
        builder.button(
            text=f"#{lot['id']} [{lot['status']}] {lot['title'][:24]}",
            callback_data=f"store_admin_view_{lot['id']}",
        )
    builder.button(text=texts["store_back_btn"], callback_data="store_admin")
    builder.adjust(1)
    await safe_edit_text(
        callback,
        texts["store_admin_lots_title"].format(count=len(lots)),
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )


@router.callback_query(F.data.startswith("store_admin_view_"))
async def store_admin_view_lot(
    callback: types.CallbackQuery,
    state: FSMContext,
    texts: dict,
    answer: bool = True,
):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    lot_id = int(callback.data.rsplit("_", 1)[-1])
    lot = await db.get_store_lot(lot_id)
    if not lot:
        if answer:
            await callback.answer(texts["store_lot_unavailable"], show_alert=True)
        return
    if answer:
        await callback.answer()
    builder = InlineKeyboardBuilder()
    target_status = "disabled" if lot["status"] == "active" else "active"
    builder.button(
        text=texts["store_admin_disable_btn"] if target_status == "disabled" else texts["store_admin_activate_btn"],
        callback_data=f"store_admin_status_{lot_id}_{target_status}",
    )
    builder.button(text=texts["store_back_btn"], callback_data="store_admin_lots")
    builder.adjust(1)
    await safe_edit_text(
        callback,
        texts["store_admin_lot_detail"].format(
            id=lot_id,
            title=html.escape(lot["title"]),
            status=lot["status"],
            price=lot["price_rp"],
            sold=lot["sold_quantity"],
            total=lot["total_quantity"],
        ),
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )


@router.callback_query(F.data.startswith("store_admin_status_"))
async def store_admin_status(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    _, _, _, lot_id, status = callback.data.split("_", 4)
    ok = await db.set_store_lot_status(int(lot_id), status)
    await callback.answer(
        texts["store_admin_status_saved"] if ok else texts["store_admin_create_error"],
        show_alert=True,
    )
    await store_admin_view_lot(callback, state, texts, answer=False)


@router.callback_query(F.data == "store_admin_orders")
async def store_admin_orders(
    callback: types.CallbackQuery,
    state: FSMContext,
    texts: dict,
    answer: bool = True,
):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    if answer:
        await callback.answer()
    purchases = await db.get_pending_store_purchases()
    builder = InlineKeyboardBuilder()
    for purchase in purchases:
        lot = purchase.get("store_lots") or {}
        builder.button(
            text=f"#{purchase['id']} · {lot.get('title', 'LOT')[:22]} · {purchase['user_id']}",
            callback_data=f"store_order_{purchase['id']}",
        )
    builder.button(text=texts["store_back_btn"], callback_data="store_admin")
    builder.adjust(1)
    content = texts["store_admin_no_orders"] if not purchases else texts["store_admin_orders_hint"]
    await safe_edit_text(
        callback,
        texts["store_admin_orders_title"].format(content=content),
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )


@router.callback_query(F.data.startswith("store_order_"))
async def store_order_detail(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    purchase_id = int(callback.data.rsplit("_", 1)[-1])
    purchase = await db.get_store_purchase(purchase_id)
    if not purchase or purchase.get("status") != "paid":
        await callback.answer(texts["store_admin_fulfill_error"], show_alert=True)
        return
    await callback.answer()
    lot = purchase.get("store_lots") or {}
    user = purchase.get("users") or {}
    payload = lot.get("reward_payload") or {}
    instructions = payload.get("instructions") or json.dumps(payload, ensure_ascii=False)
    username = user.get("username") or user.get("first_name") or str(purchase["user_id"])
    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts["store_admin_confirm_fulfill_btn"],
        callback_data=f"store_fulfill_{purchase_id}",
        style="success",
    )
    builder.button(text=texts["store_back_btn"], callback_data="store_admin_orders")
    builder.adjust(1)
    await safe_edit_text(
        callback,
        texts["store_admin_order_detail"].format(
            id=purchase_id,
            title=html.escape(lot.get("title") or "LOT"),
            user=html.escape(username),
            user_id=purchase["user_id"],
            price=purchase["price_rp"],
            reward_type=html.escape(lot.get("reward_type") or "manual"),
            instructions=html.escape(str(instructions or "—")),
        ),
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )


@router.callback_query(F.data.startswith("store_fulfill_"))
async def store_fulfill_purchase(
    callback: types.CallbackQuery,
    state: FSMContext,
    bot: Bot,
    texts: dict,
):
    if not _is_admin(callback.from_user.id):
        await callback.answer(texts["access_denied"], show_alert=True)
        return
    purchase_id = int(callback.data.rsplit("_", 1)[-1])
    purchase = await db.fulfill_store_purchase(purchase_id, callback.from_user.id)
    if not purchase:
        await callback.answer(texts["store_admin_fulfill_error"], show_alert=True)
        return
    await callback.answer(texts["store_admin_fulfilled"], show_alert=True)
    try:
        language = await db.get_user_language(purchase["user_id"])
        user_texts = get_locale_by_lang(language)
        await bot.send_message(
            purchase["user_id"],
            user_texts["store_order_fulfilled"].format(purchase_id=purchase_id),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.exception("Could not notify fulfilled purchase %s", purchase_id)
    await store_admin_orders(callback, state, texts, answer=False)
