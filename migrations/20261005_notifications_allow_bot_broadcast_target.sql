alter table public.notifications
    drop constraint if exists notifications_chat_id_fkey;

comment on column public.notifications.chat_id is
    'Telegram chat/channel id. Value 0 is reserved for in-bot broadcast to all users.';
