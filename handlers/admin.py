import logging
import html
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from database import db
from utils import is_any_admin, safe_edit_text, safe_answer
from services.localization import get_locale
from config import PANEL_ADMIN_IDS
from services.arena_config import target_chat, save_target_chat

logger = logging.getLogger(__name__)
router = Router()


def ru(texts):
    return texts.get('update_gif_btn') != 'UPDATE GIF'


async def allowed(event, texts):
    if event.from_user.id in PANEL_ADMIN_IDS and (
        event.message.chat.type == 'private' if isinstance(event, types.CallbackQuery) else event.chat.type == 'private'
    ):
        return True
    if isinstance(event, types.CallbackQuery):
        await event.answer(texts['admin_only_alert'], show_alert=True)
    return False


class PanelStates(StatesGroup):
    chat = State()


@router.callback_query(F.data == 'admin_panel')
async def panel(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not await allowed(callback, texts):
        return
    await state.clear()
    buttons = [
        [InlineKeyboardButton(text=texts['update_gif_btn'], callback_data='admin_update_gif')],
        [InlineKeyboardButton(text='ЧАТ АРЕНЫ' if ru(texts) else 'ARENA CHAT', callback_data='panel_arena')],
        [InlineKeyboardButton(text='НАЗАД' if ru(texts) else 'BACK', callback_data='main_menu')],
    ]
    await safe_edit_text(callback, '┏┅┅/ <b>PANEL</b> /\n┋\n┗┅┅┅/ Select an option /',
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == 'panel_arena')
async def arena_chat_menu(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not await allowed(callback, texts):
        return
    try:
        current = await target_chat(callback.bot)
        chats = await db.get_tracked_chats()
        choices = {str(c['chat_id']): c['title'] for c in chats if c.get('chat_type') in {'group', 'supergroup'}}
        await state.set_state(PanelStates.chat)
        await state.update_data(arena_choices=choices)
        await show_chats(callback, choices, current, texts, 0)
    except Exception:
        logger.exception('PANEL_CHAT_LIST_FAILED')
        await callback.answer(texts['admin_db_error'], show_alert=True)


async def show_chats(callback, choices, current, texts, page):
    items = list(choices.items())
    buttons = [[InlineKeyboardButton(text=str(title or cid)[:60], callback_data=f'panel_chat:{cid}')]
               for cid, title in items[page*8:page*8+8]]
    nav = []
    if page:
        nav.append(InlineKeyboardButton(text='←', callback_data=f'panel_page:{page-1}'))
    if (page+1)*8 < len(items):
        nav.append(InlineKeyboardButton(text='→', callback_data=f'panel_page:{page+1}'))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text='PANEL', callback_data='admin_panel')])
    text = (f'┏┅┅/ <b>ARENA CHAT</b> /\n┋\n┣ {current or "—"}\n┋\n┣ ' +
            ('Выберите чат или отправьте его ID / @username.' if ru(texts) else 'Select a chat or send its ID / @username.') +
            '\n┗┅┅┅/ Select an option /')
    await safe_edit_text(callback, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(PanelStates.chat, F.data.startswith('panel_page:'))
async def chat_page(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not await allowed(callback, texts):
        return
    choices = (await state.get_data()).get('arena_choices', {})
    value = callback.data.split(':')[-1]
    if not value.isdigit() or not 0 <= int(value) <= max(0, (len(choices)-1)//8):
        await callback.answer()
        return
    await show_chats(callback, choices, await target_chat(callback.bot), texts, int(value))


async def select_chat(bot, reference):
    chat = await bot.get_chat(reference)
    if chat.type not in {'group', 'supergroup'}:
        raise ValueError('Not a group')
    member = await bot.get_chat_member(chat.id, bot.id)
    if member.status not in {'creator', 'administrator', 'member'} and not (
        member.status == 'restricted' and member.is_member and member.can_send_messages):
        raise ValueError('Bot cannot send messages')
    if member.status == 'member' and chat.permissions and not chat.permissions.can_send_messages:
        raise ValueError('Chat is read-only')
    await save_target_chat(bot, chat.id)
    return chat


async def apply_chat(event, state, texts, reference):
    try:
        chat = await select_chat(event.bot, reference)
    except Exception:
        logger.exception('PANEL_CHAT_SELECTION_FAILED')
        text = ('Не удалось сохранить чат. Проверьте ID, участие бота и право отправлять сообщения.' if ru(texts)
                else 'Could not save the chat. Check its ID, bot membership and permission to send messages.')
        if isinstance(event, types.CallbackQuery):
            await event.answer(text, show_alert=True)
        else:
            await safe_answer(event, text)
        return
    await state.clear()
    text = ('Чат арены сохранён' if ru(texts) else 'Arena chat saved') + f': <b>{html.escape(chat.title or str(chat.id))}</b> ({chat.id})'
    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='PANEL', callback_data='admin_panel')]])
    if isinstance(event, types.CallbackQuery):
        await safe_edit_text(event, text, reply_markup=markup)
        await event.answer()
    else:
        await safe_answer(event, text, reply_markup=markup)


