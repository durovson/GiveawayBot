import os
from urllib.parse import quote, urlencode


DEFAULT_GRAM_DEPOSIT_WALLET = (
    "UQBmhVw9CcumCuhFnVM3vUepTpiXT5m6ffTSeZ990ySvXSf7"
)
DEFAULT_GRAM_DEPOSIT_WALLET_NAME = "notapes.ton"


def get_gram_deposit_wallet() -> str:
    return os.getenv("GRAM_DEPOSIT_WALLET", "").strip() or DEFAULT_GRAM_DEPOSIT_WALLET


def get_gram_deposit_wallet_name() -> str:
    return (
        os.getenv("GRAM_DEPOSIT_WALLET_NAME", "").strip()
        or DEFAULT_GRAM_DEPOSIT_WALLET_NAME
    )


def build_telegram_share_url(referral_link: str, invite_text: str) -> str:
    query = urlencode(
        {"url": referral_link, "text": invite_text},
        quote_via=quote,
        safe="",
    )
    return f"https://t.me/share/url?{query}"


def build_tonkeeper_transfer_url(wallet_address: str, comment: str) -> str:
    address = quote(wallet_address.strip(), safe="")
    query = urlencode({"text": comment}, quote_via=quote, safe="")
    return f"https://app.tonkeeper.com/transfer/{address}?{query}"
