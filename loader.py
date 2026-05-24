import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
