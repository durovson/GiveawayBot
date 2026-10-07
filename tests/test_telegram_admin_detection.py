import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from aiogram import Bot
from handlers.giveaway_creation import is_bot_admin
from loader import TelegramLinkAwareBot


class TelegramAdminDetectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_channels_and_groups_use_the_current_bot_identity(self):
        for chat_type in ("channel", "supergroup", "group"):
            with self.subTest(chat_type=chat_type):
                client = SimpleNamespace(
                    id=8504182834,
                    get_chat=AsyncMock(return_value=SimpleNamespace(id=-100123, type=chat_type)),
                    get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator")),
                )
                self.assertTrue(await is_bot_admin("@notapes", client))
                client.get_chat_member.assert_awaited_once_with(-100123, 8504182834)

    async def test_numeric_chat_checks_same_bot(self):
        client = SimpleNamespace(
            id=8504182834,
            get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator")),
        )
        self.assertTrue(await is_bot_admin(-100123, client))
        client.get_chat_member.assert_awaited_once_with(-100123, 8504182834)

    async def test_non_member_and_inaccessible_chat_cannot_pass(self):
        for result in ("left", "member", "restricted", "kicked", RuntimeError("member list is inaccessible")):
            with self.subTest(result=result):
                lookup = AsyncMock(
                    side_effect=result if isinstance(result, Exception) else None,
                    return_value=SimpleNamespace(status=result),
                )
                client = SimpleNamespace(id=8504182834, get_chat_member=lookup)
                self.assertFalse(await is_bot_admin(-100123, client))

    async def test_wrapper_makes_only_one_membership_request(self):
        client = TelegramLinkAwareBot("123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
        try:
            with patch.object(Bot, "get_chat_member", new=AsyncMock(side_effect=RuntimeError("inaccessible"))) as lookup:
                with self.assertRaises(RuntimeError):
                    await client.get_chat_member("https://t.me/notapes", 123456)
                lookup.assert_awaited_once_with("@notapes", 123456, request_timeout=None)
        finally:
            await client.session.close()
