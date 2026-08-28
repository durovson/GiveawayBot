import os
import unittest

os.environ.setdefault("BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")

import loader
from database import db
from services.gram_service import GramDepositService


WALLET = "UQBmhVw9CcumCuhFnVM3vUepTpiXT5m6ffTSeZ990ySvXSf7"
MASTER = "EQC47093oX5Xhb0xuk2lCr2RhS8rj-vul61u4W2UH5ORmG_O"
EVENT_ID = "09bdca46f834ab8b332b054684820890d9e174c07008ee58ce62b2c095211ee3"


class FakeResponse:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


class GramDepositServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_gram_is_credited_and_401_retries_publicly(self):
        event = {
            "event_id": EVENT_ID,
            "in_progress": False,
            # TonAPI flags this real transaction heuristically; action checks
            # remain authoritative for deposit processing.
            "is_scam": True,
            "actions": [{
                "type": "TonTransfer",
                "status": "ok",
                "TonTransfer": {
                    "sender": {"address": "0:e59907e770b4c7a7f71e23a833f1e035f704367226bdcacb2460ef9903520036"},
                    "recipient": {"address": "0:66855c3d09cba60ae8459d5337bd47a94e98974f99ba7df4d2799f7dd324af5d"},
                    "amount": 100_000_000,
                    "comment": "@not_jammm",
                },
            }],
        }
        session = FakeSession([
            FakeResponse(401, {}),
            FakeResponse(200, {"events": [event]}),
        ])
        claims = []

        async def get_setting(name):
            return "10" if name == "gram_rp_per_gram" else None

        async def claim(payload):
            claims.append(payload)
            return {"ok": True}

        old_session = loader.http_session
        old_get_setting = db.get_setting
        old_claim = db.claim_gram_deposit
        old_env = {key: os.environ.get(key) for key in (
            "GRAM_DEPOSIT_WALLET", "GRAM_JETTON_MASTER", "TONAPI_KEY"
        )}
        try:
            loader.http_session = session
            db.get_setting = get_setting
            db.claim_gram_deposit = claim
            os.environ["GRAM_DEPOSIT_WALLET"] = WALLET
            os.environ["GRAM_JETTON_MASTER"] = MASTER
            os.environ["TONAPI_KEY"] = "Bearer rejected-key"

            credited = await GramDepositService.sync()
        finally:
            loader.http_session = old_session
            db.get_setting = old_get_setting
            db.claim_gram_deposit = old_claim
            for key, value in old_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

        self.assertEqual(credited, 1)
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]["p_event_id"], EVENT_ID)
        self.assertEqual(claims[0]["p_username"], "@not_jammm")
        self.assertEqual(claims[0]["p_amount_gram"], "0.1")
        self.assertEqual(claims[0]["p_rp_amount"], 1)
        self.assertEqual(claims[0]["p_raw_data"]["transfer_kind"], "native")
        self.assertTrue(claims[0]["p_raw_data"]["event_is_scam"])
        self.assertEqual(session.requests[0][1]["headers"], {"Authorization": "Bearer rejected-key"})
        self.assertNotIn("headers", session.requests[1][1])


if __name__ == "__main__":
    unittest.main()
