import os
import asyncio
import html
import json
import logging
import re
import aiohttp
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import loader
from services.deep_links import build_ton_transfer_url, get_gram_deposit_wallet

logger = logging.getLogger(__name__)

app = FastAPI(title="Giveaway Bot Web Server")

TELEGRAM_USERNAME_COMMENT = re.compile(r"^@[A-Za-z0-9_]{1,32}$")

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


@app.get("/gram/transfer", response_class=HTMLResponse)
async def gram_transfer(comment: str, lang: str = "en"):
    """Open a wallet-neutral TON transfer link from a Telegram-safe HTTPS URL."""
    if not TELEGRAM_USERNAME_COMMENT.fullmatch(comment):
        raise HTTPException(status_code=400, detail="Invalid transfer comment")

    transfer_url = build_ton_transfer_url(get_gram_deposit_wallet(), comment)
    transfer_url_html = html.escape(transfer_url, quote=True)
    transfer_url_json = json.dumps(transfer_url)
    is_ru = lang.lower() == "ru"
    title = "Отправить GRAM" if is_ru else "Send GRAM"
    message = (
        "Выберите установленный кошелёк и укажите сумму. Адрес и комментарий уже заполнены."
        if is_ru else
        "Choose an installed wallet and enter the amount. The address and comment are prefilled."
    )
    open_text = "ОТКРЫТЬ КОШЕЛЁК" if is_ru else "OPEN WALLET"
    return HTMLResponse(
        content=f"""<!doctype html>
<html lang="{'ru' if is_ru else 'en'}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: dark; font-family: system-ui, sans-serif; }}
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
      background: #0d0d0f; color: #fff; }}
    main {{ width: min(420px, calc(100% - 40px)); text-align: center; }}
    h1 {{ font-size: 28px; margin-bottom: 12px; }}
    p {{ color: #b8b8bd; line-height: 1.5; margin-bottom: 28px; }}
    a {{ display: block; padding: 16px 20px; border-radius: 14px;
      background: #2ea65c; color: #fff; font-weight: 800;
      text-decoration: none; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(message)}</p>
    <a href="{transfer_url_html}">{html.escape(open_text)}</a>
  </main>
  <script>window.location.href = {transfer_url_json};</script>
</body>
</html>""",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )

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
