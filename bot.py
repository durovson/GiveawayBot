import asyncio
import logging
import aiohttp
import time
from aiogram import F, types
from aiogram.types import ChatMemberUpdated
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError

import loader
from loader import bot, dp, bg_tasks, wallet_tasks
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
        if "TelegramNetworkError" in msg or "Connection reset by peer" in msg:
            # Suppress stack trace for these common network resets
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
    # Initialize shared session with robust settings
    connector = aiohttp.TCPConnector(limit=100, enable_cleanup_closed=True)
    timeout = aiohttp.ClientTimeout(total=60)
    loader.http_session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    start_keep_alive()
    await db.connect()

    # Perform initial sync
    await initial_sync()

    # Start checking timed giveaways
    from handlers.completion import check_timed_giveaways
    t1 = asyncio.create_task(check_timed_giveaways(bot))
    bg_tasks.add(t1)
    t1.add_done_callback(bg_tasks.discard)

    from handlers.completion import check_periodic_notifications
    t2 = asyncio.create_task(check_periodic_notifications(bot))
    bg_tasks.add(t2)
    t2.add_done_callback(bg_tasks.discard)

    # Start daily sync task
    from tasks.sync_holders import daily_sync_task
    t3 = asyncio.create_task(daily_sync_task(bot))
    bg_tasks.add(t3)
    t3.add_done_callback(bg_tasks.discard)

    # Polling retry loop with exponential backoff
    backoff = 1
    max_backoff = 60

    while True:
        try:
            await dp.start_polling(bot, drop_pending_updates=True)
            break # Successful shutdown
        except Exception as e:
            if isinstance(e, asyncio.CancelledError):
                break

            logging.error(f"Polling error: {e}. Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)
        finally:
            # If we exited the polling but not the loop, we might want to ensure some cleanup
            # however aiogram usually cleans up its own polling state.
            pass

    logging.info("Shutting down...")

    # 1. Cancel all background tasks
    all_tasks = bg_tasks.union(wallet_tasks)
    for task in all_tasks:
        task.cancel()
    if all_tasks:
        await asyncio.gather(*all_tasks, return_exceptions=True)

    # 2. Close shared HTTP session
    if loader.http_session:
        await loader.http_session.close()

    # 3. Close TonConnect instances
    await TonConnectService.close_all()

    # 4. Close bot session
    if bot.session:
        await bot.session.close()

    await asyncio.sleep(1.0)
    logging.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped by user")
