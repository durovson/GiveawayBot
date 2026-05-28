import asyncio
import logging
from aiogram import Bot, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ChatMemberUpdated
from aiogram.enums import ParseMode

import loader
from loader import dp, bg_tasks
from database import db
from web_server import start_keep_alive
from services.ton_connect_service import TonConnectService
from services.leaderboard import LeaderboardService

# Import handlers
from handlers.main_menu import router as main_menu_router
from handlers.giveaway_creation import router as creation_router
from handlers.participants import router as participants_router
from handlers.otc_market import router as otc_market_router
from handlers.admin import router as admin_router
from handlers.notifications import router as notifications_router
from handlers.game_menu import router as game_menu_router
from handlers.wallet import router as wallet_router

# Logging Filter to suppress noisy network stack traces
class NetworkErrorFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        if "Connection reset by peer" in msg:
            # Suppress stack trace for this specific network error
            record.exc_info = None
            record.stack_info = None
        return True

logging.basicConfig(level=logging.INFO)
# Apply filter to the main aiogram dispatcher logger
logging.getLogger("aiogram.dispatcher").addFilter(NetworkErrorFilter())

@dp.my_chat_member()
async def on_my_chat_member_update(update: ChatMemberUpdated):
    if update.new_chat_member.status in ["administrator", "member"]:
        chat_id = update.chat.id
        is_tracked = await db.is_chat_tracked(chat_id)
        await db.track_chat(chat_id, update.chat.title, update.chat.type)

        if not is_tracked and update.new_chat_member.status == "administrator":
            try:
                admin_id = update.from_user.id
                await loader.bot.send_message(
                    admin_id,
                    "<tg-emoji emoji-id=\"5273741156792951269\">🤓</tg-emoji> <b>The bot is ready to work!</b>\n\n"
                    "<blockquote>The group has been automatically registered. Now you can create giveaways via private messages with the bot.</blockquote>\n\n"
                    "<i>If the group does not appear in the list, use the command /setup</i>"
                )
            except Exception:
                pass

# Registration
dp.include_router(admin_router)
dp.include_router(notifications_router)
dp.include_router(game_menu_router)
dp.include_router(wallet_router)
dp.include_router(main_menu_router)
dp.include_router(creation_router)
dp.include_router(participants_router)
dp.include_router(otc_market_router)

async def initial_sync():
    """Perform initial sync of holders before starting polling."""
    from tasks.sync_holders import fetch_holders
    logger = logging.getLogger(__name__)
    logger.info("Performing initial holders sync...")
    try:
        cached = await fetch_holders()
        holders = cached.get("holders", []) if isinstance(cached, dict) else []
        if holders:
            await db.save_snapshot(holders)
            LeaderboardService.invalidate_cache()
            logger.info("Initial sync complete: %s holders saved", len(holders))
        else:
            logger.warning("Initial sync returned no holders")
    except Exception:
        logger.exception("Initial sync failed")

async def main():
    # Initialize the bot without custom session - aiogram handles it internally
    loader.bot = Bot(
        token=loader.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    start_keep_alive()
    await db.connect()

    # Perform initial sync
    await initial_sync()

    # Start checking timed giveaways
    from handlers.completion import check_timed_giveaways
    t1 = asyncio.create_task(check_timed_giveaways(loader.bot))
    bg_tasks.add(t1)
    t1.add_done_callback(bg_tasks.discard)

    from handlers.completion import check_periodic_notifications
    t2 = asyncio.create_task(check_periodic_notifications(loader.bot))
    bg_tasks.add(t2)
    t2.add_done_callback(bg_tasks.discard)

    # Start daily sync task
    from tasks.sync_holders import daily_sync_task
    t3 = asyncio.create_task(daily_sync_task(loader.bot))
    bg_tasks.add(t3)
    t3.add_done_callback(bg_tasks.discard)

    # Polling retry loop with exponential backoff
    backoff = 1
    max_backoff = 60

    while True:
        try:
            await dp.start_polling(loader.bot, drop_pending_updates=True)
            break # Successful shutdown
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                break

            logging.error(f"Polling error: {e}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    logging.info("Shutting down...")

    # 1. Cancel all background tasks
    all_tasks = bg_tasks
    for task in all_tasks:
        task.cancel()
    if all_tasks:
        await asyncio.gather(*all_tasks, return_exceptions=True)

    # 2. Close bot session
    if loader.bot.session:
        await loader.bot.session.close()

    await asyncio.sleep(0.5)
    logging.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped by user")
