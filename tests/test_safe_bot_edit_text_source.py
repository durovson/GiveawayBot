import ast
import pathlib
import unittest


class SafeBotEditTextSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = pathlib.Path("utils.py")
        cls.source = cls.path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _function_source(self, name: str) -> str:
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return ast.get_source_segment(self.source, node)
        self.fail(f"Function {name} not found")

    def test_missing_edit_target_is_recoverable(self):
        source = self._function_source("safe_bot_edit_text")
        self.assertIn('"message to edit not found"', source)
        self.assertIn("await bot.send_message", source)

    def test_replacement_message_is_reused(self):
        source = self._function_source("safe_bot_edit_text")
        self.assertIn("_bot_edit_replacements.get", source)
        self.assertIn("_bot_edit_replacements[replacement_key] = msg.message_id", source)


if __name__ == "__main__":
    unittest.main()
