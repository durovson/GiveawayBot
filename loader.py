import os
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    # A dummy but valid-format token for import validation if not set in env
    BOT_TOKEN = "12345678:ABCDEF1234567890abcdef1234567890abc"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

ADMIN_IDS = [734720997, 786080766]
