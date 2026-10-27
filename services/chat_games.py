"""Persistent chat games and HTML presentation. No in-memory balance or timers."""
import asyncio
import html
import logging
from datetime import datetime, timedelta, timezone

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import LinkPreviewOptions
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats

from database import db
from locales.en.chat_games import TEXTS as EN
from locales.ru.chat_games import TEXTS as RU
from services.chat_game_theme import currency, emoji
from utils import safe_bot_send_message

logger = logging.getLogger(__name__)
PREFIX = "┏┅⋐[ ◍ _◍ ]っ┅"


def locale(language):
    return RU if language == "ru" else EN


def player_name(user, *, ping=True):
    name = user.get("username")
    if name:
        name = ("@" if ping else "") + name.lstrip("@")
    else:
        name = user.get("first_name") or str(user.get("telegram_id") or user.get("user_id"))
    if not ping:
        name = name.replace("@", "＠")
    return html.escape(name)


def balance_text(balance, language):
    t = locale(language)
    return (f"{PREFIX}{emoji('game')}┅/ <b>{t['balance_title']}</b> /\n┋\n"
            f"┣ <b>{t['points']}:</b> {balance} {currency()}\n┋\n"
            f"┗┅┅┅/ <b>{t['ready']}</b> /")


def top_text(rows, burned, language):
    t = locale(language)
    lines = [f"┋ {i}. {player_name(row.get('users') or {'user_id': row['user_id']}, ping=False)}"
             f" — {row.get('total_points', 0)} {currency()}" for i, row in enumerate(rows, 1)]
    return (f"┏┅{emoji('peach')}┅/ <b>{t['top_title']}</b> /\n┋\n┣ {t['ranking']}\n┋\n"
            + ("\n".join(lines) if lines else f"┋ {t['empty']}")
            + f"\n┣ ┅┅┅┅┅┅┅┅┅┅┅┅┅┅┅\n┣ <b>{t['burned']}: {burned} {currency()}</b>"
            + "\n┗┅┅┅/ SYSTEM NIGHTMARE /▱▱")


def attack_text(attack, *, result=False):
    t = locale(attack["language"])
    # Names are raw snapshots from trusted Telegram/database profiles, never HTML.
    values = {"attacker": html.escape(attack["attacker_name"]),
              "victim": html.escape(attack["victim_name"]),
              "amount": attack["amount"] if result else attack["preview_amount"], "unit": currency()}
    if not result:
        return (f"{PREFIX}{emoji('game')}┅/ <b>{t['attack_title']}</b> /\n┋\n"
                f"┣ {emoji('alarm')} <b>{t['attack_alarm']}</b>\n"
                f"┣ {t['attack'].format(**values)}\n┋\n"
                f"┣ {emoji('hourglass')} {t['reaction'].format(**values)}\n┣ {t['firewall']}\n"
                f"┋\n┣ {t['minimum']}\n┋\n┗┅┅┅/ HUMANS • NOT • APES /▱▱")
    if attack["status"] == "defended":
        return (f"{PREFIX}/ <b>Crimson Firewall</b> /\n┋\n"
                f"┣ {emoji('warning')} <b>{t['defense_alarm']}</b>\n"
                f"┣ {t['defended'].format(**values)}\n┣ {t['caught'].format(**values)}\n┋\n"
                f"┣ <b>{t['penalty']}: −15 {currency()}</b>\n"
                f"┣ <b>{t['intercepted'].format(**values)}: +10 {currency()}</b>\n"
                f"┣ <b>{t['burned']}: 5 {currency()}</b>\n┋\n┗┅┅┅/ ACCESS DENIED /▱▱")
    return (f"{PREFIX}{emoji('game')}┅/ <b>{t['success_title']}</b> /\n┋\n"
            f"┣ <b>{t['waited'].format(**values)}</b>\n┣ <b>{t['slept'].format(**values)}</b>\n┋\n"
            f"┣ {emoji('money')} <b>{t['stolen']}: +{values['amount']} {currency()}</b>\n"
            "┗┅┅┅/ BLOOD MODE /▱▱")


