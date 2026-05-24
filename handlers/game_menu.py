import html
import aiohttp
import time
from aiogram import Router, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from database import db
from utils import safe_edit_text, to_raw_address
from loader import bot
from storage import SupabaseStorage
from pytonconnect import TonConnect

router = Router()

ADMINS_TO_NOTIFY = [786080766, 734720997]
STICKERS_API_URL = "https://stickers.tools/api/v1/launching/packs/0:81abce045d81dc32c42aebc27b1ad6898bb4f89306231d2b58031908a4c267c7/holders"

# Simple memory cache for holders
holders_cache = {
    "data": [],
    "last_updated": 0
}
CACHE_TTL = 300 # 5 minutes

class ShopStates(StatesGroup):
    select_quantity = State()

async def fetch_all_api_holders():
    """Asynchronously loop through the Stickers Tools API offsets with caching."""
    global holders_cache
    now = time.time()

    if holders_cache["data"] and (now - holders_cache["last_updated"] < CACHE_TTL):
        return holders_cache["data"]

    all_holders = []
    offset = 0
    limit = 100
    success_complete = False

    async with aiohttp.ClientSession() as session:
        while True:
            url = f"{STICKERS_API_URL}?offset={offset}&limit={limit}"
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        break
                    json_data = await resp.json()
                    if not json_data.get("success") or not json_data.get("data"):
                        break
                    holders = json_data["data"].get("holders", [])
                    all_holders.extend(holders)

                    if not json_data["data"].get("hasMore") or not holders:
                        success_complete = True
                        break
                    offset += len(holders)
            except Exception:
                break

    if success_complete and all_holders:
        holders_cache["data"] = all_holders
        holders_cache["last_updated"] = now

    return all_holders if success_complete else (holders_cache["data"] or [])

@router.callback_query(F.data == "game_main")
async def open_game_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    builder = InlineKeyboardBuilder()

    # Задача 1: Кастомные эмодзи вынесены в icon_custom_emoji_id
    builder.button(text='Profile & Wallet', callback_data="game_profile", icon_custom_emoji_id="5260399854500191689")
    builder.button(text='Limited Shop', callback_data="game_shop", icon_custom_emoji_id="5920332557466997677")
    builder.button(text='Leaderboard', callback_data="game_leaderboard", icon_custom_emoji_id="5258330865674494479")
    builder.button(text='Главное меню', callback_data="main_menu", icon_custom_emoji_id="5257963315258204021")
    builder.adjust(1)

    game_text = (
        "┏┅<tg-emoji emoji-id=\"5258508428212445001\">🎮</tg-emoji>┅ <b>/ NOTAPES ARCADE /</b>\n"
        "┋\n"
        "┣ <blockquote>Welcome to the high-performance Game Matrix. Holding authorized asset packs yields passive point generation variables every 24 hours. Acquire limited drops directly from this node.</blockquote>\n"
        "┋\n"
        "┗┅┅┅/ #NOTAPES /"
    )
    await safe_edit_text(callback, game_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "game_profile")
