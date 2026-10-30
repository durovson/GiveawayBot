"""Durable destination per bot, with the deployment setting as initial default."""
import os
from database import db


def setting_key(bot_id):
    return f"arena_chat_id:{bot_id}"


async def target_chat(bot):
    if db.client is None:
        raise RuntimeError('Database unavailable')
    result = await db.client.table('settings').select('value').eq('key', setting_key(bot.id)).execute()
    value = str(result.data[0]['value'] if result.data else os.getenv('ARENA_CHAT_ID', '')).strip()
    return int(value) if value.lstrip('-').isdigit() else 0


async def save_target_chat(bot, chat_id):
    if db.client is None:
        raise RuntimeError('Database unavailable')
    await db.client.table('settings').upsert({'key': setting_key(bot.id), 'value': str(chat_id)}).execute()
