import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


class ArenaContracts(unittest.TestCase):
    def test_arena_commands_and_routes(self):
        content = (ROOT / "handlers" / "arena.py").read_text(encoding="utf-8")
        ast.parse(content)
        for callback in ("arena:menu", "arena:start", "arena:deploy",
                         "arena:stake:", "arena:join:", "arena:items", "arena:convert:"):
            self.assertIn(callback, content)
        self.assertIn("await asyncio.sleep(1)", content)

    def test_no_legacy_chat_attacks(self):
        code = (ROOT / "bot.py").read_text(encoding="utf-8")
        self.assertNotIn("dp.include_router(chat_games_router)", code)
        self.assertNotIn("SafeDefenseMiddleware()", code)
        self.assertIn("ArenaWorker.poll_forever", code)

    def test_atomic_game_database(self):
        sql = (ROOT / "supabase" / "migrations" / "20261028_arena_v2.sql").read_text(encoding="utf-8")
        self.assertIn("arena_join", sql)
        self.assertIn("arena_cancel", sql)
        self.assertIn("arena_convert", sql)
        self.assertIn("balance=balance+f.stake*2", sql)
        self.assertIn("p_rp*100", sql)
        self.assertIn("p_stake < 15", sql)
        self.assertIn("w < 70", sql)
        self.assertIn("security invoker", sql)

    def test_one_time_rp_reconciliation(self):
        sql = (ROOT / "supabase" / "migrations" / "20261028_reconcile_legacy_rp.sql").read_text(encoding="utf-8")
        self.assertIn("arena_rp_grants", sql)
        self.assertIn("arena_legacy_restitutions", sql)
        self.assertIn("on conflict(attack_id) do nothing", sql)
        self.assertIn("SAFE", (ROOT / "supabase" / "migrations" / "20261027124829_chat_bank_robber.sql").read_text().upper())


if __name__ == "__main__":
    unittest.main()
