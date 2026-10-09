import asyncio
import json
import os
import time
from pytonconnect import TonConnect
from pytonconnect.storage import IStorage
from database import db
import logging

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("CUSTOM_URL", "https://giveaway-bot-hiap.onrender.com")
if not BASE_URL.startswith("http"):
    BASE_URL = "https://" + BASE_URL
MANIFEST_URL = f"{BASE_URL.rstrip('/')}/tonconnect-manifest.json"


class SafeTonConnect(TonConnect):
    """pytonconnect 0.4.0 disconnect without its racing cleanup Future.

    The provider and status hook are SDK internals, hence the pinned version.
    Wallet notification is best effort; local/session cleanup must still finish.
    """
    DISCONNECT_TIMEOUT = 10

    async def disconnect(self):
        provider = self._provider

        def request_sent(future):
            if not future.done():
                future.set_result(None)

        try:
            session = getattr(provider, "_session", None)
            if self.connected and getattr(session, "wallet_public_key", None):
                try:
                    await asyncio.wait_for(
                        provider.send_request(
                            {"method": "disconnect", "params": []},
                            on_request_sent=request_sent,
                        ),
                        timeout=self.DISCONNECT_TIMEOUT,
                    )
                except Exception as exc:
                    logger.warning("TON_CONNECT_DISCONNECT_NOTIFY_FAILED type=%s", type(exc).__name__)
        finally:
            try:
                if provider is not None:
                    provider.close_connection()
            finally:
                try:
                    self._on_wallet_disconnected()
                finally:
                    await self._storage.remove_item(IStorage.KEY_CONNECTION)


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
    _instances = {}
    _last_access = {}
    _locks = {}
    TTL = 3600

    @classmethod
    def user_lock(cls, user_id: int):
        return cls._locks.setdefault(int(user_id), asyncio.Lock())

    @classmethod
    def is_current(cls, user_id: int, connector) -> bool:
        return cls._instances.get(int(user_id)) is connector

    @classmethod
    async def disconnect(cls, user_id: int):
        user_id = int(user_id)
        async with cls.user_lock(user_id):
            connector = cls._instances.get(user_id)
            try:
                if connector is None:
                    connector = SafeTonConnect(
                        manifest_url=MANIFEST_URL, storage=SupabaseStorage(db.client, user_id),
                    )
                    try:
                        await asyncio.wait_for(connector.restore_connection(auto_listen=False), timeout=10)
                    except Exception as exc:
                        logger.warning("TON_CONNECT_DISCONNECT_RESTORE_FAILED user_id=%s type=%s", user_id, type(exc).__name__)
                await connector.disconnect()
            finally:
                cls.drop_connector(user_id)
                # Remove connection + bridge cursor keys, even if SDK cleanup failed.
                if not db.client:
                    raise RuntimeError("Database unavailable during wallet disconnect")
                await db.client.table("ton_connect_sessions").delete().eq("user_id", user_id).execute()
            if not await db.update_user_wallet(user_id, None):
                raise RuntimeError("Wallet disconnect was not persisted")

    @classmethod
    async def close_all(cls):
        """Clean up all TonConnect instances."""
        user_ids = list(cls._instances.keys())
        for user_id in user_ids:
            connector = cls._instances.get(user_id)
            if connector:
                try:
                    if connector.connected:
                        await connector.disconnect()
                except Exception:
                    pass
            cls.drop_connector(user_id)
        if user_ids:
            logger.info(f"Cleaned up {len(user_ids)} TonConnect instances")

    @classmethod
    async def connector(cls, user_id: int) -> TonConnect:
        user_id = int(user_id)
        lock = cls.user_lock(user_id)
        async with lock:
            now = time.time()
            if user_id in cls._last_access and now - cls._last_access[user_id] > cls.TTL:
                cls.drop_connector(user_id)

            if user_id in cls._instances:
                connector = cls._instances[user_id]
                # Restoring here replaces the provider on every menu action,
                # including while a connection/disconnect is already in flight.
                cls._last_access[user_id] = now
                return connector

            await db.ensure_user_exists(user_id)
            storage = SupabaseStorage(db.client, user_id)
            connector = SafeTonConnect(manifest_url=MANIFEST_URL, storage=storage)
            try:
                await connector.restore_connection()
            except Exception:
                logger.exception("TON_CONNECT_RESTORE_FAILED_NEW user_id=%s", user_id)

            cls._instances[user_id] = connector
            cls._last_access[user_id] = now
            return connector

    @classmethod
    def drop_connector(cls, user_id: int):
        user_id = int(user_id)
        connector = cls._instances.pop(user_id, None)
        if connector is not None:
            try:
                provider = connector._provider
                if provider is not None:
                    provider.close_connection()
            except Exception as exc:
                logger.warning("TON_CONNECT_CLOSE_FAILED user_id=%s type=%s", user_id, type(exc).__name__)
        cls._last_access.pop(user_id, None)
