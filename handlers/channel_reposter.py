import os
import logging

from aiogram import Router
from aiogram.types import Message

from loader import bot

router = Router()

logger = logging.getLogger(__name__)

NEWS_CHANNEL_ID = int(
    os.getenv("NEWS_CHANNEL_ID", "0")
)

NEWS_CHAT_ID = int(
    os.getenv("NEWS_CHAT_ID", "0")
)

NEWS_TOPIC_ID = int(
    os.getenv("NEWS_TOPIC_ID", "0")
)

logger.info(
    f"NEWS reposter initialized: source={NEWS_CHANNEL_ID} target={NEWS_CHAT_ID} topic={NEWS_TOPIC_ID}"
)

def is_configured() -> bool:
    return all([
        NEWS_CHANNEL_ID,
        NEWS_CHAT_ID,
        NEWS_TOPIC_ID
    ])


@router.channel_post()
async def repost_news_post(message: Message):

    if not is_configured():
        logger.error(
            "NEWS repost config is not set"
        )
        return

    if message.chat.id != NEWS_CHANNEL_ID:
        return

    if message.chat.id == NEWS_CHAT_ID:
        return

    try:

        await bot.copy_message(
            chat_id=NEWS_CHAT_ID,
            from_chat_id=NEWS_CHANNEL_ID,
            message_id=message.message_id,
            message_thread_id=NEWS_TOPIC_ID
        )

        logger.info(
            f"News post reposted: {message.message_id}"
        )

    except Exception as e:
        logger.exception(
            f"Failed to repost news post: {e}"
        )
