import logging
import time
from typing import List, Dict, Optional

from database import db
from utils import normalize_wallet

logger = logging.getLogger(__name__)


class LeaderboardService:
    _cache: List[Dict] = []
    _cache_ts: float = 0
    TTL: int = 300

    @classmethod
    async def _load_holders(cls) -> List[Dict]:
        now = time.time()
        if cls._cache and (now - cls._cache_ts) < cls.TTL:
            return cls._cache
        holders = await db.get_latest_snapshot()
        if not holders:
            return []
        try:
            clean = []
            for row in holders:
                if not isinstance(row, dict):
                    continue
                wallet = row.get("wallet") or row.get("address") or row.get("owner")
                if not wallet:
                    continue
                clean.append(row)

            cls._cache = clean
            cls._cache_ts = now
        except Exception as e:
            logger.error(f"LEADERBOARD_CACHE_PARSE_FAILED: {e}")
            cls._cache = []
            cls._cache_ts = now
        return cls._cache

    @classmethod
    async def get_top(cls, limit: int = 10) -> List[Dict]:
        holders = await cls._load_holders()
        top = []
        for row in holders:
            wallet = row.get("wallet") or row.get("address") or row.get("owner")
            packs = row.get("packs") or row.get("packsCount") or row.get("count") or 0
            top.append({"wallet": wallet, "packs": packs})
            if len(top) >= limit:
                break
        for idx, row in enumerate(top, 1):
            row["rank"] = idx
        return top

    @classmethod
    async def get_wallet(cls, wallet: str) -> Optional[Dict]:
        holders = await cls._load_holders()
        target = normalize_wallet(wallet)
        if not target:
            return None
        for idx, row in enumerate(holders, 1):
            candidate = row.get("wallet") or row.get("address") or row.get("owner")
            if candidate and normalize_wallet(candidate) == target:
                packs = row.get("packs") or row.get("packsCount") or row.get("count") or 0
                return {"rank": idx, "wallet": candidate, "packs": packs}
        return None

    @classmethod
    async def get_rank(cls, telegram_id: int) -> Optional[Dict]:
        wallet = await db.get_user_wallet(telegram_id)
        if not wallet:
            return None
        return await cls.get_wallet(wallet)


    @classmethod
    def invalidate_cache(cls):
        cls._cache = []
        cls._cache_ts = 0
