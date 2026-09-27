"""TON Connect wallet configurations used by the bot.

The bot intentionally keeps a small, explicit allow-list instead of depending on
``pytonconnect.get_wallets()`` at runtime.  pytonconnect's bundled fallback list
is stale, so a registry/network failure can otherwise make recently added or
renamed wallets disappear from the Telegram picker.

Technical values are kept in sync with the canonical TON Connect wallets list:
https://github.com/ton-connect/wallets-list/blob/main/wallets-v2.json

Branding / connection pages:
- Keeper (formerly Tonkeeper): https://keeperwallet.com/
- My Wallet (formerly MyTonWallet): https://mywallet.io/
- Gram Wallet: https://gramwallet.io/
"""

from __future__ import annotations

from copy import deepcopy
from typing import Final


DIRECT_WALLET_ORDER: Final[tuple[str, ...]] = (
    "telegram-wallet",
    "tonkeeper",
    "mytonwallet",
    "gramwallet",
)

# pytonconnect expects a flattened config with ``bridge_url`` and
# ``universal_url``.  The app_name values are stable protocol identifiers and
# therefore remain unchanged after the Keeper / My Wallet rebrands.
_DIRECT_WALLETS: Final[dict[str, dict[str, str]]] = {
    "telegram-wallet": {
        "app_name": "telegram-wallet",
        "name": "Wallet",
        "image": "https://wallet.tg/images/logo-288.png",
        "about_url": "https://wallet.tg/",
        "universal_url": "https://t.me/wallet?attach=wallet",
        "bridge_url": "https://walletbot.me/tonconnect-bridge/bridge",
    },
    "tonkeeper": {
        "app_name": "tonkeeper",
        "name": "Keeper",
        "image": "https://tonkeeper.com/assets/tonconnect-icon.png",
        "about_url": "https://keeperwallet.com/",
        "universal_url": "https://app.tonkeeper.com/ton-connect",
        "bridge_url": "https://bridge.tonapi.io/bridge",
        "deep_link": "tonkeeper-tc://",
    },
    "mytonwallet": {
        "app_name": "mytonwallet",
        "name": "My Wallet",
        "image": "https://static.mywallet.io/mywallet/icon-288.png",
        "about_url": "https://mywallet.io/?utm_source=tc",
        "universal_url": "https://connect.mytonwallet.org",
        "bridge_url": "https://tonconnectbridge.mytonwallet.org/bridge/",
        "deep_link": "mytonwallet-tc://",
    },
    "gramwallet": {
        "app_name": "gramwallet",
        "name": "Gram Wallet",
        "image": "https://static.gramwallet.io/gramwallet/icon-288.png",
        "about_url": "https://gramwallet.io",
        "universal_url": "https://connect.gramwallet.io",
        "bridge_url": "https://tonconnectbridge.mytonwallet.org/bridge/",
        "deep_link": "gramwallet-tc://",
    },
}

_WALLET_ALIASES: Final[dict[str, str]] = {
    # Telegram Wallet.
    "telegram-wallet": "telegram-wallet",
    "wallet": "telegram-wallet",
    "telegram wallet": "telegram-wallet",
    # Keeper / legacy Tonkeeper labels.
    "tonkeeper": "tonkeeper",
    "keeper": "tonkeeper",
    # My Wallet / legacy MyTonWallet labels.
    "mytonwallet": "mytonwallet",
    "my wallet": "mytonwallet",
    "mywallet": "mytonwallet",
    # Gram Wallet.
    "gramwallet": "gramwallet",
    "gram wallet": "gramwallet",
}


def resolve_wallet_id(value: str | None) -> str | None:
    """Resolve a stable app_name from a current or legacy wallet label."""
    if not value:
        return None
    return _WALLET_ALIASES.get(value.strip().casefold())


def get_direct_wallets() -> list[dict[str, str]]:
    """Return fresh copies of the wallets shown in the Telegram picker."""
    return [deepcopy(_DIRECT_WALLETS[wallet_id]) for wallet_id in DIRECT_WALLET_ORDER]


def get_direct_wallet(wallet_id_or_name: str | None) -> dict[str, str] | None:
    """Return one wallet config by app_name or current/legacy display name."""
    wallet_id = resolve_wallet_id(wallet_id_or_name)
    if wallet_id is None:
        return None
    config = _DIRECT_WALLETS.get(wallet_id)
    return deepcopy(config) if config else None
