import unittest
from unittest.mock import AsyncMock, patch

from aiogram.methods import AnswerCallbackQuery, EditMessageMedia, SendMessage, SendMediaGroup, SetMyCommands
from aiogram.types import (BotCommand, BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup,
                           InputMediaPhoto, KeyboardButton, MessageEntity, ReplyKeyboardMarkup)

from middleware.pumpkin_display import PumpkinDisplayMiddleware, pumpkin_text, themed_request
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
        self.assertEqual(updated.text,'<b>Your 🎃: 50 🎃</b>')
        self.assertEqual(first.text,'Buy 10 🎃')
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
        self.assertEqual(updated.entities,entities)
        self.assertEqual(updated.text,'🍑 50 🎃 and 10 🎃')

    def test_media_uses_same_file_object_and_only_changes_caption(self):
        photo=BufferedInputFile(b'photo-data',filename='test.jpg')
        original=EditMessageMedia(chat_id=1,message_id=2,media=InputMediaPhoto(media=photo,caption='50 RP'))
        album=SendMediaGroup(chat_id=1,media=[original.media,InputMediaPhoto(media='telegram-file-id',caption='10 RP')])
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            updated=themed_request(original)
            updated_album=themed_request(album)
        self.assertEqual(updated.media.caption,'50 🎃')
        self.assertIs(updated.media.media,photo)
        self.assertEqual(original.media.caption,'50 RP')
        self.assertEqual([m.caption for m in updated_album.media],['50 🎃','10 🎃'])

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
        self.assertEqual(message.reply_markup.keyboard[0][0].text,'BOOST 🎃')
        self.assertTrue(message.reply_markup.resize_keyboard)


class PumpkinMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_exactly_one_telegram_request_without_new_delays_or_retries(self):
        request=AsyncMock(return_value='sent')
        original=SendMessage(chat_id=1,text='50 RP')
        with patch.object(chat_game_theme,'PUMPKIN_MODE',True):
            result=await PumpkinDisplayMiddleware()(request,'bot',original)
        self.assertEqual(result,'sent')
        self.assertEqual(request.await_count,1)
        self.assertEqual(request.call_args.args[1].text,'50 🎃')
