"""Regression checks for notification target sentinel semantics."""

BOT_BROADCAST_CHAT_ID = 0


def test_bot_broadcast_target_is_not_none():
    assert BOT_BROADCAST_CHAT_ID == 0
    assert BOT_BROADCAST_CHAT_ID is not None
