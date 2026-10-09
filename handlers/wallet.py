import asyncio
import logging
from datetime import datetime
from aiogram import Router, F, types
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from pytonconnect import TonConnect

from loader import bot, wallet_tasks
from database import db
from services.ton_connect_service import TonConnectService
from services.ton_wallets import get_direct_wallet, get_direct_wallets
from services.ui_cleanup import remember_message, clear_messages, MessageCategory
from utils import normalize_to_raw, short_wallet, safe_answer, safe_bot_send_message
from keyboards.wallet import (
    wallet_menu_keyboard,
    wallet_selection_keyboard,
    wallet_connect_keyboard,
    wallet_success_keyboard
)
from services.localization import get_locale

router = Router()
logger = logging.getLogger(__name__)
_wallet_actions = set()
_connection_waiters = {}

async def _wallet_action(callback, state, texts, action):
    user_id = callback.from_user.id
    if user_id in _wallet_actions:
        await callback.answer(texts["wallet_action_busy"], show_alert=True)
        return
    _wallet_actions.add(user_id)
    try:
        await action(callback, state, texts)
    finally:
        _wallet_actions.discard(user_id)

async def _cancel_connection_waiter(user_id: int):
    task = _connection_waiters.pop(user_id, None)
    if task and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

async def cleanup_connect(user_id: int, connector: TonConnect):
    # A timed-out old attempt must not restore/drop a newer connector.
    if TonConnectService.is_current(user_id, connector) and not connector.connected:
        TonConnectService.drop_connector(user_id)

@router.callback_query(F.data == "wallet_menu")
async def wallet_menu(callback: types.CallbackQuery, state: FSMContext, texts: dict, acknowledge=True):
    if acknowledge:
        await callback.answer()
    user_id = callback.from_user.id
    # texts from middleware
    await db.ensure_user_exists(user_id)
    try:
        wallet = await db.get_user_wallet(user_id)
        is_connected = bool(wallet)

        if is_connected:
            display_addr = short_wallet(wallet)
            text = texts["wallet_connected"].format(address=display_addr)
        else:
            text = texts["wallet_connect"]

        kb = wallet_menu_keyboard(is_connected, texts)

        try:
            await callback.message.delete()
        except:
            pass

        msg = await safe_answer(callback.message, text, reply_markup=kb, parse_mode=ParseMode.HTML)
        await remember_message(state, msg, category=MessageCategory.TEMPORARY)

    except Exception:
        logger.exception("WALLET_MENU_FAILED user_id=%s", user_id)
        await callback.answer(texts["wallet_menu_error"], show_alert=True)

