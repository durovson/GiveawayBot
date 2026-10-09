import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from database import Database
from handlers import wallet
from locales.en.wallet import TEXTS
from pytonconnect.storage import IStorage
from services.ton_connect_service import SafeTonConnect, TonConnectService


class SafeDisconnectTests(unittest.IsolatedAsyncioTestCase):
    def connector(self, has_session=True):
        storage = SimpleNamespace(remove_item=AsyncMock())
        connector = SafeTonConnect("https://example.com/tonconnect-manifest.json", storage=storage)
        connector._wallet = SimpleNamespace(account=SimpleNamespace(address="address"))
        provider = SimpleNamespace(
            _session=SimpleNamespace(wallet_public_key="public-key" if has_session else None),
            send_request=AsyncMock(), close_connection=MagicMock(),
            disconnect=AsyncMock(side_effect=asyncio.InvalidStateError("original SDK race")),
        )
        connector._provider = provider
        return connector, provider, storage

    async def test_duplicate_or_already_completed_future_does_not_raise(self):
        for completed in (False, True):
            connector, provider, storage = self.connector()
            async def send(request, on_request_sent):
                future = asyncio.get_running_loop().create_future()
                if completed:
                    future.set_result("wallet response")
                on_request_sent(future)
                on_request_sent(future)
                return await future
            provider.send_request.side_effect = send
            await connector.disconnect()
            self.assertFalse(connector.connected)
            provider.disconnect.assert_not_awaited()
            provider.close_connection.assert_called_once()
            storage.remove_item.assert_awaited_once_with(IStorage.KEY_CONNECTION)

    async def test_missing_session_is_local_cleanup_without_bridge_request(self):
        connector, provider, storage = self.connector(has_session=False)
        await connector.disconnect()
        await connector.disconnect()
        provider.send_request.assert_not_awaited()
        self.assertFalse(connector.connected)
        self.assertEqual(storage.remove_item.await_count, 2)

    async def test_network_failure_and_timeout_still_clear_local_session(self):
        for timed_out in (False, True):
            connector, provider, storage = self.connector()
            if timed_out:
                connector.DISCONNECT_TIMEOUT = 0.01
                async def blocked(*a, **kw):
                    await asyncio.Event().wait()
                provider.send_request.side_effect = blocked
            else:
                provider.send_request.side_effect = RuntimeError("offline")
            await connector.disconnect()
            self.assertFalse(connector.connected)
            provider.close_connection.assert_called_once()
            storage.remove_item.assert_awaited_once()

    async def test_cancellation_cleans_up_and_is_not_swallowed(self):
        connector, provider, storage = self.connector()
        started = asyncio.Event()
        async def blocked(*a, **kw):
            started.set()
            await asyncio.Event().wait()
        provider.send_request.side_effect = blocked
        task = asyncio.create_task(connector.disconnect())
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(connector.connected)
        storage.remove_item.assert_awaited_once()


class WalletServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = patch.multiple(TonConnectService, _instances={}, _last_access={}, _locks={})
        self.cache.start()
        self.addCleanup(self.cache.stop)

    async def test_cached_connector_is_not_restored_on_each_access(self):
        connector = SimpleNamespace(restore_connection=AsyncMock())
        TonConnectService._instances[10] = connector
        self.assertIs(await TonConnectService.connector(10), connector)
        connector.restore_connection.assert_not_awaited()

    async def test_service_purges_only_user_sessions_and_confirms_wallet_write(self):
        connector = SimpleNamespace(disconnect=AsyncMock(), _provider=None)
        TonConnectService._instances[10] = connector
        client = MagicMock()
        client.table.return_value.delete.return_value.eq.return_value.execute = AsyncMock()
        with patch("services.ton_connect_service.db.client", client), patch(
            "services.ton_connect_service.db.update_user_wallet", new=AsyncMock(return_value=True),
        ) as update:
            await TonConnectService.disconnect(10)
        self.assertNotIn(10, TonConnectService._instances)
        connector.disconnect.assert_awaited_once()
        client.table.assert_called_once_with("ton_connect_sessions")
        client.table.return_value.delete.return_value.eq.assert_called_once_with("user_id", 10)
        update.assert_awaited_once_with(10, None)

    async def test_failed_db_write_cannot_report_completed_disconnect(self):
        TonConnectService._instances[10] = SimpleNamespace(disconnect=AsyncMock(), _provider=None)
        client = MagicMock()
        client.table.return_value.delete.return_value.eq.return_value.execute = AsyncMock()
        with patch("services.ton_connect_service.db.client", client), patch(
            "services.ton_connect_service.db.update_user_wallet", new=AsyncMock(return_value=False),
        ):
            with self.assertRaisesRegex(RuntimeError, "not persisted"):
                await TonConnectService.disconnect(10)
        self.assertNotIn(10, TonConnectService._instances)

    async def test_session_delete_failure_is_not_mistaken_for_success(self):
        TonConnectService._instances[10] = SimpleNamespace(disconnect=AsyncMock(), _provider=None)
        client = MagicMock()
        client.table.return_value.delete.return_value.eq.return_value.execute = AsyncMock(side_effect=RuntimeError("DB offline"))
        with patch("services.ton_connect_service.db.client", client), patch(
            "services.ton_connect_service.db.update_user_wallet", new=AsyncMock(),
        ) as update:
            with self.assertRaisesRegex(RuntimeError, "DB offline"):
                await TonConnectService.disconnect(10)
        self.assertNotIn(10, TonConnectService._instances)
        update.assert_not_awaited()

    async def test_repeated_disconnect_without_cached_instance_is_safe(self):
        client = MagicMock()
        client.table.return_value.delete.return_value.eq.return_value.execute = AsyncMock()
        connector = SimpleNamespace(restore_connection=AsyncMock(return_value=False), disconnect=AsyncMock())
        with patch("services.ton_connect_service.db.client", client), patch(
            "services.ton_connect_service.db.update_user_wallet", new=AsyncMock(return_value=True),
        ), patch("services.ton_connect_service.SafeTonConnect", return_value=connector):
            await TonConnectService.disconnect(10)
            await TonConnectService.disconnect(10)
        self.assertEqual(connector.disconnect.await_count, 2)
        connector.restore_connection.assert_awaited_with(auto_listen=False)


class WalletHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        wallet._wallet_actions.clear()
        wallet._connection_waiters.clear()

    def callback(self):
        return SimpleNamespace(from_user=SimpleNamespace(id=10), answer=AsyncMock())

    async def test_success_answers_callback_once_and_refreshes_without_second_ack(self):
        callback, state = self.callback(), AsyncMock()
        with patch.object(TonConnectService, "disconnect", new=AsyncMock()), patch.object(
            wallet, "wallet_menu", new=AsyncMock(),
        ) as menu:
            await wallet.disconnect_wallet(callback, state, TEXTS)
        callback.answer.assert_awaited_once_with(TEXTS["wallet_disconnected_alert"], show_alert=True)
        menu.assert_awaited_once_with(callback, state, TEXTS, acknowledge=False)

    async def test_error_never_shows_success_or_deletes_current_screen(self):
        callback = self.callback()
        with patch.object(TonConnectService, "disconnect", new=AsyncMock(side_effect=RuntimeError("DB offline"))), patch.object(
            wallet, "wallet_menu", new=AsyncMock(),
        ) as menu:
            await wallet.disconnect_wallet(callback, AsyncMock(), TEXTS)
        callback.answer.assert_awaited_once_with(TEXTS["wallet_disconnect_error"], show_alert=True)
        menu.assert_not_awaited()
        self.assertNotIn(10, wallet._wallet_actions)

    async def test_double_click_does_not_start_two_disconnect_operations(self):
        first, second = self.callback(), self.callback()
        started, finish = asyncio.Event(), asyncio.Event()
        async def disconnect(user_id):
            started.set()
            await finish.wait()
        with patch.object(TonConnectService, "disconnect", new=AsyncMock(side_effect=disconnect)) as service, patch.object(
            wallet, "wallet_menu", new=AsyncMock(),
        ):
            task = asyncio.create_task(wallet.disconnect_wallet(first, AsyncMock(), TEXTS))
            await started.wait()
            await wallet.disconnect_wallet(second, AsyncMock(), TEXTS)
            second.answer.assert_awaited_once_with(TEXTS["wallet_action_busy"], show_alert=True)
            finish.set()
            await task
        service.assert_awaited_once_with(10)

    async def test_waiter_is_cancelled_before_disconnecting(self):
        waiting = asyncio.create_task(asyncio.Event().wait())
        wallet._connection_waiters[10] = waiting
        async def disconnect(user_id):
            self.assertTrue(waiting.cancelled())
        with patch.object(TonConnectService, "disconnect", new=AsyncMock(side_effect=disconnect)), patch.object(
            wallet, "wallet_menu", new=AsyncMock(),
        ):
            await wallet.disconnect_wallet(self.callback(), AsyncMock(), TEXTS)
        self.assertNotIn(10, wallet._connection_waiters)

    async def test_obsolete_waiter_never_saves_wallet_or_drops_new_connector(self):
        old = SimpleNamespace(connected=True, account=SimpleNamespace(address="stale"), on_status_change=MagicMock(return_value=MagicMock()))
        with patch.object(TonConnectService, "is_current", return_value=False), patch.object(
            wallet.db, "update_user_wallet", new=AsyncMock(),
        ) as update, patch.object(TonConnectService, "drop_connector") as drop:
            await wallet.wait_for_connection(10, old, AsyncMock(), TEXTS)
            await wallet.cleanup_connect(10, old)
        update.assert_not_awaited()
        drop.assert_not_called()


class WalletPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_wallet_write_returns_false_when_no_row_was_saved(self):
        client = MagicMock()
        client.table.return_value.upsert.return_value.execute = AsyncMock(return_value=SimpleNamespace(data=[]))
        database = Database()
        database.client = client
        self.assertFalse(await database.update_user_wallet(10, None))
        client.table.return_value.upsert.return_value.execute.return_value = SimpleNamespace(data=[{"telegram_id": 10, "wallet_address": None}])
        self.assertTrue(await database.update_user_wallet(10, None))
