import logging
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from database import db
from utils import is_any_admin, safe_edit_text, safe_answer
from services.localization import get_locale

logger = logging.getLogger(__name__)
router = Router()

# 1. Состояния для процесса обновления GIF (аналогично OTC)
class UpdateGifStates(StatesGroup):
    choosing_type = State()    # Выбор: Розыгрыши или Маркет
    waiting_for_media = State() # Ожидание самой гифки или видео

# Клавиатура выбора типа медиа
async def get_gif_type_kb(user_id: int):
    texts = await get_locale(user_id)
    buttons = [
        [InlineKeyboardButton(text=texts["giveaways_label"], callback_data="set_type_main", icon_custom_emoji_id="6032644646587338669")],
        [InlineKeyboardButton(text=texts["cancel_btn"], callback_data="cancel_update", icon_custom_emoji_id="5877629862306385808")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# 2. Обработка нажатия на кнопку "Update GIF" из главного меню
@router.callback_query(F.data == "admin_update_gif")
async def start_gif_update(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    # Жесткая проверка ID
    if user_id != 786080766:
        await callback.answer(texts["admin_only_alert"], show_alert=True)
        return

    await state.set_state(UpdateGifStates.choosing_type)
    
    await safe_edit_text(
        callback,
        texts["gif_mgmt_title"],
        reply_markup=await get_gif_type_kb(user_id),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

# 3. Выбор типа (куда ставим GIF)
@router.callback_query(UpdateGifStates.choosing_type, F.data.startswith("set_type_"))
async def process_type_choice(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    gif_type = callback.data.replace("set_type_", "")
    await state.update_data(chosen_type=gif_type)
    
    await state.set_state(UpdateGifStates.waiting_for_media)
    
    label = texts["giveaways_label"]
    await safe_edit_text(
        callback,
        texts["upload_media"].format(label=label),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ " + texts["cancel_btn"], callback_data="cancel_update")]]),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

# 4. Прием и сохранение файла (ловим анимации и видео)
@router.message(UpdateGifStates.waiting_for_media, F.animation | F.video)
async def process_gif_file(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    texts = await get_locale(user_id)
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
            texts["update_success"].format(key=setting_key),
            parse_mode=ParseMode.HTML
        )
        logger.info(f"Admin {message.from_user.id} updated GIF for {setting_key}")
    except Exception as e:
        logger.error(f"Error saving GIF: {e}")
        await safe_answer(message, texts["db_error"], parse_mode=ParseMode.HTML)
    
    await state.clear()

# 5. Обработка отмены
@router.callback_query(F.data == "cancel_update")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    texts = await get_locale(user_id)
    await state.clear()
    await safe_edit_text(callback, texts["update_cancelled"])
    await callback.answer()
