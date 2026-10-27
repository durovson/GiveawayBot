import html
import logging
import re
from datetime import timedelta

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions, Message

from database import db
from services.chat_games import ChatGameService, SafeTargetError, PREFIX, attack_text, balance_text, locale, top_text
from services.chat_game_theme import emoji
from utils import safe_bot_send_message

logger = logging.getLogger(__name__)
router = Router(name="chat_games")
GROUPS = {"group", "supergroup"}


async def send(message, text, **kwargs):
    return await safe_bot_send_message(message.bot, message.chat.id, text,
                                       message_thread_id=message.message_thread_id,
                                       link_preview_options=LinkPreviewOptions(is_disabled=True), **kwargs)


async def error(message, code, language):
    t = locale(language)
    await send(message, f"{PREFIX}{emoji('game')}┅/ <b>{t['error_title']}</b> /\n┋\n"
                       f"┣ {t.get(code, t['UNAVAILABLE'])}\n┋\n┗┅┅┅/ {t['option']} /")


async def caller(message):
    if not message.from_user or message.from_user.is_bot or message.sender_chat:
        return None
    user = await ChatGameService.registered(message.from_user.id)
    if user:
        return user
    # Only command callers get this prompt. Never react to an unregistered bystander.
    name = html.escape("@" + message.from_user.username if message.from_user.username
                       else message.from_user.first_name.replace("@", "＠"))
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="OPEN", url="https://t.me/notfunrobot?start=chat_games", style="danger")
    ]])
    await send(message, f"{PREFIX}{emoji('game')}┅/ <b>WTF???</b> /\n┋\n"
                       f"┣ {name}, you still haven't joined @notfunrobot.\n"
                       "┣ You're missing all the giveaways and activities!\n┣ Time to fix that.\n┋\n"
                       "┗┅┅┅/ <b>Select an option</b> /", reply_markup=markup)
    return None


@router.message(Command("balance"))
async def balance_command(message: Message):
    language = "en"
    try:
        user = await caller(message)
        if not user:
            return
        language = user.get("language", "en")
        response = await db.client.table("points").select("total_points").eq("user_id", user["telegram_id"]).execute()
        await send(message, balance_text(response.data[0]["total_points"] if response.data else 0, language))
    except Exception:
        logger.exception("BALANCE_COMMAND_FAILED")
        await error(message, "UNAVAILABLE", language)


@router.message(Command("top"))
async def top_command(message: Message):
    language = "en"
    try:
        user = await caller(message)
        if not user:
            return
        language = user.get("language", "en")
        # Exactly the same ordering as the existing private-chat leaderboard.
        response = await db.client.table("points").select("user_id,total_points,users(username,first_name)").order(
            "total_points", desc=True).order("packs", desc=True).order("active_referrals", desc=True).order(
            "user_id", desc=False).limit(10).execute()
        burned = await ChatGameService.rpc("get_safe_burned")
        await send(message, top_text(response.data, burned, language))
    except Exception:
        logger.exception("TOP_COMMAND_FAILED")
        await error(message, "UNAVAILABLE", language)


def raw_name(user):
    return "@" + user["username"].lstrip("@") if user.get("username") else (
        user.get("first_name") or str(user["telegram_id"])).replace("@", "＠")


async def target(message, args):
    if args:
        # Underscores in valid usernames are literal, not SQL LIKE wildcards.
        if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", args.strip()):
            return None
        return await ChatGameService.target_by_username(args.strip()[1:])
    return await ChatGameService.random_target(message.bot, message.chat.id, message.from_user.id)


@router.message(Command("safe"))
async def safe_command(message: Message, command: CommandObject):
    language = "en"
    try:
        user = await caller(message)
        if not user:
            return
        language = user.get("language", "en")
        if message.chat.type not in GROUPS:
            await error(message, "GROUP_ONLY", language)
            return
        identity = await message.bot.get_me()
        membership = await message.bot.get_chat_member(message.chat.id, identity.id)
        if membership.status not in {"administrator", "creator"} and not identity.can_read_all_group_messages:
            await error(message, "READ_ACCESS", language)
            return
        victim = await target(message, command.args)
        if not victim:
            await error(message, "TARGET_NOT_FOUND", language)
            return
        if victim["telegram_id"] == user["telegram_id"]:
            await error(message, "SELF", language)
            return
        try:
            member = await message.bot.get_chat_member(message.chat.id, victim["telegram_id"])
        except (TelegramBadRequest, TelegramForbiddenError):
            await error(message, "TARGET_UNVERIFIABLE", language)
            return
        if (member.status in {"left", "kicked"} or (member.status == "restricted" and not member.is_member)
                or getattr(getattr(member, "user", None), "is_bot", False)):
            await error(message, "TARGET_NOT_MEMBER", language)
            return
        # Stored usernames may be stale or reassigned to another Telegram user.
        # Verify the requested handle and build mentions from live Telegram data.
        current_target = getattr(member, "user", None)
        if current_target:
            if command.args and (current_target.username or "").lower() != command.args.strip()[1:].lower():
                await error(message, "TARGET_NOT_FOUND", language)
                return
            victim = {**victim, "username": current_target.username, "first_name": current_target.first_name}
        attacker = {"telegram_id": user["telegram_id"], "username": message.from_user.username,
                    "first_name": message.from_user.first_name}
        result = await ChatGameService.rpc("start_safe_attack", {
            "p_chat_id": message.chat.id, "p_message_id": message.message_id,
            "p_attacker": user["telegram_id"], "p_victim": victim["telegram_id"],
            "p_language": language, "p_attacker_name": raw_name(attacker), "p_victim_name": raw_name(victim),
            "p_thread_id": message.message_thread_id,
        })
        if not result.get("ok"):
            await error(message, result.get("error"), language)
            return
        if result.get("duplicate"):
            return
        attack = result["attack"]
        try:
            announcement = await send(message, attack_text(attack))
            await db.client.table("safe_attacks").update({
                "announcement_id": announcement.message_id,
                "started_at": announcement.date.isoformat(),
                "deadline": (announcement.date+timedelta(minutes=5)).isoformat(),
            }).eq(
                "id", attack["id"]).execute()
        except Exception:
            # A failed/unconfirmed warning cannot lead to an invisible theft.
            await ChatGameService.rpc("finish_safe_attack", {"p_id": attack["id"], "p_cancel": True})
            raise
    except SafeTargetError as selection:
        await error(message, selection.code, language)
    except Exception:
        logger.exception("SAFE_COMMAND_FAILED")
        await error(message, "UNAVAILABLE", language)
