import logging
from aiogram import Bot
from aiogram.enums import ParseMode
from pytonconnect.utils import Address
from database import db  # Наша база данных
from loader import tonconnect_manager, bot  # Объект бота и менеджер

logger = logging.getLogger(__name__)

async def register_tonconnect_callbacks():
    """Регистрирует хуки на события изменения состояния подключения TON Connect."""

    @tonconnect_manager.on_connect()
    async def on_wallet_connected(user_id: int, wallet_info: dict):
        try:
            # Извлекаем сырой аккаунт из метаданных моста
            raw_address = wallet_info.get("account", {}).get("address")
            if not raw_address:
                logger.error(f"No address found in wallet_info for user {user_id}")
                return

            # Форматируем адрес в стандартный пользовательский вид (User Friendly Bounceable, EQ...)
            bounceable_address = Address(raw_address).to_str(
                is_user_friendly=True,
                is_url_safe=True,
                is_bounceable=True
            )

            # 1. Записываем валидированный адрес кошелька в таблицу Supabase
            await db.link_wallet(user_id, bounceable_address)

            # 2. Формируем брендированное сообщение для отправки пользователю напрямую
            success_text = (
                f"┏┅<tg-emoji emoji-id=\"6041731551845159060\">🎉</tg-emoji>┅ <b>/ КОШЕЛЕК УСПЕШНО СВЯЗАН /</b>\n"
                f"┋\n"
                f"┣ Ваш адрес: <code>{bounceable_address}</code> успешно добавлен в базу!\n"
                f"┣ Каждые 24 часа система будет проверять баланс паков.\n"
                f"┋\n"
                f"┗┅┅┅/ Приятной игры /"
            )

            # Прямая отправка уведомления пользователю в ЛС
            await bot.send_message(
                chat_id=user_id,
                text=success_text,
                parse_mode=ParseMode.HTML
            )
            logger.info(f"Notification successfully dispatched to user {user_id}")

        except Exception as e:
            logger.error(f"Critical error during wallet connection callback execution: {e}")

    @tonconnect_manager.on_disconnect()
    async def on_wallet_disconnected(user_id: int):
        # На случай, если отключение произошло на стороне приложения кошелька
        await db.unlink_wallet(user_id)
        logger.info(f"Async remote disconnect event registered for user {user_id}")
