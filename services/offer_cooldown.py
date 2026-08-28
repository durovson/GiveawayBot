import os
import time


class OfferCooldown:
    _last: dict[int, float] = {}

    @classmethod
    def remaining(cls, user_id: int, listing_id: int) -> int:
        ttl = max(1, int(os.getenv("OTC_OFFER_COOLDOWN_SECONDS", "300")))
        left = ttl - (time.monotonic() - cls._last.get(user_id, 0))
        return max(0, int(left + 0.999))

    @classmethod
    def mark(cls, user_id: int, listing_id: int):
        cls._last[user_id] = time.monotonic()
