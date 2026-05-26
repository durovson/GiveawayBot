import asyncio
import logging
from aiogram import F, types
from aiogram.types import ChatMemberUpdated
from aiogram.enums import ParseMode
from loader import bot, dp
from database import db
from web_server import start_keep_alive_async
from utils import safe_bot_send_message

# Import handlers
from handlers.main_menu import router as main_menu_router
from handlers.giveaway_creation import router as creation_router
from handlers.participants import router as participants_router
from handlers.otc_market import router as otc_market_router
from handlers.admin import router as admin_router
from handlers.notifications import router as notifications_router
from handlers.game_menu import router as game_menu_router
from handlers.wallet import router as wallet_router

@dp.my_chat_member()
async def on_my_chat_member_update(update: ChatMemberUpdated):
    if update.new_chat_member.status in ["administrator", "member"]:
        chat_id = update.chat.id
        is_tracked = await db.is_chat_tracked(chat_id)
        await db.track_chat(chat_id, update.chat.title, update.chat.type)

        if not is_tracked and update.new_chat_member.status == "administrator":
            try:
                admin_id = update.from_user.id
                await bot.send_message(
                    admin_id,
                    "<tg-emoji emoji-id=\"5273741156792951269\">🤓</tg-emoji> <b>The bot is ready to work!</b>\n\n"
                    "<blockquote>The group has been automatically registered. Now you can create giveaways via private messages with the bot.</blockquote>\n\n"
                    "<i>If the group does not appear in the list, use the command /setup</i>",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass

# Registration
dp.include_router(admin_router)
dp.include_router(notifications_router)
dp.include_router(main_menu_router)
dp.include_router(game_menu_router)
dp.include_router(wallet_router)
dp.include_router(creation_router)
dp.include_router(participants_router)
dp.include_router(otc_market_router)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    await db.connect()
    background_tasks = []

    from handlers.completion import check_timed_giveaways, check_periodic_notifications
    background_tasks.append(asyncio.create_task(check_timed_giveaways(bot), name="check_timed_giveaways"))
    background_tasks.append(asyncio.create_task(check_periodic_notifications(bot), name="check_periodic_notifications"))

    from tasks.sync_holders import daily_sync_task
    background_tasks.append(asyncio.create_task(daily_sync_task(bot), name="daily_sync_task"))

    try:
        await start_keep_alive_async(bot, dp)
    finally:
        for task in background_tasks:
            task.cancel()
        await asyncio.gather(*background_tasks, return_exceptions=True)
        await bot.session.close()
        logger.info("Shutdown completed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")
