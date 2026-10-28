"""Bank Robber Arena v2: all balances and outcomes live in Supabase."""
from __future__ import annotations

import asyncio
import html
import logging
import os
from datetime import datetime, timezone
from uuid import UUID

from aiogram import F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import db
from services.chat_game_theme import emoji
from services.localization import get_locale_by_lang
from utils import safe_edit_text

router = Router(name="arena")
logger = logging.getLogger(__name__)
HEADER = "┏┅⋐[ ◍ _◍ ]っ┅🎮┅/ "
MIN_STAKE = 15
PROTECTED = 50
MIN_ENTRY = 20


def english(lang: str) -> bool:
    return lang != "ru"


def t(lang: str, ru: str, en: str) -> str:
    return en if english(lang) else ru


def username(user: types.User) -> str:
    return "@" + user.username if user.username else (user.first_name or str(user.id))


def chat_id() -> int:
    value = os.getenv("ARENA_CHAT_ID", "").strip()
    return int(value) if value.lstrip("-").isdigit() else 0


def screen(title: str, *lines: str, footer: str = "Choose an action") -> str:
    return HEADER + f"<b>{title}</b> /\n┋\n" + "\n".join("┣ " + line for line in lines) + "\n┋\n┗┅┅┅/ <b>" + footer + "</b> /"


async def rpc(name: str, params=None):
    if db.client is None:
        raise RuntimeError("Supabase is not connected")
    result = await db.client.rpc(name, params or {}).execute()
    return result.data


async def balance(user_id: int) -> int:
    result = await rpc("arena_balance", {"p_user_id": user_id})
    return int(result or 0)


def back(lang: str, data: str = "game_menu"):
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "НАЗАД", "BACK"), callback_data=data)
    return b.as_markup()


def _choose_stake(lang: str, available: int):
    spendable = max(0, available - PROTECTED)
    b = InlineKeyboardBuilder()
    if spendable >= MIN_ENTRY:
        b.button(text="15 🎃", callback_data="arena:stake:15")
    if spendable >= 50:
        b.button(text="50 🎃", callback_data="arena:stake:50")
    if spendable >= MIN_ENTRY:
        b.button(text=f"MAX · {spendable} 🎃", callback_data=f"arena:stake:{spendable}")
    b.button(text=t(lang, "ВВЕСТИ СВОЁ", "CUSTOM"), callback_data="arena:stake:custom")
    b.button(text=t(lang, "НАЗАД", "BACK"), callback_data="arena:menu")
    b.adjust(2, 1, 1, 1)
    return b.as_markup()


class ArenaStates(StatesGroup):
    stake = State()
    convert = State()


async def show_arena(callback: types.CallbackQuery, state: FSMContext, lang: str):
    user_id = callback.from_user.id
    try:
        pumpkins = await balance(user_id)
    except Exception:
        logger.exception("ARENA_BALANCE_FAILED user=%s", user_id)
        await callback.answer(t(lang, "Арена временно недоступна", "Arena is temporarily unavailable"), show_alert=True)
        return
    points = await db.get_points(user_id)
    rp = int((points or {}).get("total_points", 0))
    text = screen(
        "ARENA",
        t(lang, "Играйте с другими игроками и выигрывайте тыквы.", "Challenge players and win pumpkins."),
        "",
        f"<b>🎃 {t(lang, 'Баланс', 'Balance')}:</b> {pumpkins}",
        f"<b>RP:</b> {rp}",
        t(lang, "50 🎃 защищены от проигрыша.", "50 🎃 are protected from losses."),
        t(lang, "1 RP = 100 🎃 в магазине ITEMS.", "1 RP = 100 🎃 in the ITEMS store."),
        footer=t(lang, "Выберите действие", "Choose an action"),
    )
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "НАЧАТЬ ИГРУ", "START GAME"), callback_data="arena:start")
    b.button(text=t(lang, "НАЗАД", "BACK"), callback_data="game_menu")
    b.adjust(1)
    await safe_edit_text(callback, text, reply_markup=b.as_markup(), state=state)


@router.callback_query(F.data == "arena:menu")
async def arena_menu(callback: types.CallbackQuery, state: FSMContext, lang: str):
    await callback.answer()
    await state.clear()
    await show_arena(callback, state, lang)


