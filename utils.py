import base64
import logging
import re
import pytz
from loader import bot, ADMIN_IDS
from aiogram.exceptions import TelegramBadRequest
from aiogram import types

logger = logging.getLogger(__name__)

def normalize_to_raw(address: str):
    """Приводит любой формат адреса TON (Raw, Bounceable, Non-bounceable) к единому Raw-виду (0:hex)"""
    if not isinstance(address, str):
        return None

    if len(address) < 20:
        return None

    address = address.strip()
    if not address:
        return None

    if ":" in address:
        parts = address.split(":")
        return f"{parts[0]}:{parts[1].lower()}"

    try:
        # Корректируем Base64 строку для URL-safe и обычного вариантов
        b64_str = address.replace("-", "+").replace("_", "/")
        b64_str += "=" * ((4 - len(b64_str) % 4) % 4)
        data = base64.b64decode(b64_str)
        if len(data) >= 34:
            workchain = data[1]
            if workchain == 255:
                workchain = -1
            account_id = data[2:34].hex().lower()
            return f"{workchain}:{account_id}"
    except Exception:
        return None
    return None

def raw_to_user_friendly(raw_address: str, bounceable: bool = False) -> str:
    """Конвертирует сырой адрес (0:hex) в стандартный User-Friendly формат (начинается с UQ для non-bounceable)"""
    if not raw_address:
        return ""
    raw_address = raw_address.strip()
    if ":" not in raw_address:
        return raw_address
    try:
        parts = raw_address.split(":")
        workchain = int(parts[0])
        hex_id = parts[1].strip()
        account_bytes = bytes.fromhex(hex_id)

        # 0x51 означает Mainnet Non-bounceable (формат UQ...)
        # 0x11 означает Mainnet Bounceable (формат EQ...)
        tag = 0x11 if bounceable else 0x51
        workchain_byte = workchain & 0xFF

        buffer = bytes([tag, workchain_byte]) + account_bytes

        # Расчет контрольной суммы CRC16-CCITT (без рефлексии)
        crc = 0
        for byte in buffer:
            crc ^= (byte << 8)
            for _ in range(8):
                if crc & 0x8000:
                    crc = (crc << 1) ^ 0x1021
                else:
                    crc <<= 1
                crc &= 0xFFFF

        buffer += crc.to_bytes(2, byteorder='big')
        return base64.urlsafe_b64encode(buffer).decode('utf-8').rstrip('=')
    except Exception as e:
        logger.error(f"Error converting raw to user friendly: {e}")
        return raw_address

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
    # Hardcoded admin check as a fallback or primary
    if user_id in ADMIN_IDS:
        return True

    chats = await db.get_tracked_chats()
    for chat in chats:
        if await is_admin(chat['chat_id'], user_id):
            return True
    return False

async def is_holder(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=-1001944951957, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

async def safe_answer(message, text, **kwargs):
    state = kwargs.pop('state', None)
    # message can be Message or CallbackQuery
    actual_message = message.message if hasattr(message, 'message') and not isinstance(message, types.Message) else message

    async def _do_answer(content):
        return await actual_message.answer(content, **kwargs)

    msg = None
    try:
        msg = await _do_answer(text)
    except TelegramBadRequest as e:
        err_str = str(e)
        logger.warning(f"TelegramBadRequest in safe_answer: {err_str}. Retrying with sanitization...")
        try:
            msg = await _do_answer(strip_custom_emojis(text))
        except TelegramBadRequest:
            try:
                msg = await _do_answer(strip_all_tags(text))
            except Exception as e2:
                logger.error(f"Ultimate failure in safe_answer: {e2}")
                return None
    except Exception as e:
        logger.error(f"Unexpected error in safe_answer: {e}")
        return None

    if msg and state:
        await state.update_data(last_msg_id=msg.message_id)
    return msg

async def safe_edit_text(message, text, **kwargs):
    state = kwargs.pop('state', None)
    # message can be Message or CallbackQuery
    target = message.message if hasattr(message, 'message') and not isinstance(message, types.Message) else message

    try:
        return await target.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        err_str = str(e)
        if "message is not modified" in err_str:
            return target

        # Fallback to answer for recoverable errors
        logger.info(f"Fallback to safe_answer in safe_edit_text due to: {err_str}")
        return await safe_answer(message, text, state=state, **kwargs)
    except Exception as e:
        logger.error(f"Unexpected error in safe_edit_text: {e}")
        return await safe_answer(message, text, state=state, **kwargs)

async def safe_bot_edit_text(bot, chat_id, message_id, text, **kwargs):
    state = kwargs.pop('state', None)

    try:
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)
    except TelegramBadRequest as e:
        err_str = str(e)
        if "message is not modified" in err_str:
            return None # Still None if not modified, but that's usually fine

        # Fallback to send_message for recoverable errors
        logger.info(f"Fallback to safe_bot_send_message in safe_bot_edit_text due to: {err_str}")
        return await safe_bot_send_message(bot, chat_id, text, state=state, **kwargs)
    except Exception as e:
        logger.error(f"Unexpected error in safe_bot_edit_text: {e}")
        return await safe_bot_send_message(bot, chat_id, text, state=state, **kwargs)

async def safe_bot_send_message(bot, chat_id, text, **kwargs):
    state = kwargs.pop('state', None)

    async def _do_send(content):
        return await bot.send_message(chat_id=chat_id, text=content, **kwargs)

    msg = None
    try:
        msg = await _do_send(text)
    except TelegramBadRequest as e:
        err_str = str(e)
        logger.warning(f"TelegramBadRequest in safe_bot_send_message: {err_str}. Retrying with sanitization...")
        try:
            msg = await _do_send(strip_custom_emojis(text))
        except TelegramBadRequest:
            try:
                msg = await _do_send(strip_all_tags(text))
            except Exception as e2:
                logger.error(f"Ultimate failure in safe_bot_send_message: {e2}")
                return None
    except Exception as e:
        logger.error(f"Unexpected error in safe_bot_send_message: {e}")
        return None

    if msg and state:
        await state.update_data(last_msg_id=msg.message_id)
    return msg
