"""Persistent chat games and HTML presentation. No in-memory balance or timers."""
import asyncio
import html
import logging
import random
from collections import OrderedDict
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

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


class SafeTargetError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


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


def profile_text(user, stats, language):
    t = locale(language)
    return (f"{PREFIX}/ <b>{t['profile_title']} {player_name(user)}</b> /\n┋\n"
            f"┣ {t['rank']}: {stats.get('rank') or '—'}\n"
            f"┣ {t['profile_balance']}: {stats['balance']} {currency()}\n"
            f"┣ {t['duels']}: {stats['wins']} {t['wins']} | {stats['losses']} {t['losses']}\n"
            "┗┅┅┅/ HUMANS • NOT • APES /▱▱")


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
    _random = random.SystemRandom()
    _observed = OrderedDict()

    @classmethod
    def observe_member(cls, bot, chat_id, user, at, *, active=True, status='member'):
        """Only Telegram-delivered messages/member updates are membership evidence.

        Evidence expires after five minutes and is isolated by bot and chat.
        Never infer membership from registration, an @handle, or another chat.
        """
        key = (getattr(bot, 'id', 0), chat_id, user.id)
        previous = cls._observed.get(key)
        if previous and previous[0] > at:
            return
        cls._observed.pop(key, None)
        cls._observed[key] = (at, user, active, status)
        while len(cls._observed) > 20000:
            cls._observed.popitem(last=False)

    @classmethod
    async def chat_member(cls, bot, chat_id, user_id):
        try:
            member = await bot.get_chat_member(chat_id, user_id)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            evidence = cls._observed.get((getattr(bot, 'id', 0), chat_id, user_id))
            now = datetime.now(timezone.utc)
            if evidence and timedelta(0) <= now - evidence[0] <= timedelta(minutes=5):
                at, user, active, status = evidence
                logger.info('SAFE_MEMBER_OBSERVED_FALLBACK bot=%s chat=%s user=%s active=%s',
                            getattr(bot, 'id', 0), chat_id, user_id, active)
                return SimpleNamespace(status=status if active else 'left', user=user, is_member=active)
            message = str(exc).lower()
            if any(marker in message for marker in ('participant_id_invalid', 'user_id_invalid', 'user not found', 'member not found')):
                # A global RP account need not belong to this group. Telegram
                # rejects such peers instead of always returning status=left.
                # This is an ordinary ineligible target, not a permissions fault.
                raise SafeTargetError('READ_ACCESS' if user_id == getattr(bot, 'id', None)
                                      else 'TARGET_NOT_MEMBER') from exc
            if any(marker in message for marker in ('bot was kicked', 'bot is not a member')):
                raise SafeTargetError('READ_ACCESS') from exc
            logger.warning('SAFE_MEMBER_CHECK_FAILED bot=%s chat=%s user=%s error=%s',
                           getattr(bot, 'id', 0), chat_id, user_id, exc)
            raise
        # An explicit Telegram leave/ban always overrides prior observations.
        if member.status in {'left', 'kicked'} or (member.status == 'restricted' and not member.is_member):
            cls._observed.pop((getattr(bot, 'id', 0), chat_id, user_id), None)
        return member
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
    async def random_target(cls, bot, chat_id, attacker_id):
        """Uniform random eligible registered member; never a global outsider.

        Bot API does not expose a full member list. Enumerate registered RP
        accounts, then verify membership in this exact chat with getChatMember.
        No attack or charge is created during candidate selection.
        """
        if not db.client:
            raise RuntimeError('Database unavailable')
        own = await db.client.table('points').select('total_points').eq('user_id', attacker_id).execute()
        if not own.data or (own.data[0].get('total_points') or 0) < 15:
            raise SafeTargetError('LOW_ATTACKER')
        day = datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
        attempts = await db.client.table('safe_attacks').select('victim_id').eq(
            'attacker_id', attacker_id).eq('game_day', day).neq('status', 'cancelled').execute()
        if len(attempts.data) >= 3:
            raise SafeTargetError('DAILY_LIMIT')
        used = {row['victim_id'] for row in attempts.data}
        candidates = []
        offset = 0
        while True:
            page = await db.client.table('points').select(
                'user_id,total_points,users!inner(telegram_id,username,first_name)'
            ).gt('total_points', 50).neq('user_id', attacker_id).order('user_id').range(
                offset, offset + 499).execute()
            for row in page.data:
                if row['user_id'] not in used and row.get('users'):
                    candidates.append(row['users'])
            if len(page.data) < 500:
                break
            offset += 500
        cls._random.shuffle(candidates)
        unverified = False
        absent = 0
        for candidate in candidates:
            try:
                member = await cls.chat_member(bot, chat_id, candidate['telegram_id'])
            except SafeTargetError as exc:
                if exc.code != 'TARGET_NOT_MEMBER':
                    raise
                absent += 1
                continue
            except (TelegramBadRequest, TelegramForbiddenError):
                unverified = True
                continue
            if member.status in {'left', 'kicked'} or (member.status == 'restricted' and not member.is_member):
                continue
            if member.user.is_bot:
                continue
            return {**candidate, 'username': member.user.username, 'first_name': member.user.first_name,
                    '_chat_member': member}
        logger.info('SAFE_NO_RANDOM_TARGET bot=%s chat=%s eligible_accounts=%s absent=%s unverified=%s',
                    getattr(bot, 'id', 0), chat_id, len(candidates), absent, unverified)
        raise SafeTargetError('TARGET_UNVERIFIABLE' if unverified else 'NO_TARGETS')

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
    for language, descriptions in (("", ("local balance", "leaderboard", "Bank Robber", "player profile")),
                                   ("ru", ("баланс RP", "рейтинг игроков", "ограбление банка", "профиль игрока")),
                                   ("en", ("local balance", "leaderboard", "Bank Robber", "player profile"))):
        old = await bot.get_my_commands(scope=scope, language_code=language)
        commands = {item.command: item for item in old}
        commands.update({name: BotCommand(command=name, description=description)
                         for name, description in zip(("balance", "top", "safe", "profile"), descriptions)})
        await bot.set_my_commands(list(commands.values()), scope=scope, language_code=language)
