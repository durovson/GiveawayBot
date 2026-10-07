import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from aiogram import types
from handlers import notifications, store
from locales.en.notifications import TEXTS as NOTIFICATION_TEXTS
from locales.en.store import TEXTS as STORE_TEXTS
from services import september_wl_service as wl


class RebuiltBotFlows(unittest.IsolatedAsyncioTestCase):
    async def test_failed_status_write_keeps_previous_screen_and_state(self):
        state = AsyncMock()
        state.get_data.return_value = {"id": 7, "is_active": True}
        callback = SimpleNamespace(answer=AsyncMock())
        with patch.object(notifications.db, "update_notification_status", new=AsyncMock(return_value=False)), patch.object(notifications, "show_notification_preview", new=AsyncMock()) as preview:
            await notifications.toggle_status(callback, state, AsyncMock(), NOTIFICATION_TEXTS)
        state.update_data.assert_not_awaited()
        preview.assert_not_awaited()
        callback.answer.assert_awaited_once_with(NOTIFICATION_TEXTS["notif_toggle_error"], show_alert=True)

    async def test_status_write_updates_screen_after_persistence(self):
        state = AsyncMock()
        state.get_data.return_value = {"id": 7, "is_active": True}
        callback = SimpleNamespace(answer=AsyncMock())
        with patch.object(notifications.db, "update_notification_status", new=AsyncMock(return_value=True)) as update, patch.object(notifications, "show_notification_preview", new=AsyncMock()) as preview:
            await notifications.toggle_status(callback, state, AsyncMock(), NOTIFICATION_TEXTS)
        update.assert_awaited_once_with(7, False)
        state.update_data.assert_awaited_once_with(is_active=False)
        preview.assert_awaited_once()

    async def test_partner_channels_precede_green_check(self):
        callback = SimpleNamespace(bot=AsyncMock())
        with patch.object(store, "_resolve_channel_link", new=AsyncMock(side_effect=[("Channel A", "https://t.me/notapes"), ("Channel B", "https://t.me/patronofnot")])), patch.object(store, "_render", new=AsyncMock()) as render:
            await store.show_partner_gate(callback, {"id": 26, "mandatory_channels": ["@notapes", "@patronofnot"]}, AsyncMock(), STORE_TEXTS)
        rows = render.call_args.args[2].inline_keyboard
        self.assertEqual(rows[0][0].url, "https://t.me/notapes")
        self.assertEqual(rows[1][0].url, "https://t.me/patronofnot")
        self.assertEqual(rows[2][0].callback_data, "partner_check_26")
        self.assertEqual(rows[2][0].style, "success")

    async def test_partner_check_returns_to_ticket_selection(self):
        callback = SimpleNamespace(data="partner_check_26", bot=AsyncMock(), from_user=SimpleNamespace(id=10), answer=AsyncMock())
        state = AsyncMock()
        state.get_data.return_value = {}
        with patch.object(store.db, "get_giveaway", new=AsyncMock(return_value={"id": 26, "status": "active", "mandatory_channels": ["@notapes"]})), patch.object(store, "_is_subscribed_to_all", new=AsyncMock(return_value=(True, []))), patch.object(store, "show_ticket_store", new=AsyncMock()) as tickets:
            await store.partner_check_handler(callback, state, STORE_TEXTS)
        state.update_data.assert_awaited_once_with(partner_verified_giveaways=[26])
        tickets.assert_awaited_once_with(callback, state, STORE_TEXTS)

    async def test_partial_ticket_use_passes_exact_amount_to_atomic_rpc(self):
        callback = SimpleNamespace(data="spend_gt_26_3", id="event-1", from_user=SimpleNamespace(id=10), answer=AsyncMock())
        execute = AsyncMock(return_value=SimpleNamespace(data={"ok": True, "spent": 3, "remaining": 7}))
        client = SimpleNamespace(rpc=lambda name, payload: self._record_rpc(name, payload, execute))
        with patch.object(store.db, "client", client), patch.object(store, "_ticket_state", new=AsyncMock(return_value={"balance": 10})), patch.object(store, "show_giveaway_tickets", new=AsyncMock()):
            await store.spend_giveaway_tickets(callback, AsyncMock(), STORE_TEXTS)
        self.assertEqual(self.rpc_name, "spend_giveaway_tickets")
        self.assertEqual(self.rpc_payload["p_amount"], 3)
        self.assertEqual(self.rpc_payload["p_idempotency_key"], "tg-spend:event-1")
        execute.assert_awaited_once()

    def _record_rpc(self, name, payload, execute):
        self.rpc_name, self.rpc_payload = name, payload
        return SimpleNamespace(execute=execute)

    async def test_wl_cached_nft_count_recalculates_at_three(self):
        profile = {"september_wl_checked_at": datetime.now(timezone.utc), "september_wl_nft_count": 8, "september_wl_checked_wallet": "wallet"}
        with patch.object(wl, "normalize_to_raw", side_effect=lambda value: value), patch.object(wl, "fetch_notapes_count", new=AsyncMock()) as fetch:
            snapshot = await wl.get_wl_snapshot(10, "wallet", profile)
        self.assertEqual(snapshot.wl_count, 2)
        fetch.assert_not_awaited()
