import ast
import pathlib
import unittest


class GiveawayFsmSessionGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = pathlib.Path("middleware/referral_validator.py")
        cls.source = cls.path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def _literal_assignment(self, name):
        for node in cls_tree_body(self.tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        return ast.literal_eval(node.value)
        self.fail(f"Assignment {name} not found")

    def test_confirm_prizes_requires_expected_state(self):
        mapping = self._literal_assignment("_GIVEAWAY_REQUIRED_STATE")
        self.assertEqual(mapping["confirm_prizes"], "ENTER_PRIZES")
        self.assertEqual(mapping["confirm_giveaway"], "CONFIRMATION")

    def test_preview_callbacks_require_complete_draft(self):
        fields = self._literal_assignment("_GIVEAWAY_REQUIRED_FIELDS")
        self.assertIn("kind", fields["confirm_prizes"])
        self.assertIn("gtype", fields["confirm_prizes"])
        self.assertIn("mode_value", fields["confirm_prizes"])
        self.assertIn("winners_count", fields["confirm_prizes"])
        self.assertIn("prizes", fields["confirm_prizes"])

    def test_stale_callback_is_stopped_before_handler(self):
        middleware_source = None
        for node in cls_tree_body(self.tree):
            if isinstance(node, ast.ClassDef) and node.name == "ReferralValidatorMiddleware":
                middleware_source = ast.get_source_segment(self.source, node)
                break
        self.assertIsNotNone(middleware_source)
        self.assertIn("_state_name(current_state) != expected_state", middleware_source)
        self.assertIn("or missing_fields", middleware_source)
        self.assertIn("await _expire_giveaway_session", middleware_source)
        self.assertIn("return None", middleware_source)


def cls_tree_body(tree):
    return tree.body


if __name__ == "__main__":
    unittest.main()
