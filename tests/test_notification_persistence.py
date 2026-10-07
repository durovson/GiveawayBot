import asyncio
from types import SimpleNamespace

from database import Database


class FakeQuery:
    def __init__(self, rows):
        self.rows = rows
        self.payload = None
        self.filters = []

    def upsert(self, payload):
        self.payload = payload
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    async def execute(self):
        return SimpleNamespace(data=self.rows)


class FakeClient:
    def __init__(self, rows):
        self.query = FakeQuery(rows)

    def table(self, name):
        assert name == "notifications"
        return self.query


def test_notification_save_returns_stored_row():
    database = Database()
    database.client = FakeClient([{"id": 7, "title": "News"}])

    saved = asyncio.run(database.upsert_notification({"title": "News"}))

    assert saved == {"id": 7, "title": "News"}


def test_notification_status_requires_updated_row():
    database = Database()
    database.client = FakeClient([])

    updated = asyncio.run(database.update_notification_status(404, False))

    assert updated is False
    assert database.client.query.payload == {"is_active": False}
    assert database.client.query.filters == [("id", 404)]


def test_notification_status_reports_success_after_database_confirmation():
    database = Database()
    database.client = FakeClient([{"id": 9, "is_active": False}])

    updated = asyncio.run(database.update_notification_status(9, False))

    assert updated is True

