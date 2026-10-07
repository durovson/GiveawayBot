import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from handlers import store
from locales.en.store import TEXTS as EN
from locales.ru.store import TEXTS as RU


class TicketWalletTests(unittest.IsolatedAsyncioTestCase):
    def callback(self, data="store_tickets"):
        return SimpleNamespace(data=data, id="wallet-event", from_user=SimpleNamespace(id=10), answer=AsyncMock())

    async def test_menu_offers_and_balance_exist_with_or_without_active_giveaway(self):
        for texts in (EN, RU):
            for giveaways in ([], [{"id": 26, "title": "Drop"}]):
                for balance in (0, 12, None):
                    with self.subTest(lang=texts["store_back_btn"], active=bool(giveaways), balance=balance):
                        offers = [
                            {"code": "5", "ticket_count": 5, "price_rp": 25, "pricing_mode": "fixed"},
                            {"code": "2", "ticket_count": 2, "price_rp": 5, "pricing_mode": "per_ticket"},
                        ]
                        with (
                            patch.object(store, "_rp", new=AsyncMock(return_value=70)),
                            patch.object(store.db, "get_active_giveaways", new=AsyncMock(return_value=giveaways)),
                            patch.object(store.db, "get_ticket_wallet_balance", new=AsyncMock(return_value=balance)),
                            patch.object(store.db, "get_ticket_offers", new=AsyncMock(return_value=offers)),
                            patch.object(store, "_render", new=AsyncMock()) as render,
                        ):
                            await store.show_ticket_store(self.callback(), AsyncMock(), texts)
                        text, markup = render.call_args.args[1:3]
                        self.assertIn(f"{70}", text)
                        self.assertIn(f"{balance if balance is not None else '—'}", text)
                        buttons = [b for row in markup.inline_keyboard for b in row]
                        self.assertEqual(buttons[0].callback_data, "buy_wallet_5")
                        self.assertIn("25 RP", buttons[0].text)
                        self.assertIn("10 RP", buttons[1].text)
                        if giveaways:
                            self.assertEqual(buttons[2].callback_data, "store_tg_26")
                        else:
                            self.assertIn(texts["ticket_choose_empty"], text)
                        self.assertEqual(buttons[-1].callback_data, "store_menu")

    async def test_purchase_uses_current_user_offer_and_idempotency_then_refreshes_menu(self):
        callback, state = self.callback("buy_wallet_5"), AsyncMock()
        with (
            patch.object(store.db, "purchase_ticket_wallet", new=AsyncMock(return_value={
                "ok": True, "added": 5, "cost": 25, "available_tickets": 8,
            })) as purchase,
            patch.object(store, "show_ticket_store", new=AsyncMock()) as refresh,
        ):
            await store.buy_wallet_tickets(callback, state, EN)
        purchase.assert_awaited_once_with(10, "5", "tg:wallet-event")
        callback.answer.assert_awaited_once_with(
            EN["ticket_purchase_success"].format(added=5, cost=25, balance=8), show_alert=True,
        )
        refresh.assert_awaited_once_with(callback, state, EN)

    async def test_failed_purchase_never_displays_success(self):
        callback = self.callback("buy_wallet_10")
        with (
            patch.object(store.db, "purchase_ticket_wallet", new=AsyncMock(return_value={
                "ok": False, "error": "INSUFFICIENT_POINTS",
            })),
            patch.object(store, "show_ticket_store", new=AsyncMock()) as refresh,
        ):
            await store.buy_wallet_tickets(callback, AsyncMock(), {**EN, "not_enough_points": "Insufficient RP"})
        callback.answer.assert_awaited_once_with("Insufficient RP", show_alert=True)
        refresh.assert_not_awaited()

    async def test_stale_giveaway_button_still_buys_into_persistent_wallet(self):
        callback, state = self.callback("buy_gt_26_5"), AsyncMock()
        with (
            patch.object(store.db, "purchase_ticket_wallet", new=AsyncMock(return_value={"ok": True})) as purchase,
            patch.object(store.db, "get_giveaway", new=AsyncMock(return_value={"status": "completed"})),
            patch.object(store, "show_ticket_store", new=AsyncMock()) as refresh,
            patch.object(store, "show_giveaway_tickets", new=AsyncMock()) as detail,
        ):
            await store.buy_giveaway_tickets(callback, state, EN)
        purchase.assert_awaited_once_with(10, "5", "tg:wallet-event")
        refresh.assert_awaited_once_with(callback, state, EN)
        detail.assert_not_awaited()

    async def test_detail_combines_wallet_with_legacy_scoped_balance_not_used_tickets(self):
        client = MagicMock()
        response = client.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value
        response.execute = AsyncMock(side_effect=[
            SimpleNamespace(data=[{"tickets": 8, "available_tickets": 2}]),
            SimpleNamespace(data=[{"tickets_used": 6}]),
        ])
        with patch.object(store.db, "client", client), patch.object(
            store.db, "get_ticket_wallet_balance", new=AsyncMock(return_value=5),
        ):
            result = await store._ticket_state(26, 10)
        self.assertEqual(result["balance"], 7)
        self.assertEqual(result["used"], 6)
