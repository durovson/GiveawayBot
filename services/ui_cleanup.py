import logging
from aiogram import types
from aiogram.fsm.context import FSMContext
from loader import bot

logger = logging.getLogger(__name__)

async def remember_message(state: FSMContext, message: types.Message):
    """Save message ID to state for later cleanup."""
    if not message:
        return
    data = await state.get_data()
    messages = data.get("ui_messages", [])
    if message.message_id not in messages:
        messages.append(message.message_id)
        await state.update_data(ui_messages=messages)

async def clear_messages(chat_id: int, state: FSMContext):
    """Delete all remembered messages and clear the list in state."""
    data = await state.get_data()
    messages = data.get("ui_messages", [])
    for msg_id in messages:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    await state.update_data(ui_messages=[])
