import os
import unittest
from urllib.parse import parse_qs, urlparse

import httpx

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from services.deep_links import (
    DEFAULT_GRAM_DEPOSIT_WALLET,
    build_gram_transfer_gateway_url,
    build_telegram_share_url,
    build_ton_transfer_url,
    get_gram_deposit_wallet,
)
from web_server import app


class DeepLinkTests(unittest.TestCase):
    def test_telegram_share_url_round_trip(self):
        referral = "https://t.me/MyBot?start=ref_A1B2C3"
        text = "┏┅🔞┅/ INVITE /\n┋\n┣ Immerse yourself in NOTAPES"
        result = build_telegram_share_url(referral, text)
        parsed = urlparse(result)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "t.me")
        self.assertEqual(parsed.path, "/share/url")
        self.assertEqual(parse_qs(parsed.query), {"url": [referral], "text": [text]})
        self.assertNotIn(" ", result)

    def test_universal_ton_link_prefills_address_and_comment(self):
        result = build_ton_transfer_url(DEFAULT_GRAM_DEPOSIT_WALLET, "@not_jammm")
        parsed = urlparse(result)

        self.assertEqual(parsed.scheme, "ton")
        self.assertEqual(parsed.netloc, "transfer")
        self.assertEqual(parsed.path, f"/{DEFAULT_GRAM_DEPOSIT_WALLET}")
        self.assertEqual(parse_qs(parsed.query), {"text": ["@not_jammm"]})

    def test_universal_ton_link_supports_nanogram_amount(self):
        result = build_ton_transfer_url(
            DEFAULT_GRAM_DEPOSIT_WALLET,
            "@not_jammm",
            amount=100_000_000,
        )
        self.assertEqual(parse_qs(urlparse(result).query), {
            "text": ["@not_jammm"],
            "amount": ["100000000"],
        })

    def test_gateway_is_https_and_localized(self):
        old_base = os.environ.get("GRAM_TRANSFER_PUBLIC_URL")
        os.environ["GRAM_TRANSFER_PUBLIC_URL"] = "https://bot.example/"
        try:
            parsed = urlparse(build_gram_transfer_gateway_url("@not_jammm", "ru"))
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(parsed.netloc, "bot.example")
            self.assertEqual(parsed.path, "/gram/transfer")
            self.assertEqual(parse_qs(parsed.query), {
                "comment": ["@not_jammm"],
                "lang": ["ru"],
            })
        finally:
            if old_base is None:
                os.environ.pop("GRAM_TRANSFER_PUBLIC_URL", None)
            else:
                os.environ["GRAM_TRANSFER_PUBLIC_URL"] = old_base

    def test_deposit_wallet_has_production_default(self):
        old_value = os.environ.pop("GRAM_DEPOSIT_WALLET", None)
        try:
            self.assertEqual(get_gram_deposit_wallet(), DEFAULT_GRAM_DEPOSIT_WALLET)
        finally:
            if old_value is not None:
                os.environ["GRAM_DEPOSIT_WALLET"] = old_value


class GramTransferGatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_gateway_contains_universal_link_and_localized_fallback(self):
        response = await self.client.get(
            "/gram/transfer",
            params={"comment": "@not_jammm", "lang": "ru"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("ton://transfer/", response.text)
        self.assertIn("ОТКРЫТЬ КОШЕЛЁК", response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")

    async def test_gateway_rejects_invalid_comment(self):
        response = await self.client.get(
            "/gram/transfer",
            params={"comment": "not-a-telegram-username"},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
