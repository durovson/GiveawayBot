import os
import json
import asyncio
import logging
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from pytonconnect import TonConnect
from pytonconnect.storage import IStorage
from datetime import datetime
import secrets

from database import db
from utils import safe_edit_text, safe_bot_edit_text, raw_to_user_friendly
from loader import bot

logger = logging.getLogger(__name__)
router = Router()

# Dynamic MANIFEST_URL
BASE_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("CUSTOM_URL", "https://giveaway-bot-hiap.onrender.com")
if not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL
MANIFEST_URL = f"{BASE_URL.rstrip('/')}/tonconnect-manifest.json"

class WalletConnectState(StatesGroup):
    waiting_for_connection = State()

class SupabaseStorage(IStorage):
    def __init__(self, supabase_client, user_id: int):
        self.supabase = supabase_client
        self.user_id = user_id

    async def set_item(self, key: str, value: str) -> None:
        await self.supabase.table("ton_connect_sessions").upsert({
            "user_id": int(self.user_id),
            "key": str(key),
            "value": str(value),
            "updated_at": datetime.now().isoformat()
        }).execute()

    async def get_item(self, key: str, default_value: str = None) -> str:
        response = await self.supabase.table("ton_connect_sessions") \
            .select("value") \
            .eq("user_id", int(self.user_id)) \
            .eq("key", str(key)) \
            .execute()

        data = response.data
        if data and len(data) > 0:
            return data[0]["value"]
        return default_value

    async def remove_item(self, key: str) -> None:
        await self.supabase.table("ton_connect_sessions") \
            .delete() \
            .eq("user_id", int(self.user_id)) \
            .eq("key", str(key)) \
            .execute()

def format_address(address: str) -> str:
    if not address:
        return "Unknown"

    # Принудительно конвертируем сырой hex (0:...) в красивый UQ...
    friendly_addr = raw_to_user_friendly(address)
    return f"{friendly_addr[:6]}...{friendly_addr[-6:]}"

@router.callback_query(F.data == "wallet_menu")
async def wallet_menu_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    wallet = await db.get_user_wallet(user_id)

    if wallet:
        formatted_addr = format_address(wallet)
        text = (
            "<b>💳 Wallet connected!</b>\n\n"
            f"<blockquote>Your address: <code>{formatted_addr}</code></blockquote>\n\n"
            "You can disconnect your wallet if you want to link another one."
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="Disconnect", callback_data="disconnect_wallet")
        builder.button(text="Back", callback_data="game_menu")
        builder.adjust(1)
    else:
        text = (
            "<b>💳 Wallet not connected</b>\n\n"
            "<blockquote>Connect your TON wallet to verify ownership and participate in the ecosystem.</blockquote>"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="Connect Wallet", callback_data="connect_wallet")
        builder.button(text="Back", callback_data="game_menu")
        builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "connect_wallet")
async def start_wallet_connect(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    storage = SupabaseStorage(db.client, user_id)
    connector = TonConnect(manifest_url=MANIFEST_URL, storage=storage)

    if await connector.restore_connection() and connector.connected:
        await callback.answer("Wallet is already connected!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="Tonkeeper", callback_data="wallet_select:tonkeeper")
    builder.button(text="MyTonWallet", callback_data="wallet_select:mytonwallet")
    builder.button(text="Tonhub", callback_data="wallet_select:tonhub")
    builder.button(text="Telegram Wallet", callback_data="wallet_select:telegram-wallet")
    builder.button(text="Back", callback_data="wallet_menu")
    builder.adjust(2)

    await safe_edit_text(callback, text="<b>💳 Select your TON wallet:</b>", reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data.startswith("wallet_select:"))
async def process_wallet_selection(callback: types.CallbackQuery, state: FSMContext):
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

    res = connector.connect(target_wallet)
    connect_url = await res if asyncio.iscoroutine(res) else res

    builder = InlineKeyboardBuilder()
    builder.button(text=f"Open {target_wallet.get('name', 'Wallet')}", url=connect_url)
    builder.button(text="❌ Cancel", callback_data="wallet_menu")
    builder.adjust(1)

    sent_message = await safe_edit_text(callback, text="<b>🔗 Confirm connection in your wallet application.</b>", reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

    await state.set_state(WalletConnectState.waiting_for_connection)
    asyncio.create_task(wait_bridge_connection(connector, user_id, chat_id, sent_message.message_id, state))

async def wait_bridge_connection(connector: TonConnect, user_id: int, chat_id: int, msg_id: int, state: FSMContext):
    try:
        await asyncio.wait_for(connector.wait_for_connection(), timeout=180)
        if connector.connected:
            raw_address = connector.wallet.account.address

            # Save address to our users table
            await db.update_user_wallet(user_id, raw_address)

            await state.clear()

            friendly_addr = format_address(raw_address)
            await bot.send_message(chat_id=user_id, text=f"<b>🎉 Wallet successfully connected!</b>\nAddress: <code>{friendly_addr}</code>", parse_mode=ParseMode.HTML)

    except asyncio.TimeoutError:
        await state.clear()
        try:
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="❌ Connection timeout reached.", parse_mode=ParseMode.HTML)
        except:
            pass
    except Exception as e:
        logger.error(f"Error in wait_bridge_connection: {e}")
        await state.clear()

@router.callback_query(F.data == "disconnect_wallet")
async def disconnect_wallet_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    storage = SupabaseStorage(db.client, user_id)
    connector = TonConnect(MANIFEST_URL, storage)

    try:
        if await connector.restore_connection():
            await connector.disconnect()

        await db.update_user_wallet(user_id, None)

        # Clear sessions for this user in Supabase
        await db.client.table("ton_connect_sessions").delete().eq("user_id", user_id).execute()

        await wallet_menu_handler(callback)
    except Exception as e:
        logger.error(f"Error disconnecting wallet: {e}")
        await callback.answer("❌ Error disconnecting wallet.", show_alert=True)
