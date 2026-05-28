import os
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

ADMIN_IDS = [786080766, 734720997]

# Shared sets for background task tracking
bg_tasks = set()
wallet_tasks = set()

# Shared http session (initialized in bot.py)
http_session = None

# aiogram bot & dispatcher
session = AiohttpSession()
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher(storage=MemoryStorage())