class ChatGameService:
    @staticmethod
    async def rpc(name, params=None):
        if not db.client:
            raise RuntimeError("Database unavailable")
        response = await db.client.rpc(name, params or {}).execute()
        return response.data

    @staticmethod
    async def registered(user_id):
        if not db.client:
            raise RuntimeError("Database unavailable")
        response = await db.client.table("users").select("telegram_id,username,first_name,language").eq(
            "telegram_id", user_id).execute()
        return response.data[0] if response.data else None

    @staticmethod
    async def target_by_username(username):
        # Validate in the handler; ilike is only used without wildcard characters.
        response = await db.client.table("users").select("telegram_id,username,first_name").ilike(
            "username", username.replace("_", "\\_")).limit(2).execute()
        return response.data[0] if len(response.data) == 1 else None

    @classmethod
    async def tick(cls, bot):
        due = await db.client.table("safe_attacks").select("id,deadline").eq("status", "pending").lte(
            "deadline", (datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat()).order("deadline").limit(50).execute()
        for attack in due.data:
            try:
                await cls.rpc("finish_safe_attack", {"p_id": attack["id"]})
            except Exception:
                logger.exception("SAFE_SETTLEMENT_RETRY attack_id=%s", attack["id"])
        for attack in await cls.rpc("claim_safe_notifications") or []:
            try:
                await safe_bot_send_message(bot, attack["chat_id"], attack_text(attack, result=True),
                                            message_thread_id=attack.get("thread_id"),
                                            link_preview_options=LinkPreviewOptions(is_disabled=True))
            except (TelegramForbiddenError, TelegramBadRequest):
                # Permanent Telegram failure must not reverse a settled operation.
                logger.exception("SAFE_RESULT_UNDELIVERABLE attack_id=%s", attack["id"])
            except Exception:
                logger.exception("SAFE_RESULT_RETRY attack_id=%s", attack["id"])
                continue
            await db.client.table("safe_attacks").update({
                "notified_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", attack["id"]).execute()

    @classmethod
    async def poll_forever(cls, bot):
        # Allow buffered incoming updates to activate defenses after a restart.
        recovered_before = datetime.now(timezone.utc).isoformat()
        await asyncio.sleep(10)
        recovered = False
        while True:
            try:
                if not recovered:
                    # Fail closed and retry if recovery fails: never silently
                    # kill the worker or steal during an unobserved downtime.
                    await cls.recover_overdue(recovered_before)
                    recovered = True
                await cls.tick(bot)
            except Exception:
                logger.exception("SAFE_WORKER_FAILED")
            await asyncio.sleep(2)

    @classmethod
    async def recover_overdue(cls, restarted_at):
        while True:
            pending = await db.client.table("safe_attacks").select("id").eq("status", "pending").lt(
                "deadline", restarted_at).order("id").limit(50).execute()
            if not pending.data:
                return
            for attack in pending.data:
                await cls.rpc("finish_safe_attack", {"p_id": attack["id"], "p_cancel": True})


async def register_chat_commands(bot):
    """Add group-menu commands without replacing existing commands or private menus."""
    scope = BotCommandScopeAllGroupChats()
    for language, descriptions in (("", ("local balance", "leaderboard", "Bank Robber")),
                                   ("ru", ("баланс RP", "рейтинг игроков", "ограбление банка")),
                                   ("en", ("local balance", "leaderboard", "Bank Robber"))):
        old = await bot.get_my_commands(scope=scope, language_code=language)
        commands = {item.command: item for item in old}
        commands.update({name: BotCommand(command=name, description=description)
                         for name, description in zip(("balance", "top", "safe"), descriptions)})
        await bot.set_my_commands(list(commands.values()), scope=scope, language_code=language)
