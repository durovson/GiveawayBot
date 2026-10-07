import os
import unittest
from unittest.mock import AsyncMock, patch

from aiogram import types

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from handlers import giveaway_creation


def _callback() -> types.CallbackQuery:
    return types.CallbackQuery(
        id="admin-recheck",
        from_user=types.User(id=1001, is_bot=False, first_name="Admin"),
        chat_instance="test-chat-instance",
        data="recheck_admin",
    )


class GiveawayAdminRecheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_admin_check_uses_direct_membership_lookup(self):
        bot = AsyncMock()
        bot.id = 8504182834
        bot.get_chat.return_value = types.Chat(
            id=-1004468874781,
            type="channel",
            title="Patron of NOT",
        )
        bot.get_chat_member.return_value = types.ChatMemberOwner(
            user=types.User(id=8504182834, is_bot=True, first_name="Bot"),
            is_anonymous=False,
        )

        result = await giveaway_creation.is_bot_admin("@patronofnot", bot)

        self.assertTrue(result)
        bot.get_chat_member.assert_awaited_once_with(-1004468874781, 8504182834)

    async def test_handler_does_not_acknowledge_callback_before_check(self):
        callback = _callback()
        checker = AsyncMock()

        with (
            patch.object(types.CallbackQuery, "answer", new=AsyncMock()) as answer,
            patch.object(
                giveaway_creation,
                "check_bot_admin_in_channels",
                new=checker,
            ),
        ):
            await giveaway_creation.recheck_admin(
                callback,
                AsyncMock(),
                AsyncMock(),
                {},
            )

        answer.assert_not_awaited()
        checker.assert_awaited_once()

    async def test_success_acknowledges_once_and_advances(self):
        callback = _callback()
        state = AsyncMock()
        state.get_data.return_value = {
            "mandatory_channels": ["@notapes"],
            "is_editing": False,
        }

        with (
            patch.object(
                giveaway_creation,
                "is_bot_admin",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                giveaway_creation,
                "callback_answer_wrapper",
                new=AsyncMock(),
            ) as answer,
            patch.object(
                giveaway_creation,
                "ask_access_type",
                new=AsyncMock(),
            ) as next_screen,
        ):
            await giveaway_creation.check_bot_admin_in_channels(
                callback,
                state,
                AsyncMock(),
                {"giveaway_channels_verified_alert": "Verified"},
            )

        answer.assert_awaited_once_with(callback, "Verified")
        next_screen.assert_awaited_once()

    async def test_failure_shows_visible_alert(self):
        callback = _callback()
        bot = AsyncMock()
        bot.get_me.return_value = types.User(
            id=8504182834, is_bot=True, first_name="crash test", username="nothumanizer_bot"
        )
        state = AsyncMock()
        state.get_data.return_value = {
            "mandatory_channels": ["@notapes"],
        }
        texts = {
            "giveaway_bot_not_admin": "Missing: {channels}",
            "giveaway_admin_check_failed_alert": "Still unavailable",
            "giveaway_i_added_btn": "I ADDED!",
            "giveaway_main_menu_btn": "MAIN MENU",
        }

        with (
            patch.object(
                giveaway_creation,
                "is_bot_admin",
                new=AsyncMock(return_value=False),
            ),
            patch.object(types.CallbackQuery, "answer", new=AsyncMock()) as answer,
            patch.object(
                giveaway_creation,
                "safe_edit_text",
                new=AsyncMock(),
            ),
        ):
            await giveaway_creation.check_bot_admin_in_channels(
                callback,
                state,
                bot,
                texts,
            )

        answer.assert_awaited_once_with("Still unavailable", show_alert=True)


if __name__ == "__main__":
    unittest.main()
