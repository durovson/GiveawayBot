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
            logger.info("✅ Connected to Supabase!")
        except Exception as e:
            logger.error(f"❌ Connection error: {e}")

    def _check_client(self) -> bool:
        if not self.client:
            logger.error("❌ Supabase client not initialized. Call connect() first.")
            return False
        return True

    async def track_chat(self, chat_id: int, title: str, chat_type: Optional[str] = None):
        if not self._check_client(): return
        try:
            await self.client.table("chats").upsert({
                "chat_id": int(chat_id),
                "title": str(title),
                "chat_type": str(chat_type) if chat_type else None
            }).execute()
        except Exception as e:
            logger.error(f"Error tracking chat {chat_id}: {e}")

    async def is_chat_tracked(self, chat_id: int) -> bool:
        if not self._check_client(): return False
        try:
            response = await self.client.table("chats").select("chat_id").eq("chat_id", int(chat_id)).execute()
            return len(response.data) > 0
        except Exception as e:
            logger.error(f"Error checking if chat {chat_id} is tracked: {e}")
            return False

    async def get_tracked_chats(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("chats").select("*").execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting tracked chats: {e}")
            return []

    async def get_tracked_groups(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("chats").select("*").in_("chat_type", ["group", "supergroup", "channel"]).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting tracked groups: {e}")
            return []

    async def create_giveaway(self, creator_id: int, chat_id: int, title: str, mode: str, value: Any, winners_count: int, prizes: List[str], end_at: Optional[datetime] = None, mandatory_channels: List[str] = [], allowed_users: Optional[List[str]] = None) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            data = {
                "creator_id": int(creator_id),
                "chat_id": int(chat_id),
                "title": str(title),
                "mode": str(mode),
                "value": str(value),
                "winners_count": int(winners_count),
                "prizes": prizes,
                "status": "pending",
                "end_at": end_at.isoformat() if end_at else None,
                "mandatory_channels": mandatory_channels,
                "allowed_users": allowed_users
            }
            response = await self.client.table("giveaways").insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating giveaway: {e}")
            return None

    async def add_giveaway_message(self, giveaway_id: int, chat_id: int, message_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("giveaway_messages").upsert({
                "giveaway_id": int(giveaway_id),
                "chat_id": int(chat_id),
                "message_id": int(message_id)
            }).execute()
        except Exception as e:
            logger.error(f"Error adding giveaway message: {e}")

    async def get_giveaway_messages(self, giveaway_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("giveaway_messages").select("*").eq("giveaway_id", int(giveaway_id)).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting giveaway messages for {giveaway_id}: {e}")
            return []

    async def finish_giveaway(self, giveaway_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("giveaways").update({"status": "finished"}).eq("id", int(giveaway_id)).execute()
        except Exception as e:
            logger.error(f"Error finishing giveaway {giveaway_id}: {e}")

    async def update_giveaway_status(self, giveaway_id: int, status: str) -> bool:
        if not self._check_client(): return False
        try:
            await self.client.table("giveaways").update({"status": str(status)}).eq("id", int(giveaway_id)).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating giveaway {giveaway_id} status to {status}: {e}")
            return False

    async def get_expired_giveaways(self, now: datetime) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await (self.client.table("giveaways")
                .select("*")
                .eq("status", "active")
                .eq("mode", "timed")
                .lte("end_at", now.isoformat())
                .execute())
            return response.data
        except Exception as e:
            logger.error(f"Error fetching expired giveaways: {e}")
            return []

    async def get_giveaway(self, giveaway_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("giveaways").select("*").eq("id", int(giveaway_id)).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting giveaway {giveaway_id}: {e}")
            return None

    async def add_participant(self, giveaway_id: int, user_id: int, username: Optional[str]) -> bool:
        if not self._check_client(): return False
        try:
            await self.client.table("participants").insert({
                "giveaway_id": int(giveaway_id),
                "user_id": int(user_id),
                "username": str(username) if username else None
            }).execute()
            return True
        except Exception as e:
            if "duplicate key value violates unique constraint" in str(e) or "409" in str(e):
                return False
            logger.error(f"Error adding participant {user_id} to {giveaway_id}: {e}")
            return False

    async def remove_participant(self, giveaway_id: int, user_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("participants").delete().eq("giveaway_id", int(giveaway_id)).eq("user_id", int(user_id)).execute()
        except Exception as e:
            logger.error(f"Error removing participant {user_id} from {giveaway_id}: {e}")

    async def get_participants(self, giveaway_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("participants").select("*").eq("giveaway_id", int(giveaway_id)).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting participants for {giveaway_id}: {e}")
            return []

    async def get_user_created_giveaways(self, user_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("giveaways").select("*, chats(title)").eq("creator_id", int(user_id)).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting user {user_id} created giveaways: {e}")
            return []

    async def save_winners(self, giveaway_id: int, winners: List[Dict]):
        if not self._check_client(): return
        try:
            data = []
            for w in winners:
                data.append({
                    "giveaway_id": int(giveaway_id),
                    "user_id": int(w['user_id']),
                    "username": str(w['username']) if w.get('username') else None,
                    "prize": str(w['prize'])
                })
            if data:
                await self.client.table("winners").insert(data).execute()
        except Exception as e:
            logger.error(f"Error saving winners for {giveaway_id}: {e}")

    async def get_giveaway_winners(self, giveaway_id: int) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("winners").select("*").eq("giveaway_id", int(giveaway_id)).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting winners for {giveaway_id}: {e}")
            return []

    async def get_setting(self, key: str) -> Optional[str]:
        if not self._check_client(): return None
        try:
            response = await self.client.table("settings").select("value").eq("key", str(key)).execute()
            return response.data[0]["value"] if response.data else None
        except Exception as e:
            logger.error(f"Error getting setting {key}: {e}")
            return None

    async def update_setting(self, key: str, value: str):
        if not self._check_client(): return
        try:
            await self.client.table("settings").upsert({"key": str(key), "value": str(value)}).execute()
        except Exception as e:
            logger.error(f"Error updating setting {key}: {e}")

    async def upsert_notification(self, data: dict) -> bool:
        if not self._check_client(): return False
        try:
            clean_data = {
                "title": str(data['title']),
                "text": str(data['text']),
                "custom_buttons": data.get('custom_buttons', []),
                "interval_hours": float(data['interval_hours']),
                "chat_id": int(data['chat_id']),
                "is_active": bool(data.get('is_active', True))
            }
            if data.get('id'):
                clean_data['id'] = int(data['id'])
            if data.get('button_url'):
                clean_data['button_url'] = str(data['button_url'])
            if data.get('button_text'):
                clean_data['button_text'] = str(data['button_text'])

            await self.client.table("notifications").upsert(clean_data).execute()
            return True
        except Exception as e:
            logger.error(f"Error upserting notification: {e}")
            return False

    async def get_notifications(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("notifications").select("*").execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting notifications: {e}")
            return []

    async def get_active_notifications(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            response = await self.client.table("notifications").select("*").eq("is_active", True).execute()
            return response.data
        except Exception as e:
            logger.error(f"Error getting active notifications: {e}")
            return []

    async def update_notification_last_msg(self, notification_id: int, last_message_id: Optional[int]):
        if not self._check_client(): return
        try:
            await self.client.table("notifications").update({
                "last_message_id": int(last_message_id) if last_message_id is not None else None
            }).eq("id", int(notification_id)).execute()
        except Exception as e:
            logger.error(f"Error updating notification {notification_id} last message id: {e}")

    async def update_notification_stats(self, notification_id: int, last_sent: datetime, last_message_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("notifications").update({
                "last_sent": last_sent.isoformat(),
                "last_message_id": int(last_message_id)
            }).eq("id", int(notification_id)).execute()
        except Exception as e:
            logger.error(f"Error updating notification {notification_id} stats: {e}")

    async def create_initial_profile(self, user_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("users_game_profile").upsert({
                "id": int(user_id), "points_balance": 0.0, "packs_count": 0
            }).execute()
        except Exception as e:
            logger.error(f"Error creating initial profile for {user_id}: {e}")

    async def get_game_profile(self, user_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            res = await self.client.table("users_game_profile").select("*").eq("id", int(user_id)).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Error getting game profile for {user_id}: {e}")
            return None

    async def get_shop_items(self) -> List[Dict]:
        if not self._check_client(): return []
        try:
            res = await self.client.table("shop_items").select("*").order("id").execute()
            return res.data
        except Exception as e:
            logger.error(f"Error getting shop items: {e}")
            return []

    async def get_shop_item_by_id(self, item_id: int) -> Optional[Dict]:
        if not self._check_client(): return None
        try:
            res = await self.client.table("shop_items").select("*").eq("id", int(item_id)).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Error getting shop item {item_id}: {e}")
            return None

    async def process_purchase(self, user_id: int, item_id: int, quantity: int, total_cost: float) -> Optional[int]:
        if not self._check_client(): return None
        try:
            params = {
                "p_user_id": int(user_id),
                "p_item_id": int(item_id),
                "p_quantity": int(quantity),
                "p_total_cost": float(total_cost)
            }
            res = await self.client.rpc("process_purchase_v2", params).execute()
            return int(res.data) if res.data else None
        except Exception as e:
            logger.error(f"Atomic transaction failure: {e}")
            return None

    async def link_wallet(self, user_id: int, wallet_address: str):
        if not self._check_client(): return
        try:
            await self.client.table("users_game_profile").update({
                "wallet_address": str(wallet_address)
            }).eq("id", int(user_id)).execute()
            logger.info(f"✅ Wallet {wallet_address} linked to user {user_id}")
        except Exception as e:
            logger.error(f"Error linking wallet for {user_id}: {e}")

    async def unlink_wallet(self, user_id: int):
        if not self._check_client(): return
        try:
            await self.client.table("users_game_profile").update({
                "wallet_address": None
            }).eq("id", int(user_id)).execute()
            logger.info(f"🔄 Wallet unlinked for user {user_id}")
        except Exception as e:
            logger.error(f"Error unlinking wallet for {user_id}: {e}")

db = Database()
