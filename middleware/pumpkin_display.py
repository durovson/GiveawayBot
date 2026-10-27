"""Seasonal display at the Telegram boundary; balances and callbacks stay RP."""
import re

from aiogram.client.session.middlewares.base import BaseRequestMiddleware

from services import chat_game_theme


# Never rewrite destinations, HTML attributes, wallets or machine-readable code.
_PROTECTED = re.compile(
    r'(<(?:code|pre)\b[^>]*>.*?</(?:code|pre)>|<[^>]+>|'
    r'(?:https?|tg|ton|tonkeeper)://[^\s<>]+)', re.IGNORECASE | re.DOTALL
)
_UNIT = re.compile(r'(?<![\w@/])(?:RP|РП)(?!\w)')


def pumpkin_text(value):
    if not isinstance(value, str) or not chat_game_theme.PUMPKIN_MODE:
        return value
    pieces = _PROTECTED.split(value)
    for i in range(0, len(pieces), 2):
        # Both RP and 🎃 occupy two UTF-16 code units. Telegram entity
        # offsets/lengths therefore remain unchanged, including after emojis.
        pieces[i] = _UNIT.sub('🎃', pieces[i])
    return ''.join(pieces)


def _markup(markup):
    for field in ('inline_keyboard', 'keyboard'):
        rows = getattr(markup, field, None)
        if rows is None:
            continue
        changed = False
        result = []
        for row in rows:
            updated_row = []
            for button in row:
                text = pumpkin_text(button.text)
                if text != button.text:
                    button = button.model_copy(update={'text': text})
                    changed = True
                updated_row.append(button)
            result.append(updated_row)
        return markup.model_copy(update={field: result}) if changed else markup
    return markup


def _caption(media):
    text = getattr(media, 'caption', None)
    updated = pumpkin_text(text)
    return media.model_copy(update={'caption': updated}) if updated != text else media


def themed_request(method):
    if not chat_game_theme.PUMPKIN_MODE:
        return method
    updates = {}
    for field in ('text', 'caption', 'description', 'short_description'):
        value = getattr(method, field, None)
        updated = pumpkin_text(value)
        if updated != value:
            updates[field] = updated
    markup = getattr(method, 'reply_markup', None)
    if markup is not None:
        updated = _markup(markup)
        if updated is not markup:
            updates['reply_markup'] = updated
    media = getattr(method, 'media', None)
    if isinstance(media, list):
        updated = [_caption(item) for item in media]
        if any(a is not b for a, b in zip(media, updated)):
            updates['media'] = updated
    elif media is not None and hasattr(media, 'caption'):
        updated = _caption(media)
        if updated is not media:
            updates['media'] = updated
    commands = getattr(method, 'commands', None)
    if isinstance(commands, list):
        updated = [item.model_copy(update={'description': pumpkin_text(item.description)})
                   if pumpkin_text(item.description) != item.description else item for item in commands]
        if any(a is not b for a, b in zip(commands, updated)):
            updates['commands'] = updated
    return method.model_copy(update=updates) if updates else method


class PumpkinDisplayMiddleware(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        return await make_request(bot, themed_request(method))
