import os
import logging
from typing import List, Optional, Dict, Any
from supabase import create_async_client, AsyncClient
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.url = os.environ.get("SUPABASE_URL", "").strip()
        self.key = os.environ.get("SUPABASE_KEY", "").strip()
        self.client: Optional[AsyncClient] = None

    async def connect(self):
        if not self.url or not self.key:
            logger.error("❌ SUPABASE_URL or SUPABASE_KEY is missing!")
            return
        try:
            self.client = await create_async_client(self.url, self.key)
            logger.info("✅ Supabase client initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Supabase client: {e}")

    def _check_client(self) -> bool:
        return self.client is not None

    async def track_chat(self, chat_id: int, title: str):
        if not self._check_client(): return
        try:
            await self.client.table("chats").upsert({
                "chat_id": chat_id,
                "title": title
            }).execute()
        except Exception as e:
            logger.error(f"Error tracking chat: {e}")

    async def is_chat_tracked(self, chat_id: int) -> bool:
        if not self._check_client(): return False
        try:
            response = await self.client.table("chats").select("chat_id").eq("chat_id", chat_id).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking if chat is tracked: {e}")
            return False

    async def get_tracked_chats(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("chats").select("*").execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting tracked chats: {e}")
            return []

    async def create_giveaway(self, creator_id: int, chat_id: int, title: str, mode: str, value: Any, winners_count: int, prizes: List[str], end_at: Optional[datetime] = None) -> Dict:
        if not self._check_client(): return {}
        try:
            data = {
                "creator_id": creator_id,
                "chat_id": chat_id,
                "title": title,
                "mode": mode,
                "value": str(value),
                "winners_count": winners_count,
                "prizes": prizes,
                "status": "active",
                "end_at": end_at.isoformat() if end_at else None
            }
            response = await self.client.table("giveaways").insert(data).execute()
            return response.data[0]
        except Exception as e:
            logger.error(f"Error creating giveaway: {e}")
            return {}

    async def add_giveaway_message(self, giveaway_id: int, chat_id: int, message_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("giveaway_messages").upsert({
                "giveaway_id": giveaway_id,
                "chat_id": chat_id,
                "message_id": message_id
            }).execute()
        except Exception as e:
            logger.error(f"Error adding giveaway message: {e}")

    async def get_giveaway_messages(self, giveaway_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("giveaway_messages").select("*").eq("giveaway_id", giveaway_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting giveaway messages: {e}")
            return []

    async def finish_giveaway(self, giveaway_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("giveaways").update({"status": "finished"}).eq("id", giveaway_id).execute()
        except Exception as e:
            logger.error(f"Error finishing giveaway: {e}")

    async def get_expired_giveaways(self, now: datetime) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("giveaways") \
                .select("*") \
                .eq("status", "active") \
                .eq("mode", "timed") \
                .lte("end_at", now.isoformat()) \
                .execute()
            return response.data
        except Exception as e:
            logger.error(f"Error fetching expired giveaways: {e}")
            return []

    async def get_giveaway(self, giveaway_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("giveaways").select("*").eq("id", giveaway_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting giveaway: {e}")
            return None

    async def add_participant(self, giveaway_id: int, user_id: int, username: Optional[str]) -> bool:
        if not self._check_client(): return False
        try:
            existing = await self.client.table("participants").select("*").eq("giveaway_id", giveaway_id).eq("user_id", user_id).execute()
            if existing.data:
                return False
            await self.client.table("participants").insert({
                "giveaway_id": giveaway_id,
                "user_id": user_id,
                "username": username
            }).execute()
            return True
        except Exception as e:
            logger.error(f"Error adding participant: {e}")
            return False

    async def get_participants(self, giveaway_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("participants").select("*").eq("giveaway_id", giveaway_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting participants: {e}")
            return []

    async def get_user_created_giveaways(self, user_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("giveaways").select("*, chats(title)").eq("creator_id", user_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting user created giveaways: {e}")
            return []

    async def save_winners(self, giveaway_id: int, winners: List[Dict]):
        if not self._check_client(): return
        try:
            data = []
            for w in winners:
                data.append({
                    "giveaway_id": giveaway_id,
                    "user_id": w['user_id'],
                    "username": w['username'],
                    "prize": w['prize']
                })
            if data:
                await self.client.table("winners").insert(data).execute()
        except Exception as e:
            logger.error(f"Error saving winners: {e}")

    async def get_giveaway_winners(self, giveaway_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("winners").select("*").eq("giveaway_id", giveaway_id).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting giveaway winners: {e}")
            return []

    async def get_setting(self, key: str) -> Optional[str]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("settings").select("value").eq("key", key).execute()
            return response.data[0]["value"] if response.data else None
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return None

    async def update_setting(self, key: str, value: str):
        if not self._check_client(): return
        try:
            await self.client.table("settings").upsert({"key": key, "value": value}).execute()
        except Exception as e:
            logger.error(f"Error updating setting {key}: {e}")

db = Database()
