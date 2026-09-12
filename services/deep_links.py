import os
from urllib.parse import quote, urlencode


DEFAULT_GRAM_DEPOSIT_WALLET = (
    "UQBmhVw9CcumCuhFnVM3vUepTpiXT5m6ffTSeZ990ySvXSf7"
)
DEFAULT_GRAM_DEPOSIT_WALLET_NAME = "notapes.ton"
DEFAULT_PUBLIC_BASE_URL = "https://giveaway-bot-hiap.onrender.com"


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


def get_public_base_url() -> str:
    return (
        os.getenv("GRAM_TRANSFER_PUBLIC_URL", "").strip()
        or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        or os.getenv("CUSTOM_URL", "").strip()
        or DEFAULT_PUBLIC_BASE_URL
    ).rstrip("/")


def build_ton_transfer_url(
    wallet_address: str,
    comment: str,
    amount: int | None = None,
) -> str:
    address = quote(wallet_address.strip(), safe="")
    params: dict[str, str | int] = {"text": comment}
    if amount is not None:
        if amount <= 0:
            raise ValueError("amount must be a positive number of nanograms")
        params["amount"] = amount
    query = urlencode(params, quote_via=quote, safe="")
    return f"ton://transfer/{address}?{query}"


def build_gram_transfer_gateway_url(comment: str, language: str = "en") -> str:
    query = urlencode(
        {"comment": comment, "lang": "ru" if language == "ru" else "en"},
        quote_via=quote,
        safe="",
    )
    return f"{get_public_base_url()}/gram/transfer?{query}"
