import logging
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext

from database import db
from services.localization import get_locale
from services.points_service import PointsService
from utils import safe_edit_text

logger = logging.getLogger(__name__)
router = Router()

TICKET_COST = 50

async def show_store_menu(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    user_id = callback.from_user.id
    # texts from middleware

    # Get user data and points
    user = await db.get_user_by_telegram_id(user_id)
    points_data = await db.get_points(user_id)

    if not points_data:
        await PointsService.recalculate_points(user_id)
        points_data = await db.get_points(user_id)

    rp = points_data.get("total_points", 0) if points_data else 0
    tickets = user.get("active_tickets", 0) if user else 0

    text = texts["store_menu_title"].format(rp=rp, tickets=tickets)

    builder = InlineKeyboardBuilder()
    builder.button(text=texts["buy_1_btn"], callback_data="buy_tickets_1")
    builder.button(text=texts["buy_5_btn"], callback_data="buy_tickets_5")
    builder.button(text=texts["buy_10_btn"], callback_data="buy_tickets_10")
    builder.button(text=texts["game_main_menu_btn"], callback_data="game_menu", icon_custom_emoji_id="6042137469204303531", style="danger")
    builder.adjust(3, 1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)

@router.callback_query(F.data == "store_menu")
async def store_menu_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_store_menu(callback, state, texts)

@router.callback_query(F.data.startswith("buy_tickets_"))
async def buy_tickets_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    amount = int(callback.data.split("_")[-1])
    user_id = callback.from_user.id
    # texts from middleware

    cost = amount * TICKET_COST

    points_data = await db.get_points(user_id)
    if not points_data:
        await PointsService.recalculate_points(user_id)
        points_data = await db.get_points(user_id)

    rp = points_data.get("total_points", 0) if points_data else 0

    if rp < cost:
        await callback.answer(texts["not_enough_points"], show_alert=True)
        return

    # Spend RP and add tickets
    await db.add_spent_points(user_id, cost)
    await db.add_active_tickets(user_id, amount)

    # Recalculate total_points to reflect the burn
    await PointsService.recalculate_points(user_id)

    await callback.answer(texts["purchase_success"].format(amount=amount), show_alert=True)
    await show_store_menu(callback, state, texts)