@router.callback_query(F.data == "arena:start")
async def arena_start(callback: types.CallbackQuery, state: FSMContext, lang: str):
    await callback.answer()
    try:
        pumpkins = await balance(callback.from_user.id)
    except Exception:
        await callback.answer()
        logger.exception("ARENA_STAKE_FAILED")
        return
    text = screen(
        "SYSTEM: PENDING",
        t(lang, "ВЫДЕЛЕНИЕ ПАКЕТОВ ДЛЯ ИНИЦИАЛИЗАЦИИ:", "ALLOCATING PACKETS FOR INITIALIZATION:"),
        t(lang, "Несгораемый минимум на узле: 50 🎃", "Protected node minimum: 50 🎃"),
        t(lang, "При поражении вы теряете выделенный объём данных.", "You lose your staked data if defeated."),
        f"{t(lang, 'Текущий баланс', 'Current balance')}: <b>{pumpkins} 🎃</b>",
        footer=t(lang, "Быстрый выбор объёма атаки", "Quick stake selection"),
    )
    await safe_edit_text(callback, text, reply_markup=_choose_stake(lang, pumpkins), state=state)


async def stake_confirmation(callback: types.CallbackQuery, state: FSMContext, lang: str, amount: int):
    available = await balance(callback.from_user.id)
    if available < PROTECTED + max(MIN_ENTRY, amount) or amount < MIN_STAKE:
        await callback.answer(t(lang, "Нужно минимум 20 свободных 🎃 и 50 защищённых 🎃.", "You need 20 spendable 🎃 plus 50 protected 🎃."), show_alert=True)
        return
    await state.update_data(arena_stake=amount)
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "РАЗВЕРНУТЬ ЭКСПЛОИТ", "DEPLOY EXPLOIT"), callback_data="arena:deploy")
    b.button(text=t(lang, "НАЗАД", "BACK"), callback_data="arena:start")
    b.adjust(1)
    await safe_edit_text(
        callback,
        screen(
            t(lang, "АТАКА ПОДГОТОВЛЕНА", "EXPLOIT READY"),
            f"{t(lang, 'Выделено', 'Staked')}: <b>{amount} 🎃</b>",
            t(lang, "Сумма будет заблокирована до завершения игры.", "The stake is locked until the match ends."),
            footer=t(lang, "Подтвердите действие", "Confirm action"),
        ),
        reply_markup=b.as_markup(), state=state,
    )


@router.callback_query(F.data.startswith("arena:stake:"))
async def select_stake(callback: types.CallbackQuery, state: FSMContext, lang: str):
    raw = (callback.data or "").split(":")[-1]
    if raw == "custom":
        await callback.answer()
        await state.set_state(ArenaStates.stake)
        await safe_edit_text(callback,
            screen("SYSTEM: PENDING", t(lang, "Введите количество 🎃 (минимум 15):", "Enter 🎃 amount (minimum 15):")),
            reply_markup=back(lang, "arena:start"), state=state)
        return
    await callback.answer()
    await stake_confirmation(callback, state, lang, int(raw))


@router.message(ArenaStates.stake, F.chat.type == "private")
async def custom_stake(message: types.Message, state: FSMContext, lang: str):
    try:
        amount = int((message.text or "").strip())
    except ValueError:
        amount = 0
    if amount < MIN_STAKE:
        await message.answer(t(lang, "Введите целое число от 15.", "Enter an integer of at least 15."))
        return
    await state.set_state(None)
    await state.update_data(arena_stake=amount)
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "РАЗВЕРНУТЬ", "DEPLOY"), callback_data="arena:deploy")
    b.button(text=t(lang, "НАЗАД", "BACK"), callback_data="arena:start")
    await message.answer(screen("EXPLOIT READY", f"{amount} 🎃"), reply_markup=b.as_markup())


