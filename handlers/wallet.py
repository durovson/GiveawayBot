import asyncio
import logging
from aiogram import Router, F, types, html
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ParseMode
from pytonconnect import TonConnect
from pytonconnect.exceptions import UserRejectsError
from postgrest.exceptions import APIError

from loader import bot
from database import db
from services.ton_connect_service import TonConnectService
from services.ui_cleanup import remember_message, clear_messages
from utils import normalize_to_raw, raw_to_user_friendly, safe_edit_text, safe_bot_edit_text

router = Router()
logger = logging.getLogger(__name__)

async def finish_wallet_flow(callback: types.CallbackQuery, state: FSMContext, success=True):
    from handlers.game_menu import show_game_menu
    await state.clear()
    await show_game_menu(callback, state)

async def cleanup_connect(user_id: int, state: FSMContext):
    try:
        connector = await TonConnectService.connector(user_id)
        if not connector.connected:
             TonConnectService.drop_connector(user_id)
    except Exception:
        pass

@router.callback_query(F.data == "wallet_menu")
async def wallet_menu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    wallet = await db.get_user_wallet(user_id)

    if wallet:
        friendly_addr = raw_to_user_friendly(wallet)
        text = (
            f"<b><tg-emoji emoji-id=\"5431520110395292209\">💎</tg-emoji> Wallet Connected</b>\n\n"
            f"<blockquote><code>{friendly_addr}</code></blockquote>\n\n"
            f"<i>You can disconnect this wallet and link a new one if needed.</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Disconnect", callback_data="disconnect_wallet")],
            [InlineKeyboardButton(text="◀️ Back", callback_data="game_menu")]
        ])
    else:
        text = (
            f"<b><tg-emoji emoji-id=\"5431520110395292209\">💎</tg-emoji> Connect Wallet</b>\n\n"
            f"<blockquote>Link your TON wallet to participate in the game and receive rewards.</blockquote>\n\n"
            f"<i>Choose your preferred wallet below:</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Connect Wallet", callback_data="connect_wallet")],
            [InlineKeyboardButton(text="◀️ Back", callback_data="game_menu")]
        ])

    await safe_edit_text(callback, text, kb, state=state)

@router.callback_query(F.data == "disconnect_wallet")
async def disconnect_wallet(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id

    # 1. Clear from DB
    await db.update_user_wallet(user_id, None)

    # 2. Clear from TonConnect
    try:
        connector = await TonConnectService.connector(user_id)
        if connector.connected:
            await connector.disconnect()
        TonConnectService.drop_connector(user_id)
    except Exception:
        pass

    await callback.answer("Wallet disconnected", show_alert=True)
    await wallet_menu(callback, state)

@router.callback_query(F.data == "connect_wallet")
async def connect_wallet(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    connector = await TonConnectService.connector(user_id)

    wallets_list = connector.get_wallets()
    # Filter only supported wallets
    supported = ["Tonkeeper", "MyTonWallet", "Tonhub", "Telegram Wallet"]
    available = [w for w in wallets_list if w['name'] in supported]

    if not available:
        await callback.answer("No supported wallets found.", show_alert=True)
        return

    kb_list = []
    for w in available:
        kb_list.append([InlineKeyboardButton(text=w['name'], callback_data=f"select_wallet_{w['name']}")])
    kb_list.append([InlineKeyboardButton(text="◀️ Back", callback_data="wallet_menu")])

    await safe_edit_text(
        callback,
        "<b>Select your wallet:</b>",
        InlineKeyboardMarkup(inline_keyboard=kb_list),
        state=state
    )

@router.callback_query(F.data.startswith("select_wallet_"))
async def select_wallet(callback: types.CallbackQuery, state: FSMContext):
    wallet_name = callback.data.replace("select_wallet_", "")
    user_id = callback.from_user.id
    connector = await TonConnectService.connector(user_id)

    wallets_list = connector.get_wallets()
    wallet_config = next((w for w in wallets_list if w['name'] == wallet_name), None)

    if not wallet_config:
        await callback.answer("Wallet configuration not found.", show_alert=True)
        return

    generated_url = await connector.connect(wallet_config)

    # Check if universal link or direct bridge
    url = generated_url

    text = (
        f"<b><tg-emoji emoji-id=\"5773950294719202419\">📲</tg-emoji> Connecting {wallet_name}</b>\n\n"
        f"<blockquote>Please click the button below to open your wallet and confirm the connection.</blockquote>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Open Wallet", url=url)],
        [InlineKeyboardButton(text="◀️ Cancel", callback_data="wallet_menu")]
    ])

    await safe_edit_text(callback, text, kb, state=state)

    # Polling for connection status
    # We use a background task for this specific connection attempt
    asyncio.create_task(wait_for_connection(user_id, connector, callback, state))

async def wait_for_connection(user_id: int, connector: TonConnect, callback: types.CallbackQuery, state: FSMContext):
    # This task is short-lived for the duration of the connection attempt
    def status_changed(wallet_info):
        pass

    def items_sent(items):
        pass

    unsubscribe = connector.on_status_change(status_changed)

    try:
        # Wait up to 3 minutes for connection
        raw_address = None
        for _ in range(180):
            if connector.connected:
                if connector.account and connector.account.address:
                    raw_address = normalize_to_raw(connector.account.address)
                    break
            await asyncio.sleep(1)

        if raw_address:
            await db.update_user_wallet(user_id, raw_address)
            msg = await bot.send_message(
                user_id,
                f"<b><tg-emoji emoji-id=\"5431520110395292209\">💎</tg-emoji> Success!</b>\n\n"
                f"Your wallet has been linked: <code>{raw_to_user_friendly(raw_address)}</code>",
                parse_mode=ParseMode.HTML,
            )
            await remember_message(state, msg)
        await cleanup_connect(user_id, state)
        await finish_wallet_flow(callback, state, success=bool(raw_address))
    except asyncio.TimeoutError:
        await cleanup_connect(user_id, state)
        await finish_wallet_flow(callback, state, success=False)
    except UserRejectsError:
        await cleanup_connect(user_id, state)
        await finish_wallet_flow(callback, state, success=False)
    except asyncio.CancelledError:
        await cleanup_connect(user_id, state)
        await finish_wallet_flow(callback, state, success=False)
        raise # Added raise as per requirement
    except APIError as e:
        logger.warning("TON_CONNECT_BRIDGE_WARNING user_id=%s error=%s", user_id, e)
        await cleanup_connect(user_id, state)
        await finish_wallet_flow(callback, state, success=False)
    except Exception as e:
        logger.error(f"Error in wallet connection flow: {e}")
        await cleanup_connect(user_id, state)
        await finish_wallet_flow(callback, state, success=False)
    finally:
        unsubscribe()
