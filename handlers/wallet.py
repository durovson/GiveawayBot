import asyncio
import logging
from aiogram import Router, F, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from pytonconnect import TonConnect

from loader import bot, wallet_tasks
from database import db
from services.ton_connect_service import TonConnectService
from services.ui_cleanup import remember_message, clear_messages, MessageCategory
from utils import normalize_to_raw, short_wallet, safe_answer, safe_bot_send_message
from keyboards.wallet import (
    wallet_menu_keyboard,
    wallet_selection_keyboard,
    wallet_connect_keyboard,
    wallet_success_keyboard
)

router = Router()
logger = logging.getLogger(__name__)

async def cleanup_connect(user_id: int):
    try:
        connector = await TonConnectService.connector(user_id)
        if not connector.connected:
             TonConnectService.drop_connector(user_id)
    except Exception:
        logger.exception("CLEANUP_CONNECT_FAILED user_id=%s", user_id)

@router.callback_query(F.data == "wallet_menu")
async def wallet_menu(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    await db.ensure_user_exists(user_id)
    try:
        wallet = await db.get_user_wallet(user_id)
        is_connected = bool(wallet)

        if is_connected:
            display_addr = short_wallet(wallet)
            text = (
                f"┏┅<tg-emoji emoji-id=\"5431520110395292209\">👛</tg-emoji>┅ / <b>Wallet Connected</b> /\n"
                "┋\n"
                f"┣ <code>{display_addr}</code>\n"
                "┋\n"
                f"┗┅┅┅/ <b>You can disconnect this wallet and link a new one if needed.</b> /"
            )
        else:
            text = (
                f"┏┅<tg-emoji emoji-id=\"5431520110395292209\">👛</tg-emoji> <b>Connect Wallet</b> /\n"
                "┋\n"
                f"┣ Connect your TON wallet to access holder features and giveaways.\n"
                "┋\n"
                f"┗┅┅┅/ <b>Choose your preferred wallet below:</b> /"
            )

        kb = wallet_menu_keyboard(is_connected)

        try:
            await callback.message.delete()
        except:
            pass

        msg = await safe_answer(callback.message, text, reply_markup=kb, parse_mode=ParseMode.HTML)
        await remember_message(state, msg, category=MessageCategory.TEMPORARY)

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
        TonConnectService.drop_connector(user_id)
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

    supported = ["Tonkeeper", "MyTonWallet", "Telegram Wallet"]
    available = [w for w in wallets_list if w['name'] in supported]

    if not available:
        await callback.answer("No supported wallets found.", show_alert=True)
        return

    kb = wallet_selection_keyboard(available)

    try:
        await callback.message.delete()
    except:
        pass

    msg = await safe_answer(callback.message,
        "<b>Select your wallet:</b>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )
    await remember_message(state, msg, category=MessageCategory.TEMPORARY)

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
        f"┏┅<tg-emoji emoji-id=\"5431520110395292209\">👛</tg-emoji>┅ / {wallet_name} <b>Connection</b> /\n"
        f"┋\n"
        f"┗┅┅┅/ <b>Tap the button below and confirm connection inside</b> {wallet_name}"
    )

    kb = wallet_connect_keyboard(url)

    try:
        await callback.message.delete()
    except:
        pass

    msg = await safe_answer(callback.message, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await remember_message(state, msg, category=MessageCategory.TEMPORARY)

    task = asyncio.create_task(wait_for_connection_with_timeout(user_id, connector, state))
    wallet_tasks.add(task)
    task.add_done_callback(wallet_tasks.discard)

async def wait_for_connection_with_timeout(user_id: int, connector: TonConnect, state: FSMContext):
    try:
        await asyncio.wait_for(wait_for_connection(user_id, connector, state), timeout=190)
    except asyncio.TimeoutError:
        logger.warning("WALLET_CONNECTION_TIMEOUT user_id=%s", user_id)
        await cleanup_connect(user_id)
    except Exception:
        logger.exception("WAIT_FOR_CONNECTION_WITH_TIMEOUT_CRASH user_id=%s", user_id)
        await cleanup_connect(user_id)

async def wait_for_connection(user_id: int, connector: TonConnect, state: FSMContext):
    def status_changed(wallet_info):
        pass

    unsubscribe = connector.on_status_change(status_changed)

    try:
        raw_address = None
        for _ in range(180):
            try:
                if connector.connected:
                    if connector.account and connector.account.address:
                        raw_address = normalize_to_raw(connector.account.address)
                        break
            except Exception:
                logger.exception("CONNECTOR_STATUS_CHECK_FAILED user_id=%s", user_id)
            await asyncio.sleep(1)

        if raw_address:
            try:
                # 1. Clear temporary messages (connect menus)
                await clear_messages(user_id, state, category=MessageCategory.TEMPORARY)

                await db.update_user_wallet(user_id, raw_address)
                display_addr = short_wallet(raw_address)

                # 2. Send success notification (PERSISTENT)
                msg1 = await safe_bot_send_message(bot,
                    user_id,
                    f"┏┅<tg-emoji emoji-id=\"5431520110395292209\">👛</tg-emoji>┅ / <b>Success!</b> /\n"
                    f"┋\n"
                    f"┗┅┅┅/ <b>Your wallet has been linked:</b> <code>{display_addr}</code>",
                    parse_mode=ParseMode.HTML,
                )
                await remember_message(state, msg1, category=MessageCategory.PERSISTENT)

                # 3. Send action button
                kb = wallet_success_keyboard()
                msg2 = await safe_bot_send_message(bot, user_id, "Return to the game:", reply_markup=kb)
                await remember_message(state, msg2, category=MessageCategory.PERSISTENT)

            except Exception:
                logger.exception("SUCCESS_MESSAGE_POST_SAVE_FAILED user_id=%s", user_id)

        await cleanup_connect(user_id)
    except Exception:
        logger.exception("WAIT_FOR_CONNECTION_CRASH user_id=%s", user_id)
        await cleanup_connect(user_id)
    finally:
        try:
            unsubscribe()
        except Exception:
            pass
