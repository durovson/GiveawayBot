import os
os.environ.setdefault('BOT_TOKEN','123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi')
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from services.arena_emoji import ASSETS, arena_emojis
from handlers import arena


class ArenaPresentationTests(unittest.IsolatedAsyncioTestCase):
    async def test_ports_are_scanned_before_connection_in_both_languages(self):
        bot=SimpleNamespace(send_message=AsyncMock())
        match={'host_id':1,'guest_id':2,'host_name':'A','guest_name':'B','language':'ru'}
        with patch.object(arena.db,'get_user_language',new=AsyncMock(side_effect=['ru','en'])), \
             patch.object(arena.asyncio,'sleep',new=AsyncMock()):
            await arena.simulate(bot,match)
        for uid, scan, node in ((1,'СКАНИРОВАНИЕ ПОРТОВ','ПОДКЛЮЧЕНИЕ К УЗЛУ'),(2,'SCANNING PORTS','CONNECTING TO NODE')):
            texts=[call.args[1] for call in bot.send_message.await_args_list if call.args[0]==uid]
            self.assertIn(scan,texts[0])
            self.assertGreater(next(i for i,text in enumerate(texts) if node in text),0)

    def test_all_assets_and_no_nested_tags(self):
        for token, (glyph, asset) in ASSETS.items():
            expected=f'<tg-emoji emoji-id="{asset}">{glyph}</tg-emoji>'
            self.assertEqual(arena_emojis(token),expected)
            self.assertEqual(arena_emojis(expected),expected)
        self.assertIn('5316930493223025689',arena.screen('RESULT','🏁'))
        self.assertIn('5337037846475720165',arena.screen('FIGHT','👾'))

    async def test_menu_spacing_and_store_balance_order_both_languages(self):
        callback=SimpleNamespace(from_user=SimpleNamespace(id=1),answer=AsyncMock())
        state=AsyncMock()
        for lang, title in (('ru','STORE: ЖЕТОНЫ'),('en','STORE: TOKENS')):
            with patch.object(arena,'balance',new=AsyncMock(return_value=220)), \
                 patch.object(arena.db,'get_points',new=AsyncMock(return_value={'total_points':73})), \
                 patch.object(arena,'safe_edit_text',new=AsyncMock()) as edit:
                await arena.items(callback,state,lang)
                text=edit.call_args.args[1]
                self.assertIn(title,text)
                self.assertLess(text.index('73'),text.index('220'))
                self.assertLess(text.index('220'),text.index('1 RP = 100'))
                await arena.show_arena(callback,state,lang)
                text=edit.call_args.args[1]
                self.assertIn('220\n┋\n┣ [ <b>50',text)
                await arena.arena_store_hub(callback,state,lang)
                buttons=[b for row in edit.call_args.kwargs['reply_markup'].inline_keyboard for b in row]
                button=next(b for b in buttons if b.callback_data=='arena:items')
                self.assertEqual(button.text,'ЖЕТОНЫ' if lang=='ru' else 'TOKENS')
                self.assertIsNone(button.icon_custom_emoji_id)

    async def test_unaffordable_custom_stake_does_not_advance_or_charge(self):
        message=SimpleNamespace(from_user=SimpleNamespace(id=1),text='100',answer=AsyncMock())
        state=AsyncMock()
        with patch.object(arena,'balance',new=AsyncMock(return_value=70)), \
             patch.object(arena,'rpc',new=AsyncMock()) as rpc:
            await arena.custom_stake(message,state,'ru')
        self.assertIn('от 15 до 20',message.answer.call_args.args[0])
        state.update_data.assert_not_awaited()
        rpc.assert_not_awaited()
