import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
from database import db

# Загрузка переменных окружения
load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

# Чистая инициализация бота и диспетчера aiogram
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
