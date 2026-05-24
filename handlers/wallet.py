import os
import asyncio
import logging
from aiogram import Router, F, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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

# Manifest URL - should point to the Flask endpoint
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("CUSTOM_URL", "https://giveaway-bot-hiap.onrender.com")
if not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL
MANIFEST_URL = f"{BASE_URL.rstrip('/')}/tonconnect-manifest.json"

class WalletConnectState(StatesGroup):
    waiting_for_connection = State()

def format_address(address: str) -> str:
    """Safely formats TON address for display if Address utility is missing."""
    if not address:
        return "Unknown"
    if len(address) <= 12:
        return address
    return f"{address[:6]}...{address[-6:]}"

@router.callback_query(F.data == "start_connect")
async def start_wallet_connect(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    storage = SupabaseStorage(db.client, user_id)
    connector = TonConnect(manifest_url=MANIFEST_URL, storage=storage)

    # Check for existing connection
    is_restored = await connector.restore_connection()
    if is_restored and connector.connected:
        await callback.answer("Wallet is already connected!", show_alert=True)
        return

    # Получаем список поддерживаемых кошельков
    wallets = connector.get_wallets()
    builder = InlineKeyboardBuilder()

    for wallet in wallets:
        # Проверяем популярные кошельки
        app_name = wallet.get('appName') or wallet.get('app_name')
        if app_name in ['tonkeeper', 'mytonwallet', 'tonhub', 'telegram-wallet']:
            res = connector.connect(wallet)
            connect_url = await res if asyncio.iscoroutine(res) else res
            builder.button(text=wallet.get('name'), url=connect_url)

    builder.button(text="❌ Cancel", callback_data="cancel_connect")
    builder.adjust(2)

    connect_text = (
        f"┏┅<tg-emoji emoji-id=\"5316612764427367709\">🔗</tg-emoji>┅ <b>/ WALLET LINKING /</b>\n"
        f"┋\n"
        f"┣ <blockquote>Select your preferred TON wallet. You have 3 minutes to confirm the action in your wallet application.</blockquote>\n"
        f"┋\n"
        f"┗┅┅┅/ Choose a wallet /"
    )

    sent_message = await safe_edit_text(callback, connect_text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

    await state.set_state(WalletConnectState.waiting_for_connection)
    await state.update_data(connect_msg_id=sent_message.message_id)

    # Start background waiter
    asyncio.create_task(
        wait_bridge_connection(connector, user_id, chat_id, sent_message.message_id, state)
    )

async def wait_bridge_connection(connector: TonConnect, user_id: int, chat_id: int, msg_id: int, state: FSMContext):
    try:
        # Обертываем в asyncio.wait_for для корректной работы таймаута в библиотеке pytonconnect
        await asyncio.wait_for(connector.wait_for_connection(), timeout=180)

        if connector.connected:
            raw_address = connector.wallet.account.address

            # Use raw address for DB, but format for display
            friendly_address_display = format_address(raw_address)

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
                f"┣ <b>Address:</b> <code>{friendly_address_display}</code>\n"
                f"┣ <b>Bonus:</b> <b>+100 PTS</b> added to your balance!\n"
                f"┋\n"
                f"┗┅┅┅/ Welcome to NOTAPES /"
            )

            await bot.send_message(
                chat_id=chat_id,
                text=success_text,
                parse_mode=ParseMode.HTML
            )

            try:
                await bot.delete_message(chat_id, msg_id)
            except Exception:
                pass

    except asyncio.TimeoutError:
        current_state = await state.get_state()
        if current_state == WalletConnectState.waiting_for_connection:
            await state.clear()
            timeout_text = (
                f"┏┅<tg-emoji emoji-id=\"5258420634785947640\">🔄</tg-emoji>┅ <b>/ SESSION EXPIRED /</b>\n"
                f"┋\n"
                f"┣ <blockquote>The 3-minute waiting period has ended. Please restart the process to link your wallet.</blockquote>\n"
                f"┋\n"
                f"┗┅┅┅/ #NOTAPES /"
            )
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=timeout_text,
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"TON Connect error: {e}")
        await state.clear()

@router.callback_query(F.data == "cancel_connect", WalletConnectState.waiting_for_connection)
async def cancel_wallet_connect(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    cancel_text = (
        f"┏┅<tg-emoji emoji-id=\"5258420634785947640\">🔄</tg-emoji>┅ <b>/ LINKING CANCELED /</b>\n"
        f"┋\n"
        f"┣ <blockquote>The wallet linking process has been canceled by the user. Internal descriptors remain unchanged.</blockquote>\n"
        f"┋\n"
        f"┗┅┅┅/ #NOTAPES /"
    )
    await safe_edit_text(callback, cancel_text, parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "unlink_wallet_request")
async def process_unlink_wallet(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    await db.unlink_wallet(user_id)
    await callback.answer("🔄 Кошелек успешно отключен от вашего профиля!", show_alert=True)

    # Refresh profile view - using a hack to import here to avoid circular dependencies
    from handlers.game_menu import open_profile
    await open_profile(callback)
