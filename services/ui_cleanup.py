from aiogram.fsm.context import FSMContext


async def remember_message(state: FSMContext, message):
    data = await state.get_data()
    messages = data.get("wallet_messages", [])
    messages.append(message.message_id)
    await state.update_data(wallet_messages=messages)


async def clear_messages(bot, chat_id: int, state: FSMContext):
    data = await state.get_data()
    messages = data.get("wallet_messages", [])

    for msg_id in messages:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass

    await state.update_data(wallet_messages=[])