async def open_profile(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    profile = await db.get_game_profile(user_id)
    if not profile:
        await db.create_initial_profile(user_id)
        profile = {"wallet_address": None, "points_balance": 0.0, "packs_count": 0}

    wallet = profile.get("wallet_address")
    wallet_str = f"<code>{wallet[:6]}...{wallet[-6:]}</code>" if wallet else "❌ Not Connected"

    # Dynamic pack verification
    packs_count = 0
    if wallet:
        try:
            user_raw = to_raw_address(wallet)
            api_holders = await fetch_all_api_holders()
            for holder in api_holders:
                if to_raw_address(holder.get("addr")) == user_raw:
                    packs_count = holder.get("count", 0)
                    break
        except Exception:
            packs_count = 0

    builder = InlineKeyboardBuilder()
    if not wallet:
        builder.button(text='Connect TON Wallet', callback_data="connect_ton_wallet", icon_custom_emoji_id="5316612764427367709")
    else:
        builder.button(text='Disconnect Wallet', callback_data="unlink_wallet_request", icon_custom_emoji_id="5258420634785947640")

    builder.button(text='◀️ Назад', callback_data="game_main")
    builder.button(text='В главное меню', callback_data="main_menu", icon_custom_emoji_id="5257963315258204021")
    builder.adjust(1)

    profile_text = (
        f"┏┅<tg-emoji emoji-id=\"5260399854500191689\">👤</tg-emoji>┅ <b>/ USER PROFILE /</b>\n"
        f"┋\n"
        f"┣ <blockquote>Personal account statistics and cryptographic connection metadata. Verify token states and balances below.</blockquote>\n"
        f"┋\n"
        f"┣ <b>User ID:</b> <code>{user_id}</code>\n"
        f"┣ <b>TON Wallet:</b> {wallet_str}\n"
        f"┣ <b>Packs Held:</b> <code>{packs_count} NFT</code>\n"
        f"┣ <b>Points Balance:</b> <code>{profile.get('points_balance', 0.0)} </code>\n"
        f"┋\n"
        f"┗┅┅┅/ #NOTAPES /"
    )
    await safe_edit_text(callback, profile_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "game_shop")
async def open_shop(callback: types.CallbackQuery, state: FSMContext = None):
    await callback.answer()
    if state:
        await state.clear()
    items = await db.get_shop_items()
    builder = InlineKeyboardBuilder()
    for item in items:
        if item['stock_limit'] > 0:
            builder.button(text=f"{item['title']} — {item['price']} PTS ({item['stock_limit']} left)", callback_data=f"buy_item_{item['id']}")

    # Задача 3: Раздельные кнопки Назад и В главное меню
    builder.button(text='◀️ Назад', callback_data="game_main")
    builder.button(text='В главное меню', callback_data="main_menu", icon_custom_emoji_id="5257963315258204021")
    builder.adjust(1)

    shop_text = (
        "┏┅<tg-emoji emoji-id=\"5920332557466997677\">🏪</tg-emoji>┅ <b>/ LIMITED DROP SHOP /</b>\n"
        "┋\n"
        "┣ <blockquote>Exchange your point assets for rare items. Allocations are finite and subject to strict supply ceilings. Real-time quantities update automatically upon transaction.</blockquote>\n"
        "┋\n"
        "┗┅┅┅/ #NOTAPES /"
    )
    await safe_edit_text(callback, shop_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("buy_item_"))
async def handle_buy_item(callback: types.CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split("_")[2])
    item = await db.get_shop_item_by_id(item_id)
    if not item:
        await callback.answer("Item not found.", show_alert=True)
        return

    await state.update_data(buy_item_id=item_id, buy_item_price=item['price'], buy_item_title=item['title'], buy_item_qty=1)
    await render_quantity_menu(callback, item['title'], 1, item['price'])
    await state.set_state(ShopStates.select_quantity)

async def render_quantity_menu(callback, title, qty, price):
    total = qty * price
    builder = InlineKeyboardBuilder()
    builder.button(text="-1", callback_data="qty_minus_1")
    builder.button(text=str(qty), callback_data="qty_current")
    builder.button(text="+1", callback_data="qty_plus_1")
    builder.button(text=f"Confirm Purchase ({total} PTS)", callback_data="confirm_buy_item", style="success")
    builder.button(text="Cancel", callback_data="game_shop", style="danger")
    builder.adjust(3, 1, 1)

    text = f"<b>Buying {html.escape(title)}</b>\n\nSelect quantity:"
    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(ShopStates.select_quantity)
async def process_qty_change(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    current_qty = data.get("buy_item_qty", 1)
    item_id = data.get("buy_item_id")
    price = data.get("buy_item_price")
    title = data.get("buy_item_title")

    if callback.data == "qty_minus_1":
        if current_qty > 1:
            current_qty -= 1
            await state.update_data(buy_item_qty=current_qty)
            return await render_quantity_menu(callback, title, current_qty, price)
        await callback.answer()
    elif callback.data == "qty_plus_1":
        current_qty += 1
        await state.update_data(buy_item_qty=current_qty)
        return await render_quantity_menu(callback, title, current_qty, price)
    elif callback.data == "confirm_buy_item":
        await callback.answer()
        # Verify stock again
        item = await db.get_shop_item_by_id(item_id)
        if not item or item['stock_limit'] < current_qty:
             live_stock = item['stock_limit'] if item else 0
             await callback.answer(f"Insufficient stock! Available: {live_stock}", show_alert=True)
             await state.update_data(buy_item_qty=live_stock)
             return await render_quantity_menu(callback, title, live_stock, price)

        user_id = callback.from_user.id
        profile = await db.get_game_profile(user_id)

        current_price = float(item['price'])
        total_cost = current_qty * current_price

        if float(profile.get("points_balance", 0.0)) < total_cost:
            await callback.answer("🚨 Недостаточно очков для покупки!", show_alert=True)
            return

        order_id = await db.process_purchase(user_id, item_id, current_qty, total_cost)
        if order_id:
            await callback.answer("🎉 Purchase successfully completed!", show_alert=True)

            success_text = (
                f"┏┅<tg-emoji emoji-id=\"6041731551845159060\">🎉</tg-emoji>┅ <b>/ ORDER #{order_id} CREATED /</b>\n"
                f"┋\n"
                f"┣ <blockquote>Your order has been successfully generated and passed to the processing system. Stock allocation is complete.</blockquote>\n"
                f"┋\n"
                f"┣ <b>@klassikaone</b> will contact you shortly for delivery.\n"
                f"┋\n"
                f"┣ <b>Details:</b> {current_qty}x {html.escape(title)}\n"
                f"┗┅┅┅/ Spent: {total_cost} PTS /"
            )
            builder = InlineKeyboardBuilder()
            builder.button(text='Shop', callback_data="game_shop", icon_custom_emoji_id="5920332557466997677")
            builder.button(text='В главное меню', callback_data="main_menu", icon_custom_emoji_id="5257963315258204021")
            builder.adjust(1)
            await safe_edit_text(callback, success_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

            buyer_username = f"@{callback.from_user.username}" if callback.from_user.username else f"ID: {user_id}"
            admin_alert_text = (
                f"┏┅<tg-emoji emoji-id=\"5260249440450520061\">🤚</tg-emoji>┅ <b>/ NEW ORDER /</b>\n"
                f"┋\n"
                f"┣ <blockquote>New purchase notification received. Manual verification and asset delivery required.</blockquote>\n"
                f"┋\n"
                f"┣ <b>Order Number:</b> <code>#{order_id}</code>\n"
                f"┣ <b>Buyer:</b> {buyer_username} (<code>{user_id}</code>)\n"
                f"┣ <b>Items:</b> {current_qty}x <b>{html.escape(title)}</b>\n"
                f"┋\n"
                f"┗┅┅┅/ Deliver Order /"
            )
            for admin_id in ADMINS_TO_NOTIFY:
                try:
                    await bot.send_message(admin_id, admin_alert_text, parse_mode=ParseMode.HTML)
                except Exception:
                    pass
            await state.clear()
        else:
            await callback.answer("Ошибка транзакции базы данных или недостаточно средств/товара.", show_alert=True)
    else:
        await render_quantity_menu(callback, title, current_qty, price)

@router.callback_query(F.data == "connect_ton_wallet")
async def handle_connect_wallet(callback: types.CallbackQuery, state: FSMContext):
    from handlers.wallet import start_wallet_connect
    await start_wallet_connect(callback, state)

@router.callback_query(F.data == "disconnect_ton_wallet")
async def handle_disconnect_wallet(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    from handlers.wallet import MANIFEST_URL
    # Задача 2: Передаем динамический db.client, чтобы избежать AttributeError 'NoneType'
    storage = SupabaseStorage(db.client, user_id)
    connector = TonConnect(manifest_url=MANIFEST_URL, storage=storage)

    is_restored = await connector.restore_connection()
    if is_restored and connector.connected:
        await connector.disconnect()

    await db.unlink_wallet(user_id)

    disconnect_text = (
        "┏┅<tg-emoji emoji-id=\"5258420634785947640\">🔄</tg-emoji>┅ <b>/ WALLET DISCONNECTED /</b>\n"
        "┋\n"
        "┣ <blockquote>The cryptographic address has been successfully unlinked from your gaming profile. Internal descriptors are cleared. Points accumulation from NFT packs is frozen.</blockquote>\n"
        "┋\n"
        "┗┅┅┅/ #NOTAPES /"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад в профиль", callback_data="game_profile")
    builder.button(text='В главное меню', callback_data="main_menu", icon_custom_emoji_id="5257963315258204021")
    builder.adjust(1)

    await safe_edit_text(callback, disconnect_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "game_leaderboard")
async def open_leaderboard(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    profile = await db.get_game_profile(user_id)
    user_wallet = profile.get("wallet_address") if profile else None
    user_wallet_raw = to_raw_address(user_wallet)

    api_holders = await fetch_all_api_holders()

    leader_rows = ""
    user_in_top_10 = False
    user_rank_data = None

    for idx, holder in enumerate(api_holders, 1):
        addr = holder.get("addr", "Unknown")
        count = holder.get("count", 0)
        short_addr = f"{addr[:6]}...{addr[-4:]}"

        if idx <= 10:
            leader_rows += f"┋ <b>{idx}.</b> <code>{short_addr}</code> — {count} packs\n"

        if user_wallet_raw and to_raw_address(addr) == user_wallet_raw:
            user_in_top_10 = idx <= 10
            user_rank_data = (idx, short_addr, count)

    if user_wallet and not user_in_top_10:
        leader_rows += "┋ ┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
        if user_rank_data:
            leader_rows += f"┋ <b>{user_rank_data[0]}.</b> <code>{user_rank_data[1]}</code> (Вы) — {user_rank_data[2]} packs\n"
        else:
            short_user_w = f"{user_wallet[:6]}...{user_wallet[-4:]}"
            leader_rows += f"┋ <b>Н/А.</b> <code>{short_user_w}</code> (Вы) — 0 packs\n"

    builder = InlineKeyboardBuilder()
    # Задача 3: Раздельная навигация на одной строчке
    builder.button(text='◀️ Назад', callback_data="game_main")
    builder.button(text='В главное меню', callback_data="main_menu", icon_custom_emoji_id="5257963315258204021")
    builder.adjust(2)

    leader_text = (
        "┏┅<tg-emoji emoji-id=\"5258330865674494479\">🍑</tg-emoji>┅ <b>/ PACK HOLDERS LEADERBOARD /</b>\n"
        "┋\n"
        "┣ <blockquote>Global ranking of tokenized collection distribution. Data is synchronized in real-time directly via the Stickers Tools API aggregator.</blockquote>\n"
        "┋\n"
        f"{leader_rows}"
        "┋\n"
        "┗┅┅┅/ Live Blockchain Parsing /"
    )
    await safe_edit_text(callback, leader_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
