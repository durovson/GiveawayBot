import os
import aiohttp
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from dotenv import load_dotenv

from services.telegram_chat_ref import normalize_telegram_chat_ref

load_dotenv()

from config import ADMIN_IDS

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in environment variables")

# Shared sets for background task tracking
bg_tasks = set()
wallet_tasks = set()

# Shared http session (initialized in bot.py)
http_session = None


_ADMIN_STATUSES = {"administrator", "creator"}


def _chat_member_status(member):
    """Return a plain Bot API status string for aiogram chat-member objects."""
    status = getattr(member, "status", None)
    return getattr(status, "value", status)


class TelegramLinkAwareBot(Bot):
    """Bot API wrapper that accepts public t.me links as chat references.

    Telegram occasionally returns a stale/non-admin result from getChatMember during
    channel permission changes. For checks of the bot itself, fall back to the
    channel's administrator list so giveaway creation does not get stuck on a false
    "bot is not an administrator" screen.
    """

    async def get_chat(self, chat_id, request_timeout=None):
        return await super().get_chat(
            normalize_telegram_chat_ref(chat_id),
            request_timeout=request_timeout,
        )

    async def get_chat_administrators(self, chat_id, request_timeout=None):
        return await super().get_chat_administrators(
            normalize_telegram_chat_ref(chat_id),
            request_timeout=request_timeout,
        )

    async def _get_self_admin_via_list(self, chat_id, request_timeout=None):
        admins = await super().get_chat_administrators(
            normalize_telegram_chat_ref(chat_id),
            request_timeout=request_timeout,
        )
        for admin in admins:
            if admin.user.id == self.id:
                return admin
        return None

    async def get_chat_member(self, chat_id, user_id, request_timeout=None):
        normalized_chat_id = normalize_telegram_chat_ref(chat_id)

        try:
            member = await super().get_chat_member(
                normalized_chat_id,
                user_id,
                request_timeout=request_timeout,
            )
        except Exception as exc:
            # Giveaway admin checks ask for the bot's own membership. If that
            # lookup fails, verify against getChatAdministrators before reporting
            # a false negative to the user.
            if user_id != self.id:
                raise

            logger.warning(
                "getChatMember failed for bot admin check chat=%r bot_id=%s: %s; "
                "trying getChatAdministrators",
                normalized_chat_id,
                self.id,
                exc,
            )
            try:
                admin = await self._get_self_admin_via_list(
                    normalized_chat_id,
                    request_timeout=request_timeout,
                )
            except Exception as fallback_exc:
                logger.warning(
                    "getChatAdministrators fallback failed chat=%r bot_id=%s: %s",
                    normalized_chat_id,
                    self.id,
                    fallback_exc,
                )
                raise exc

            if admin is not None:
                logger.info(
                    "Confirmed bot administrator via getChatAdministrators "
                    "chat=%r bot_id=%s",
                    normalized_chat_id,
                    self.id,
                )
                return admin

            logger.warning(
                "Bot id=%s not present in administrator list for chat=%r",
                self.id,
                normalized_chat_id,
            )
            raise exc

        # If getChatMember gives a non-admin status for the bot itself, cross-check
        # the authoritative administrators list before accepting the negative.
        if user_id == self.id and _chat_member_status(member) not in _ADMIN_STATUSES:
            try:
                admin = await self._get_self_admin_via_list(
                    normalized_chat_id,
                    request_timeout=request_timeout,
                )
            except Exception as exc:
                logger.warning(
                    "Could not cross-check bot admin list chat=%r bot_id=%s: %s",
                    normalized_chat_id,
                    self.id,
                    exc,
                )
            else:
                if admin is not None:
                    logger.info(
                        "getChatMember status=%r but administrator list confirms "
                        "bot_id=%s in chat=%r",
                        _chat_member_status(member),
                        self.id,
                        normalized_chat_id,
                    )
                    return admin

                logger.warning(
                    "Bot admin check negative chat=%r bot_id=%s status=%r",
                    normalized_chat_id,
                    self.id,
                    _chat_member_status(member),
                )

        return member


# aiogram bot & dispatcher
session = AiohttpSession()
from aiogram.client.default import DefaultBotProperties
bot = TelegramLinkAwareBot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())
