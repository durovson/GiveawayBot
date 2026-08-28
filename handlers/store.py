import asyncio
import html

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_IDS
from database import db
from services.points_service import PointsService
from utils import safe_answer, safe_edit_text

router = Router()


async def _rp(user_id: int) -> int:
    points = await db.get_points(user_id)
    if not points:
        await PointsService.recalculate_points(user_id)
        points = await db.get_points(user_id)
    return int(points.get("total_points", 0)) if points else 0


async def _render(event, text: str, keyboard, state: FSMContext | None = None):
    if isinstance(event, types.CallbackQuery):
        return await safe_edit_text(event, text, reply_markup=keyboard,
                                    parse_mode=ParseMode.HTML, state=state)
    return await safe_answer(event, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def show_store_menu(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    rp = await _rp(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["store_tickets_btn"], callback_data="store_tickets",
                   icon_custom_emoji_id="5260726538302660868")
    builder.button(text=texts["store_lots_btn"], callback_data="store_lots",
                   icon_custom_emoji_id="5983399041197675256")
    if callback.from_user.id in ADMIN_IDS:
        builder.button(text=texts["store_admin_btn"], callback_data="store_admin",
                       icon_custom_emoji_id="5258096772776991776")
    builder.button(text=texts["game_main_menu_btn"], callback_data="game_menu",
                   icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(2, 1, 1)
    await _render(callback, texts["store_hub_title"].format(rp=rp, tickets="—"),
                  builder.as_markup(), state)


async def show_ticket_store(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    rp, giveaways = await asyncio.gather(_rp(callback.from_user.id), db.get_active_giveaways())
    builder = InlineKeyboardBuilder()
    for giveaway in giveaways:
        builder.button(text=f"#{giveaway['id']} · {giveaway['title'][:38]}",
                       callback_data=f"store_tg_{giveaway['id']}")
    builder.button(text=texts["store_back_btn"], callback_data="store_menu",
                   icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)
    content = texts["ticket_choose_empty"] if not giveaways else texts["ticket_choose_hint"]
    await _render(callback, texts["ticket_choose_title"].format(rp=rp, content=content),
                  builder.as_markup(), state)


async def show_giveaway_tickets(event, giveaway_id: int, texts: dict,
                                state: FSMContext | None = None):
    user_id = event.from_user.id
    giveaway, rp, tickets, offers = await asyncio.gather(
        db.get_giveaway(giveaway_id), _rp(user_id),
        db.get_giveaway_ticket_balance(giveaway_id, user_id), db.get_ticket_offers(),
    )
    if not giveaway or giveaway.get("status") != "active":
        if isinstance(event, types.CallbackQuery):
            await event.answer(texts["giveaway_finished"], show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    for offer in offers:
        if offer["mode"] == "fill":
            added = max(0, offer["ticket_count"] - tickets)
            price = offer["price_rp"] * added if offer["pricing_mode"] == "per_ticket" else offer["price_rp"]
            label = texts["ticket_offer_max"].format(price=price)
        else:
            price = offer["price_rp"]
            label = texts["ticket_offer_add"].format(count=offer["ticket_count"], price=price)
        builder.button(text=label, callback_data=f"buy_gt_{giveaway_id}_{offer['code']}")
    builder.button(text=texts["ticket_enter_btn"], callback_data=f"join_{giveaway_id}", style="success")
    builder.button(text=texts["store_back_btn"], callback_data="store_tickets",
                   icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)
    prizes = ", ".join(map(str, giveaway.get("prizes") or [])) or "—"
    await _render(event, texts["ticket_giveaway_detail"].format(
        id=giveaway_id, title=html.escape(giveaway["title"]),
        prizes=html.escape(prizes), tickets=tickets, rp=rp,
    ), builder.as_markup(), state)


async def show_lots_store(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    rp, lots = await asyncio.gather(_rp(callback.from_user.id), db.get_active_store_lots())
    builder = InlineKeyboardBuilder()
    for lot in lots:
        remaining = max(0, lot["total_quantity"] - lot["sold_quantity"])
        builder.button(text=texts["store_lot_button"].format(
            title=lot["title"][:30], price=lot["price_rp"], remaining=remaining),
            callback_data=f"store_lot_{lot['id']}")
    builder.button(text=texts["store_back_btn"], callback_data="store_menu",
                   icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)
    content = texts["store_lots_empty"] if not lots else texts["store_lots_hint"]
    await _render(callback, texts["store_lots_title"].format(rp=rp, content=content),
                  builder.as_markup(), state)


async def show_lot_detail(event, lot_id: int, texts: dict, state: FSMContext | None = None):
    lot, rp = await asyncio.gather(db.get_store_lot(lot_id), _rp(event.from_user.id))
    if not lot or lot.get("status") not in {"active", "sold_out"}:
        if isinstance(event, types.CallbackQuery):
            await event.answer(texts["store_lot_unavailable"], show_alert=True)
        return
    remaining = max(0, lot["total_quantity"] - lot["sold_quantity"])
    builder = InlineKeyboardBuilder()
    if remaining and lot["status"] == "active":
        builder.button(text=texts["store_buy_lot_btn"].format(price=lot["price_rp"]),
                       callback_data=f"store_buy_lot_{lot_id}", style="success")
    builder.button(text=texts["store_back_btn"], callback_data="store_lots",
                   icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)
    await _render(event, texts["store_lot_detail"].format(
        title=html.escape(lot["title"]),
        description=html.escape(lot.get("description") or texts["store_no_description"]),
        price=lot["price_rp"], remaining=remaining, total=lot["total_quantity"], rp=rp,
    ), builder.as_markup(), state)


@router.callback_query(F.data == "store_menu")
async def store_menu_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_store_menu(callback, state, texts)


@router.callback_query(F.data == "store_tickets")
async def store_tickets_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_ticket_store(callback, state, texts)


@router.callback_query(F.data.startswith("store_tg_"))
async def ticket_giveaway_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_giveaway_tickets(callback, int(callback.data.rsplit("_", 1)[1]), texts, state)


@router.callback_query(F.data.startswith("buy_gt_"))
async def buy_giveaway_tickets(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    _, _, giveaway_id, code = callback.data.split("_", 3)
    result = await db.purchase_giveaway_tickets(callback.from_user.id, int(giveaway_id), code, f"tg:{callback.id}")
    if not result.get("ok"):
        errors = {"INSUFFICIENT_POINTS": texts["not_enough_points"],
                  "TICKET_LIMIT_REACHED": texts["ticket_limit"],
                  "ALREADY_JOINED": texts["giveaway_already_joined"]}
        await callback.answer(errors.get(result.get("error"), texts["store_purchase_error"]), show_alert=True)
        return
    await callback.answer(texts["ticket_purchase_success"].format(
        added=result.get("added", 0), cost=result.get("cost", 0)), show_alert=True)
    await show_giveaway_tickets(callback, int(giveaway_id), texts, state)


@router.callback_query(F.data == "store_lots")
async def store_lots_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_lots_store(callback, state, texts)


@router.callback_query(F.data.startswith("store_lot_"))
async def store_lot_detail_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_lot_detail(callback, int(callback.data.rsplit("_", 1)[1]), texts, state)


@router.callback_query(F.data.startswith("store_buy_lot_"))
async def buy_lot_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    lot_id = int(callback.data.rsplit("_", 1)[1])
    result = await db.purchase_store_lot_atomic(callback.from_user.id, lot_id, f"tg:{callback.id}")
    if not result.get("ok"):
        errors = {"INSUFFICIENT_POINTS": texts["store_lot_not_enough_rp"], "SOLD_OUT": texts["store_lot_sold_out"],
                  "LOT_NOT_ACTIVE": texts["store_lot_unavailable"], "LOT_NOT_FOUND": texts["store_lot_unavailable"],
                  "USER_LIMIT_REACHED": texts["store_lot_limit_reached"]}
        await callback.answer(errors.get(result.get("error"), texts["store_purchase_error"]), show_alert=True)
        return
    await callback.answer(texts["store_lot_purchase_success"].format(
        purchase_id=result.get("purchase_id")), show_alert=True)
    await show_lot_detail(callback, lot_id, texts, state)
