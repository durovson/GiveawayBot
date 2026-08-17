import asyncio
import html
import logging

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from database import db
from services.points_service import PointsService
from utils import safe_edit_text

logger = logging.getLogger(__name__)
router = Router()

TICKET_COST = 50


async def _wallet_snapshot(user_id: int) -> tuple[int, int]:
    user, points_data = await asyncio.gather(
        db.get_user_by_telegram_id(user_id),
        db.get_points(user_id),
    )
    if not points_data:
        await PointsService.recalculate_points(user_id)
        points_data = await db.get_points(user_id)
    return (
        points_data.get("total_points", 0) if points_data else 0,
        user.get("active_tickets", 0) if user else 0,
    )


async def show_store_menu(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    rp, tickets = await _wallet_snapshot(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts["store_tickets_btn"],
        callback_data="store_tickets",
        icon_custom_emoji_id="5260726538302660868",
    )
    builder.button(
        text=texts["store_lots_btn"],
        callback_data="store_lots",
        icon_custom_emoji_id="5983399041197675256",
    )
    if callback.from_user.id in ADMIN_IDS:
        builder.button(
            text=texts["store_admin_btn"],
            callback_data="store_admin",
            icon_custom_emoji_id="5258096772776991776",
        )
    builder.button(
        text=texts["game_main_menu_btn"],
        callback_data="game_menu",
        icon_custom_emoji_id="6042137469204303531",
        style="danger",
    )
    builder.adjust(2, 1, 1)
    await safe_edit_text(
        callback,
        texts["store_hub_title"].format(rp=rp, tickets=tickets),
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )


async def show_ticket_store(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    rp, tickets = await _wallet_snapshot(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["buy_1_btn"], callback_data="buy_tickets_1")
    builder.button(text=texts["buy_5_btn"], callback_data="buy_tickets_5")
    builder.button(text=texts["buy_10_btn"], callback_data="buy_tickets_10")
    builder.button(
        text=texts["store_back_btn"],
        callback_data="store_menu",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(3, 1)
    await safe_edit_text(
        callback,
        texts["store_menu_title"].format(rp=rp, tickets=tickets),
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )


async def show_lots_store(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    (rp, _), lots = await asyncio.gather(
        _wallet_snapshot(callback.from_user.id),
        db.get_active_store_lots(),
    )
    builder = InlineKeyboardBuilder()

    for lot in lots:
        remaining = max(0, lot["total_quantity"] - lot["sold_quantity"])
        builder.button(
            text=texts["store_lot_button"].format(
                title=lot["title"][:30],
                price=lot["price_rp"],
                remaining=remaining,
            ),
            callback_data=f"store_lot_{lot['id']}",
        )

    builder.button(
        text=texts["store_back_btn"],
        callback_data="store_menu",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(1)

    content = texts["store_lots_empty"] if not lots else texts["store_lots_hint"]
    await safe_edit_text(
        callback,
        texts["store_lots_title"].format(rp=rp, content=content),
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )


async def show_lot_detail(
    callback: types.CallbackQuery,
    state: FSMContext,
    texts: dict,
    lot_id: int,
):
    lot = await db.get_store_lot(lot_id)
    if not lot or lot.get("status") not in {"active", "sold_out"}:
        await callback.answer(texts["store_lot_unavailable"], show_alert=True)
        await show_lots_store(callback, state, texts)
        return

    remaining = max(0, lot["total_quantity"] - lot["sold_quantity"])
    description = html.escape(lot.get("description") or texts["store_no_description"])
    builder = InlineKeyboardBuilder()
    if remaining > 0 and lot["status"] == "active":
        builder.button(
            text=texts["store_buy_lot_btn"].format(price=lot["price_rp"]),
            callback_data=f"store_buy_lot_{lot_id}",
            style="success",
        )
    image_url = (lot.get("image_url") or "").strip()
    if image_url.startswith(("https://", "http://")):
        builder.button(text=texts["store_open_media_btn"], url=image_url)
    builder.button(
        text=texts["store_back_btn"],
        callback_data="store_lots",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(1)

    await safe_edit_text(
        callback,
        texts["store_lot_detail"].format(
            title=html.escape(lot["title"]),
            description=description,
            price=lot["price_rp"],
            remaining=remaining,
            total=lot["total_quantity"],
        ),
        reply_markup=builder.as_markup(),
        parse_mode=ParseMode.HTML,
        state=state,
    )


@router.callback_query(F.data == "store_menu")
async def store_menu_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_store_menu(callback, state, texts)


@router.callback_query(F.data == "store_tickets")
async def store_tickets_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_ticket_store(callback, state, texts)


@router.callback_query(F.data == "store_lots")
async def store_lots_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_lots_store(callback, state, texts)


@router.callback_query(F.data.startswith("store_lot_"))
async def store_lot_detail_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    lot_id = int(callback.data.rsplit("_", 1)[-1])
    await show_lot_detail(callback, state, texts, lot_id)


@router.callback_query(F.data.startswith("buy_tickets_"))
async def buy_tickets_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    amount = int(callback.data.rsplit("_", 1)[-1])
    result = await db.purchase_tickets_atomic(
        user_id=callback.from_user.id,
        amount=amount,
        unit_cost=TICKET_COST,
        idempotency_key=f"tg:{callback.id}",
    )
    if not result.get("ok"):
        text = (
            texts["not_enough_points"]
            if result.get("error") == "INSUFFICIENT_POINTS"
            else texts["store_purchase_error"]
        )
        await callback.answer(text, show_alert=True)
        return

    await callback.answer(texts["purchase_success"].format(amount=amount), show_alert=True)
    await show_ticket_store(callback, state, texts)


@router.callback_query(F.data.startswith("store_buy_lot_"))
async def buy_lot_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    lot_id = int(callback.data.rsplit("_", 1)[-1])
    result = await db.purchase_store_lot_atomic(
        user_id=callback.from_user.id,
        lot_id=lot_id,
        idempotency_key=f"tg:{callback.id}",
    )
    if not result.get("ok"):
        errors = {
            "INSUFFICIENT_POINTS": texts["store_lot_not_enough_rp"],
            "SOLD_OUT": texts["store_lot_sold_out"],
            "LOT_NOT_ACTIVE": texts["store_lot_unavailable"],
            "LOT_NOT_FOUND": texts["store_lot_unavailable"],
            "USER_LIMIT_REACHED": texts["store_lot_limit_reached"],
        }
        await callback.answer(
            errors.get(result.get("error"), texts["store_purchase_error"]),
            show_alert=True,
        )
        if result.get("error") in {"SOLD_OUT", "LOT_NOT_ACTIVE", "LOT_NOT_FOUND"}:
            await show_lots_store(callback, state, texts)
        return

    success_key = (
        "store_lot_ticket_success"
        if result.get("ticket_reward", 0) > 0
        else "store_lot_purchase_success"
    )
    await callback.answer(
        texts[success_key].format(
            purchase_id=result.get("purchase_id"),
            tickets=result.get("ticket_reward", 0),
        ),
        show_alert=True,
    )
    await show_lot_detail(callback, state, texts, lot_id)