@router.callback_query(F.data == "disconnect_wallet")
async def disconnect_wallet(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await _wallet_action(callback, state, texts, _disconnect_wallet)

async def _disconnect_wallet(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    user_id = callback.from_user.id
    try:
        await _cancel_connection_waiter(user_id)
        await TonConnectService.disconnect(user_id)
    except Exception:
        logger.exception("DISCONNECT_WALLET_FAILED user_id=%s", user_id)
        await callback.answer(texts["wallet_disconnect_error"], show_alert=True)
        return

    await callback.answer(texts["wallet_disconnected_alert"], show_alert=True)
    await wallet_menu(callback, state, texts, acknowledge=False)

@router.callback_query(F.data == "connect_wallet")
async def connect_wallet(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await _wallet_action(callback, state, texts, _connect_wallet)

async def _connect_wallet(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    user_id = callback.from_user.id
    # texts from middleware
    await db.ensure_user_exists(user_id)
    try:
        # Create/restore the connector here so service/storage problems are
        # surfaced before the user selects a wallet.  The wallet picker itself
        # is an explicit local allow-list: pytonconnect's bundled fallback list
        # is stale and may omit renamed/new wallets when its remote fetch fails.
        await TonConnectService.connector(user_id)
    except Exception:
        logger.exception("CONNECT_WALLET_GET_CONNECTOR_FAILED user_id=%s", user_id)
        await callback.answer(texts["wallet_service_unavailable"], show_alert=True)
        return

    available = get_direct_wallets()
    kb = wallet_selection_keyboard(available, texts)

    try:
        await callback.message.delete()
    except:
        pass

    msg = await safe_answer(callback.message,
        texts["wallet_select_wallet"],
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )
    await remember_message(state, msg, category=MessageCategory.TEMPORARY)

@router.callback_query(F.data.startswith("select_wallet_"))
async def select_wallet(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    await _wallet_action(callback, state, texts, _select_wallet)

async def _select_wallet(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    wallet_key = callback.data.replace("select_wallet_", "", 1)
    wallet_config = get_direct_wallet(wallet_key)
    wallet_name = wallet_config["name"] if wallet_config else wallet_key
    user_id = callback.from_user.id
    # texts from middleware
    await db.ensure_user_exists(user_id)

    if not wallet_config:
        await callback.answer(texts["wallet_config_not_found"], show_alert=True)
        return

    try:
        await _cancel_connection_waiter(user_id)
        connector = await TonConnectService.connector(user_id)
        async with TonConnectService.user_lock(user_id):
            if connector.connected:
                await connector.disconnect()

            # Preserve the wallet's HTTPS universal-link flow.
            url = await connector.connect(wallet_config)
    except Exception:
        logger.exception("SELECT_WALLET_FAILED user_id=%s wallet=%s", user_id, wallet_key)
        await callback.answer(texts["wallet_init_failed"], show_alert=True)
        return

    text = texts["wallet_connection_title"].format(wallet_name=wallet_name)

    kb = wallet_connect_keyboard(url, texts)

    try:
        await callback.message.delete()
    except:
        pass

    msg = await safe_answer(callback.message, text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await remember_message(state, msg, category=MessageCategory.TEMPORARY)

    task = asyncio.create_task(wait_for_connection_with_timeout(user_id, connector, state, texts))
    _connection_waiters[user_id] = task
    wallet_tasks.add(task)
    task.add_done_callback(wallet_tasks.discard)
    def clear_waiter(finished):
        if _connection_waiters.get(user_id) is finished:
            _connection_waiters.pop(user_id, None)
    task.add_done_callback(clear_waiter)

async def wait_for_connection_with_timeout(user_id: int, connector: TonConnect, state: FSMContext, texts: dict):
    try:
        await asyncio.wait_for(wait_for_connection(user_id, connector, state, texts), timeout=190)
    except asyncio.TimeoutError:
        logger.warning("WALLET_CONNECTION_TIMEOUT user_id=%s", user_id)
        await cleanup_connect(user_id, connector)
    except Exception:
        logger.exception("WAIT_FOR_CONNECTION_WITH_TIMEOUT_CRASH user_id=%s", user_id)
        await cleanup_connect(user_id, connector)

async def wait_for_connection(user_id: int, connector: TonConnect, state: FSMContext, texts: dict):
    def status_changed(wallet_info, texts=texts):
        pass

    unsubscribe = connector.on_status_change(status_changed)

    try:
        raw_address = None
        for _ in range(180):
            if not TonConnectService.is_current(user_id, connector):
                return
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
                # texts from middleware
                # 1. Clear temporary messages (connect menus)
                await clear_messages(user_id, state, category=MessageCategory.TEMPORARY)

                async with TonConnectService.user_lock(user_id):
                    if not TonConnectService.is_current(user_id, connector):
                        return
                    if not await db.update_user_wallet(user_id, raw_address):
                        raise RuntimeError("Wallet connection was not persisted")

                # Referral system hook: set wallet_connected_at and referral_status
                user_data = await db.get_user_by_telegram_id(user_id)
                if user_data and not user_data.get("wallet_connected_at"):
                    await db.update_user_fields(
                        user_id,
                        wallet_connected_at=datetime.now().isoformat(),
                        referral_status="wallet_connected"
                    )

                display_addr = short_wallet(raw_address)

                # 2. Send success notification (PERSISTENT)
                msg1 = await safe_bot_send_message(bot,
                    user_id,
                    texts["wallet_success_title"].format(address=display_addr),
                    parse_mode=ParseMode.HTML,
                )
                await remember_message(state, msg1, category=MessageCategory.PERSISTENT)

                # 3. Send action button
                state_data = await state.get_data()
                return_callback = state_data.get("wallet_return_callback")
                kb = wallet_success_keyboard(
                    texts,
                    callback_data=return_callback or "game_menu",
                    button_text=texts.get("september_wl_return_btn") if return_callback == "september_wl" else None,
                )
                msg2 = await safe_bot_send_message(bot, user_id, texts["wallet_return_to_game"], reply_markup=kb)
                await remember_message(state, msg2, category=MessageCategory.PERSISTENT)

            except Exception:
                logger.exception("SUCCESS_MESSAGE_POST_SAVE_FAILED user_id=%s", user_id)

        await cleanup_connect(user_id, connector)
    except Exception:
        logger.exception("WAIT_FOR_CONNECTION_CRASH user_id=%s", user_id)
        await cleanup_connect(user_id, connector)
    finally:
        try:
            unsubscribe()
        except Exception:
            pass
