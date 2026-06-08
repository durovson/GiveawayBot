import asyncio
import os
import sys
import logging
from datetime import datetime

# Add the root directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def update_username_manual(user_id: int, username: str, first_name: str):
    """Updates username and display_name in users and points tables manually."""
    if username:
        display = f"@{username}"
    elif first_name:
        display = first_name
    else:
        display = f"User {user_id}"

    # Update users table
    try:
        await db.client.table("users").update({
            "username": username,
            "first_name": first_name
        }).eq("telegram_id", user_id).execute()
    except Exception as e:
        logger.error(f"Error updating users table for {user_id}: {e}")

    # Update points table
    try:
        await db.client.table("points").upsert({
            "user_id": user_id,
            "username": username,
            "display_name": display,
            "updated_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"Error updating points table for {user_id}: {e}")

async def migrate_names():
    logger.info("Starting name migration...")

    # 1. Get all points records
    try:
        response = await db.client.table("points").select("user_id, username, display_name").execute()
        points_records = response.data
    except Exception as e:
        logger.error(f"Error fetching points: {e}")
        return

    count = 0
    for record in points_records:
        user_id = record.get("user_id")
        username = record.get("username")
        display_name = record.get("display_name")

        # Check if we need to update
        if not display_name or display_name == str(user_id) or display_name.isdigit() or display_name == f"User {user_id}":
            # Try to get from users table first
            user_data = await db.get_user_by_telegram_id(user_id)

            user_username = user_data.get("username") if user_data else None
            user_first_name = user_data.get("first_name") if user_data else None

            if user_username or user_first_name:
                logger.info(f"Updating user {user_id} from users table: @{user_username} / {user_first_name}")
                await update_username_manual(user_id, user_username, user_first_name)
                count += 1
            else:
                # Still no name in users table
                logger.info(f"Ensuring default name for user {user_id}")
                await update_username_manual(user_id, None, None)
                count += 1

    logger.info(f"Migration finished. Updated {count} records.")

if __name__ == "__main__":
    asyncio.run(migrate_names())
