import logging
import html
from aiogram import Router, F, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from database import db
from utils import is_any_admin, safe_edit_text, safe_answer

logger = logging.getLogger(__name__)
router = Router()

# Главный администратор системы
MAIN_ADMIN_ID = 786080766

# Состояния для процесса обновления GIF (аналогично OTC)
class UpdateGifStates(StatesGroup):
    choosing_type = State()    # Выбор: Розыгрыши или Маркет
    waiting_for_media = State() # Ожидание самой гифки или видео

# Клавиатура выбора типа медиа
def get_gif_type_kb():
    buttons = [
        [InlineKeyboardButton(text="🎁 Giveaways", callback_data="set_type_main")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_update")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Вспомогательный метод моментального восстановления интерфейса SYSTEM CORE
def get_system_submenu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Giveaway", callback_data="create_giveaway")
    builder.button(text="History", callback_data="history_created")
    builder.button(text="OTC Market", callback_data="otc_market")
    builder.button(text="Notifications", callback_data="manage_notifications")
    builder.button(text="Update GIF", callback_data="admin_update_gif")
    builder.button(text='🏘 <tg-emoji emoji-id="5257963315258204021">🏘</tg-emoji> Back to Main Menu', callback_data="main_menu")
    builder.adjust(2)
    return builder.as_markup()

# 2. Обработка нажатия на кнопку "Update GIF" из главного меню
@router.callback_query(F.data == "admin_update_gif")
async def start_gif_update(callback: types.CallbackQuery, state: FSMContext):
    # Жесткая проверка ID главного администратора
    if callback.from_user.id != MAIN_ADMIN_ID:
        await callback.answer("❌ Access denied. Only for the main administrator.", show_alert=True)
        return

    await state.set_state(UpdateGifStates.choosing_type)
    
    await safe_edit_text(
        callback,
        "📝 <b>GIF Management</b>\n\nSelect which section's animation you want to update:",
        reply_markup=get_gif_type_kb(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

# 3. Выбор типа (куда ставим GIF)
@router.callback_query(UpdateGifStates.choosing_type, F.data.startswith("set_type_"))
async def process_type_choice(callback: types.CallbackQuery, state: FSMContext):
    gif_type = callback.data.replace("set_type_", "")
    await state.update_data(chosen_type=gif_type)
    
    await state.set_state(UpdateGifStates.waiting_for_media)
    
    label = "Giveaways"
    await safe_edit_text(
        callback,
        f"🎬 <b>Upload Media</b>\n\nPlease send a <b>GIF</b> or <b>Video</b> for the <b>{label}</b> section.\n\n"
        "<blockquote>Note: Telegram might convert large GIFs to videos, but I will handle both.</blockquote>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_update")]]),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

# 4. Прием и сохранение файла (ловим анимации и видео)
@router.message(UpdateGifStates.waiting_for_media, F.animation | F.video)
async def process_gif_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    gif_type = data.get("chosen_type")
    
    # Ключ для базы данных
    setting_key = "main_gif" if gif_type == "main" else "otc_gif"
    
    # Получаем file_id в зависимости от типа сообщения
    file_id = message.animation.file_id if message.animation else message.video.file_id

    # Генерация навигационной клавиатуры для экрана успешного завершения
    nav_builder = InlineKeyboardBuilder()
    nav_builder.button(text="⚙️ System Core", callback_data="system_submenu")
    nav_builder.button(text='🏘 <tg-emoji emoji-id="5257963315258204021">🏘</tg-emoji> Main Menu', callback_data="main_menu")
    nav_builder.adjust(1)

    try:
        # Сохранение в Supabase
        await db.update_setting(setting_key, file_id)
        
        success_text = (
            f"┏┅<tg-emoji emoji-id=\"6041731551845159060\">🎉</tg-emoji>┅ <b>/ CONFIGURATION UPDATED /</b>\n"
            f"┋\n"
            f"┣ <blockquote>The new media asset configuration for <code>{setting_key}</code> has been successfully pushed to the core repository and is now live.</blockquote>\n"
            f"┋\n"
            f"┗┅┅┅/ System Synchronized /"
        )

        await safe_answer(
            message,
            success_text,
            reply_markup=nav_builder.as_markup(),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Admin {message.from_user.id} updated GIF for {setting_key}")
    except Exception as e:
        logger.error(f"Error saving GIF: {e}")
        await safe_answer(
            message,
            "❌ <b>Database Error</b>\nFailed to save the new file ID.",
            reply_markup=nav_builder.as_markup()
        )
    
    await state.clear()

# 5. Обработка отмены (Перехватывает любой стейт процесса и возвращает в System Core)
@router.callback_query(F.data == "cancel_update", StateFilter("*"))
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("🚫 Update cancelled")

    # Прямая бесшовная сборка и рендеринг исходного меню SYSTEM CORE (вместо пустого текста)
    system_text = (
        "┏┅<tg-emoji emoji-id=\"5258096772776991776\">⚙️</tg-emoji>┅ <b>/ SYSTEM CORE /</b>\n"
        "┋\n"
        "┣ <blockquote>Authorized executive dashboard. Legacy operational privileges and holder infrastructure subroutines are fully online.</blockquote>\n"
        "┋\n"
        "┗┅┅┅/ #NOTAPES /"
    )

    await safe_edit_text(
        callback,
        system_text,
        reply_markup=get_system_submenu_keyboard(),
        parse_mode=ParseMode.HTML
    )
