import asyncio
import logging
import math
import os
import time
from decimal import Decimal, InvalidOperation

import loader
from database import db
from utils import normalize_to_raw

logger = logging.getLogger(__name__)


class GramDepositService:
    _last_error_log = 0.0
    _last_auth_warning = 0.0
    _last_sync_error: str | None = None

    @staticmethod
    def _log_poll_error(message: str):
        now = time.monotonic()
        if now - GramDepositService._last_error_log >= 600:
            logger.warning(message, exc_info=True)
            GramDepositService._last_error_log = now

    @staticmethod
    def _warn_rejected_key():
        now = time.monotonic()
        if now - GramDepositService._last_auth_warning >= 600:
            logger.warning("TONAPI_KEY was rejected; using public GRAM history access")
            GramDepositService._last_auth_warning = now

    @staticmethod
    def configured() -> bool:
        # Native GRAM (formerly TON) does not have a jetton master.  A master is
        # only needed when the legacy GRM jetton is accepted as well.
        return bool(os.getenv("GRAM_DEPOSIT_WALLET"))

    @staticmethod
    def last_sync_error() -> str | None:
        return GramDepositService._last_sync_error

    @staticmethod
    def _authorization_headers() -> dict[str, str]:
        key = os.getenv("TONAPI_KEY", "").strip().strip('"').strip("'")
        if key.lower().startswith("bearer "):
            key = key[7:].strip()
        return {"Authorization": f"Bearer {key}"} if key else {}

    @staticmethod
    async def _load_events(url: str) -> list[dict]:
        headers = GramDepositService._authorization_headers()
        async with loader.http_session.get(
            url, params={"limit": 100}, headers=headers, timeout=20
        ) as response:
            # Public TonAPI access is sufficient for polling.  Retry without a
            # stale/malformed optional key instead of disabling deposits.
            if response.status != 401 or not headers:
                response.raise_for_status()
                return (await response.json()).get("events", [])

        GramDepositService._warn_rejected_key()
        async with loader.http_session.get(
            url, params={"limit": 100}, timeout=20
        ) as response:
            response.raise_for_status()
            return (await response.json()).get("events", [])

    @staticmethod
    async def sync() -> int:
        if not GramDepositService.configured() or not loader.http_session:
            return 0
        wallet = os.environ["GRAM_DEPOSIT_WALLET"].strip()
        master = os.getenv("GRAM_JETTON_MASTER", "").strip()
        try:
            wallet_raw = normalize_to_raw(wallet)
            master_raw = normalize_to_raw(master) if master else None
        except Exception:
            logger.error("GRAM wallet or jetton master address is invalid")
            GramDepositService._last_sync_error = "configuration"
            return 0
        decimals = int(os.getenv("GRAM_DECIMALS", "9"))
        rate = Decimal(await db.get_setting("gram_rp_per_gram") or os.getenv("GRAM_RP_PER_GRAM", "10"))
        url = f"https://tonapi.io/v2/accounts/{wallet}/events"
        try:
            events = await GramDepositService._load_events(url)
        except Exception:
            GramDepositService._last_sync_error = "api"
            GramDepositService._log_poll_error("GRAM deposit history request failed")
            return 0
        GramDepositService._last_sync_error = None

        credited = 0
        for event in reversed(events):
            # TonAPI's event-level scam heuristic may flag a valid native
            # transfer (for example because of its text comment).  We verify
            # the successful action, asset and recipient below instead.
            if event.get("in_progress"):
                continue
            for index, action in enumerate(event.get("actions") or []):
                transfer = action.get("TonTransfer") or action.get("ton_transfer")
                transfer_kind = "native"
                if not transfer:
                    transfer = action.get("JettonTransfer") or action.get("jetton_transfer")
                    transfer_kind = "jetton"
                if not transfer or action.get("status", "ok") != "ok":
                    continue
                recipient = transfer.get("recipient") or {}
                recipient_address = recipient.get("address") if isinstance(recipient, dict) else recipient
                jetton = transfer.get("jetton") or {}
                jetton_address = jetton.get("address") if isinstance(jetton, dict) else None
                comment = str(transfer.get("comment") or "").strip()
                try:
                    recipient_matches = normalize_to_raw(str(recipient_address)) == wallet_raw
                    jetton_matches = (
                        transfer_kind == "native"
                        or (
                            master_raw is not None
                            and jetton_address is not None
                            and normalize_to_raw(str(jetton_address)) == master_raw
                        )
                    )
                except Exception:
                    continue
                if not recipient_matches or not jetton_matches:
                    continue
                if not comment.startswith("@") or len(comment) < 2:
                    continue
                try:
                    amount_decimals = 9 if transfer_kind == "native" else decimals
                    amount = Decimal(str(transfer["amount"])) / (Decimal(10) ** amount_decimals)
                except (KeyError, InvalidOperation):
                    continue
                rp_amount = math.floor(amount * rate)
                if amount < Decimal("0.1") or rp_amount <= 0:
                    continue
                sender = transfer.get("sender") or {}
                sender_address = sender.get("address") if isinstance(sender, dict) else str(sender)
                event_id = event.get("event_id") or event.get("eventId")
                if not event_id:
                    continue
                result = await db.claim_gram_deposit({
                    "p_event_id": str(event_id),
                    "p_action_index": index, "p_username": comment,
                    "p_sender_address": sender_address, "p_amount_gram": str(amount),
                    "p_rp_amount": rp_amount,
                    "p_raw_data": {
                        "action": action,
                        "transfer_kind": transfer_kind,
                        "event_is_scam": bool(event.get("is_scam")),
                    },
                })
                if result.get("ok") and not result.get("duplicate"):
                    credited += 1
        return credited

    @staticmethod
    async def poll_forever():
        interval = max(30, int(os.getenv("GRAM_POLL_SECONDS", "60")))
        while True:
            try:
                await GramDepositService.sync()
            except asyncio.CancelledError:
                raise
            except Exception:
                GramDepositService._log_poll_error("GRAM deposit polling failed")
            await asyncio.sleep(interval)
