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
from utils import safe_answer, safe_edit_text

router = Router()
logger = logging.getLogger(__name__)


async def _rp(user_id: int) -> int:
    points = await db.get_points(user_id)
    if not points:
        await PointsService.recalculate_points(user_id)
        points = await db.get_points(user_id)
    return int(points.get("total_points", 0)) if points else 0


async def _render(event, text: str, keyboard, state: FSMContext | None = None):
    if isinstance(event, types.CallbackQuery):
        return await safe_edit_text(
            event,
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            state=state,
        )
    return await safe_answer(
        event,
        text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


def _rpc_payload(data) -> dict:
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return {}


async def _ticket_state(giveaway_id: int, user_id: int) -> dict:
    """Return purchased balance and already-used raffle weight."""
    result = {"total": 1, "balance": 0, "used": 0}
    if not db.client:
        return result

    try:
        response = await (
            db.client.table("giveaway_ticket_balances")
            .select("tickets,available_tickets")
            .eq("giveaway_id", giveaway_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if response.data:
            row = response.data[0]
            result["total"] = max(1, int(row.get("tickets") or 1))
            result["balance"] = max(0, int(row.get("available_tickets") or 0))
    except Exception as exc:
        logger.warning("Ticket balance v2 unavailable, using legacy balance: %s", exc)
        try:
            response = await (
                db.client.table("giveaway_ticket_balances")
                .select("tickets")
                .eq("giveaway_id", giveaway_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if response.data:
                result["total"] = max(1, int(response.data[0].get("tickets") or 1))
        except Exception:
            pass

    try:
        response = await (
            db.client.table("participants")
            .select("tickets_used")
            .eq("giveaway_id", giveaway_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if response.data:
            result["used"] = max(1, int(response.data[0].get("tickets_used") or 1))
    except Exception as exc:
        logger.warning("Could not read participant ticket weight: %s", exc)

    return result


async def _resolve_channel_link(bot, channel) -> tuple[str, str | None]:
    raw = str(channel).strip()
    fallback_label = raw.lstrip("@") or raw
    fallback_url = (
        f"https://t.me/{raw.lstrip('@')}"
        if raw.startswith("@")
        else None
    )

    try:
        chat = await bot.get_chat(channel)
    except Exception as exc:
        logger.warning("Could not resolve giveaway channel %s: %s", channel, exc)
        return fallback_label, fallback_url

    label = str(getattr(chat, "title", None) or getattr(chat, "username", None) or fallback_label)
    username = getattr(chat, "username", None)
    if username:
        return label, f"https://t.me/{username}"

    invite_link = getattr(chat, "invite_link", None)
    if invite_link:
        return label, invite_link

    try:
        invite = await bot.create_chat_invite_link(
            chat_id=chat.id,
            name="Giveaway access",
        )
        return label, invite.invite_link
    except Exception as exc:
        logger.warning("Could not create invite link for giveaway channel %s: %s", channel, exc)
        return label, fallback_url


async def show_partner_gate(
    callback: types.CallbackQuery,
    giveaway: dict,
    state: FSMContext,
    texts: dict,
):
    builder = InlineKeyboardBuilder()
    for channel in giveaway.get("mandatory_channels") or []:
        label, url = await _resolve_channel_link(callback.bot, channel)
        if url:
            builder.button(text=label[:50], url=url)

    builder.button(
        text=texts["partner_check_btn"],
        callback_data=f"partner_check_{giveaway['id']}",
        style="success",
    )
    builder.button(
        text=texts["store_back_btn"],
        callback_data="store_tickets",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(1)
    await _render(callback, texts["partner_gate_title"], builder.as_markup(), state)


async def _is_subscribed_to_all(bot, user_id: int, channels: list) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in {"member", "administrator", "creator"}:
                missing.append(str(channel))
        except Exception as exc:
            logger.error("Subscription check failed for %s: %s", channel, exc)
            missing.append(str(channel))
    return not missing, missing


async def show_store_menu(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    rp = await _rp(callback.from_user.id)
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
        text=texts["store_back_btn"],
        callback_data="game_menu",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(2, 1, 1)
    await _render(
        callback,
        texts["store_hub_title"].format(rp=rp, tickets="—"),
        builder.as_markup(),
        state,
    )


async def show_ticket_store(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    rp, giveaways = await asyncio.gather(
        _rp(callback.from_user.id),
        db.get_active_giveaways(),
    )
    builder = InlineKeyboardBuilder()
    for giveaway in giveaways:
        builder.button(
            text=f"#{giveaway['id']} · {giveaway['title'][:38]}",
            callback_data=f"store_tg_{giveaway['id']}",
        )
    builder.button(
        text=texts["store_back_btn"],
        callback_data="store_menu",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(1)
    content = (
        texts["ticket_choose_empty"]
        if not giveaways
        else texts["ticket_choose_hint"]
    )
    await _render(
        callback,
        texts["ticket_choose_title"].format(rp=rp, content=content),
        builder.as_markup(),
        state,
    )


async def show_giveaway_tickets(
    event,
    giveaway_id: int,
    texts: dict,
    state: FSMContext | None = None,
):
    user_id = event.from_user.id
    giveaway, rp, offers, ranking, ticket_state = await asyncio.gather(
        db.get_giveaway(giveaway_id),
        _rp(user_id),
        db.get_ticket_offers(),
        db.get_giveaway_ticket_ranking(giveaway_id, user_id),
        _ticket_state(giveaway_id, user_id),
    )
    if not giveaway or giveaway.get("status") != "active":
        if isinstance(event, types.CallbackQuery):
            await event.answer(texts["giveaway_finished"], show_alert=True)
        return

    balance = ticket_state["balance"]
    used = ticket_state["used"]

    builder = InlineKeyboardBuilder()
    for offer in offers:
        price = (
            offer["price_rp"] * offer["ticket_count"]
            if offer["pricing_mode"] == "per_ticket"
            else offer["price_rp"]
        )
        label = texts["ticket_offer_add"].format(
            count=offer["ticket_count"],
            price=price,
        )
        builder.button(
            text=label,
            callback_data=f"buy_gt_{giveaway_id}_{offer['code']}",
        )

    joined = ranking["rank"] is not None
    if not joined:
        builder.button(
            text=texts["ticket_enter_btn"],
            callback_data=f"join_{giveaway_id}",
            style="success",
        )
    elif balance > 0:
        for amount in (1, 2, 3, 5, 10):
            if amount <= balance:
                builder.button(
                    text=texts["ticket_use_btn"].format(count=amount),
                    callback_data=f"spend_gt_{giveaway_id}_{amount}",
                )
        if balance > 1:
            builder.button(
                text=texts["ticket_use_all_btn"].format(count=balance),
                callback_data=f"spend_gt_{giveaway_id}_all",
                style="success",
            )

    builder.button(
        text=texts["store_back_btn"],
        callback_data="store_tickets",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(1)

    def display_name(row):
        username = str(row.get("username") or "").strip()
        if not username:
            return str(row.get("user_id"))
        if not username.startswith("@") and " " not in username:
            username = f"@{username}"
        return html.escape(username)

    ranking_lines = [
        f"┋ {index}. {display_name(row)} — {max(1, int(row.get('tickets_used') or 1))}"
        for index, row in enumerate(ranking["top"], 1)
    ]
    ranking_text = (
        "\n".join(ranking_lines)
        if ranking_lines
        else texts["ticket_ranking_empty"]
    )
    if not joined:
        your_rank = texts["ticket_not_ranked"]
    else:
        your_rank = (
            f"{ranking['rank']}. "
            f"{display_name({'username': event.from_user.username, 'user_id': user_id})} "
            f"— {used}"
        )

    await _render(
        event,
        texts["ticket_giveaway_detail"].format(
            id=giveaway_id,
            title=html.escape(giveaway["title"]),
            balance=balance,
            used=used,
            rp=rp,
            ranking=ranking_text,
            your_rank=your_rank,
        ),
        builder.as_markup(),
        state,
    )


async def show_lots_store(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    rp, lots = await asyncio.gather(
        _rp(callback.from_user.id),
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
    await _render(
        callback,
        texts["store_lots_title"].format(rp=rp, content=content),
        builder.as_markup(),
        state,
    )


async def show_lot_detail(
    event,
    lot_id: int,
    texts: dict,
    state: FSMContext | None = None,
):
    lot, rp = await asyncio.gather(
        db.get_store_lot(lot_id),
        _rp(event.from_user.id),
    )
    if not lot or lot.get("status") not in {"active", "sold_out"}:
        if isinstance(event, types.CallbackQuery):
            await event.answer(texts["store_lot_unavailable"], show_alert=True)
        return
    remaining = max(0, lot["total_quantity"] - lot["sold_quantity"])
    builder = InlineKeyboardBuilder()
    if remaining and lot["status"] == "active":
        builder.button(
            text=texts["store_buy_lot_btn"].format(price=lot["price_rp"]),
            callback_data=f"store_buy_lot_{lot_id}",
            style="success",
        )
    builder.button(
        text=texts["store_back_btn"],
        callback_data="store_lots",
        icon_custom_emoji_id="5877629862306385808",
    )
    builder.adjust(1)
    await _render(
        event,
        texts["store_lot_detail"].format(
            title=html.escape(lot["title"]),
            description=html.escape(
                lot.get("description") or texts["store_no_description"]
            ),
            price=lot["price_rp"],
            remaining=remaining,
            total=lot["total_quantity"],
            rp=rp,
        ),
        builder.as_markup(),
        state,
    )


@router.callback_query(F.data == "store_menu")
async def store_menu_handler(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    await callback.answer()
    await show_store_menu(callback, state, texts)


@router.callback_query(F.data == "store_tickets")
async def store_tickets_handler(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    await callback.answer()
    await show_ticket_store(callback, state, texts)


@router.callback_query(F.data.startswith("store_tg_"))
async def ticket_giveaway_handler(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    await callback.answer()
    giveaway_id = int(callback.data.rsplit("_", 1)[1])
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway or giveaway.get("status") != "active":
        await callback.answer(texts["giveaway_finished"], show_alert=True)
        return

    channels = giveaway.get("mandatory_channels") or []
    state_data = await state.get_data()
    verified = {
        int(item)
        for item in state_data.get("partner_verified_giveaways", [])
    }
    if channels and giveaway_id not in verified:
        await show_partner_gate(callback, giveaway, state, texts)
        return

    await show_giveaway_tickets(callback, giveaway_id, texts, state)


@router.callback_query(F.data.startswith("partner_check_"))
async def partner_check_handler(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    giveaway_id = int(callback.data.rsplit("_", 1)[1])
    giveaway = await db.get_giveaway(giveaway_id)
    if not giveaway or giveaway.get("status") != "active":
        await callback.answer(texts["giveaway_finished"], show_alert=True)
        return

    channels = giveaway.get("mandatory_channels") or []
    ok, missing = await _is_subscribed_to_all(
        callback.bot,
        callback.from_user.id,
        channels,
    )
    if not ok:
        await callback.answer(
            texts["partner_check_failed"],
            show_alert=True,
        )
        return

    data = await state.get_data()
    verified = {
        int(item)
        for item in data.get("partner_verified_giveaways", [])
    }
    verified.add(giveaway_id)
    await state.update_data(partner_verified_giveaways=sorted(verified))
    await callback.answer(texts["partner_check_success"])
    await show_ticket_store(callback, state, texts)


@router.callback_query(F.data.startswith("buy_gt_"))
async def buy_giveaway_tickets(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    _, _, giveaway_id, code = callback.data.split("_", 3)
    result = await db.purchase_giveaway_tickets(
        callback.from_user.id,
        int(giveaway_id),
        code,
        f"tg:{callback.id}",
    )
    if not result.get("ok"):
        errors = {
            "INSUFFICIENT_POINTS": texts["not_enough_points"],
            "TICKET_LIMIT_REACHED": texts["ticket_limit"],
            "GIVEAWAY_NOT_ACTIVE": texts["giveaway_finished"],
        }
        await callback.answer(
            errors.get(result.get("error"), texts["store_purchase_error"]),
            show_alert=True,
        )
        return
    await callback.answer(
        texts["ticket_purchase_success"].format(
            added=result.get("added", 0),
            cost=result.get("cost", 0),
            balance=result.get("available_tickets", 0),
        ),
        show_alert=True,
    )
    await show_giveaway_tickets(callback, int(giveaway_id), texts, state)


@router.callback_query(F.data.startswith("spend_gt_"))
async def spend_giveaway_tickets(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    _, _, giveaway_id_raw, amount_raw = callback.data.split("_", 3)
    giveaway_id = int(giveaway_id_raw)
    ticket_state = await _ticket_state(giveaway_id, callback.from_user.id)
    balance = ticket_state["balance"]

    amount = balance if amount_raw == "all" else int(amount_raw)
    if amount <= 0 or amount > balance:
        await callback.answer(texts["ticket_use_insufficient"], show_alert=True)
        return

    if not db.client:
        await callback.answer(texts["store_purchase_error"], show_alert=True)
        return

    try:
        response = await db.client.rpc(
            "spend_giveaway_tickets",
            {
                "p_user_id": callback.from_user.id,
                "p_giveaway_id": giveaway_id,
                "p_amount": amount,
                "p_idempotency_key": f"tg-spend:{callback.id}",
            },
        ).execute()
        result = _rpc_payload(response.data)
    except Exception as exc:
        logger.error("Ticket spend failed: %s", exc)
        result = {"ok": False, "error": "SPEND_FAILED"}

    if not result.get("ok"):
        errors = {
            "NOT_PARTICIPATING": texts["ticket_join_first"],
            "INSUFFICIENT_TICKETS": texts["ticket_use_insufficient"],
            "GIVEAWAY_NOT_ACTIVE": texts["giveaway_finished"],
        }
        await callback.answer(
            errors.get(result.get("error"), texts["store_purchase_error"]),
            show_alert=True,
        )
        return

    await callback.answer(
        texts["ticket_use_success"].format(
            spent=result.get("spent", amount),
            remaining=result.get("remaining", max(0, balance - amount)),
        ),
        show_alert=True,
    )
    await show_giveaway_tickets(callback, giveaway_id, texts, state)


@router.callback_query(F.data == "store_lots")
async def store_lots_handler(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    await callback.answer()
    await show_lots_store(callback, state, texts)


@router.callback_query(F.data.startswith("store_lot_"))
async def store_lot_detail_handler(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    await callback.answer()
    await show_lot_detail(
        callback,
        int(callback.data.rsplit("_", 1)[1]),
        texts,
        state,
    )


@router.callback_query(F.data.startswith("store_buy_lot_"))
async def buy_lot_handler(
    callback: types.CallbackQuery, state: FSMContext, texts: dict
):
    lot_id = int(callback.data.rsplit("_", 1)[1])
    result = await db.purchase_store_lot_atomic(
        callback.from_user.id,
        lot_id,
        f"tg:{callback.id}",
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
        return
    await callback.answer(
        texts["store_lot_purchase_success"].format(
            purchase_id=result.get("purchase_id")
        ),
        show_alert=True,
    )
    await show_lot_detail(callback, lot_id, texts, state)
