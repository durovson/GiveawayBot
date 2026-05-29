import os
import asyncio
import logging
import aiohttp
from fastapi import FastAPI, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import loader

logger = logging.getLogger(__name__)

app = FastAPI(title="Giveaway Bot Web Server")

@app.get("/health")
async def health():
    """Basic health check."""
    return {"status": "ok"}

@app.get("/ready")
async def readiness():
    """Detailed readiness check."""
    from database import db
    checks = {
        "bot_initialized": loader.bot is not None,
        "database_connected": db.client is not None,
    }
    status = "ok" if all(checks.values()) else "error"
    return {"status": status, "checks": checks}

@app.get("/")
async def index():
    return {"message": "Bot is running"}

@app.get("/tonconnect-manifest.json")
async def tonconnect_manifest():
    return FileResponse('tonconnect-manifest.json')

async def ping_self():
    """Self-ping task to keep the instance alive on Render."""
    await asyncio.sleep(20)
    logger.info("Starting self-ping background task")

    while True:
        url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("CUSTOM_URL")
        if url:
            try:
                if not url.startswith("http"):
                    url = "https://" + url
                health_url = f"{url.rstrip('/')}/health"

                # Use shared session if available, otherwise temporary one
                session = loader.http_session
                if session and not session.closed:
                    async with session.get(health_url, timeout=10) as resp:
                        if resp.status == 200:
                            logger.debug("Self-ping successful")
                        else:
                            logger.warning("Self-ping returned status %s", resp.status)
                else:
                    async with aiohttp.ClientSession() as temp_session:
                        async with temp_session.get(health_url, timeout=10) as resp:
                            pass
            except Exception as e:
                logger.error("Error during self-ping: %s", e)

        await asyncio.sleep(14 * 60) # Ping every 14 minutes
