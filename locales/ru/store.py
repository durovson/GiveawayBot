TEXTS = {
    "store_hub_title": (
        "┏┅⋐[ ◍ _◍ ]っ┅<tg-emoji emoji-id=\"5983399041197675256\">🏪</tg-emoji>┅/ <b>STORE HUB</b> /\n"
        "┋\n┣ <b>Ваши RP:</b> {rp}\n┣ <b>Активные билеты:</b> {tickets}\n┋\n"
        "┣ [1] Билеты удачи\n┣ [2] Лоты и награды\n┋\n"
        "┗┅┅┅/ <b>Выберите раздел</b> /"
    ),
    "store_tickets_btn": "БИЛЕТЫ",
    "store_lots_btn": "ЛОТЫ",
    "store_admin_btn": "УПРАВЛЕНИЕ STORE",
    "store_back_btn": "НАЗАД",
    "store_lots_title": (
        "┏┅⋐[ ◍ _◍ ]っ┅<tg-emoji emoji-id=\"5235695112419303615\">🎁</tg-emoji>┅/ <b>ЛОТЫ</b> /\n"
        "┋\n┣ <b>Ваши RP:</b> {rp}\n┋\n{content}\n┋\n"
        "┗┅┅┅/ <b>Выберите лот</b> /"
    ),
    "store_lots_hint": "┣ Доступные награды публикуются администрацией.",
    "store_lots_empty": "┣ Активных лотов пока нет.",
    "store_lot_button": "{title} · {price} RP · {remaining} шт.",
    "store_lot_detail": (
        "┏┅<tg-emoji emoji-id=\"5235695112419303615\">🎁</tg-emoji>┅/ <b>{title}</b> /\n"
        "┋\n┣ {description}\n┋\n┣ <b>Цена:</b> {price} RP\n"
        "┣ <b>Осталось:</b> {remaining} / {total}\n┋\n"
        "┗┅┅┅/ <b>Выберите действие</b> /"
    ),
    "store_no_description": "Описание не указано.",
    "store_buy_lot_btn": "КУПИТЬ ЗА {price} RP",
    "store_open_media_btn": "ОТКРЫТЬ ИЗОБРАЖЕНИЕ",
    "store_lot_unavailable": "❌ Лот больше недоступен.",
    "store_lot_not_enough_rp": "❌ Недостаточно RP для покупки этого лота.",
    "store_lot_sold_out": "❌ Лот уже распродан.",
    "store_lot_limit_reached": "❌ Вы достигли лимита покупок этого лота.",
    "store_purchase_error": "❌ Покупка не выполнена. Попробуйте ещё раз.",
    "store_lot_purchase_success": "✅ Покупка #{purchase_id} оплачена! Администратор выполнит выдачу награды.",
    "store_lot_ticket_success": "✅ Покупка #{purchase_id} завершена! Начислено билетов: {tickets}.",
    "store_order_fulfilled": "✅ <b>Заказ #{purchase_id} выполнен.</b> Награда выдана администратором.",
    "store_admin_title": (
        "┏┅<tg-emoji emoji-id=\"5258096772776991776\">⚙️</tg-emoji>┅/ <b>STORE ADMIN</b> /\n"
        "┋\n┣ Создавайте лоты и обрабатывайте выдачу наград.\n┋\n"
        "┗┅┅┅/ <b>Выберите действие</b> /"
    ),
    "store_admin_create_btn": "СОЗДАТЬ ЛОТ",
    "store_admin_lots_btn": "ВСЕ ЛОТЫ",
    "store_admin_orders_btn": "ЗАКАЗЫ НА ВЫДАЧУ",
    "store_admin_enter_title": "┏┅/ <b>НАЗВАНИЕ ЛОТА</b> /\n┗┅┅┅/ Введите название до 120 символов /",
    "store_admin_enter_description": "┏┅/ <b>ОПИСАНИЕ</b> /\n┗┅┅┅/ Введите описание или <code>-</code> /",
    "store_admin_enter_price": "┏┅/ <b>ЦЕНА</b> /\n┗┅┅┅/ Введите цену в RP целым числом /",
    "store_admin_enter_quantity": "┏┅/ <b>КОЛИЧЕСТВО</b> /\n┗┅┅┅/ Введите доступное количество /",
    "store_admin_enter_image": "┏┅/ <b>ИЗОБРАЖЕНИЕ</b> /\n┗┅┅┅/ Введите http(s)-ссылку или <code>-</code> /",
    "store_admin_select_reward": "┏┅/ <b>ТИП НАГРАДЫ</b> /\n┗┅┅┅/ Выберите тип выдачи /",
    "store_reward_manual_btn": "РУЧНАЯ",
    "store_reward_ticket_btn": "БИЛЕТЫ",
    "store_reward_role_btn": "РОЛЬ",
    "store_reward_channel_btn": "ДОСТУП В КАНАЛ",
    "store_reward_sticker_btn": "СТИКЕР",
    "store_reward_nft_btn": "NFT",
    "store_reward_physical_btn": "ФИЗИЧЕСКИЙ ПРИЗ",
    "store_reward_custom_btn": "ДРУГОЕ",
    "store_admin_enter_ticket_reward": "┏┅/ <b>БИЛЕТЫ</b> /\n┗┅┅┅/ Сколько билетов начислить автоматически? /",
    "store_admin_enter_reward_payload": "┏┅/ <b>ИНСТРУКЦИЯ ВЫДАЧИ</b> /\n┗┅┅┅/ Опишите, что должен выдать администратор /",
    "store_admin_enter_limit": "┏┅/ <b>ЛИМИТ НА ПОЛЬЗОВАТЕЛЯ</b> /\n┗┅┅┅/ Введите количество покупок /",
    "store_admin_invalid_number": "❌ Введите положительное целое число.",
    "store_admin_invalid_url": "❌ Нужна ссылка http(s) или символ -.",
    "store_admin_preview": (
        "┏┅/ <b>ПРЕДПРОСМОТР ЛОТА</b> /\n┣ <b>{title}</b>\n┣ {description}\n"
        "┣ Цена: {price} RP\n┣ Количество: {quantity}\n"
        "┣ Награда: {reward}\n┣ Лимит: {limit}\n┗┅┅┅/ <b>Опубликовать?</b> /"
    ),
    "store_admin_publish_btn": "ОПУБЛИКОВАТЬ",
    "store_admin_created_alert": "✅ Лот создан и опубликован.",
    "store_admin_create_error": "❌ Не удалось сохранить изменения.",
    "store_admin_lots_title": "┏┅/ <b>ВСЕ ЛОТЫ</b> /\n┣ Найдено: {count}\n┗┅┅┅/ Выберите лот /",
    "store_admin_lot_detail": (
        "┏┅/ <b>ЛОТ #{id}</b> /\n┣ {title}\n┣ Статус: {status}\n"
        "┣ Цена: {price} RP\n┣ Продано: {sold}/{total}\n┗┅┅┅/ Выберите действие /"
    ),
    "store_admin_disable_btn": "ОТКЛЮЧИТЬ",
    "store_admin_activate_btn": "АКТИВИРОВАТЬ",
    "store_admin_status_saved": "✅ Статус обновлён.",
    "store_admin_orders_title": "┏┅/ <b>ЗАКАЗЫ НА ВЫДАЧУ</b> /\n{content}\n┗┅┅┅/ Выберите заказ /",
    "store_admin_no_orders": "┣ Новых заказов нет.",
    "store_admin_orders_hint": "┣ Нажатие подтверждает выдачу награды.",
    "store_admin_order_detail": (
        "┏┅/ <b>ЗАКАЗ #{id}</b> /\n┣ Лот: {title}\n┣ Покупатель: {user} (<code>{user_id}</code>)\n"
        "┣ Оплачено: {price} RP\n┣ Тип: {reward_type}\n┣ Инструкция: {instructions}\n"
        "┗┅┅┅/ <b>Подтвердите фактическую выдачу</b> /"
    ),
    "store_admin_confirm_fulfill_btn": "НАГРАДА ВЫДАНА",
    "store_admin_fulfilled": "✅ Заказ отмечен выполненным.",
    "store_admin_fulfill_error": "❌ Заказ уже обработан или недоступен.",
}
