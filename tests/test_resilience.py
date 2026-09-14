import os
import unittest
from unittest.mock import AsyncMock, patch

import aiohttp

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import loader
from database import Database
from services.gram_service import GramDepositService


class FakeResponse:
    def __init__(self, status: int, payload=None, headers=None):
        self.status = status
        self.payload = payload or {}
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def read(self):
        return b""

    async def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status >= 400:
            raise aiohttp.ClientResponseError(None, (), status=self.status)


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def get(self, *_args, **_kwargs):
        self.calls += 1
        return next(self.responses)


class DatabaseRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_read_is_retried(self):
        database = Database()
        operation = AsyncMock(
            side_effect=[RuntimeError("{'code': 504, 'message': 'upstream'}"), "ok"]
        )
        with patch("database.asyncio.sleep", new=AsyncMock()) as sleep:
            result = await database._retry_read(operation, "test read")
        self.assertEqual(result, "ok")
        self.assertEqual(operation.await_count, 2)
        sleep.assert_awaited_once_with(0.5)

    async def test_non_transient_error_is_not_retried(self):
        database = Database()
        operation = AsyncMock(side_effect=ValueError("bad query"))
        with self.assertRaises(ValueError):
            await database._retry_read(operation, "test read")
        self.assertEqual(operation.await_count, 1)


class TonApiRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_error_is_retried(self):
        fake_session = FakeSession([
            FakeResponse(500),
            FakeResponse(200, {"events": [{"event_id": "event-1"}]}),
        ])
        old_session = loader.http_session
        loader.http_session = fake_session
        try:
            with patch("services.gram_service.asyncio.sleep", new=AsyncMock()):
                events = await GramDepositService._load_events("https://example.test/events")
        finally:
            loader.http_session = old_session
        self.assertEqual(events, [{"event_id": "event-1"}])
        self.assertEqual(fake_session.calls, 2)


if __name__ == "__main__":
    unittest.main()
