import ast
import os
import pathlib
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from aiogram import Bot
from loader import TelegramLinkAwareBot, bot


class TelegramAdminDetectionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = pathlib.Path("loader.py")
        cls.source = cls.path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _class_source(self, name: str) -> str:
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == name:
                return ast.get_source_segment(self.source, node)
        self.fail(f"Class {name} not found")

    def test_bot_wrapper_normalizes_administrator_list_calls(self):
        source = self._class_source("TelegramLinkAwareBot")
        self.assertIn("async def get_chat_administrators", source)
        self.assertIn("normalize_telegram_chat_ref", source)

    def test_self_membership_check_falls_back_to_admin_list(self):
        source = self._class_source("TelegramLinkAwareBot")
        self.assertIn("_get_self_admin_via_list", source)
        self.assertIn("getChatAdministrators", source)
        self.assertIn("user_id == self.id", source)
        self.assertIn("return_bots=True", source)

    def test_numeric_channel_id_retries_public_alias(self):
        source = self._class_source("TelegramLinkAwareBot")
        self.assertIn("_public_chat_aliases", source)
        self.assertIn("_chat_ref_candidates", source)
        self.assertIn("_get_chat_member_with_alias_retry", source)
        self.assertIn("aliases[chat.id]", source)

    def test_false_admin_result_is_logged_with_status(self):
        source = self._class_source("TelegramLinkAwareBot")
        self.assertIn("Bot admin check negative", source)
        self.assertIn("_chat_member_status(member)", source)

    def test_universal_admin_check_uses_read_only_boost_probe(self):
        source = self._class_source("TelegramLinkAwareBot")
        self.assertIn("verify_self_administrator", source)
        self.assertIn("get_user_chat_boosts", source)
        self.assertIn("_self_chat_statuses", source)


class TelegramAdminDetectionRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_boost_probe_confirms_channel_administrator(self):
        with (
            patch.object(
                TelegramLinkAwareBot,
                "get_chat_member",
                new=AsyncMock(side_effect=RuntimeError("member list is inaccessible")),
            ),
            patch.object(
                Bot,
                "get_user_chat_boosts",
                new=AsyncMock(return_value=SimpleNamespace(boosts=[])),
            ) as boost_probe,
        ):
            result = await bot.verify_self_administrator(-1004468874781)

        self.assertTrue(result)
        boost_probe.assert_awaited_once_with(
            -1004468874781,
            bot.id,
            request_timeout=None,
        )

    async def test_recent_my_chat_member_status_is_final_fallback(self):
        bot._self_chat_statuses = {-1004468874781: "administrator"}
        try:
            with (
                patch.object(
                    TelegramLinkAwareBot,
                    "get_chat_member",
                    new=AsyncMock(side_effect=RuntimeError("member list is inaccessible")),
                ),
                patch.object(
                    Bot,
                    "get_user_chat_boosts",
                    new=AsyncMock(side_effect=RuntimeError("probe unavailable")),
                ),
            ):
                result = await bot.verify_self_administrator(-1004468874781)
        finally:
            bot._self_chat_statuses = {}

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
