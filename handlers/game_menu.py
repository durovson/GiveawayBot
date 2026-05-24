import html
import aiohttp
import time
from aiogram import Router, types, F
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from database import db
from utils import safe_edit_text
from loader import bot, tonconnect_manager

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

                    if not json_data["data"].get("hasMore") or len(holders) < limit:
                        success_complete = True
                        break
                    offset += limit
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
    builder.button(text='<tg-emoji emoji-id="5260399854500191689">👤</tg-emoji> Profile & Wallet', callback_data="game_profile")
    builder.button(text='🏪 <tg-emoji emoji-id="5920332557466997677">🏪</tg-emoji> Limited Shop', callback_data="game_shop")
    builder.button(text='🍑 <tg-emoji emoji-id="5258330865674494479">🍑</tg-emoji> Leaderboard', callback_data="game_leaderboard")
    builder.button(text='🏘 <tg-emoji emoji-id="5257963315258204021">🏘</tg-emoji> Main Menu', callback_data="main_menu")
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

    builder = InlineKeyboardBuilder()
    if not wallet:
        builder.button(text='<tg-emoji emoji-id="5316612764427367709">🔗</tg-emoji> Connect TON Wallet', callback_data="connect_ton_wallet")
    else:
        builder.button(text='<tg-emoji emoji-id="5258420634785947640">🔄</tg-emoji> Disconnect Wallet', callback_data="disconnect_ton_wallet")
    builder.button(text='🏘 <tg-emoji emoji-id="5257963315258204021">🏘</tg-emoji> Back to Arcade', callback_data="game_main")
    builder.adjust(1)

    profile_text = (
        f"┏┅<tg-emoji emoji-id=\"5260399854500191689\">👤</tg-emoji>┅ <b>/ USER PROFILE /</b>\n"
        f"┋\n"
        f"┣ <blockquote>Personal account statistics and cryptographic connection metadata. Verify token states and balances below.</blockquote>\n"
        f"┋\n"
        f"┣ <b>User ID:</b> <code>{user_id}</code>\n"
        f"┣ <b>TON Wallet:</b> {wallet_str}\n"
        f"┣ <b>Packs Held:</b> <code>{profile.get('packs_count', 0)} NFT</code>\n"
        f"┣ <b>Points Balance:</b> <code>{profile.get('points_balance', 0.0)} $PTS</code>\n"
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
    builder.button(text='🏘 <tg-emoji emoji-id="5257963315258204021">🏘</tg-emoji> Back to Arcade', callback_data="game_main")
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
async def setup_quantity_selector(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    item_id = int(callback.data.split("_")[2])
    item = await db.get_shop_item_by_id(item_id)
    if not item or item['stock_limit'] <= 0:
        await callback.answer("This item is out of stock!", show_alert=True)
        return

    await state.set_state(ShopStates.select_quantity)
    await state.update_data(item_id=item_id, current_qty=1, max_qty=item['stock_limit'], price=float(item['price']))
    await render_quantity_menu(callback, item['title'], 1, float(item['price']))

async def render_quantity_menu(callback: types.CallbackQuery, title: str, qty: int, price: float):
    builder = InlineKeyboardBuilder()
    builder.button(text="– 1", callback_data="qty_minus")
    builder.button(text='<tg-emoji emoji-id="5258134813302332906">📦</tg-emoji> Кол-во: ' + str(qty), callback_data="qty_ignore")
    builder.button(text="+ 1", callback_data="qty_plus")
    builder.button(text='<tg-emoji emoji-id="5260726538302660868">✅</tg-emoji> Купить за ' + str(qty * price) + ' PTS', callback_data="qty_confirm")
    builder.button(text='🏘 <tg-emoji emoji-id="5257963315258204021">🏘</tg-emoji> Отмена', callback_data="game_shop")
    builder.adjust(3, 1, 1)

    menu_text = (
        f"┏┅🏘 <tg-emoji emoji-id=\"5257963315258204021\">🏘</tg-emoji>┅ <b>/ НАСТРОЙКА ПОКУПКИ /</b>\n"
        f"┋\n"
        f"┣ <blockquote>Укажите точный объем партий для резервирования. Изменение балансов пересчитывается без дополнительных сетевых вызовов базы.</blockquote>\n"
        f"┋\n"
        f"┣ <b>Предмет:</b> {html.escape(title)}\n"
        f"┋\n"
        f"┗┅┅┅/ Итого: {qty * price} PTS /"
    )
    await safe_edit_text(callback, menu_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(ShopStates.select_quantity)
async def process_quantity_change(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if callback.data == "game_shop":
        await state.clear()
        return await open_shop(callback)

    if not callback.data.startswith("qty_"):
        return

    data = await state.get_data()
    current_qty, item_id, price = data['current_qty'], data['item_id'], data['price']
    item = await db.get_shop_item_by_id(item_id)
    if not item:
        await callback.answer("🚨 Item no longer available.", show_alert=True)
        await state.clear()
        return await open_shop(callback)

    title = item['title']
    live_stock = item['stock_limit']

    if callback.data == "qty_minus" and current_qty > 1:
        current_qty -= 1
        # Check if current_qty is now within live stock just in case
        current_qty = min(current_qty, live_stock)
        await state.update_data(current_qty=current_qty)
        await render_quantity_menu(callback, title, current_qty, price)
    elif callback.data == "qty_plus" and current_qty < live_stock:
        current_qty += 1
        await state.update_data(current_qty=current_qty)
        await render_quantity_menu(callback, title, current_qty, price)
    elif callback.data == "qty_confirm":
        # Cap current_qty to live_stock if it somehow exceeded it
        if current_qty > live_stock:
             await callback.answer(f"🚨 Stock updated. Max available: {live_stock}", show_alert=True)
             await state.update_data(current_qty=live_stock)
             return await render_quantity_menu(callback, title, live_stock, price)

        user_id = callback.from_user.id
        profile = await db.get_game_profile(user_id)

        # Calculate total cost using latest price from database
        current_price = float(item['price'])
        total_cost = current_qty * current_price

        if float(profile.get("points_balance", 0.0)) < total_cost:
            await callback.answer("🚨 Недостаточно очков для покупки!", show_alert=True)
            return

        order_id = await db.process_purchase(user_id, item_id, current_qty, total_cost)
        if order_id:
            await callback.answer("🎉 Покупка успешно оформлена!", show_alert=True)

            success_text = (
                f"┏┅<tg-emoji emoji-id=\"6041731551845159060\">🎉</tg-emoji>┅ <b>/ ЗАКАЗ №{order_id} ОФОРМЛЕН /</b>\n"
                f"┋\n"
                f"┣ <blockquote>Ваш заказ успешно сгенерирован и передан в систему обработки. Распределение складских остатков завершено.</blockquote>\n"
                f"┋\n"
                f"┣ Скоро с вами свяжется <b>@klassikaone</b> для получения.\n"
                f"┋\n"
                f"┣ <b>Детали:</b> {current_qty}x {html.escape(title)}\n"
                f"┗┅┅┅/ Списано: {total_cost} PTS /"
            )
            builder = InlineKeyboardBuilder()
            builder.button(text='🏪 <tg-emoji emoji-id="5920332557466997677">🏪</tg-emoji> Магазин', callback_data="game_shop")
            await safe_edit_text(callback, success_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

            buyer_username = f"@{callback.from_user.username}" if callback.from_user.username else f"ID: {user_id}"
            admin_alert_text = (
                f"┏┅🤚 <tg-emoji emoji-id=\"5260249440450520061\">🤚</tg-emoji>┅ <b>/ НОВЫЙ ЗАКАЗ /</b>\n"
                f"┋\n"
                f"┣ <blockquote>Получено новое уведомление о покупке. Требуется ручная сверка и выдача ассетов.</blockquote>\n"
                f"┋\n"
                f"┣ <b>Номер заказа:</b> <code>#{order_id}</code>\n"
                f"┣ <b>Покупатель:</b> {buyer_username} (<code>{user_id}</code>)\n"
                f"┣ <b>Что приобрел:</b> {current_qty}x <b>{html.escape(title)}</b>\n"
                f"┋\n"
                f"┗┅┅┅/ Выдать заказ /"
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
        # For ignore and other qty_ cases, just re-render to keep the menu active
        await render_quantity_menu(callback, title, current_qty, price)

@router.callback_query(F.data == "connect_ton_wallet")
async def handle_connect_wallet(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id

    # Инициализируем коннектор под текущего пользователя через менеджер
    connector = tonconnect_manager.get_connector(user_id)

    # Генерируем универсальную ссылку для подключения (подходит для большинства кошельков)
    wallets = connector.get_wallets()
    # Запрашиваем дефолтную универсальную ссылку подключения
    generated_url = await connector.connect(wallets[0] if wallets else "tonkeeper")

    connect_text = (
        "┏┅<tg-emoji emoji-id=\"5316612764427367709\">🔗</tg-emoji>┅ <b>/ TON CONNECT ACTIVATION /</b>\n"
        "┋\n"
        "┣ <blockquote>Для успешной привязки криптографического кошелька нажмите на кнопку генерации сессии ниже. Вы будете автоматически перенаправлены в интерфейс приложения.</blockquote>\n"
        "┋\n"
        "┗┅┅┅/ Ссылка активна 3 минуты /"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Connect via Wallet App", url=generated_url)
    builder.button(text="◀️ Отмена", callback_data="game_profile")
    builder.adjust(1)

    await safe_edit_text(callback, connect_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "disconnect_ton_wallet")
async def handle_disconnect_wallet(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    # 1. Сбрасываем активный сетевой мост в библиотеке
    connector = tonconnect_manager.get_connector(user_id)
    if connector.connected:
        await connector.disconnect()

    # 2. Обнуляем записи структуры данных в Supabase
    await db.unlink_wallet(user_id)

    disconnect_text = (
        "┏┅<tg-emoji emoji-id=\"5258420634785947640\">🔄</tg-emoji>┅ <b>/ WALLET DISCONNECTED /</b>\n"
        "┋\n"
        "┣ <blockquote>Криптографический адрес успешно отвязан от игрового профиля. Внутренние дескрипторы очищены. Пассивное накопление очков за владение NFT-паками заморожено.</blockquote>\n"
        "┋\n"
        "┗┅┅┅/ #NOTAPES /"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ В профиль", callback_data="game_profile")
    builder.adjust(1)

    await safe_edit_text(callback, disconnect_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "game_leaderboard")
async def open_leaderboard(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    profile = await db.get_game_profile(user_id)
    user_wallet = profile.get("wallet_address") if profile else None

    # Fetch ALL data dynamically from Stickers Tools API with caching
    api_holders = await fetch_all_api_holders()

    # Build Top 10 rows
    leader_rows = ""
    user_in_top_10 = False
    user_rank_data = None

    for idx, holder in enumerate(api_holders, 1):
        addr = holder.get("addr", "Unknown")
        count = holder.get("count", 0)
        short_addr = f"{addr[:6]}...{addr[-4:]}"

        if idx <= 10:
            leader_rows += f"┋ <b>{idx}.</b> <code>{short_addr}</code> — {count} packs\n"

        if user_wallet and addr.lower() == user_wallet.lower():
            user_in_top_10 = idx <= 10
            user_rank_data = (idx, short_addr, count)

    # Append separate row if user is NOT in the top 10 rows
    if user_wallet and not user_in_top_10:
        leader_rows += "┋ ┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n"
        if user_rank_data:
            leader_rows += f"┋ <b>{user_rank_data[0]}.</b> <code>{user_rank_data[1]}</code> (Вы) — {user_rank_data[2]} packs\n"
        else:
            short_user_w = f"{user_wallet[:6]}...{user_wallet[-4:]}"
            leader_rows += f"┋ <b>Н/А.</b> <code>{short_user_w}</code> (Вы) — 0 packs\n"

    builder = InlineKeyboardBuilder()
    builder.button(text='🏘 <tg-emoji emoji-id="5257963315258204021">🏘</tg-emoji> Back to Arcade', callback_data="game_main")
    builder.adjust(1)

    leader_text = (
        "┏┅🍑 <tg-emoji emoji-id=\"5258330865674494479\">🍑</tg-emoji>┅ <b>/ PACK HOLDERS LEADERBOARD /</b>\n"
        "┋\n"
        "┣ <blockquote>Глобальный рейтинг распределения токенизированных коллекций. Данные синхронизируются в реальном времени напрямую через агрегатор Stickers Tools API.</blockquote>\n"
        "┋\n"
        f"{leader_rows}"
        "┋\n"
        "┗┅┅┅/ Live Blockchain Parsing /"
    )
    await safe_edit_text(callback, leader_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
