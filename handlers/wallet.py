import asyncio
import logging
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from pytonconnect import TonConnect
from pytonconnect.exceptions import UserRejectsError
from postgrest.exceptions import APIError

from loader import bot, wallet_tasks
from database import db
from services.ton_connect_service import TonConnectService
from services.ui_cleanup import remember_message, clear_messages
from utils import normalize_to_raw, short_wallet, safe_answer, safe_bot_send_message

router = Router()
logger = logging.getLogger(__name__)

async def finish_wallet_flow(callback: types.CallbackQuery, state: FSMContext):
    try:
        from handlers.game_menu import show_game_menu
        await state.clear()
        await show_game_menu(callback, state)
    except Exception:
        logger.exception("FINISH_WALLET_FLOW_FAILED")

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

        try:
            await callback.message.delete()
        except:
            pass
        msg = await safe_answer(callback.message, text, reply_markup=kb, parse_mode=ParseMode.HTML)
        if msg:
            await remember_message(state, msg)
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

    # Restricted to only 3 providers
    supported = ["Tonkeeper", "MyTonWallet", "Telegram Wallet"]
    available = [w for w in wallets_list if w['name'] in supported]

    if not available:
        await callback.answer("No supported wallets found.", show_alert=True)
        return

    kb_list = []
    for w in available:
        kb_list.append([InlineKeyboardButton(text=w['name'], callback_data=f"select_wallet_{w['name']}")])
    kb_list.append([InlineKeyboardButton(text="◀️ Back", callback_data="wallet_menu")])

    try:
        await callback.message.delete()
    except:
        pass
    msg = await safe_answer(callback.message,
        "<b>Select your wallet:</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list),
        parse_mode=ParseMode.HTML
    )
    if msg:
        await remember_message(state, msg)

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

    try:
        await callback.message.delete()
    except:
        pass
    msg = await safe_answer(callback.message, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    if msg:
        await remember_message(state, msg)

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
                # Cleanup temporary UI before showing success
                await clear_messages(user_id, state)

                await db.update_user_wallet(user_id, raw_address)
                display_addr = short_wallet(raw_address)

                # Send Success message
                await safe_bot_send_message(bot,
                    user_id,
                    f"<b><tg-emoji emoji-id=\"5431520110395292209\">👛</tg-emoji> Success!</b>\n\n"
                    f"Your wallet has been linked: <code>{display_addr}</code>",
                    parse_mode=ParseMode.HTML,
                )

                # Send Refreshed Main Menu
                from handlers.main_menu import get_main_menu_keyboard, MAIN_MENU_TEXT
                await safe_bot_send_message(bot,
                    user_id,
                    MAIN_MENU_TEXT,
                    reply_markup=await get_main_menu_keyboard(user_id),
                    parse_mode=ParseMode.HTML
                )
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
