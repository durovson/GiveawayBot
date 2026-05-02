import re
import pytz
from loader import bot
from aiogram.exceptions import TelegramBadRequest

def strip_custom_emojis(text: str) -> str:
    """Removes <tg-emoji> tags but keeps the standard emoji content."""
    return re.sub(r'<tg-emoji emoji-id=".*?">(.*?)</tg-emoji>', r'\1', text)

def strip_all_tags(text: str) -> str:
    """Removes all HTML tags."""
    return re.sub(r'<[^>]+>', '', text)

async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except Exception:
        return False

async def is_any_admin(user_id: int) -> bool:
    from database import db
    # Hardcoded admin check as a fallback or primary
    if user_id in [786080766, 734720997]:
        return True

    chats = await db.get_tracked_chats()
    for chat in chats:
        if await is_admin(chat['chat_id'], user_id):
            return True
    return False

async def safe_answer(message, text, **kwargs):
    try:
        return await message.answer(text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" not in str(e):
            raise e
        try:
            return await message.answer(strip_custom_emojis(text), **kwargs)
        except TelegramBadRequest:
            return await message.answer(strip_all_tags(text), **kwargs)

async def safe_edit_text(message, text, **kwargs):
    # message can be Message or CallbackQuery
    target = message.message if hasattr(message, 'message') else message
    try:
        return await target.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" not in str(e):
            raise e
        try:
            return await target.edit_text(strip_custom_emojis(text), **kwargs)
        except TelegramBadRequest:
            return await target.edit_text(strip_all_tags(text), **kwargs)

async def safe_bot_edit_text(bot, chat_id, message_id, text, **kwargs):
    try:
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" not in str(e):
            raise e
        try:
            return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=strip_custom_emojis(text), **kwargs)
        except TelegramBadRequest:
            return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=strip_all_tags(text), **kwargs)

async def safe_bot_send_message(bot, chat_id, text, **kwargs):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" not in str(e):
            raise e
        try:
            return await bot.send_message(chat_id=chat_id, text=strip_custom_emojis(text), **kwargs)
        except TelegramBadRequest:
            return await bot.send_message(chat_id=chat_id, text=strip_all_tags(text), **kwargs)