@router.callback_query(F.data == "arena:deploy")
async def deploy(callback: types.CallbackQuery, state: FSMContext, lang: str):
    await callback.answer()
    target_chat = chat_id()
    if not target_chat:
        await safe_edit_text(callback, screen("SYSTEM: OFFLINE",
            t(lang, "Игровой чат пока не подключён.", "Game chat is not configured.")),
            reply_markup=back(lang, "arena:start"), state=state)
        return
    data = await state.get_data()
    amount = int(data.get("arena_stake") or 0)
    if amount < MIN_STAKE:
        return
    try:
        result = await rpc("arena_open", {
            "p_user_id": callback.from_user.id,
            "p_stake": amount,
            "p_chat_id": target_chat,
            "p_name": username(callback.from_user),
            "p_language": lang,
        })
    except Exception:
        logger.exception("ARENA_OPEN_FAILED")
        await safe_edit_text(callback, screen("SYSTEM: ERROR",
            t(lang, "Игра временно недоступна. Баланс не списан, если создание не подтверждено.", "Game unavailable; verify balance before retrying.")),
            reply_markup=back(lang, "arena:menu"), state=state)
        return
    if not result or not result.get("ok"):
        await safe_edit_text(callback, screen("SYSTEM: ERROR",
            t(lang, "Игра не открыта: ", "Game not opened: ") + html.escape((result or {}).get("error", "UNKNOWN"))),
            reply_markup=back(lang, "arena:menu"), state=state)
        return
    match = result["fight"]
    mid = match["id"]
    me = await callback.bot.get_me()
    link = f"https://t.me/{me.username}?start=arena_{mid}"
    announcement = screen(
        t(lang, "СЕТЕВАЯ УГРОЗА", "NETWORK THREAT"),
        f"🚨 {html.escape(match['host_name'])} " + t(lang, "развернул боевой эксплоит!", "has deployed a combat exploit!"),
        t(lang, "🎯 Требуется соперник для проверки атаки.", "🎯 A challenger is needed to validate the attack."),
        "",
        f"💵 {t(lang, 'Ресурс', 'Stake')}: <b>{amount} 🎃</b>",
        t(lang, "⏳ До детонации: 5 минут", "⏳ Detonation in 5 minutes"),
        footer=t(lang, "СИСТЕМА ИЩЕТ СОПЕРНИКА", "SEARCHING FOR OPPONENT"),
    )
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "ПРИНЯТЬ БОЙ", "ACCEPT FIGHT"), url=link)
    try:
        sent = await callback.bot.send_message(target_chat, announcement, reply_markup=b.as_markup())
        await db.client.table("arena_fights").update({"announcement_id": sent.message_id}).eq("id", mid).execute()
    except Exception:
        logger.exception("ARENA_ANNOUNCE_FAILED fight=%s", mid)
        await rpc("arena_cancel", {"p_id": mid, "p_user_id": callback.from_user.id, "p_expire": False})
        await safe_edit_text(callback, screen("SYSTEM: ERROR",
            t(lang, "Не удалось отправить анонс, ставка возвращена.", "Announcement failed; stake was refunded.")),
            reply_markup=back(lang, "arena:menu"), state=state)
        return
    await state.clear()
    await safe_edit_text(callback, screen(
        t(lang, "ЭКСПЛОИТ РАЗВЕРНУТ", "EXPLOIT DEPLOYED"),
        t(lang, "ИНИЦИИРОВАТЬ СЕТЕВУЮ АТАКУ (DEPLOY)", "NETWORK ATTACK INITIALIZED"),
        f"{t(lang, 'ЗАБЛОКИРОВАНО ПОД АТАКУ', 'STAKED')}: <b>{amount} 🎃</b>",
        t(lang, "[ СТАТУС: ПОДКЛЮЧЕНИЕ ОППОНЕНТА... ]", "[ STATUS: CONNECTING OPPONENT... ]"),
        t(lang, "Ждём, пока соперник примет ваш вызов.", "Waiting for a player to accept your challenge."),
        t(lang, "Автоотмена: 5 минут.", "Auto-cancel: 5 minutes."),
        footer=t(lang, "Пингование шлюзов...", "Pinging gateways..."),
    ), reply_markup=_cancel_keyboard(lang, mid), state=state)


def _cancel_keyboard(lang: str, match_id: str):
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "ОТМЕНИТЬ ИГРУ", "CANCEL GAME"), callback_data=f"arena:cancel:{match_id}")
    return b.as_markup()


@router.callback_query(F.data.startswith("arena:cancel:"))
async def cancel_game(callback: types.CallbackQuery, state: FSMContext, lang: str):
    await callback.answer()
    mid = (callback.data or "").split(":")[-1]
    try:
        result = await rpc("arena_cancel", {"p_id":mid,"p_user_id":callback.from_user.id})
    except Exception:
        logger.exception("ARENA_CANCEL_FAILED")
        return
    await safe_edit_text(callback,
        screen("SYSTEM: CANCELLED",
            t(lang, "Игра отменена. Тыквы возвращены на баланс.", "Game cancelled. Your pumpkins were refunded.")
            if result and result.get("ok") else t(lang, "Игра уже закрыта.", "Game already closed.")),
        reply_markup=back(lang, "arena:menu"), state=state)