@router.callback_query(PanelStates.chat, F.data.startswith('panel_chat:'))
async def choose_chat(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not await allowed(callback, texts):
        return
    cid = callback.data.split(':')[-1]
    if cid not in (await state.get_data()).get('arena_choices', {}):
        await callback.answer(texts['admin_only_alert'], show_alert=True)
        return
    await apply_chat(callback, state, texts, int(cid))


@router.message(PanelStates.chat)
async def enter_chat(message: types.Message, state: FSMContext, texts: dict):
    if not await allowed(message, texts):
        return
    value = (message.text or '').strip()
    if not (value.startswith('@') or value.lstrip('-').isdigit()):
        await safe_answer(message, 'ID / @username')
        return
    await apply_chat(message, state, texts, int(value) if value.lstrip('-').isdigit() else value)

# 1. Состояния для процесса обновления GIF (аналогично OTC)
class UpdateGifStates(StatesGroup):
    choosing_type = State()    # Выбор: Розыгрыши или Маркет
    waiting_for_media = State() # Ожидание самой гифки или видео

# Клавиатура выбора типа медиа
async def get_gif_type_kb(user_id: int, texts: dict):
    # texts from middleware
    buttons = [
        [InlineKeyboardButton(text=texts["admin_giveaways_label"], callback_data="set_type_main", icon_custom_emoji_id="6032644646587338669")],
        [InlineKeyboardButton(text=texts["admin_cancel_btn"], callback_data="cancel_update", icon_custom_emoji_id="5877629862306385808")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# 2. Обработка нажатия на кнопку "Update GIF" из главного меню
@router.callback_query(F.data == "admin_update_gif")
async def start_gif_update(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    user_id = callback.from_user.id
    # texts from middleware
    # Жесткая проверка ID
    if not await allowed(callback, texts):
        return

    await state.set_state(UpdateGifStates.choosing_type)
    
    await safe_edit_text(
        callback,
        texts["admin_gif_mgmt_title"],
        reply_markup=await get_gif_type_kb(user_id, texts),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

# 3. Выбор типа (куда ставим GIF)
@router.callback_query(UpdateGifStates.choosing_type, F.data.startswith("set_type_"))
async def process_type_choice(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not await allowed(callback, texts):
        return
    user_id = callback.from_user.id
    # texts from middleware
    gif_type = callback.data.replace("set_type_", "")
    await state.update_data(chosen_type=gif_type)
    
    await state.set_state(UpdateGifStates.waiting_for_media)
    
    label = texts["admin_giveaways_label"]
    await safe_edit_text(
        callback,
        texts["admin_upload_media"].format(label=label),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ " + texts["admin_cancel_btn"], callback_data="cancel_update")]]),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

# 4. Прием и сохранение файла (ловим анимации и видео)
@router.message(UpdateGifStates.waiting_for_media, F.animation | F.video)
async def process_gif_file(message: types.Message, state: FSMContext, texts: dict):
    if not await allowed(message, texts):
        return
    user_id = message.from_user.id
    # texts from middleware
    data = await state.get_data()
    gif_type = data.get("chosen_type")
    
    # Ключ для базы данных
    setting_key = "main_gif"
    
    # Получаем file_id в зависимости от типа сообщения
    file_id = message.animation.file_id if message.animation else message.video.file_id

    try:
        # Сохранение в Supabase
        if db.client is None:
            raise RuntimeError('Database unavailable')
        await db.client.table('settings').upsert({'key': setting_key, 'value': file_id}).execute()
        
        await safe_answer(
            message,
            texts["admin_update_success"].format(key=setting_key),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Admin {message.from_user.id} updated GIF for {setting_key}")
    except Exception as e:
        logger.error(f"Error saving GIF: {e}")
        await safe_answer(message, texts["admin_db_error"], parse_mode=ParseMode.HTML)
    
    await state.clear()

# 5. Обработка отмены
@router.callback_query(F.data == "cancel_update")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext, texts: dict):
    if not await allowed(callback, texts):
        return
    user_id = callback.from_user.id
    # texts from middleware
    await state.clear()
    await safe_edit_text(callback, texts["admin_update_cancelled"])
    await callback.answer()
