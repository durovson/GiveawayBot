import re
import logging
from loader import bot
from aiogram.exceptions import TelegramBadRequest
from aiogram import types
from pytoniq_core import Address

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
    try:
        member = await bot.get_chat_member(-1001944951957, user_id)
        return member.status not in ["left", "kicked"]
    except Exception:
        return False

# --- TON UTILS ---

def normalize_wallet(addr: str) -> str:
    """Normalize TON address to a consistent user-friendly format."""
    if not addr or not isinstance(addr, str):
        return ""
    try:
        return Address(addr).to_str(
            is_user_friendly=True,
            is_url_safe=True,
            is_bounceable=False,
            is_test_only=False
        ).lower()
    except Exception:
        return addr.lower().strip()

def normalize_to_raw(address: str) -> str:
    """Normalize TON address to raw format (0:hex) with safety."""
    if not address or not isinstance(address, str):
        return ""
    try:
        # If it's already in raw format or can be parsed
        try:
            return Address(address).to_str(is_user_friendly=False).lower()
        except:
            if ":" in address:
                parts = address.split(":")
                if len(parts) == 2:
                    return f"{parts[0]}:{parts[1].lower()}"
            return address.lower().strip()
    except Exception:
        return ""

def raw_to_user_friendly(address: str) -> str:
    """Convert address to user-friendly format."""
    if not address or not isinstance(address, str):
        return ""
    try:
        return Address(address).to_str(is_user_friendly=True, is_url_safe=True, is_bounceable=False)
    except Exception:
        return address

def short_wallet(addr: str) -> str:
    """Returns a shortened version of the wallet address for UI."""
    if not addr:
        return "Not connected"

    friendly = addr
    try:
        friendly = Address(addr).to_str(is_user_friendly=True, is_url_safe=True, is_bounceable=False)
    except:
        pass

    if len(friendly) <= 12:
        return friendly
    return f"{friendly[:6]}...{friendly[-6:]}"

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

        if any(x in err_msg for x in [
            "document_invalid",
            "there is no text in the message to edit",
            "message can't be edited",
            "message to edit not found",
            "message is not modified"
        ]):
            try:
                await target.delete()
            except Exception:
                pass

            safe_kwargs = kwargs.copy()
            safe_kwargs.pop("parse_mode", None)

            msg = await target.answer(
                strip_custom_emojis(text),
                **safe_kwargs
            )

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

def get_message_link(chat, message_id: int) -> str:
    """Generates a link to a Telegram message."""
    if chat.username:
        return f"https://t.me/{chat.username}/{message_id}"
    
    # For private groups/channels, use the c/ID format
    # The ID must be without the -100 prefix
    chat_id = str(chat.id)
    if chat_id.startswith("-100"):
        chat_id = chat_id[4:]
    elif chat_id.startswith("-"):
        chat_id = chat_id[1:]
        
    return f"https://t.me/c/{chat_id}/{message_id}"
