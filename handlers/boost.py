import asyncio
import html
import os

from aiogram import F, Router, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import db
from services.gram_service import GramDepositService
from utils import safe_edit_text

router = Router()


async def show_boost(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    nft, sticker, rate = await asyncio.gather(
        db.get_setting("boost_nft_purchase_rp"), db.get_setting("boost_sticker_purchase_rp"),
        db.get_setting("gram_rp_per_gram"),
    )
    wallet = os.getenv("GRAM_DEPOSIT_WALLET") or texts["boost_not_configured"]
    builder = InlineKeyboardBuilder()
    builder.button(text=texts["boost_check_btn"], callback_data="boost_check", style="success")
    builder.button(text=texts["game_back_btn"], callback_data="game_menu",
                   icon_custom_emoji_id="5877629862306385808")
    builder.adjust(1)
    await safe_edit_text(callback, texts["boost_title"].format(
        holder=50, nft=nft or 0, sticker=sticker or 0, rate=rate or 10,
        wallet=html.escape(wallet), username=html.escape("@" + (callback.from_user.username or "username")),
    ), reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML, state=state)


@router.callback_query(F.data == "boost_menu")
async def boost_menu(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await callback.answer()
    await show_boost(callback, state, texts)


@router.callback_query(F.data == "boost_check")
async def boost_check(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    before = (await db.get_points(callback.from_user.id) or {}).get("total_points", 0)
    credited = await GramDepositService.sync()
    after = (await db.get_points(callback.from_user.id) or {}).get("total_points", 0)
    await callback.answer(texts["boost_check_result"].format(added=max(0, after - before), processed=credited), show_alert=True)
    await show_boost(callback, state, texts)
