import json
import os
from pytonconnect import TonConnect
from pytonconnect.storage import IStorage
from database import db
import logging

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("CUSTOM_URL", "https://giveaway-bot-hiap.onrender.com")
if not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL
MANIFEST_URL = f"{BASE_URL.rstrip('/')}/tonconnect-manifest.json"

class SupabaseStorage(IStorage):
    def __init__(self, supabase_client, user_id: int):
        self.supabase = supabase_client
        self.user_id = int(user_id)

    async def set_item(self, key: str, value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        try:
            await self.supabase.table("ton_connect_sessions").upsert({
                "user_id": self.user_id,
                "key": key,
                "value": value
            }, on_conflict="user_id,key").execute()
        except Exception:
            logger.exception("TON_CONNECT_STORAGE_SET_FAILED user_id=%s key=%s", self.user_id, key)

    async def get_item(self, key: str, default_value: str = None):
        try:
            response = await self.supabase.table("ton_connect_sessions").select("value").eq(
                "user_id", self.user_id
            ).eq("key", key).execute()

            data = response.data
            if data and len(data) > 0:
                return data[0]["value"]
        except Exception:
            logger.exception("TON_CONNECT_STORAGE_GET_FAILED user_id=%s key=%s", self.user_id, key)
        return default_value

    async def remove_item(self, key: str):
        try:
            await self.supabase.table("ton_connect_sessions").delete().eq(
                "user_id", self.user_id
            ).eq("key", key).execute()
        except Exception:
            logger.exception("TON_CONNECT_STORAGE_REMOVE_FAILED user_id=%s key=%s", self.user_id, key)

class TonConnectService:
    @classmethod
    async def connector(cls, user_id: int) -> TonConnect:
        user_id = int(user_id)
        await db.ensure_user_exists(user_id)
        storage = SupabaseStorage(db.client, user_id)
        connector = TonConnect(manifest_url=MANIFEST_URL, storage=storage)
        try:
            await connector.restore_connection()
        except Exception:
            pass
        return connector
