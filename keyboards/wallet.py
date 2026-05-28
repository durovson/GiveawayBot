from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup

def wallet_menu_keyboard(is_connected: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if is_connected:
        builder.button(text="❌ Disconnect", callback_data="disconnect_wallet")
    else:
        builder.button(text="🔗 Connect Wallet", callback_data="connect_wallet")

    builder.button(text="◀️ Back", callback_data="game_menu")
    builder.adjust(1)
    return builder.as_markup()

def wallet_selection_keyboard(available_wallets: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for w in available_wallets:
        builder.button(text=w['name'], callback_data=f"select_wallet_{w['name']}")
    builder.button(text="◀️ Back", callback_data="wallet_menu")
    builder.adjust(1)
    return builder.as_markup()

def wallet_connect_keyboard(url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Open Wallet", url=url)
    builder.button(text="◀️ Cancel", callback_data="wallet_menu")
    builder.adjust(1)
    return builder.as_markup()

def wallet_success_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Go to Game Menu", callback_data="game_menu")
    builder.adjust(1)
    return builder.as_markup()
