import os
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher

logger = logging.getLogger(__name__)

async def health(request):
    return web.Response(text="OK", status=200)

async def index(request):
    return web.Response(text="Bot is running", status=200)

async def tonconnect_manifest(request):
    app_url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("CUSTOM_URL", "https://giveaway-bot-hiap.onrender.com")
    if not app_url.startswith("http"):
        app_url = "https://" + app_url

    manifest = {
        "url": app_url,
        "name": "Giveaway Bot System",
        "iconUrl": "https://i.ibb.co/CKLMgCcD/photo-2026-05-22-22-45-17.jpg"
    }
    return web.json_response(manifest)

async def start_keep_alive_async(bot: Bot, dp: Dispatcher):
    app = web.Application()
    app.router.add_get('/health', health)
    app.router.add_get('/', index)
    app.router.add_get('/tonconnect-manifest.json', tonconnect_manifest)

    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)

    logger.info(f"Starting aiohttp server on port {port}")
    await site.start()

    # Keep the bot polling in the same loop
    try:
        await dp.start_polling(bot, drop_pending_updates=True)
    finally:
        await runner.cleanup()

# Legacy functions for compatibility (if needed) but we use start_keep_alive_async now
def start_keep_alive():
    pass
