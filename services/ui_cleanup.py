import logging
from enum import Enum
from aiogram import types
from aiogram.fsm.context import FSMContext
import loader

logger = logging.getLogger(__name__)

class MessageCategory(str, Enum):
    TEMPORARY = "temporary"
    PERSISTENT = "persistent"
    SYSTEM = "system"

async def _get_migrated_data(state: FSMContext) -> dict:
    """Get UI messages from state and migrate if it's in the old format."""
    data = await state.get_data()
    stored = data.get("ui_messages", {})

    # If legacy list format is detected, migrate it to TEMPORARY category
    if isinstance(stored, list):
        logger.info("Migrating legacy UI message list to new format")
        new_data = {cat.value: [] for cat in MessageCategory}
        for msg_id in stored:
            new_data[MessageCategory.TEMPORARY.value].append({
                "message_id": msg_id,
                "chat_id": None
            })
        await state.update_data(ui_messages=new_data)
        return new_data

    if not isinstance(stored, dict):
        stored = {cat.value: [] for cat in MessageCategory}
        await state.update_data(ui_messages=stored)

    return stored

async def remember_message(state: FSMContext, message: types.Message, category: MessageCategory = MessageCategory.TEMPORARY):
    """Save message ID and chat ID to state for later cleanup."""
    if not message:
        return

    ui_messages = await _get_migrated_data(state)
    cat_key = category.value

    if cat_key not in ui_messages:
        ui_messages[cat_key] = []

    # Check if already present
    exists = any(m.get("message_id") == message.message_id and m.get("chat_id") == message.chat.id
                 for m in ui_messages[cat_key])

    if not exists:
        ui_messages[cat_key].append({
            "message_id": message.message_id,
            "chat_id": message.chat.id
        })
        await state.update_data(ui_messages=ui_messages)
        logger.debug("Remembered message %s in chat %s (category: %s)",
                     message.message_id, message.chat.id, cat_key)

async def clear_messages(chat_id: int, state: FSMContext, category: MessageCategory = None):
    """Delete remembered messages. If category is None, clear ALL categories."""
    ui_messages = await _get_migrated_data(state)

    # Identify which categories to clear
    if category:
        categories_to_clear = [category.value]
    else:
        categories_to_clear = [c.value for c in MessageCategory]

    for cat in categories_to_clear:
        messages = ui_messages.get(cat, [])
        for msg in messages:
            target_chat_id = msg.get("chat_id") or chat_id
            msg_id = msg.get("message_id")

            if not msg_id:
                continue

            try:
                await loader.bot.delete_message(target_chat_id, msg_id)
            except Exception:
                pass

        ui_messages[cat] = []

    await state.update_data(ui_messages=ui_messages)
    logger.debug("Cleared messages for categories: %s", categories_to_clear)
