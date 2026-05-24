from pytonconnect.storage import IStorage
from datetime import datetime

class SupabaseStorage(IStorage):
    def __init__(self, supabase_client, user_id: int):
        self.supabase = supabase_client
        self.user_id = user_id

    async def set_item(self, key: str, value: str) -> None:
        await self.supabase.table("ton_connect_sessions").upsert({
            "user_id": int(self.user_id),
            "key": str(key),
            "value": str(value),
            "updated_at": datetime.now().isoformat()
        }).execute()

    async def get_item(self, key: str, default_value: str = None) -> str:
        response = await self.supabase.table("ton_connect_sessions") \
            .select("value") \
            .eq("user_id", int(self.user_id)) \
            .eq("key", str(key)) \
            .execute()

        data = response.data
        if data and len(data) > 0:
            return data[0]["value"]
        return default_value

    async def remove_item(self, key: str) -> None:
        await self.supabase.table("ton_connect_sessions") \
            .delete() \
            .eq("user_id", int(self.user_id)) \
            .eq("key", str(key)) \
            .execute()
