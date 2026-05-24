import os
import asyncio
import logging
from aiogram import Router, F, types
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder

from pytonconnect import TonConnect
from loader import bot
from database import db
from storage import SupabaseStorage
from utils import safe_edit_text

logger = logging.getLogger(__name__)
router = Router()

BASE_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("CUSTOM_URL", "https://giveaway-bot-hiap.onrender.com")
if not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL
MANIFEST_URL = f"{BASE_URL.rstrip('/')}/tonconnect-manifest.json"

class WalletConnectState(StatesGroup):
    waiting_for_connection = State()

def format_address(address: str) -> str:
    if not address: return "Unknown"
    return f"{address[:6]}...{address[-6:]}"

@router.callback_query(F.data == "start_connect")
async def start_wallet_connect(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    storage = SupabaseStorage(db.client, user_id)
    connector = TonConnect(manifest_url=MANIFEST_URL, storage=storage)

    if await connector.restore_connection() and connector.connected:
        await callback.answer("Wallet is already connected!", show_alert=True)
        return

    # Шаг 1: Статическое меню выбора кошелька без циклов перезаписи сессий
    builder = InlineKeyboardBuilder()
    builder.button(text="Tonkeeper", callback_data="wallet_select:tonkeeper")
    builder.button(text="MyTonWallet", callback_data="wallet_select:mytonwallet")
    builder.button(text="Tonhub", callback_data="wallet_select:tonhub")
    builder.button(text="Telegram Wallet", callback_data="wallet_select:telegram-wallet")
    builder.button(text="❌ Cancel", callback_data="cancel_connect")
    builder.adjust(2)

    connect_text = (
        f"┏┅<tg-emoji emoji-id=\"5316612764427367709\">🔗</tg-emoji>┅ <b>/ WALLET LINKING /</b>\n"
        f"┋\n"
        f"┣ <blockquote>Select your preferred TON wallet.</blockquote>\n"
        f"┋\n"
        f"┗┅┅┅/ Choose a wallet /"
    )
    await safe_edit_text(callback, text=connect_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("wallet_select:"))
async def process_wallet_selection(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    selected_app = callback.data.split(":")[1]

    storage = SupabaseStorage(db.client, user_id)
    connector = TonConnect(manifest_url=MANIFEST_URL, storage=storage)

    wallets = connector.get_wallets()
    target_wallet = None
    for w in wallets:
        if w.get('appName', w.get('app_name')) == selected_app:
            target_wallet = w
            break

    if not target_wallet:
        await callback.answer("Wallet not supported!", show_alert=True)
        return

    # Шаг 2: Генерация сессии ИСКЛЮЧИТЕЛЬНО для одного выбранного кошелька
    res = connector.connect(target_wallet)
    connect_url = await res if asyncio.iscoroutine(res) else res

    builder = InlineKeyboardBuilder()
    builder.button(text=f"Open {target_wallet.get('name', 'Wallet')}", url=connect_url)
    builder.button(text="❌ Cancel", callback_data="cancel_connect")
    builder.adjust(1)

    connect_text = (
        f"┏┅<tg-emoji emoji-id=\"5316612764427367709\">🔗</tg-emoji>┅ <b>/ WALLET LINKING /</b>\n"
        f"┋\n"
        f"┣ <blockquote>Click the button below to open your wallet application. You have 3 minutes to confirm the connection.</blockquote>\n"
        f"┋\n"
        f"┗┅┅┅/ Confirm in App /"
    )
    sent_message = await safe_edit_text(callback, text=connect_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

    await state.set_state(WalletConnectState.waiting_for_connection)
    await state.update_data(connect_msg_id=sent_message.message_id)

    asyncio.create_task(wait_bridge_connection(connector, user_id, chat_id, sent_message.message_id, state))

async def wait_bridge_connection(connector: TonConnect, user_id: int, chat_id: int, msg_id: int, state: FSMContext):
    try:
        await asyncio.wait_for(connector.wait_for_connection(), timeout=180)
        if connector.connected:
            raw_address = connector.wallet.account.address

            # Database transaction: points +100 and save address
            res = await db.client.table("users_game_profile").select("points_balance").eq("id", user_id).execute()
            current_points = 0.0
            if res.data:
                current_points = float(res.data[0].get("points_balance", 0.0))

            # Update profile
            await db.client.table("users_game_profile").upsert({
                "id": user_id,
                "wallet_address": raw_address,
                "points_balance": current_points + 100.0
            }).execute()

            await state.clear()
            success_text = (
                f"┏┅<tg-emoji emoji-id=\"6041731551845159060\">🎉</tg-emoji>┅ <b>/ WALLET CONNECTED /</b>\n"
                f"┋\n"
                f"┣ <b>Address:</b> <code>{format_address(raw_address)}</code>\n"
                f"┣ <b>Bonus:</b> <b>+100 PTS</b> added to your balance!\n"
                f"┋\n"
                f"┗┅┅┅/ Welcome to NOTAPES /"
            )
            await bot.send_message(chat_id=chat_id, text=success_text, parse_mode=ParseMode.HTML)
            try: await bot.delete_message(chat_id, msg_id)
            except: pass
    except asyncio.TimeoutError:
        if await state.get_state() == WalletConnectState.waiting_for_connection:
            await state.clear()
            try: await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="❌ Время ожидания подключения истекло.", parse_mode=ParseMode.HTML)
            except: pass
    except Exception as e:
        logger.error(f"TON Connect error: {e}")
        await state.clear()

@router.callback_query(F.data == "cancel_connect", WalletConnectState.waiting_for_connection)
async def cancel_wallet_connect(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit_text(callback, text="❌ Подключение отменено.", parse_mode=ParseMode.HTML)
