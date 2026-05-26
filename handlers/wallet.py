import asyncio
import logging
from aiogram import Router, types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from pytonconnect import TonConnect
from pytonconnect.exceptions import UserRejectsError
from postgrest.exceptions import APIError

from database import db
from utils import safe_edit_text, raw_to_user_friendly
from loader import bot
from services.ton_connect_service import TonConnectService
from services.ui_cleanup import remember_message, clear_messages
from handlers.main_menu import MAIN_MENU_TEXT, get_main_menu_keyboard

logger = logging.getLogger(__name__)
router = Router()


class WalletConnectState(StatesGroup):
    waiting_for_connection = State()


def format_address(address: str) -> str:
    if not address:
        return "Unknown"

    friendly_addr = raw_to_user_friendly(address)
    return f"{friendly_addr[:6]}...{friendly_addr[-6:]}"


async def await_wallet(connector: TonConnect, user_id: int):
    await connector.wait_for_connection()

    if connector.connected:
        address = connector.wallet.account.address
        await db.update_user_wallet(user_id, address)
        return address

    return None


async def finish_wallet_flow(callback: types.CallbackQuery, state: FSMContext, success: bool = True):
    await clear_messages(callback.bot, callback.message.chat.id, state)
    await state.clear()
    status_text = "✅ Wallet connected" if success else "❌ Wallet connection cancelled"
    await callback.bot.send_message(callback.message.chat.id, status_text)
    await callback.bot.send_message(
        callback.message.chat.id,
        MAIN_MENU_TEXT,
        reply_markup=await get_main_menu_keyboard(callback.from_user.id),
        parse_mode=ParseMode.HTML,
    )


async def cleanup_connect(user_id: int, state: FSMContext):
    await db.client.table("ton_connect_sessions").delete().eq("user_id", user_id).execute()
    TonConnectService.drop_connector(user_id)


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
    await callback.answer()
    user_id = callback.from_user.id
    connector = await TonConnectService.connector(user_id)

    if connector.connected:
        await callback.answer("Wallet is already connected!", show_alert=True)
        return

    builder = InlineKeyboardBuilder()
    builder.button(text="Tonkeeper", callback_data="wallet_select:tonkeeper")
    builder.button(text="MyTonWallet", callback_data="wallet_select:mytonwallet")
    builder.button(text="Tonhub", callback_data="wallet_select:tonhub")
    builder.button(text="Telegram Wallet", callback_data="wallet_select:telegram-wallet")
    builder.button(text="Back", callback_data="wallet_menu")
    builder.adjust(2)

    msg = await safe_edit_text(callback, text="<b>💳 Select your TON wallet:</b>", reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
    await state.update_data(wallet_messages=[msg.message_id])


@router.callback_query(F.data.startswith("wallet_select:"))
async def process_wallet_selection(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    selected_app = callback.data.split(":")[1]

    connector = await TonConnectService.connector(user_id)
    wallets = connector.get_wallets()

    target_wallet = None
    for wallet in wallets:
        if wallet.get("appName", wallet.get("app_name")) == selected_app:
            target_wallet = wallet
            break

    if not target_wallet:
        await callback.answer("Wallet not supported!", show_alert=True)
        return

    def status_changed(wallet):
        logger.info("TON_CONNECT_CONNECTED")

    def status_error(e):
        logger.error("TON_CONNECT_FAILED")

    unsubscribe = lambda: None

    try:
        unsubscribe = connector.on_status_change(status_changed, status_error)
        res = connector.connect(target_wallet)
        connect_url = await res if asyncio.iscoroutine(res) else res

        builder = InlineKeyboardBuilder()
        builder.button(text=f"Open {target_wallet.get('name', 'Wallet')}", url=connect_url)
        builder.button(text="❌ Cancel", callback_data="wallet_cancel_connect")
        builder.adjust(1)

        msg = await safe_edit_text(
            callback,
            text="<b>🔗 Confirm connection in your wallet application.</b>",
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.HTML,
        )
        await remember_message(state, msg)

        await state.set_state(WalletConnectState.waiting_for_connection)
        raw_address = await asyncio.wait_for(await_wallet(connector, user_id), timeout=120)

        if raw_address:
            friendly_addr = format_address(raw_address)
            msg = await bot.send_message(
                chat_id=chat_id,
                text=f"<b>🎉 Wallet successfully connected!</b>\nAddress: <code>{friendly_addr}</code>",
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


@router.callback_query(F.data == "wallet_cancel_connect")
async def wallet_cancel_connect_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer("Connection canceled.")
    await cleanup_connect(callback.from_user.id, state)
    await finish_wallet_flow(callback, state, success=False)


@router.callback_query(F.data == "disconnect_wallet")
async def disconnect_wallet_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    user_id = callback.from_user.id
    connector = await TonConnectService.connector(user_id)

    try:
        if connector.connected:
            await connector.disconnect()
    except Exception:
        pass

    await cleanup_connect(user_id, state)
    await db.update_user_wallet(user_id, None)

    await wallet_menu_handler(callback)
