import asyncio
import os
from database import db
from datetime import datetime

async def test():
    # This script assumes environment variables are set correctly for the DB to connect.
    # We will just test the method logic if we can mock the client or just check if it exists.
    print("Testing DB logic...")
    user_id = 553996797

    # 1. Check if we can call is_community_joined
    try:
        joined = await db.is_community_joined(user_id)
        print(f"is_community_joined result: {joined}")
    except Exception as e:
        print(f"Error calling is_community_joined: {e}")

    # 2. Check get_user_by_telegram_id
    try:
        user = await db.get_user_by_telegram_id(user_id)
        if user:
            print(f"User found. community_joined_at: {user.get('community_joined_at')}")
        else:
            print("User not found")
    except Exception as e:
        print(f"Error calling get_user_by_telegram_id: {e}")

if __name__ == "__main__":
    # We need a dummy env for the script to run without crashing if not connected
    os.environ.setdefault("SUPABASE_URL", "https://example.com")
    os.environ.setdefault("SUPABASE_KEY", "key")
    asyncio.run(test())
