<<<<<<< SEARCH
@router.callback_query(F.data.startswith("notif_chat_"), NotificationStates.SELECTING_CHATS)
async def select_notif_chat(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()
    chat_id = int(callback.data.split("_")[-1])
    await state.update_data(chat_id=chat_id)
    await show_notification_params(callback, state, bot)
    await state.set_state(NotificationStates.CONFIRMATION)
=======
@router.callback_query(F.data.startswith("notif_chat_"), NotificationStates.SELECTING_CHATS)
async def select_notif_chat(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    try:
        await callback.answer()
    except Exception as e:
        logger.warning(f"Сбой отправки callback.answer (игнорируем): {e}")

    chat_id = int(callback.data.split("_")[-1])
    await state.update_data(chat_id=chat_id)
    await show_notification_params(callback, state, bot)
    await state.set_state(NotificationStates.CONFIRMATION)
>>>>>>> REPLACE
