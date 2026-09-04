import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from services.giveaway_formatting import (
    format_prize_html,
    format_prizes_html,
    format_moscow_datetime,
    parse_moscow_giveaway_time,
)


MSK = ZoneInfo("Europe/Moscow")
UTC = ZoneInfo("UTC")


class MoscowGiveawayTimeTests(unittest.TestCase):
    def test_time_only_today(self):
        now = datetime(2026, 9, 4, 10, 0, tzinfo=MSK)
        self.assertEqual(
            parse_moscow_giveaway_time("11:00", now),
            datetime(2026, 9, 4, 8, 0, tzinfo=UTC),
        )

    def test_time_only_rolls_to_tomorrow_when_passed(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=MSK)
        self.assertEqual(
            parse_moscow_giveaway_time("11:00", now),
            datetime(2026, 9, 5, 8, 0, tzinfo=UTC),
        )

    def test_supported_explicit_date_variants(self):
        now = datetime(2026, 9, 3, 10, 0, tzinfo=MSK)
        expected = datetime(2026, 9, 4, 15, 0, tzinfo=UTC)
        for value in (
            "18:00 04.09", "18.00 4/9", "18:00, 04-09-2026",
            "04.09 18:00", "4/9/26, 18.00",
        ):
            with self.subTest(value=value):
                self.assertEqual(parse_moscow_giveaway_time(value, now), expected)

    def test_invalid_or_past_explicit_date_is_rejected(self):
        now = datetime(2026, 9, 4, 12, 0, tzinfo=MSK)
        self.assertIsNone(parse_moscow_giveaway_time("11:00 04.09", now))
        self.assertIsNone(parse_moscow_giveaway_time("25:00"))
        self.assertIsNone(parse_moscow_giveaway_time("18:00 31.02"))

    def test_utc_storage_is_displayed_in_moscow(self):
        self.assertEqual(
            format_moscow_datetime("2026-09-04T08:00:00+00:00"),
            "04.09.2026 11:00 MSK",
        )


class PrizeFormattingTests(unittest.TestCase):
    def test_url_is_embedded_into_preceding_phrase(self):
        self.assertEqual(
            format_prize_html("Exclusive NFT https://example.com/nft, sticker, role"),
            '<a href="https://example.com/nft">Exclusive NFT</a>, sticker, role',
        )

    def test_plain_text_and_html_are_escaped(self):
        self.assertEqual(format_prize_html("A < B"), "A &lt; B")

    def test_each_prize_gets_its_own_link(self):
        self.assertEqual(
            format_prizes_html(["NFT https://a.example", "Role https://b.example"]),
            '<a href="https://a.example">NFT</a>, <a href="https://b.example">Role</a>',
        )


if __name__ == "__main__":
    unittest.main()
