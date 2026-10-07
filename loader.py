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

    Telegram may reject member-list methods for a numeric channel id while the
    public @username reference still works. Remember public aliases resolved by
    getChat and retry membership/admin lookups through that alias. Bot API 10.0
    also added ``return_bots`` to getChatAdministrators; explicitly request bots
    when checking our own administrator entry.
    """

    def _remember_public_alias(self, requested_chat_id, chat) -> None:
        if not isinstance(requested_chat_id, str):
            return
        normalized = normalize_telegram_chat_ref(requested_chat_id)
        if not isinstance(normalized, str) or not normalized.startswith("@"):
            return
        aliases = getattr(self, "_public_chat_aliases", None)
        if aliases is None:
            aliases = {}
            self._public_chat_aliases = aliases
        aliases[chat.id] = normalized

    def _chat_ref_candidates(self, chat_id):
        normalized = normalize_telegram_chat_ref(chat_id)
        candidates = [normalized]
        if isinstance(normalized, int) or (
            isinstance(normalized, str) and normalized.startswith("-")
        ):
            try:
                numeric_id = int(normalized)
            except (TypeError, ValueError):
                numeric_id = None
            if numeric_id is not None:
                alias = getattr(self, "_public_chat_aliases", {}).get(numeric_id)
                if alias and alias not in candidates:
                    candidates.append(alias)
        return candidates

    async def get_chat(self, chat_id, request_timeout=None):
        normalized_chat_id = normalize_telegram_chat_ref(chat_id)
        chat = await super().get_chat(
            normalized_chat_id,
            request_timeout=request_timeout,
        )
        self._remember_public_alias(normalized_chat_id, chat)
        return chat

    async def get_chat_administrators(
        self,
        chat_id,
        return_bots=None,
        request_timeout=None,
    ):
        last_exc = None
        for candidate in self._chat_ref_candidates(chat_id):
            try:
                return await super().get_chat_administrators(
                    candidate,
                    return_bots=return_bots,
                    request_timeout=request_timeout,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "getChatAdministrators failed chat=%r candidate=%r: %s",
                    chat_id,
                    candidate,
                    exc,
                )
        if last_exc is not None:
            raise last_exc
        return []

    async def _get_self_admin_via_list(self, chat_id, request_timeout=None):
        admins = await self.get_chat_administrators(
            chat_id,
            return_bots=True,
            request_timeout=request_timeout,
        )
        for admin in admins:
            if admin.user.id == self.id:
                return admin
        return None

    async def _get_chat_member_with_alias_retry(
        self,
        chat_id,
        user_id,
        request_timeout=None,
    ):
        last_exc = None
        for candidate in self._chat_ref_candidates(chat_id):
            try:
                return await super().get_chat_member(
                    candidate,
                    user_id,
                    request_timeout=request_timeout,
                )
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "getChatMember failed chat=%r candidate=%r user_id=%s: %s",
                    chat_id,
                    candidate,
                    user_id,
                    exc,
                )
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No Telegram chat reference candidates available")

    async def get_chat_member(self, chat_id, user_id, request_timeout=None):
        try:
            member = await self._get_chat_member_with_alias_retry(
                chat_id,
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
                "trying getChatAdministrators(return_bots=True)",
                chat_id,
                self.id,
                exc,
            )
            try:
                admin = await self._get_self_admin_via_list(
                    chat_id,
                    request_timeout=request_timeout,
                )
            except Exception as fallback_exc:
                logger.warning(
                    "getChatAdministrators fallback failed chat=%r bot_id=%s: %s",
                    chat_id,
                    self.id,
                    fallback_exc,
                )
                raise exc

            if admin is not None:
                logger.info(
                    "Confirmed bot administrator via getChatAdministrators "
                    "chat=%r bot_id=%s",
                    chat_id,
                    self.id,
                )
                return admin

            logger.warning(
                "Bot id=%s not present in administrator list for chat=%r",
                self.id,
                chat_id,
            )
            raise exc

        # If getChatMember gives a non-admin status for the bot itself, cross-check
        # the authoritative administrators list before accepting the negative.
        if user_id == self.id and _chat_member_status(member) not in _ADMIN_STATUSES:
            try:
                admin = await self._get_self_admin_via_list(
                    chat_id,
                    request_timeout=request_timeout,
                )
            except Exception as exc:
                logger.warning(
                    "Could not cross-check bot admin list chat=%r bot_id=%s: %s",
                    chat_id,
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
                        chat_id,
                    )
                    return admin

                logger.warning(
                    "Bot admin check negative chat=%r bot_id=%s status=%r",
                    chat_id,
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
