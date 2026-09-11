import os
import unittest
from urllib.parse import parse_qs, urlparse

from services.deep_links import (
    DEFAULT_GRAM_DEPOSIT_WALLET,
    build_telegram_share_url,
    build_tonkeeper_transfer_url,
    get_gram_deposit_wallet,
)


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

    def test_tonkeeper_link_prefills_address_and_comment(self):
        result = build_tonkeeper_transfer_url(DEFAULT_GRAM_DEPOSIT_WALLET, "@not_jammm")
        parsed = urlparse(result)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "app.tonkeeper.com")
        self.assertEqual(parsed.path, f"/transfer/{DEFAULT_GRAM_DEPOSIT_WALLET}")
        self.assertEqual(parse_qs(parsed.query), {"text": ["@not_jammm"]})

    def test_deposit_wallet_has_production_default(self):
        old_value = os.environ.pop("GRAM_DEPOSIT_WALLET", None)
        try:
            self.assertEqual(get_gram_deposit_wallet(), DEFAULT_GRAM_DEPOSIT_WALLET)
        finally:
            if old_value is not None:
                os.environ["GRAM_DEPOSIT_WALLET"] = old_value


if __name__ == "__main__":
    unittest.main()