@router.message(F.chat.type == "private", F.text.regexp(r"^/start(?:@\w+)? arena_[0-9A-Fa-f-]{36}$"))
async def game_deep_link(message: types.Message, state: FSMContext, lang: str):
    mid = (message.text or "").rsplit("arena_", 1)[-1]
    try:
        UUID(mid)
        response = await db.client.table("arena_fights").select(
            "id,host_id,host_name,stake,status,deadline"
        ).eq("id", mid).single().execute()
        match = response.data
    except Exception:
        match = None
    if not match or match["status"] != "waiting":
        await message.answer(screen("SYSTEM: CLOSED",
            t(lang, "Этот вызов уже недоступен.", "This challenge is no longer available.")))
        return
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "ПРИНЯТЬ БОЙ", "ACCEPT FIGHT"), callback_data=f"arena:join:{mid}")
    b.button(text=t(lang, "НАЗАД", "BACK"), callback_data="arena:menu")
    b.adjust(1)
    await message.answer(screen(
        "ARENA: FIGHT",
        f"{t(lang, 'Создатель', 'Host')}: {html.escape(match['host_name'])}",
        f"{t(lang, 'Ставка', 'Stake')}: {match['stake']} 🎃",
        t(lang, "Победитель получит обе ставки.", "Winner receives both stakes."),
    ), reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("arena:join:"))
async def join_match(callback: types.CallbackQuery, state: FSMContext, lang: str):
    await callback.answer()
    mid = (callback.data or "").split(":")[-1]
    try:
        result = await rpc("arena_join", {
            "p_id": mid, "p_user_id": callback.from_user.id,
            "p_name": username(callback.from_user),
        })
    except Exception:
        logger.exception("ARENA_JOIN_FAILED")
        return
    if not result or not result.get("ok"):
        await safe_edit_text(callback, screen("SYSTEM: ERROR",
            html.escape((result or {}).get("error", "UNAVAILABLE"))),
            reply_markup=back(lang, "arena:menu"), state=state)
        return
    fight = result["fight"]
    if result.get("duplicate"):
        return
    await safe_edit_text(callback, screen("SYSTEM: READY",
        t(lang, "Соперник найден! Симуляция началась.", "Opponent matched! Simulation starting.")),
        reply_markup=back(lang, "arena:menu"), state=state)
    asyncio.create_task(simulate(callback.bot, fight), name=f"arena-sim:{mid}")


async def simulate(bot: types.Bot, match: dict) -> None:
    """Narration is presentation only. The outcome was already committed atomically."""
    host, guest = html.escape(match["host_name"]), html.escape(match["guest_name"])
    lang = match.get("language", "en")
    stages = [
        ("ЗАПУСК СИМУЛЯЦИИ...", "SIMULATION STARTING...", [
            f"⚡️ {host} разогнал частоту процессора до предела...",
            f"🍌 {host} бросил заражённый банан-модификатор в {guest}!",
            f"🛡 Firewall игрока {guest} перегружен.",
        ], [
            f"⚡️ {host} overclocked the processor...",
            f"🍌 {host} threw an infected banana modifier at {guest}!",
            f"🛡 {guest}'s firewall is overloaded.",
        ]),
        ("ПОДКЛЮЧЕНИЕ К УЗЛУ...", "CONNECTING TO NODE...", [
            f"👾 {guest} попытался подделать подпись Crimson Firewall...",
            f"📡 {host} перехватил трафик и запустил обратный импульс!",
            f"⚠️ Пакеты {guest} заблокированы на шлюзе.",
        ], [
            f"👾 {guest} tried to forge the Crimson Firewall signature...",
            f"📡 {host} intercepted traffic and sent a return pulse!",
            f"⚠️ {guest}'s packets were blocked at the gateway.",
        ]),
        ("СКАНИРОВАНИЕ ПОРТОВ...", "SCANNING PORTS...", [
            f"🎃 {host} закидал сетевой стек оппонента тыквами...",
            f"☠️ Система {guest} перезапускается!",
        ], [
            f"🎃 {host} flooded the opponent's network stack with pumpkins...",
            f"☠️ {guest}'s system is rebooting!",
        ]),
    ]
    for title_ru,title_en,ru_lines,en_lines in stages:
        text = f"<b>[{t(lang,title_ru,title_en)}]</b>\n" + "\n".join(ru_lines if lang=="ru" else en_lines)
        for user_id in (match["host_id"],match["guest_id"]):
            try:
                await bot.send_message(user_id,text)
            except Exception:
                logger.info("ARENA_PRIVATE_NARRATION_UNDELIVERABLE user=%s",user_id)
        await asyncio.sleep(1)


