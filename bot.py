import asyncio
import logging
import aiohttp
import os
import uvicorn
from aiogram import F, types
from aiogram.types import ChatMemberUpdated
from aiogram.enums import ParseMode

import loader
from loader import bot, dp, bg_tasks, wallet_tasks
from database import db
from web_server import app, ping_self
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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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

async def run_bot():
    """Start aiogram polling."""
    logger.info("Starting bot polling...")
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    except Exception:
        logger.exception("Bot polling crashed")

async def run_server():
    """Start uvicorn server."""
    port = int(os.environ.get("PORT", 10000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server = uvicorn.Server(config)
    logger.info("Starting FastAPI server on port %s...", port)
    await server.serve()

async def main():
    # 1. Initialize shared resources
    loader.http_session = aiohttp.ClientSession()
    await db.connect()

    # 2. Perform initial sync
    await initial_sync()

    # 3. Start background tasks
    from handlers.completion import check_timed_giveaways, check_periodic_notifications
    from tasks.sync_holders import daily_sync_task

    t1 = asyncio.create_task(check_timed_giveaways(bot))
    bg_tasks.add(t1)

    t2 = asyncio.create_task(check_periodic_notifications(bot))
    bg_tasks.add(t2)

    t3 = asyncio.create_task(daily_sync_task(bot))
    bg_tasks.add(t3)

    # 4. Start self-ping task
    t4 = asyncio.create_task(ping_self())
    bg_tasks.add(t4)

    # 5. Run Bot and Server together
    try:
        await asyncio.gather(
            run_bot(),
            run_server()
        )
    except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
        logger.info("Shutdown signal received")
    finally:
        logger.info("Shutting down...")

        # Graceful Shutdown Sequence

        # 1. Cancel all background tasks
        all_tasks = bg_tasks.union(wallet_tasks)
        logger.info("Cancelling %s background tasks...", len(all_tasks))
        for task in all_tasks:
            task.cancel()

        if all_tasks:
            try:
                # Wait for cancellation with timeout
                await asyncio.wait_for(asyncio.gather(*all_tasks, return_exceptions=True), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Shutdown timed out waiting for tasks to cancel")
            except Exception:
                logger.exception("Error during tasks cancellation")

        # 2. Close shared HTTP session
        if loader.http_session and not loader.http_session.closed:
            logger.info("Closing shared HTTP session...")
            await loader.http_session.close()

        # 3. Close TonConnect instances
        logger.info("Closing TonConnect instances...")
        await TonConnectService.close_all()

        # 4. Close bot session
        if bot.session:
            logger.info("Closing bot session...")
            await bot.session.close()

        logger.info("Shutdown complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
