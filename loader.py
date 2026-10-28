import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from services.telegram_chat_ref import normalize_telegram_chat_ref

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

bg_tasks = set()
wallet_tasks = set()
http_session = None


class TelegramLinkAwareBot(Bot):
    """Accept public Telegram links without changing Bot API membership results."""

    async def get_chat(self, chat_id, request_timeout=None):
        return await super().get_chat(
            normalize_telegram_chat_ref(chat_id), request_timeout=request_timeout
        )

    async def get_chat_member(self, chat_id, user_id, request_timeout=None):
        return await super().get_chat_member(
            normalize_telegram_chat_ref(chat_id),
            user_id,
            request_timeout=request_timeout,
        )


session = AiohttpSession()
bot = TelegramLinkAwareBot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())
