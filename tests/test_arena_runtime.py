from __future__ import annotations

import unittest

from locales.en.game_menu import TEXTS as EN_GAME
from locales.ru.game_menu import TEXTS as RU_GAME
from services.chat_game_theme import EMOJI
from handlers.arena import _choose_stake, back, item_keyboard, screen, t


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
        self.assertTrue(any(x.icon_custom_emoji_id == EMOJI["pumpkin"][1] for row in enough for x in row))

    def test_shop_exchange_buttons(self):
        b = item_keyboard("en")
        rows = [button for row in b.inline_keyboard for button in row]
        self.assertTrue(any("1 RP → 100" in button.text for button in rows))
        self.assertTrue(any(button.callback_data == "arena:convert:10" for button in rows))
        conversions = [button for button in rows if button.callback_data.startswith('arena:convert:') and button.callback_data != 'arena:convert:custom']
        self.assertTrue(all(button.text.endswith('🎃') and button.icon_custom_emoji_id is None for button in conversions))

    def test_menu_back_and_emojis(self):
        self.assertEqual(back("ru").inline_keyboard[0][0].callback_data, "game_menu")
        display = screen("ARENA", "50 🎃")
        self.assertIn("┏┅", display)
        self.assertIn(f'emoji-id="{EMOJI["game"][1]}"', display)
        self.assertIn(f'emoji-id="{EMOJI["pumpkin"][1]}"', display)

    def test_game_menu_linebreaks_and_premium_emojis(self):
        for texts in (EN_GAME, RU_GAME):
            content = texts["game_menu_title"].format(rp=80, refs=1)
            self.assertNotIn(r"\n", content, "Literal backslash-n in game menu")
            self.assertIn("ARENA:", content)
            self.assertIn("STORE:", content)
            for name in ("game", "store", "pumpkin"):
                self.assertIn(f'emoji-id="{EMOJI[name][1]}"', content)


if __name__ == "__main__":
    unittest.main()
