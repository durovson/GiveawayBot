import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from database import db
from utils import is_any_admin, safe_edit_text, safe_answer

logger = logging.getLogger(__name__)
router = Router()

# 1. Состояния для процесса обновления GIF (аналогично OTC)
class UpdateGifStates(StatesGroup):
    choosing_type = State()    # Выбор: Розыгрыши или Маркет
    waiting_for_media = State() # Ожидание самой гифки или видео

# Клавиатура выбора типа медиа
def get_gif_type_kb():
    buttons = [
        [InlineKeyboardButton(text="Giveaways", callback_data="set_type_main", icon_custom_emoji_id="6032644646587338669")],
        [InlineKeyboardButton(text="Cancel", callback_data="cancel_update", icon_custom_emoji_id="5877629862306385808")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# 2. Обработка нажатия на кнопку "Update GIF" из главного меню
@router.callback_query(F.data == "admin_update_gif")
async def start_gif_update(callback: types.CallbackQuery, state: FSMContext):
    # Жесткая проверка ID
    if callback.from_user.id != 786080766:
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
        "<i>Note: Telegram might convert large GIFs to videos, but I will handle both.</i>",
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
    setting_key = "main_gif"
    
    # Получаем file_id в зависимости от типа сообщения
    file_id = message.animation.file_id if message.animation else message.video.file_id

    try:
        # Сохранение в Supabase
        await db.update_setting(setting_key, file_id)
        
        await safe_answer(
            message,
            f"✅ <b>Successfully updated!</b>\n\nThe new media for <code>{setting_key}</code> has been saved and is now active.",
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Admin {message.from_user.id} updated GIF for {setting_key}")
    except Exception as e:
        logger.error(f"Error saving GIF: {e}")
        await safe_answer(message, "❌ <b>Database Error</b>\nFailed to save the new file ID.")
    
    await state.clear()

# 5. Обработка отмены
@router.callback_query(F.data == "cancel_update")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit_text(callback, "🚫 Update cancelled. Returning to main menu...")
    await callback.answer()
