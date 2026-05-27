import re
import logging
from loader import bot
from aiogram.exceptions import TelegramBadRequest
from aiogram import types

logger = logging.getLogger(__name__)

def strip_custom_emojis(text: str) -> str:
    return re.sub(r'<tg-emoji emoji-id=["\'].*?["\']>(.*?)</tg-emoji>', r'\1', text)

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
    if user_id in [786080766, 734720997]:
        return True

    chats = await db.get_tracked_chats()
    for chat in chats:
        if await is_admin(chat['chat_id'], user_id):
            return True
    return False

async def is_holder(user_id: int) -> bool:
    return True

# --- TON UTILS ---

def normalize_to_raw(address: str) -> str:
    """Normalize TON address to raw format (0:hex) with safety."""
    if not address or not isinstance(address, str):
        return ""
    try:
        # Simple normalization: if it's already 0:..., keep it, else lower it
        if ":" in address:
            parts = address.split(":")
            if len(parts) == 2:
                return f"{parts[0]}:{parts[1].lower()}"
        return address.lower().strip()
    except Exception:
        return ""

def raw_to_user_friendly(address: str) -> str:
    """Convert raw address to short friendly format for UI with safety."""
    if not address or not isinstance(address, str):
        return ""
    try:
        if ":" in address:
            parts = address.split(":")
            addr = parts[1]
            return f"UQ{addr[:4]}...{addr[-4:]}".upper()
        if len(address) > 12:
            return f"{address[:6]}...{address[-4:]}"
        return address
    except Exception:
        return address

# --- UI HELPERS ---

async def safe_answer(message, text, **kwargs):
    try:
        return await message.answer(text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" not in str(e) and "DOCUMENT_INVALID" not in str(e):
            raise e
        try:
            return await message.answer(strip_custom_emojis(text), **kwargs)
        except TelegramBadRequest:
            return await message.answer(strip_all_tags(text), **kwargs)

async def safe_edit_text(message, text, **kwargs):
    if isinstance(message, types.CallbackQuery):
        target = message.message
    else:
        target = message

    if not target:
        return None

    state = kwargs.pop('state', None)

    try:
        msg = await target.edit_text(text, **kwargs)
        if msg and state:
            await state.update_data(last_msg_id=msg.message_id)
        return msg
    except TelegramBadRequest as e:
        err_msg = str(e).lower()

        if "message is not modified" in err_msg:
            return target

        if any(x in err_msg for x in ["document_invalid", "there is no text in the message to edit", "message can't be edited", "message to edit not found"]):
            try:
                await target.delete()
            except Exception:
                pass

            msg = await target.answer(text, **kwargs)
            if msg and state:
                await state.update_data(last_msg_id=msg.message_id)
            return msg

        if "can't parse entities" in err_msg:
            try:
                return await target.edit_text(strip_custom_emojis(text), **kwargs)
            except TelegramBadRequest:
                return await target.edit_text(strip_all_tags(text), **kwargs)
        raise e

async def safe_bot_edit_text(bot, chat_id, message_id, text, **kwargs):
    try:
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)
    except TelegramBadRequest as e:
        err_msg = str(e).lower()
        if any(x in err_msg for x in ["document_invalid", "message is not modified", "can't be edited", "no text in the message"]):
            try:
                await bot.delete_message(chat_id, message_id)
            except:
                pass
            return await bot.send_message(chat_id, text, **kwargs)

        if "can't parse entities" in err_msg:
            try:
                return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=strip_custom_emojis(text), **kwargs)
            except TelegramBadRequest:
                return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=strip_all_tags(text), **kwargs)
        raise e

async def safe_bot_send_message(bot, chat_id, text, **kwargs):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
    except TelegramBadRequest as e:
        if "can't parse entities" not in str(e) and "DOCUMENT_INVALID" not in str(e):
            raise e
        try:
            return await bot.send_message(chat_id=chat_id, text=strip_custom_emojis(text), **kwargs)
        except TelegramBadRequest:
            return await bot.send_message(chat_id=chat_id, text=strip_all_tags(text), **kwargs)
