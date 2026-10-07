import asyncio
from types import SimpleNamespace

from handlers.store import _resolve_channel_link


class PublicLinkFallbackBot:
    async def get_chat(self, chat_id):
        assert chat_id == "@notapes"
        raise RuntimeError("temporary Telegram failure")


class PrivateChatBot:
    async def get_chat(self, chat_id):
        assert chat_id == "-1001234567890"
        return SimpleNamespace(
            id=-1001234567890,
            title="Partner Club",
            username=None,
            invite_link=None,
        )

    async def create_chat_invite_link(self, chat_id, name):
        assert chat_id == -1001234567890
        assert name == "Giveaway access"
        return SimpleNamespace(invite_link="https://t.me/+partnerInvite")


def test_public_tme_link_is_normalized_and_kept_as_direct_link():
    label, url = asyncio.run(
        _resolve_channel_link(PublicLinkFallbackBot(), "https://t.me/notapes")
    )

    assert label == "notapes"
    assert url == "https://t.me/notapes"


def test_private_partner_chat_gets_an_invite_link():
    label, url = asyncio.run(
        _resolve_channel_link(PrivateChatBot(), "-1001234567890")
    )

    assert label == "Partner Club"
    assert url == "https://t.me/+partnerInvite"