def item_keyboard(lang: str):
    b=InlineKeyboardBuilder()
    for rp in (1,5,10):
        b.button(text=f"{rp} RP → {rp*100} 🎃", callback_data=f"arena:convert:{rp}")
    b.button(text=t(lang,"ВВЕСТИ СВОЁ","CUSTOM"),callback_data="arena:convert:custom")
    b.button(text=t(lang,"НАЗАД","BACK"),callback_data="store_menu")
    b.adjust(1)
    return b.as_markup()


@router.callback_query(F.data == "arena:items")
async def items(callback: types.CallbackQuery,state:FSMContext,lang:str):
    await callback.answer()
    try:
        points, pumpkins = await asyncio.gather(db.get_points(callback.from_user.id),balance(callback.from_user.id))
    except Exception:
        logger.exception("ARENA_ITEMS_FAILED")
        return
    await safe_edit_text(callback,screen("STORE: ITEMS",
        t(lang,"Обмен RP на игровую валюту:","Exchange RP for Arena currency:"),
        "<b>1 RP = 100 🎃</b>",
        f"RP: {(points or {}).get('total_points',0)}",
        f"🎃: {pumpkins}",
        t(lang,"Тыквы используются только в боях.","Pumpkins are only used in fights."),
    ),reply_markup=item_keyboard(lang),state=state)


@router.callback_query(F.data.startswith("arena:convert:"))
async def convert(callback:types.CallbackQuery,state:FSMContext,lang:str):
    raw=(callback.data or "").split(":")[-1]
    if raw=="custom":
        await callback.answer()
        await state.set_state(ArenaStates.convert)
        await safe_edit_text(callback,screen("ITEMS",t(lang,"Сколько RP обменять?","How many RP to convert?")),
            reply_markup=back(lang,"arena:items"),state=state)
        return
    await callback.answer()
    await _convert(callback.from_user.id,int(raw),f"click:{callback.id}",lang,callback=callback,state=state)


async def _convert(user_id:int,rp:int,key:str,lang:str,callback=None,state=None,message=None):
    if rp < 1 or rp > 10000:
        return
    try:
        result=await rpc("arena_convert",{"p_user_id":user_id,"p_rp":rp,"p_key":key})
    except Exception:
        logger.exception("ARENA_CONVERT_FAILED")
        return
    text=screen("STORE: ITEMS",
        (t(lang,"Обмен выполнен!","Conversion complete!") + f" +{rp*100} 🎃")
        if result and result.get("ok") else
        t(lang,"Недостаточно RP или ошибка обмена.","Insufficient RP or conversion error."),
        f"🎃: {result.get('balance','—')}" if result and result.get("ok") else "",
    )
    if callback:
        await safe_edit_text(callback,text,reply_markup=back(lang,"arena:items"),state=state)
    elif message:
        await message.answer(text,reply_markup=back(lang,"arena:items"))


@router.message(ArenaStates.convert, F.chat.type=="private")
async def custom_convert(message:types.Message,state:FSMContext,lang:str):
    try:
        rp=int((message.text or "").strip())
    except ValueError:
        rp=0
    if not 1<=rp<=10000:
        await message.answer(t(lang,"Введите число от 1 до 10000.","Enter a number from 1 to 10000."))
        return
    await state.clear()
    await _convert(message.from_user.id,rp,f"message:{message.chat.id}:{message.message_id}",lang,message=message)


@router.callback_query(F.data == "store_menu")
async def arena_store_hub(callback: types.CallbackQuery, state: FSMContext, lang: str):
    """The public STORE now offers Tickets and Arena ITEMS; legacy lots are not linked."""
    await callback.answer()
    points = await db.get_points(callback.from_user.id)
    try:
        pumpkins = await balance(callback.from_user.id)
    except Exception:
        pumpkins = 0
    b = InlineKeyboardBuilder()
    b.button(text=t(lang, "БИЛЕТЫ", "TICKETS"), callback_data="store_tickets")
    b.button(text="ITEMS", callback_data="arena:items")
    b.button(text=t(lang, "НАЗАД", "BACK"), callback_data="game_menu")
    b.adjust(2, 1)
    text = screen(
        "STORE",
        t(lang, "Билеты для розыгрышей и игровая валюта Арены.", "Giveaway tickets and Arena currency."),
        f"<b>RP:</b> {int((points or {}).get('total_points',0))}",
        f"<b>🎃:</b> {pumpkins}",
        t(lang, "ITEMS: 1 RP = 100 🎃. RP остаются отдельной валютой.", "ITEMS: 1 RP = 100 🎃. RP stays a separate currency."),
    )
    await safe_edit_text(callback, text, reply_markup=b.as_markup(), state=state)
