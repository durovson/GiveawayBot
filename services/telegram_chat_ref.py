"""Utilities for accepting Telegram channel references in user-facing formats."""

from urllib.parse import urlsplit


_TELEGRAM_HOSTS = {
    "t.me",
    "www.t.me",
    "telegram.me",
    "www.telegram.me",
}


def _is_public_username(value: str) -> bool:
    """Return whether *value* can be used as a public Telegram username."""
    return (
        5 <= len(value) <= 32
        and all(ch.isascii() and (ch.isalnum() or ch == "_") for ch in value)
    )


def normalize_telegram_chat_ref(chat_id):
    """Normalize public t.me links to the ``@username`` form expected by Bot API.

    Numeric chat IDs and already-normalized ``@username`` values are returned
    unchanged. Private invite links (``t.me/+...`` / ``joinchat``) are deliberately
    left unchanged because Telegram cannot resolve them to a chat through getChat.
    """
    if not isinstance(chat_id, str):
        return chat_id

    raw = chat_id.strip()
    if not raw or raw.startswith("@") or raw.startswith("-"):
        return raw

    candidate = raw
    lower = candidate.lower()
    if lower.startswith(("t.me/", "www.t.me/", "telegram.me/", "www.telegram.me/")):
        candidate = f"https://{candidate}"

    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return raw

    hostname = (parsed.hostname or "").lower()
    if hostname not in _TELEGRAM_HOSTS:
        return raw

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return raw

    # Public post-preview links can be written as t.me/s/<username>/<message_id>.
    if parts[0].lower() == "s":
        if len(parts) < 2:
            return raw
        username = parts[1]
    else:
        username = parts[0]

    if username.startswith("+") or username.lower() in {"joinchat", "c"}:
        return raw

    username = username.lstrip("@")
    if not _is_public_username(username):
        return raw

    return f"@{username}"
