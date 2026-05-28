import asyncio
import logging
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from pytonconnect import TonConnect

import loader
from database import db
from services.ton_connect_service import TonConnectService
from utils import normalize_to_raw, short_wallet, safe_edit_text, safe_bot_send_message

router = Router()
logger = logging.getLogger(__name__)

@router.callback_query(F.data == "wallet_menu")
async def wallet_menu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await db.ensure_user_exists(user_id)
    try:
        wallet = await db.get_user_wallet(user_id)

        if wallet:
            display_addr = short_wallet(wallet)
            text = (
                f"<b><tg-emoji emoji-id=\"5431520110395292209\">👛</tg-emoji> Wallet Connected</b>\n\n"
                f"<blockquote><code>{display_addr}</code></blockquote>\n\n"
                f"<i>You can disconnect this wallet and link a new one if needed.</i>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Disconnect", callback_data="disconnect_wallet")],
                [InlineKeyboardButton(text="◀️ Back", callback_data="game_menu")]
            ])
        else:
            text = (
                f"<b><tg-emoji emoji-id=\"5431520110395292209\">👛</tg-emoji> Connect Wallet</b>\n\n"
                f"Connect your TON wallet to access holder features, OTC and giveaways.\n\n"
                f"<i>Choose your preferred wallet below:</i>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Connect Wallet", callback_data="connect_wallet")],
                [InlineKeyboardButton(text="◀️ Back", callback_data="game_menu")]
            ])

        await safe_edit_text(callback, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        logger.exception("WALLET_MENU_FAILED user_id=%s", user_id)
        await callback.answer("Wallet menu error.", show_alert=True)

@router.callback_query(F.data == "disconnect_wallet")
async def disconnect_wallet(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await db.ensure_user_exists(user_id)
    try:
        await db.update_user_wallet(user_id, None)
        connector = await TonConnectService.connector(user_id)
        if connector.connected:
            await connector.disconnect()
    except Exception:
        logger.exception("DISCONNECT_WALLET_FAILED user_id=%s", user_id)

    await callback.answer("Wallet disconnected", show_alert=True)
    await wallet_menu(callback, state)

@router.callback_query(F.data == "connect_wallet")
async def connect_wallet(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await db.ensure_user_exists(user_id)
    try:
        connector = await TonConnectService.connector(user_id)
        wallets_list = connector.get_wallets()
    except Exception:
        logger.exception("CONNECT_WALLET_GET_CONNECTOR_FAILED user_id=%s", user_id)
        await callback.answer("Connection service temporarily unavailable.", show_alert=True)
        return

    # Restricted providers
    supported = ["Tonkeeper", "MyTonWallet", "Telegram Wallet"]
    available = [w for w in wallets_list if w['name'] in supported]

    if not available:
        await callback.answer("No supported wallets found.", show_alert=True)
        return

    kb_list = []
    for w in available:
        kb_list.append([InlineKeyboardButton(text=w['name'], callback_data=f"select_wallet_{w['name']}")])
    kb_list.append([InlineKeyboardButton(text="◀️ Back", callback_data="wallet_menu")])

    await safe_edit_text(callback,
        "<b>Select your wallet:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list),
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data.startswith("select_wallet_"))
async def select_wallet(callback: types.CallbackQuery, state: FSMContext):
    wallet_name = callback.data.replace("select_wallet_", "")
    user_id = callback.from_user.id
    await db.ensure_user_exists(user_id)
    try:
        connector = await TonConnectService.connector(user_id)
        wallets_list = connector.get_wallets()
        wallet_config = next((w for w in wallets_list if w['name'] == wallet_name), None)

        if not wallet_config:
            await callback.answer("Wallet configuration not found.", show_alert=True)
            return

        if connector.connected:
            try:
                await connector.disconnect()
            except Exception:
                pass

        url = await connector.connect(wallet_config)
    except Exception:
        logger.exception("SELECT_WALLET_FAILED user_id=%s wallet=%s", user_id, wallet_name)
        await callback.answer("Failed to initiate connection.", show_alert=True)
        return

    text = (
        f"<b><tg-emoji emoji-id=\"5431520110395292209\">👛</tg-emoji> {wallet_name} Connection</b>\n\n"
        f"<blockquote>\n"
        f"Tap the button below and confirm connection inside {wallet_name}.\n"
        f"</blockquote>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Open Wallet", url=url)],
        [InlineKeyboardButton(text="◀️ Cancel", callback_data="wallet_menu")]
    ])

    await safe_edit_text(callback, text, reply_markup=kb, parse_mode=ParseMode.HTML)

    # Start temporary wait task
    asyncio.create_task(wait_for_connection(user_id, connector))

async def wait_for_connection(user_id: int, connector: TonConnect):
    try:
        raw_address = None
        # Simple polling for 5 minutes
        for _ in range(300):
            try:
                if connector.connected:
                    if connector.account and connector.account.address:
                        raw_address = normalize_to_raw(connector.account.address)
                        break
            except Exception:
                pass
            await asyncio.sleep(1)

        if raw_address:
            try:
                await db.update_user_wallet(user_id, raw_address)
                display_addr = short_wallet(raw_address)

                # Send Success message
                await safe_bot_send_message(loader.bot,
                    user_id,
                    f"<b><tg-emoji emoji-id=\"5431520110395292209\">👛</tg-emoji> Success!</b>\n\n"
                    f"Your wallet has been linked: <code>{display_addr}</code>",
                    parse_mode=ParseMode.HTML,
                )

                # Send Refreshed Main Menu
                from handlers.main_menu import get_main_menu_keyboard, MAIN_MENU_TEXT
                await safe_bot_send_message(loader.bot,
                    user_id,
                    MAIN_MENU_TEXT,
                    reply_markup=await get_main_menu_keyboard(user_id),
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                logger.exception("SUCCESS_MESSAGE_POST_SAVE_FAILED user_id=%s", user_id)

        # Ensure disconnection after link or timeout
        try:
            if connector.connected:
                await connector.disconnect()
        except Exception:
            pass

    except Exception:
        logger.exception("WAIT_FOR_CONNECTION_CRASH user_id=%s", user_id)
