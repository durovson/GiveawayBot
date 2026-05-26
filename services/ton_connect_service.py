import asyncio
import json
import os
import time
from datetime import datetime, timezone

from pytonconnect import TonConnect
from pytonconnect.storage import IStorage
from postgrest.exceptions import APIError

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

    async def ensure_user_exists(self, user_id: int):
        response = await (
            self.supabase
            .table("users")
            .select("telegram_id")
            .eq("telegram_id", int(user_id))
            .limit(1)
            .execute()
        )
        if response.data:
            return

        try:
            await self.supabase.table("users").insert({"telegram_id": int(user_id)}).execute()
        except APIError:
            pass

    async def set_item(self, key: str, value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value)

        await self.ensure_user_exists(self.user_id)

        try:
            await self.supabase.table("ton_connect_sessions").upsert({
                "user_id": self.user_id,
                "key": key,
                "value": value
            }, on_conflict="user_id,key").execute()
        except APIError as e:
            logger.warning("TON_CONNECT_STORAGE_WARNING user_id=%s key=%s error=%s", self.user_id, key, e)

    async def get_item(self, key: str, default_value: str = None):
        response = await self.supabase.table("ton_connect_sessions").select("value").eq(
            "user_id", self.user_id
        ).eq("key", key).execute()

        data = response.data
        if data and len(data) > 0:
            return data[0]["value"]
        return default_value

    async def remove_item(self, key: str):
        await self.supabase.table("ton_connect_sessions").delete().eq(
            "user_id", self.user_id
        ).eq("key", key).execute()


class TonConnectService:
    _instances = {}
    _last_access = {}
    _locks = {}
    TTL = 3600

    @classmethod
    async def connector(cls, user_id: int) -> TonConnect:
        user_id = int(user_id)
        lock = cls._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            now = time.time()
            if user_id in cls._last_access and now - cls._last_access[user_id] > cls.TTL:
                cls.drop_connector(user_id)

            if user_id in cls._instances:
                connector = cls._instances[user_id]
                try:
                    await connector.restore_connection()
                except Exception:
                    cls.drop_connector(user_id)
                    connector = None
                if connector is not None and user_id in cls._instances:
                    cls._last_access[user_id] = now
                    return connector

            storage = SupabaseStorage(db.client, user_id)
            connector = TonConnect(manifest_url=MANIFEST_URL, storage=storage)
            try:
                await connector.restore_connection()
            except Exception:
                cls.drop_connector(user_id)
                storage = SupabaseStorage(db.client, user_id)
                connector = TonConnect(manifest_url=MANIFEST_URL, storage=storage)

            cls._instances[user_id] = connector
            cls._last_access[user_id] = now
            return connector

    @classmethod
    def drop_connector(cls, user_id: int):
        user_id = int(user_id)
        cls._instances.pop(user_id, None)
        cls._last_access.pop(user_id, None)
        cls._locks.pop(user_id, None)
