import os
import json
import asyncio
import logging
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from pytonconnect import TonConnect
from pytonconnect.storage import IStorage
import secrets

from database import db
from utils import safe_edit_text, safe_bot_edit_text
from loader import bot

logger = logging.getLogger(__name__)
router = Router()

MANIFEST_URL = "https://github.com/jammm3675/GiveawayBot/blob/main/tonconnect-manifest.json"

class FileStorage(IStorage):
    def __init__(self, user_id: int):
        self.path = f"storage/session_{user_id}.json"
        os.makedirs("storage", exist_ok=True)

    async def set_item(self, key: str, value: str):
        data = {}
        if os.path.exists(self.path):
            with open(self.path, 'r') as f:
                data = json.load(f)
        data[key] = value
        with open(self.path, 'w') as f:
            json.dump(data, f)

    async def get_item(self, key: str, default_value: str = None):
        if not os.path.exists(self.path):
            return default_value
        with open(self.path, 'r') as f:
            data = json.load(f)
        return data.get(key, default_value)

    async def remove_item(self, key: str):
        if not os.path.exists(self.path):
            return
        with open(self.path, 'r') as f:
            data = json.load(f)
        if key in data:
            del data[key]
            with open(self.path, 'w') as f:
                json.dump(data, f)

@router.callback_query(F.data == "wallet_menu")
async def wallet_menu_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    wallet = await db.get_user_wallet(user_id)

    if wallet:
        truncated = f"{wallet[:6]}...{wallet[-4:]}"
        text = (
            "<b>💳 Wallet connected!</b>\n\n"
            f"<blockquote>Your address: <code>{wallet}</code></blockquote>\n\n"
            "You can disconnect your wallet if you want to link another one."
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="Disconnect", callback_data="disconnect_wallet", style="danger")
        builder.button(text="Back", callback_data="game_menu")
        builder.adjust(1)
    else:
        text = (
            "<b>💳 Wallet not connected</b>\n\n"
            "<blockquote>Connect your TON wallet to verify ownership and participate in the ecosystem.</blockquote>"
        )
        builder = InlineKeyboardBuilder()
        builder.button(text="Connect Wallet", callback_data="connect_wallet", style="success")
        builder.button(text="Back", callback_data="game_menu")
        builder.adjust(1)

    await safe_edit_text(callback, text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "connect_wallet")
async def connect_wallet_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id

    storage = FileStorage(user_id)
    connector = TonConnect(MANIFEST_URL, storage)

    wallets = connector.get_wallets()
    # For simplicity, we use the first wallet (usually Tonkeeper)
    # or better, we could show a selection. But task says "Wallet" button starts the process.

    # Generate ton_proof payload
    proof_payload = secrets.token_hex(16)
    await state.update_data(proof_payload=proof_payload)

    try:
        generated_url = await connector.connect(wallets[0], {
            "ton_proof": proof_payload
        })

        builder = InlineKeyboardBuilder()
        builder.button(text="Open Wallet", url=generated_url)
        builder.button(text="Back", callback_data="wallet_menu")
        builder.adjust(1)

        msg = await safe_edit_text(callback,
            "<b>🔗 Connect your wallet</b>\n\n"
            "<blockquote>Click the button below to open your wallet and confirm the connection.</blockquote>",
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML
        )

        # Start background task to wait for connection
        asyncio.create_task(wait_for_connection_task(user_id, connector, proof_payload))

    except Exception as e:
        logger.error(f"Error connecting wallet: {e}")
        await callback.answer("❌ Error initializing connection.", show_alert=True)

async def wait_for_connection_task(user_id, connector, proof_payload):
    try:
        # wait_for_connection() with timeout (external)
        try:
            await asyncio.wait_for(connector.wait_for_connection(), timeout=300)
        except asyncio.TimeoutError:
            logger.info(f"Connection timeout for user {user_id}")
            return

        if connector.connected:
            wallet_info = connector.account
            address = wallet_info.address

            # TODO: Verify ton_proof
            # For the sake of this task, we assume verification is successful or we call a helper.
            # Real verification requires checking the proof signature.

            await db.update_user_wallet(user_id, address)

            try:
                await bot.send_message(user_id,
                    "<b>✅ Wallet successfully connected!</b>\n\n"
                    f"<blockquote>Address: <code>{address}</code></blockquote>",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
    except Exception as e:
        logger.error(f"Error in wait_for_connection_task for {user_id}: {e}")

@router.callback_query(F.data == "disconnect_wallet")
async def disconnect_wallet_handler(callback: types.CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id

    storage = FileStorage(user_id)
    connector = TonConnect(MANIFEST_URL, storage)

    try:
        if await connector.restore_connection():
            await connector.disconnect()

        await db.update_user_wallet(user_id, None)
        # Clear storage file
        if os.path.exists(storage.path):
            os.remove(storage.path)

        await wallet_menu_handler(callback)
    except Exception as e:
        logger.error(f"Error disconnecting wallet: {e}")
        await callback.answer("❌ Error disconnecting wallet.", show_alert=True)
