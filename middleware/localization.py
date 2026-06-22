from aiogram import BaseMiddleware
from typing import Callable, Dict, Any, Awaitable
from aiogram.types import TelegramObject

from database import db
from services.localization import get_locale_by_lang

class LocalizationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")

        if user:
            lang = await db.get_user_language(user.id)
            data["texts"] = get_locale_by_lang(lang)
            data["lang"] = lang
        else:
            # Fallback for events without a user (rare in message/callback)
            data["texts"] = get_locale_by_lang("en")
            data["lang"] = "en"

        return await handler(event, data)
