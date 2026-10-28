"""Persistent Arena timer and result outbox. An update/restart cannot replay the prize."""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timezone

from database import db
from handlers.arena import screen, t

logger = logging.getLogger(__name__)


async def _rpc(name: str, args=None):
    response = await db.client.rpc(name, args or {}).execute()
    return response.data


async def _send(bot, user_id: int, text: str):
    try:
        await bot.send_message(user_id, text)
    except Exception:
        logger.warning("ARENA_DM_FAILED user=%s", user_id, exc_info=True)


def _name(raw: str) -> str:
    return html.escape(str(raw or "Player"))


class ArenaWorker:
    @staticmethod
    async def _resolve(bot, match: dict) -> None:
        lang = match["language"]
        host, guest = _name(match["host_name"]), _name(match["guest_name"])
        winner_id = match["winner_id"]
        winner = host if winner_id == match["host_id"] else guest
        loser = guest if winner_id == match["host_id"] else host
        stake = int(match["stake"])
        final = screen(
            t(lang,"СЕССИЯ ЗАКРЫТА","SESSION CLOSED"),
            t(lang,"🏁 Логи сетевой стычки обработаны.","🏁 The network skirmish logs have been processed."),
            "",
            f"🥇 {t(lang,'Взломщик','Hacker')}: <b>{winner}</b> ({t(lang,'Логи','Logs')}: +{stake} 🎃)",
            f"⚰️ {t(lang,'Жертва','Victim')}: <b>{loser}</b> (" +
                t(lang,"Система скомпрометирована","System compromised") + ")",
            footer="TERMINAL CLOSED",
        )
        # Mark delivered only after the public conclusion is sent.
        try:
            await bot.send_message(match["chat_id"],final)
        except Exception:
            logger.warning("ARENA_GROUP_RESULT_FAILED match=%s",match["id"],exc_info=True)
            return
        await db.client.table("arena_fights").update({
            "notified_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", match["id"]).is_("notified_at","null").execute()
        for uid in (match["host_id"],match["guest_id"]):
            try:
                user_lang = await db.get_user_language(uid) or lang
            except Exception:
                user_lang = lang
            won = uid == winner_id
            try:
                row = await db.client.table("arena_wallets").select("balance").eq("user_id",uid).single().execute()
                current = int((row.data or {}).get("balance",0))
            except Exception:
                current = 0
            if won:
                txt = screen(
                    t(user_lang,"ВЗЛОМ УСПЕШЕН","HACK SUCCESSFUL"),
                    t(user_lang,"[+] Firewall противника подавлен.","[+] Opponent firewall suppressed."),
                    f"[+] {t(user_lang,'Изъято из пула','Won from pool')}: +{stake} 🎃",
                    "",
                    f"{t(user_lang,'Ваш баланс','Your balance')}: <b>{current} 🎃</b>",
                )
            else:
                txt = screen(
                    t(user_lang,"СИСТЕМА ВЗЛОМАНА","SYSTEM BREACHED"),
                    t(user_lang,"[-] Ваша защита была скомпрометирована","[-] Your defenses were compromised") + f" {winner}",
                    f"[-] {t(user_lang,'Потеряно','Lost')}: -{stake} 🎃",
                    "",
                    f"{t(user_lang,'Защищённый остаток и баланс','Protected reserve and balance')}: <b>{current} 🎃</b>",
                )
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            b=InlineKeyboardBuilder()
            b.button(text=t(lang,"ГЛАВНОЕ МЕНЮ","MAIN MENU"),callback_data="main_menu")
            try:
                await bot.send_message(uid,txt,reply_markup=b.as_markup())
            except Exception:
                logger.warning("ARENA_PERSONAL_RESULT_FAILED user=%s match=%s",uid,match["id"])

    @classmethod
    async def tick(cls, bot) -> None:
        expired = await _rpc("arena_expire") or []
        for match in expired:
            lang = match["language"]
            try:
                await bot.send_message(match["chat_id"],screen(
                    t(lang,"ЭКСПЛОИТ ОТОЗВАН","EXPLOIT CANCELLED"),
                    t(lang,"Противник не был найден за 5 минут.","No opponent joined within 5 minutes."),
                    f"{t(lang,'Возврат','Refund')}: {match['stake']} 🎃",
                    footer="TERMINAL CLOSED",
                ))
            except Exception:
                logger.warning("ARENA_EXPIRED_GROUP_FAILED match=%s",match["id"])
            await _send(bot,match["host_id"],screen(
                t(lang,"ВРЕМЯ ИСТЕКЛО","TIME EXPIRED"),
                t(lang,"Ставка возвращена на ваш баланс.","Your stake has been refunded."),
            ))
        for fight in await _rpc("arena_claim_results") or []:
            try:
                await cls._resolve(bot,fight)
            except Exception:
                logger.exception("ARENA_RESULT_RETRY match=%s",fight["id"])

    @classmethod
    async def poll_forever(cls, bot) -> None:
        while True:
            try:
                await cls.tick(bot)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("ARENA_WORKER_FAILED")
            await asyncio.sleep(3)
