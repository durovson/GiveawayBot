from __future__ import annotations

import unittest

from handlers.arena import (
    _choose_stake,
    back,
    item_keyboard,
    screen,
    t,
)


class ArenaRuntimeTests(unittest.TestCase):
    def test_two_languages(self):
        self.assertEqual(t("ru", "НАЗАД", "BACK"), "НАЗАД")
        self.assertEqual(t("en", "НАЗАД", "BACK"), "BACK")

    def test_stake_and_protected_minimum(self):
        empty = _choose_stake("ru", 50).inline_keyboard
        self.assertNotIn("arena:stake:15", [x.callback_data for row in empty for x in row])
        enough = _choose_stake("en", 70).inline_keyboard
        self.assertIn("arena:stake:15", [x.callback_data for row in enough for x in row])
        self.assertNotIn("arena:stake:50", [x.callback_data for row in enough for x in row])

    def test_shop_exchange_buttons(self):
        b = item_keyboard("en")
        rows = [button for row in b.inline_keyboard for button in row]
        self.assertTrue(any("1 RP → 100 🎃" in b.text for b in rows))
        self.assertTrue(any(b.callback_data == "arena:convert:10" for b in rows))

    def test_menu_back(self):
        self.assertEqual(back("ru").inline_keyboard[0][0].callback_data, "game_menu")
        self.assertIn("┏┅", screen("ARENA", "50 🎃"))


if __name__ == "__main__":
    unittest.main()
