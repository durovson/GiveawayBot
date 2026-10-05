import unittest

from services.telegram_chat_ref import normalize_telegram_chat_ref


class TelegramChatReferenceTests(unittest.TestCase):
    def test_public_channel_links_are_normalized(self):
        cases = {
            "t.me/patronofnot": "@patronofnot",
            "https://t.me/patronofnot": "@patronofnot",
            "http://t.me/patronofnot/123": "@patronofnot",
            "https://www.t.me/patronofnot?single": "@patronofnot",
            "https://telegram.me/patronofnot": "@patronofnot",
            "https://t.me/s/patronofnot/123": "@patronofnot",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(normalize_telegram_chat_ref(source), expected)

    def test_existing_chat_identifiers_are_unchanged(self):
        self.assertEqual(normalize_telegram_chat_ref("@patronofnot"), "@patronofnot")
        self.assertEqual(normalize_telegram_chat_ref("-1001234567890"), "-1001234567890")
        self.assertEqual(normalize_telegram_chat_ref(-1001234567890), -1001234567890)

    def test_private_invite_links_are_not_falsely_converted(self):
        invite = "https://t.me/+AbCdEf123456"
        self.assertEqual(normalize_telegram_chat_ref(invite), invite)
        legacy = "https://t.me/joinchat/AbCdEf123456"
        self.assertEqual(normalize_telegram_chat_ref(legacy), legacy)


if __name__ == "__main__":
    unittest.main()
