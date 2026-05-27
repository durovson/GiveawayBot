import os
import threading
import time
import requests
import logging
import subprocess
from flask import Flask, send_from_directory

logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/health')
def health():
    return "OK", 200

@app.route('/')
def index():
    return "Bot is running", 200

@app.route('/tonconnect-manifest.json')
def tonconnect_manifest():
    return send_from_directory('.', 'tonconnect-manifest.json')

def run_gunicorn():
    port = int(os.environ.get("PORT", 10000))
    cmd = [
        "gunicorn",
        "-w", "1",
        "-k", "gthread",
        "-b", f"0.0.0.0:{port}",
        "web_server:app"
    ]
    logger.info("Starting gunicorn: %s", " ".join(cmd))
    subprocess.Popen(cmd)

def ping_self():
    time.sleep(20)
    while True:
        url = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("CUSTOM_URL")
        if url:
            try:
                if not url.startswith("http"):
                    url = "https://" + url
                health_url = f"{url.rstrip('/')}/health"
                requests.get(health_url, timeout=10)
            except Exception as e:
                logger.error(f"Error pinging self: {e}")
        time.sleep(14 * 60)

def start_keep_alive():
    run_gunicorn()
    threading.Thread(target=ping_self, daemon=True).start()
