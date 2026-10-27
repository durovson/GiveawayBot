import html
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from aiogram.types import Message, Chat, User
from aiogram.filters import CommandObject
from handlers import chat_games as handlers
from middleware.safe_defense import SafeDefenseMiddleware
from services import chat_games as service
from services import chat_game_theme as theme
from utils import strip_custom_emojis


class ChatGameFormattingTests(unittest.TestCase):
    def attack(self, language="ru", status="pending"):
        return {"language": language, "status": status, "attacker_name": "@bad<name>",
                "victim_name": "@target", "preview_amount": 15, "amount": 17}

    def test_both_themes_both_languages_all_blocks_and_custom_emoji_fallback(self):
        for pumpkin in (True, False):
            with patch.object(theme, "PUMPKIN_MODE", pumpkin):
                for lang in ("ru", "en"):
                    t = service.locale(lang)
                    balance = service.balance_text(75, lang)
                    self.assertIn(t["balance_title"], balance)
                    self.assertIn("75", balance)
                    self.assertEqual("🎃" in balance, pumpkin)
                    for status in ("pending", "stolen", "defended"):
                        text = service.attack_text(self.attack(lang, status), result=status != "pending")
                        self.assertIn("@bad&lt;name&gt;", text)
                        self.assertNotIn("@bad<name>", text)
                        fallback = strip_custom_emojis(text)
                        self.assertNotIn("tg-emoji", fallback)
                        self.assertEqual("🎃" in fallback, pumpkin)
                        if status == "defended":
                            self.assertIn("−15", text)
                            self.assertIn("+10", text)
                            self.assertIn(t["burned"], text)

    def test_top_uses_rp_order_received_but_never_mentions_users(self):
        text = service.top_text([
            {"user_id": 1, "total_points": 175, "users": {"username": "not_jammm"}},
            {"user_id": 2, "total_points": 70, "users": {"first_name": "@someone <b>"}},
            {"user_id": 3, "total_points": 10, "users": None},
        ], 15, "ru")
        self.assertNotIn("@", text)
        self.assertNotIn("tg://user", text)
        self.assertIn("1. not_jammm — 175", text)
        self.assertIn("2. ＠someone &lt;b&gt; — 70", text)
        self.assertIn("3. 3 — 10", text)
        self.assertIn("Сожжено: 15", text)

    def test_custom_emoji_ids_exact(self):
        self.assertEqual(theme.EMOJI["pumpkin"][1], "5368309348739074032")
        self.assertEqual(theme.EMOJI["game"][1], "5258508428212445001")
        self.assertEqual(len(theme.EMOJI), 7)

    def test_first_name_cannot_ping_arbitrary_bystanders(self):
        self.assertEqual(handlers.raw_name({"telegram_id": 1,"first_name": "Hello @bystander"}), "Hello ＠bystander")


