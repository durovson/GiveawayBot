import os
os.environ.setdefault('BOT_TOKEN', '123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from handlers import admin, main_menu
from services import arena_config
from locales.en.main_menu import TEXTS


class PanelTests(unittest.IsolatedAsyncioTestCase):
    async def test_visibility_is_independent_of_other_admins(self):
        with patch.object(main_menu, 'PANEL_ADMIN_IDS', {786080766}):
            for uid, visible in ((786080766, True), (734720997, False), (123, False)):
                kb = await main_menu.get_main_menu_keyboard(uid, TEXTS, False)
                buttons = [b for row in kb.inline_keyboard for b in row]
                self.assertEqual(any(b.callback_data == 'admin_panel' for b in buttons), visible)
                self.assertFalse(any(b.callback_data == 'admin_update_gif' for b in buttons))

    async def test_unauthorized_cannot_upload_or_choose_chat_even_with_state(self):
        event = SimpleNamespace(from_user=SimpleNamespace(id=123), chat=SimpleNamespace(type='private'))
        state = SimpleNamespace(get_data=AsyncMock())
        with patch.object(admin, 'PANEL_ADMIN_IDS', {786080766}), patch.object(admin, 'select_chat', new=AsyncMock()) as select:
            await admin.enter_chat(event, state, TEXTS)
            await admin.process_gif_file(event, state, TEXTS)
        select.assert_not_awaited()
        state.get_data.assert_not_awaited()

    async def test_chat_validation_rejects_channels_and_missing_membership(self):
        bot = SimpleNamespace(id=99, get_chat=AsyncMock(return_value=SimpleNamespace(id=-100, type='channel')),
                              get_chat_member=AsyncMock(return_value=SimpleNamespace(status='left')))
        with patch.object(admin, 'save_target_chat', new=AsyncMock()) as save:
            with self.assertRaises(ValueError):
                await admin.select_chat(bot, -100)
            bot.get_chat.return_value=SimpleNamespace(id=-100, type='supergroup', permissions=None)
            with self.assertRaises(ValueError):
                await admin.select_chat(bot, -100)
            save.assert_not_awaited()
            bot.get_chat_member.return_value=SimpleNamespace(status='administrator')
            await admin.select_chat(bot, -100)
            save.assert_awaited_once_with(bot, -100)

    async def test_saved_destination_overrides_env_and_is_scoped_by_bot(self):
        query=MagicMock()
        query.select.return_value=query
        query.eq.return_value=query
        query.execute=AsyncMock(return_value=SimpleNamespace(data=[{'value':'-100123'}]))
        with patch.object(arena_config.db, 'client', SimpleNamespace(table=MagicMock(return_value=query))), \
             patch.dict(os.environ, {'ARENA_CHAT_ID':'-100999'}):
            self.assertEqual(await arena_config.target_chat(SimpleNamespace(id=99)), -100123)
            query.eq.assert_called_with('key','arena_chat_id:99')
            query.execute.return_value=SimpleNamespace(data=[])
            self.assertEqual(await arena_config.target_chat(SimpleNamespace(id=100)), -100999)
            query.execute.side_effect=RuntimeError('database offline')
            with self.assertRaises(RuntimeError):
                await arena_config.target_chat(SimpleNamespace(id=99))
