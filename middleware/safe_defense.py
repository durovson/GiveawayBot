import logging

from aiogram import BaseMiddleware

from database import db
from services.chat_games import ChatGameService

logger = logging.getLogger(__name__)


class SafeDefenseMiddleware(BaseMiddleware):
    """Observe messages before command/FSM filters. No reply for bystanders."""

    async def __call__(self, handler, event, data):
        user = event.from_user
        if event.chat.type in {'group', 'supergroup'}:
            bot = data.get('bot') or event.bot
            if user and not user.is_bot and not event.sender_chat and not getattr(event, 'left_chat_member', None):
                ChatGameService.observe_member(bot, event.chat.id, user, event.date)
            for member in getattr(event, 'new_chat_members', None) or []:
                ChatGameService.observe_member(bot, event.chat.id, member, event.date)
            departed = getattr(event, 'left_chat_member', None)
            if departed:
                ChatGameService.observe_member(bot, event.chat.id, departed, event.date, active=False)
        if (event.chat.type in {"group", "supergroup"} and user and not user.is_bot
                and not event.sender_chat and event.content_type not in {
                    "new_chat_members", "left_chat_member", "pinned_message", "new_chat_title",
                    "new_chat_photo", "delete_chat_photo", "group_chat_created", "supergroup_chat_created",
                    "channel_chat_created", "migrate_to_chat_id", "migrate_from_chat_id",
                }):
            try:
                await db._retry_read(lambda: ChatGameService.rpc("react_to_safe_attacks", {
                    "p_chat_id": event.chat.id, "p_user_id": user.id,
                    "p_message_id": event.message_id, "p_message_at": event.date.isoformat(),
                }), "safe defense")
            except Exception:
                logger.exception("SAFE_DEFENSE_FAILED chat=%s user=%s", event.chat.id, user.id)
        return await handler(event, data)
