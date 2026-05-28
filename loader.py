import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

ADMIN_IDS = [786080766, 734720997]

# Shared sets for background task tracking
bg_tasks = set()

# Bot will be initialized in bot.py main()
bot: Bot = None
dp = Dispatcher(storage=MemoryStorage())
