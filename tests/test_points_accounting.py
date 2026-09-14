import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

from services.holder_service import HolderService
from services.points_service import PointsService


class PointsAccountingTests(unittest.IsolatedAsyncioTestCase):
    async def test_holder_join_and_manual_adjustment_are_recalculated(self):
        points = {
            "packs": 2,
            "active_referrals": 1,
            "external_points": 15,
            "manual_adjustment": -5,
            "spent_points": 10,
        }
        user = {
            "wallet_address": None,
            "holder_join_bonus_awarded_at": "2026-09-14T10:00:00+00:00",
        }

        with (
            patch(
                "services.points_service.db.get_points",
                new=AsyncMock(return_value=points),
            ),
            patch(
                "services.points_service.db.get_user_by_telegram_id",
                new=AsyncMock(return_value=user),
            ),
            patch(
                "services.points_service.db.is_og_holder",
                new=AsyncMock(return_value=False),
            ),
            patch(
                "services.points_service.db.upsert_points",
                new=AsyncMock(),
            ) as upsert,
        ):
            result = await PointsService.recalculate_points(1001)

        self.assertEqual(result, 80)
        upsert.assert_awaited_once_with(
            user_id=1001,
            holder_bonus=50,
            total_points=80,
        )

    async def test_og_and_holder_join_bonus_do_not_stack(self):
        with (
            patch(
                "services.points_service.db.get_points",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "services.points_service.db.get_user_by_telegram_id",
                new=AsyncMock(return_value={
                    "wallet_address": None,
                    "holder_join_bonus_awarded_at": "2026-09-14T10:00:00+00:00",
                }),
            ),
            patch(
                "services.points_service.db.is_og_holder",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "services.points_service.db.upsert_points",
                new=AsyncMock(),
            ) as upsert,
        ):
            result = await PointsService.recalculate_points(1002)

        self.assertEqual(result, 50)
        self.assertEqual(upsert.await_args.kwargs["holder_bonus"], 50)


class HolderJoinBonusTests(unittest.IsolatedAsyncioTestCase):
    async def test_claimed_bonus_marks_holder_and_recalculates(self):
        with (
            patch(
                "services.holder_service.db.claim_holder_join_bonus",
                new=AsyncMock(return_value=True),
            ),
            patch(
                "services.holder_service.db.upsert_points",
                new=AsyncMock(),
            ) as upsert,
            patch.object(
                PointsService,
                "recalculate_points",
                new=AsyncMock(return_value=50),
            ) as recalculate,
        ):
            result = await HolderService.award_holder_join_bonus(1003)

        self.assertTrue(result)
        upsert.assert_awaited_once_with(1003, is_holder=True)
        recalculate.assert_awaited_once_with(1003)

    async def test_already_claimed_bonus_is_not_recalculated(self):
        with (
            patch(
                "services.holder_service.db.claim_holder_join_bonus",
                new=AsyncMock(return_value=False),
            ),
            patch.object(
                PointsService,
                "recalculate_points",
                new=AsyncMock(),
            ) as recalculate,
        ):
            result = await HolderService.award_holder_join_bonus(1004)

        self.assertFalse(result)
        recalculate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
