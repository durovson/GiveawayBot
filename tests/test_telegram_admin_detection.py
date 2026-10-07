import ast
import pathlib
import unittest


class TelegramAdminDetectionSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = pathlib.Path("loader.py")
        cls.source = cls.path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _class_source(self, name: str) -> str:
        for node in self.tree.body:
            if isinstance(node, ast.ClassDef) and node.name == name:
                return ast.get_source_segment(self.source, node)
        self.fail(f"Class {name} not found")

    def test_bot_wrapper_normalizes_administrator_list_calls(self):
        source = self._class_source("TelegramLinkAwareBot")
        self.assertIn("async def get_chat_administrators", source)
        self.assertIn("normalize_telegram_chat_ref(chat_id)", source)

    def test_self_membership_check_falls_back_to_admin_list(self):
        source = self._class_source("TelegramLinkAwareBot")
        self.assertIn("_get_self_admin_via_list", source)
        self.assertIn("getChatAdministrators", source)
        self.assertIn("user_id == self.id", source)

    def test_false_admin_result_is_logged_with_status(self):
        source = self._class_source("TelegramLinkAwareBot")
        self.assertIn("Bot admin check negative", source)
        self.assertIn("_chat_member_status(member)", source)


if __name__ == "__main__":
    unittest.main()
