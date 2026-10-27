import unittest
from unittest.mock import AsyncMock, patch
from aiogram.exceptions import TelegramBadRequest

from aiogram.methods import AnswerCallbackQuery, EditMessageMedia, SendMessage, SendMediaGroup, SetMyCommands
from aiogram.types import (BotCommand, BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup,
                           InputMediaPhoto, KeyboardButton, MessageEntity, ReplyKeyboardMarkup)

from middleware.pumpkin_display import PUMPKIN_HTML, PUMPKIN_ID, PumpkinDisplayMiddleware, pumpkin_text, themed_request
from services import chat_game_theme


class PumpkinDisplayTests(unittest.TestCase):
    def test_global_labels_but_not_names_destinations_or_code(self):
        text = ('Your RP: 50 RP; RP price; 10 РП; @RP @some_RP ARP /RP\n'
                '<a href="https://example.com/RP">Buy for 10 RP</a> '
                '<code>RP</code> <pre>RP wallet</pre> https://example.com/RP')
        with patch.object(chat_game_theme, 'PUMPKIN_MODE', True):
            changed = pumpkin_text(text)
        self.assertIn('Your 🎃: 50 🎃; 🎃 price; 10 🎃', changed)
        self.assertIn('@RP @some_RP ARP /RP', changed)
        self.assertIn('href="https://example.com/RP">Buy for 10 🎃</a>', changed)
        self.assertIn('<code>RP</code> <pre>RP wallet</pre> https://example.com/RP', changed)

    def test_normal_archive_keeps_original_request_and_keyboard(self):
        original = SendMessage(chat_id=1, text='50 RP', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='Buy 10 RP', callback_data='buy_RP')]]))
        with patch.object(chat_game_theme, 'PUMPKIN_MODE', False):
            self.assertIs(themed_request(original), original)

    def test_markup_preserves_callbacks_urls_colors_and_original_object(self):
        original = SendMessage(chat_id=1, text='<b>Your RP: 50 RP</b>', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='Buy 10 RP',callback_data='buy_RP',style='success'),
            InlineKeyboardButton(text='BOOST RP',url='https://example.com/RP?text=RP',style='danger')]]))
        with patch.object(chat_game_theme, 'PUMPKIN_MODE', True):
            updated = themed_request(original)
        first,second = updated.reply_markup.inline_keyboard[0]
        self.assertEqual(updated.text,f'<b>Your {PUMPKIN_HTML}: 50 {PUMPKIN_HTML}</b>')
        self.assertEqual(first.text,'Buy 10')
        self.assertEqual(first.icon_custom_emoji_id,PUMPKIN_ID)
        self.assertEqual(first.callback_data,'buy_RP')
        self.assertEqual(first.style,'success')
        self.assertEqual(second.url,'https://example.com/RP?text=RP')
        self.assertEqual(second.style,'danger')
        self.assertEqual(original.reply_markup.inline_keyboard[0][0].text,'Buy 10 RP')
        self.assertEqual(original.text,'<b>Your RP: 50 RP</b>')

    def test_entity_offsets_are_identical_in_utf16(self):
        text='🍑 50 RP and 10 РП'
        entities=[MessageEntity(type='bold',offset=3,length=5)]
        original=SendMessage(chat_id=1,text=text,entities=entities,parse_mode=None)
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            updated=themed_request(original)
        self.assertEqual(len(text.encode('utf-16-le')),len(updated.text.encode('utf-16-le')))
        self.assertEqual([e for e in updated.entities if e.type!='custom_emoji'],entities)
        self.assertEqual([(e.offset,e.length,e.custom_emoji_id) for e in updated.entities if e.type=='custom_emoji'],
                         [(6,2,PUMPKIN_ID),(16,2,PUMPKIN_ID)])
        self.assertEqual(updated.text,'🍑 50 🎃 and 10 🎃')

    def test_media_uses_same_file_object_and_only_changes_caption(self):
        photo=BufferedInputFile(b'photo-data',filename='test.jpg')
        original=EditMessageMedia(chat_id=1,message_id=2,media=InputMediaPhoto(media=photo,caption='50 RP'))
        album=SendMediaGroup(chat_id=1,media=[original.media,InputMediaPhoto(media='telegram-file-id',caption='10 RP')])
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            updated=themed_request(original)
            updated_album=themed_request(album)
        self.assertEqual(updated.media.caption,f'50 {PUMPKIN_HTML}')
        self.assertIs(updated.media.media,photo)
        self.assertEqual(original.media.caption,'50 RP')
        self.assertEqual([m.caption for m in updated_album.media],[f'50 {PUMPKIN_HTML}',f'10 {PUMPKIN_HTML}'])

    def test_callback_alerts_reply_keyboards_and_command_descriptions(self):
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            alert=themed_request(AnswerCallbackQuery(callback_query_id='RP',text='Added 5 RP',show_alert=True))
            command=themed_request(SetMyCommands(commands=[BotCommand(command='balance',description='Balance RP')]))
            message=themed_request(SendMessage(chat_id=1,text='RP',reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text='BOOST RP')]],resize_keyboard=True)))
        self.assertEqual(alert.text,'Added 5 🎃')
        self.assertEqual(alert.callback_query_id,'RP')
        self.assertTrue(alert.show_alert)
        self.assertEqual(command.commands[0].description,'Balance 🎃')
        self.assertEqual(command.commands[0].command,'balance')
        self.assertEqual(message.reply_markup.keyboard[0][0].text,'BOOST')
        self.assertEqual(message.reply_markup.keyboard[0][0].icon_custom_emoji_id,PUMPKIN_ID)
        self.assertTrue(message.reply_markup.resize_keyboard)

    def test_literal_and_rp_become_premium_without_nesting_existing_emoji(self):
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            text=pumpkin_text(f'50 RP 10 🎃 {PUMPKIN_HTML}',rich=True)
        self.assertEqual(text,f'50 {PUMPKIN_HTML} 10 {PUMPKIN_HTML} {PUMPKIN_HTML}')

    def test_code_entities_are_not_rewritten(self):
        original=SendMessage(chat_id=1,text='RP and RP',parse_mode=None,
                             entities=[MessageEntity(type='code',offset=0,length=2)])
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            updated=themed_request(original)
        self.assertEqual(updated.text,'RP and 🎃')
        self.assertEqual([(e.offset,e.custom_emoji_id) for e in updated.entities if e.type=='custom_emoji'],[(7,PUMPKIN_ID)])


class PumpkinMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_exactly_one_telegram_request_without_new_delays_or_retries(self):
        request=AsyncMock(return_value='sent')
        original=SendMessage(chat_id=1,text='50 RP')
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            result=await PumpkinDisplayMiddleware()(request,'bot',original)
        self.assertEqual(result,'sent')
        self.assertEqual(request.await_count,1)
        self.assertEqual(request.call_args.args[1].text,f'50 {PUMPKIN_HTML}')

    async def test_document_rejection_gets_one_non_recursive_plain_fallback(self):
        original=SendMessage(chat_id=1,text=f'50 RP {PUMPKIN_HTML}',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text='Buy 10 RP',callback_data='buy_RP',style='success')]]))
        request=AsyncMock(side_effect=[TelegramBadRequest(method=original,message='DOCUMENT_INVALID'),'sent'])
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            self.assertEqual(await PumpkinDisplayMiddleware()(request,'bot',original),'sent')
        self.assertEqual(request.await_count,2)
        rich=request.await_args_list[0].args[1]
        fallback=request.await_args_list[1].args[1]
        self.assertIn(PUMPKIN_HTML,rich.text)
        self.assertEqual(fallback.text,'50 🎃 🎃')
        self.assertIsNone(fallback.reply_markup.inline_keyboard[0][0].icon_custom_emoji_id)
        self.assertEqual(fallback.reply_markup.inline_keyboard[0][0].callback_data,'buy_RP')
        self.assertEqual(fallback.reply_markup.inline_keyboard[0][0].style,'success')
        self.assertEqual(original.text,f'50 RP {PUMPKIN_HTML}')

    async def test_unknown_network_outcome_is_never_retried(self):
        request=AsyncMock(side_effect=TimeoutError('unknown send outcome'))
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            with self.assertRaises(TimeoutError):
                await PumpkinDisplayMiddleware()(request,'bot',SendMessage(chat_id=1,text='10 RP'))
        self.assertEqual(request.await_count,1)