class ChatGameHandlersTests(unittest.IsolatedAsyncioTestCase):
    def message(self, **overrides):
        values = dict(from_user=SimpleNamespace(id=1, is_bot=False, username="caller", first_name="Caller"),
                      sender_chat=None, chat=SimpleNamespace(id=-100, type="supergroup"),
                      message_id=123, message_thread_id=None, reply_to_message=None,
                      date=datetime.now(timezone.utc), bot=SimpleNamespace(
                          get_me=AsyncMock(return_value=SimpleNamespace(id=99, can_read_all_group_messages=False)),
                          get_chat_member=AsyncMock(return_value=SimpleNamespace(status="administrator"))))
        values.update(overrides)
        return SimpleNamespace(**values)

    def user(self, lang="ru"):
        return {"telegram_id": 1, "username": "caller", "language": lang}

    def query(self, data):
        query = MagicMock()
        for name in ("select", "eq", "order", "limit", "update", "ilike", "lte", "lt"):
            getattr(query, name).return_value = query
        query.execute = AsyncMock(return_value=SimpleNamespace(data=data))
        return query

    async def test_unknown_caller_always_english_red_open_button_and_no_mutation(self):
        with patch.object(service.ChatGameService, "registered", new=AsyncMock(return_value=None)), \
             patch.object(handlers, "send", new=AsyncMock()) as send:
            result = await handlers.caller(self.message())
        self.assertIsNone(result)
        self.assertIn("you still haven't joined @notfunrobot", send.call_args.args[1])
        button = send.call_args.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.style, "danger")
        self.assertEqual(button.url, "https://t.me/notfunrobot?start=chat_games")

    async def test_anonymous_and_bot_callers_ignored(self):
        with patch.object(service.ChatGameService, "registered", new=AsyncMock()) as registered:
            self.assertIsNone(await handlers.caller(self.message(sender_chat=object())))
            self.assertIsNone(await handlers.caller(self.message(from_user=SimpleNamespace(is_bot=True))))
        registered.assert_not_awaited()

    async def test_balance_is_existing_global_rp_and_missing_row_is_zero(self):
        for rows, expected in (([{"total_points": 70}], "70"), ([], "0")):
            query = self.query(rows)
            with patch.object(handlers, "caller", new=AsyncMock(return_value=self.user())), \
                 patch.object(handlers.db, "client", SimpleNamespace(table=MagicMock(return_value=query))), \
                 patch.object(handlers, "send", new=AsyncMock()) as send:
                await handlers.balance_command(self.message())
            self.assertIn(expected, send.call_args.args[1])
            self.assertIn("БАЛАНС", send.call_args.args[1])

    async def test_safe_help_and_private_chat_never_charge(self):
        for message, expected in ((self.message(), "help"),
                                  (self.message(chat=SimpleNamespace(id=1, type="private")), "GROUP_ONLY")):
            with patch.object(handlers, "caller", new=AsyncMock(return_value=self.user())), \
                 patch.object(handlers, "error", new=AsyncMock()) as error, \
                 patch.object(service.ChatGameService, "rpc", new=AsyncMock()) as rpc:
                await handlers.safe_command(message, CommandObject(command="safe"))
            self.assertEqual(error.call_args.args[1], expected)
            rpc.assert_not_awaited()

    async def test_username_validation_does_not_allow_pattern_injection(self):
        with patch.object(service.ChatGameService, "target_by_username", new=AsyncMock(return_value={})) as target:
            for invalid in ("@abc%xyz", "@test,username.eq.admin", "@x", "hello", "@test name"):
                self.assertIsNone(await handlers.target(self.message(), invalid))
            await handlers.target(self.message(), "@not_jammm")
        target.assert_awaited_once_with("not_jammm")

    async def test_username_underscores_are_literal(self):
        query = self.query([{"telegram_id": 2}])
        with patch.object(service.db, "client", SimpleNamespace(table=MagicMock(return_value=query))):
            await service.ChatGameService.target_by_username("not_jammm")
        query.ilike.assert_called_once_with("username", "not\\_jammm")

    async def test_start_and_warning_are_in_callers_language(self):
        attack = ChatGameFormattingTests().attack()
        attack["id"] = 7
        query = self.query([])
        with patch.object(handlers, "caller", new=AsyncMock(return_value=self.user("en"))), \
             patch.object(handlers, "target", new=AsyncMock(return_value={"telegram_id": 2, "username": "target"})), \
             patch.object(service.ChatGameService, "rpc", new=AsyncMock(return_value={"ok": True, "attack": attack})) as rpc, \
             patch.object(handlers.db, "client", SimpleNamespace(table=MagicMock(return_value=query))), \
             patch.object(handlers, "send", new=AsyncMock(return_value=SimpleNamespace(message_id=124, date=datetime.now(timezone.utc)))):
            await handlers.safe_command(self.message(), CommandObject(command="safe", args="@target"))
        self.assertEqual(rpc.call_args.args[1]["p_language"], "en")
        self.assertEqual(rpc.call_args.args[1]["p_message_id"], 123)
        self.assertEqual(query.update.call_args.args[0]["announcement_id"], 124)

    async def test_send_failure_cancels_and_refunds(self):
        attack = ChatGameFormattingTests().attack(); attack["id"] = 8
        rpc = AsyncMock(side_effect=[{"ok": True, "attack": attack}, {"ok": True}])
        with patch.object(handlers, "caller", new=AsyncMock(return_value=self.user())), \
             patch.object(handlers, "target", new=AsyncMock(return_value={"telegram_id": 2})), \
             patch.object(service.ChatGameService, "rpc", rpc), \
             patch.object(handlers, "send", new=AsyncMock(side_effect=RuntimeError("offline"))), \
             patch.object(handlers, "error", new=AsyncMock()):
            await handlers.safe_command(self.message(), CommandObject(command="safe", args="@target"))
        self.assertEqual(rpc.await_args_list[-1].args, ("finish_safe_attack", {"p_id": 8, "p_cancel": True}))

    async def test_replayed_update_does_not_send_warning_twice(self):
        with patch.object(handlers, "caller", new=AsyncMock(return_value=self.user())), \
             patch.object(handlers, "target", new=AsyncMock(return_value={"telegram_id": 2})), \
             patch.object(service.ChatGameService, "rpc", new=AsyncMock(return_value={"ok": True, "duplicate": True})), \
             patch.object(handlers, "send", new=AsyncMock()) as send:
            await handlers.safe_command(self.message(), CommandObject(command="safe", args="@target"))
        send.assert_not_awaited()

    async def test_privacy_mode_prevents_invisible_attacks(self):
        message = self.message()
        message.bot.get_chat_member.return_value = SimpleNamespace(status="member")
        with patch.object(handlers, "caller", new=AsyncMock(return_value=self.user())), \
             patch.object(handlers, "target", new=AsyncMock(return_value={"telegram_id": 2})), \
             patch.object(service.ChatGameService, "rpc", new=AsyncMock()) as rpc, \
             patch.object(handlers, "error", new=AsyncMock()) as error:
            await handlers.safe_command(message, CommandObject(command="safe", args="@target"))
        self.assertEqual(error.call_args.args[1], "READ_ACCESS")
        rpc.assert_not_awaited()

    async def test_stale_reassigned_handle_cannot_target_the_wrong_person(self):
        message = self.message()
        message.bot.get_chat_member.side_effect = [SimpleNamespace(status="administrator"),
            SimpleNamespace(status="member",user=SimpleNamespace(is_bot=False,username="renamed_user",first_name="T"))]
        with patch.object(handlers, "caller", new=AsyncMock(return_value=self.user())), \
             patch.object(handlers, "target", new=AsyncMock(return_value={"telegram_id": 2,"username":"old_handle"})), \
             patch.object(service.ChatGameService, "rpc", new=AsyncMock()) as rpc, \
             patch.object(handlers, "error", new=AsyncMock()) as error:
            await handlers.safe_command(message, CommandObject(command="safe", args="@old_handle"))
        self.assertEqual(error.call_args.args[1],"TARGET_NOT_FOUND")
        rpc.assert_not_awaited()

    async def test_defense_observes_media_without_pinging_or_registering_bystanders(self):
        for payload in ({"text": "hello"}, {"sticker": {"file_id": "x", "file_unique_id": "x", "type": "regular",
                                                           "width": 1,"height": 1,"is_animated": False,"is_video": False}},
                        {"voice": {"file_id": "x", "file_unique_id": "x", "duration": 1}}):
            event = Message(message_id=10, date=datetime.now(timezone.utc), chat=Chat(id=-100,type="supergroup"),
                            from_user=User(id=2,is_bot=False,first_name="Target"), **payload)
            handler = AsyncMock()
            with patch.object(service.ChatGameService, "rpc", new=AsyncMock(return_value=0)) as rpc:
                await SafeDefenseMiddleware()(handler,event,{})
            self.assertEqual(rpc.call_args.args[0], "react_to_safe_attacks")
            self.assertEqual(rpc.call_args.args[1]["p_user_id"],2)
            handler.assert_awaited_once()

    async def test_private_and_service_messages_do_not_trigger_defense(self):
        for event in (Message(message_id=10,date=datetime.now(timezone.utc),chat=Chat(id=2,type="private"),
                              from_user=User(id=2,is_bot=False,first_name="T"),text="hello"),
                      Message(message_id=10,date=datetime.now(timezone.utc),chat=Chat(id=-100,type="supergroup"),
                              from_user=User(id=2,is_bot=False,first_name="T"),new_chat_title="title")):
            with patch.object(service.ChatGameService, "rpc", new=AsyncMock()) as rpc:
                await SafeDefenseMiddleware()(AsyncMock(),event,{})
            rpc.assert_not_awaited()

    async def test_command_registration_preserves_other_commands(self):
        bot = SimpleNamespace(get_my_commands=AsyncMock(return_value=[SimpleNamespace(command="help",description="Help")]),
                              set_my_commands=AsyncMock())
        await service.register_chat_commands(bot)
        self.assertEqual(bot.set_my_commands.await_count,3)
        for call in bot.set_my_commands.await_args_list:
            self.assertEqual({c.command for c in call.args[0]}, {"help","balance","top","safe"})
            self.assertEqual(call.kwargs["scope"].type,"all_group_chats")

    async def test_worker_settles_persisted_attack_and_sends_stored_language(self):
        attack = ChatGameFormattingTests().attack("ru", "defended")
        attack.update(id=7, chat_id=-100, thread_id=11)
        query = self.query([{"id": 7}])
        with patch.object(service.db, "client", SimpleNamespace(table=MagicMock(return_value=query))), \
             patch.object(service.ChatGameService, "rpc", new=AsyncMock(side_effect=[{"ok": True}, [attack]])) as rpc, \
             patch.object(service, "safe_bot_send_message", new=AsyncMock()) as send:
            await service.ChatGameService.tick(object())
        self.assertEqual(rpc.await_args_list[0].args, ("finish_safe_attack", {"p_id": 7}))
        self.assertIn("СИГНАЛИЗАЦИЯ", send.call_args.args[2])
        self.assertEqual(send.call_args.kwargs["message_thread_id"],11)
        datetime.fromisoformat(query.update.call_args.args[0]["notified_at"])

    async def test_notification_network_failure_is_not_acknowledged(self):
        attack = ChatGameFormattingTests().attack("en", "stolen")
        attack.update(id=7,chat_id=-100)
        query = self.query([])
        with patch.object(service.db, "client", SimpleNamespace(table=MagicMock(return_value=query))), \
             patch.object(service.ChatGameService, "rpc", new=AsyncMock(return_value=[attack])), \
             patch.object(service, "safe_bot_send_message", new=AsyncMock(side_effect=RuntimeError("network"))):
            await service.ChatGameService.tick(object())
        query.update.assert_not_called()

    async def test_restart_refunds_overdue_attacks_instead_of_unobserved_theft(self):
        query = self.query([])
        query.execute.side_effect = [SimpleNamespace(data=[{"id": 8}]),SimpleNamespace(data=[])]
        with patch.object(service.db, "client", SimpleNamespace(table=MagicMock(return_value=query))), \
             patch.object(service.ChatGameService, "rpc", new=AsyncMock()) as rpc:
            await service.ChatGameService.recover_overdue("2026-10-27T15:00:00+00:00")
        rpc.assert_awaited_once_with("finish_safe_attack", {"p_id":8,"p_cancel":True})
        query.lt.assert_called_with("deadline","2026-10-27T15:00:00+00:00")

    async def test_recalculation_combines_current_credits_under_db_lock(self):
        from services.points_service import PointsService
        query = self.query(135)
        client = SimpleNamespace(rpc=MagicMock(return_value=query))
        with patch.object(service.db, "client", client), \
             patch.object(service.db, "get_points", new=AsyncMock(return_value={"packs": 10,"manual_adjustment":0})), \
             patch.object(service.db, "get_user_by_telegram_id", new=AsyncMock(return_value={"telegram_id":1})), \
             patch.object(service.db, "is_og_holder", new=AsyncMock(return_value=False)), \
             patch.object(service.db, "upsert_points", new=AsyncMock()) as stale_write:
            self.assertEqual(await PointsService.recalculate_points(1),135)
        client.rpc.assert_called_once_with("update_calculated_rp",{"p_user_id":1,"p_holder_bonus":0,"p_calculated":100})
        stale_write.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
