import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from database import db
from handlers.otc_market import OfferCooldown, submit_offer
from services.localization import get_locale_by_lang


class FakeState:
    def __init__(self):
        self.cleared = False

    async def get_data(self):
        return {"offer_listing_id": 7}

    async def clear(self):
        self.cleared = True


class FakeMessage:
    def __init__(self):
        self.text = "2.5"
        self.from_user = SimpleNamespace(id=200, username="buyer")
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text, kwargs))


class OTCNotificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_seller_notification_uses_seller_language(self):
        offer_payloads = []

        async def get_listing(_listing_id):
            return {"id": 7, "seller_id": 100, "item_name": "Rare NFT", "status": "active"}

        async def ensure_user(_user_id):
            return None

        async def create_offer(data):
            offer_payloads.append(data)
            return {"id": 55}

        async def get_language(user_id):
            self.assertEqual(user_id, 100)
            return "ru"

        old_methods = {
            "get_otc_listing": db.get_otc_listing,
            "ensure_user_exists": db.ensure_user_exists,
            "create_otc_offer": db.create_otc_offer,
            "get_user_language": db.get_user_language,
        }
        old_remaining = OfferCooldown.__dict__["remaining"]
        old_mark = OfferCooldown.__dict__["mark"]
        try:
            db.get_otc_listing = get_listing
            db.ensure_user_exists = ensure_user
            db.create_otc_offer = create_offer
            db.get_user_language = get_language
            OfferCooldown.remaining = classmethod(lambda _cls, _user_id, _listing_id: 0)
            OfferCooldown.mark = classmethod(lambda _cls, _user_id, _listing_id: None)

            message = FakeMessage()
            state = FakeState()
            bot = FakeBot()
            await submit_offer(message, state, bot, get_locale_by_lang("en"))
        finally:
            for name, method in old_methods.items():
                setattr(db, name, method)
            OfferCooldown.remaining = old_remaining
            OfferCooldown.mark = old_mark

        self.assertTrue(state.cleared)
        self.assertEqual(offer_payloads[0]["amount_ton"], "2.5")
        self.assertEqual(len(bot.messages), 1)
        seller_id, seller_notice, kwargs = bot.messages[0]
        self.assertEqual(seller_id, 100)
        self.assertIn("НОВОЕ OTC-ПРЕДЛОЖЕНИЕ", seller_notice)
        self.assertIn("Покупатель:", seller_notice)
        buttons = [button.text for row in kwargs["reply_markup"].inline_keyboard for button in row]
        self.assertEqual(buttons, ["ПРИНЯТЬ", "ОТКЛОНИТЬ", "ПРОФИЛЬ"])
        self.assertIn("Your offer", message.answers[0][0])

    def test_buyer_result_is_branded_in_each_locale(self):
        en = get_locale_by_lang("en")["otc_offer_buyer_result"]
        ru = get_locale_by_lang("ru")["otc_offer_buyer_result"]
        self.assertIn("OTC OFFER UPDATE", en)
        self.assertIn("СТАТУС OTC-ПРЕДЛОЖЕНИЯ", ru)
        self.assertTrue(en.startswith("┏┅⋐"))
        self.assertTrue(ru.startswith("┏┅⋐"))

    def test_all_otc_offer_copy_uses_gram(self):
        keys = (
            "otc_offer_amount_prompt", "otc_offer_invalid",
            "otc_offer_seller_notice", "otc_offer_sent",
            "otc_offer_buyer_result",
        )
        for lang in ("en", "ru"):
            texts = get_locale_by_lang(lang)
            for key in keys:
                self.assertIn("GRAM", texts[key])
                self.assertNotIn(" TON", texts[key])


if __name__ == "__main__":
    unittest.main()
