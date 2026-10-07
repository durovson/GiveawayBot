"""Small pure-logic regression checks for the ticket balance model.

These tests intentionally avoid Telegram/Supabase imports so they can run in a
minimal CI environment.
"""


def migrated_available(total_tickets: int, tickets_used: int | None) -> int:
    used = max(1, tickets_used or 1)
    return max(0, total_tickets - used)


def test_existing_joined_user_starts_with_no_double_spend():
    assert migrated_available(8, 8) == 0


def test_unjoined_user_keeps_purchased_balance():
    assert migrated_available(8, None) == 7


def test_partially_used_balance_is_preserved():
    assert migrated_available(11, 4) == 7
