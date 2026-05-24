import os
import json
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram_tonconnect.storage.base import BaseStorage
from aiogram_tonconnect.tonconnect import TonConnectManager
from dotenv import load_dotenv
from database import db

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class SupabaseTonConnectStorage(BaseStorage):
    """Реализация персистентного моста хранения сессий TON Connect в Supabase."""
    def __init__(self, db_instance):
        self.db = db_instance

    def _get_user_id(self, key: str) -> int:
        try:
            # Вычленяем чистый ID пользователя из внутреннего ключа aiogram-tonconnect
            return int(key.split(":")[0]) if ":" in key else int(key)
        except ValueError:
            return 0

    async def get_storage_data(self, key: str) -> dict:
        user_id = self._get_user_id(key)
        if not user_id: return {}
        
        profile = await self.db.get_game_profile(user_id)
        if profile and profile.get("tonconnect_session"):
            try:
                return json.loads(profile["tonconnect_session"])
            except Exception:
                return {}
        return {}

    async def set_storage_data(self, key: str, value: dict) -> None:
        user_id = self._get_user_id(key)
        if not user_id or not self.db._check_client(): return
        
        await self.db.client.table("users_game_profile").update({
            "tonconnect_session": json.dumps(value)
        }).eq("id", user_id).execute()

    async def delete_storage_data(self, key: str) -> None:
        user_id = self._get_user_id(key)
        if not user_id or not self.db._check_client(): return
        
        await self.db.client.table("users_game_profile").update({
            "tonconnect_session": None
        }).eq("id", user_id).execute()

# Инициализация менеджера
MANIFEST_URL = os.environ.get("TONCONNECT_MANIFEST_URL", "").strip()

# Глобальный объект управления TON Connect ассетами
tonconnect_manager = TonConnectManager(
    manifest_url=MANIFEST_URL,
    storage=SupabaseTonConnectStorage(db)
)
