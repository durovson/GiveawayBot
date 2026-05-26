from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class User:
    telegram_id: int
    wallet_address: Optional[str] = None


@dataclass
class Giveaway:
    id: int
    creator_id: int
    chat_id: int
    title: str
    mode: str
    value: Any
    winners_count: int
    status: str
    message_id: Optional[int] = None
    created_at: Optional[datetime] = None


@dataclass
class Participant:
    giveaway_id: int
    user_id: int
    username: Optional[str] = None


@dataclass
class Winner:
    giveaway_id: int
    user_id: int
    username: Optional[str] = None
    prize: Optional[str] = None


@dataclass
class Notification:
    id: int
    chat_id: int
    message_text: str
    is_active: bool = True
