"""Small pure-logic regression checks for the ticket balance model.

These tests intentionally avoid Telegram/Supabase imports so they can run in a
minimal CI environment.
"""

from pathlib import Path


def migrated_available(total_tickets: int, tickets_used: int | None) -> int:
    used = max(1, tickets_used or 1)
    return max(0, total_tickets - used)


def test_existing_joined_user_starts_with_no_double_spend():
    assert migrated_available(8, 8) == 0


def test_unjoined_user_keeps_purchased_balance():
    assert migrated_available(8, None) == 7


def test_partially_used_balance_is_preserved():
    assert migrated_available(11, 4) == 7


def test_database_migration_adds_and_spends_only_requested_tickets():
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "20261005_partial_giveaway_ticket_balance.sql"
    ).read_text(encoding="utf-8")

    assert "v_new_available := v_available + v_add" in migration
    assert "v_remaining := v_available - p_amount" in migration
    assert "v_used := v_used + p_amount" in migration
    assert "if not found or v_available < p_amount" in migration
