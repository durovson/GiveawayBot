"""Seasonal display at the Telegram boundary; balances and callbacks stay RP."""
import logging
import re

from aiogram.client.default import Default
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import MessageEntity

from services import chat_game_theme


# Never rewrite destinations, HTML attributes, wallets or machine-readable code.
_PROTECTED = re.compile(
    r'(<(?:code|pre|tg-emoji)\b[^>]*>.*?</(?:code|pre|tg-emoji)>|<[^>]+>|'
    r'(?:https?|tg|ton|tonkeeper)://[^\s<>]+)', re.IGNORECASE | re.DOTALL
)
_UNIT = re.compile(r'(?<![\w@/])(?:RP|РП)(?!\w)|🎃')
PUMPKIN_ID = '5368309348739074032'
PUMPKIN_HTML = f'<tg-emoji emoji-id="{PUMPKIN_ID}">🎃</tg-emoji>'
logger = logging.getLogger(__name__)


def pumpkin_text(value, *, rich=False, force_plain=False, protected_entities=()):
    if not isinstance(value, str) or not chat_game_theme.PUMPKIN_MODE:
        return value
    if force_plain:
        value = re.sub(r'</?tg-emoji\b[^>]*>', '', value)
    pieces = _PROTECTED.split(value)
    cursor = 0
    for i, piece in enumerate(pieces):
        # Both RP and 🎃 occupy two UTF-16 code units. Telegram entity
        # offsets/lengths therefore remain unchanged, including after emojis.
        if i % 2 == 0:
            def replacement(match):
                offset = len(value[:cursor + match.start()].encode('utf-16-le')) // 2
                if any(e.offset <= offset < e.offset + e.length and e.type in {
                    'custom_emoji', 'code', 'pre', 'url', 'mention', 'email'
                } for e in protected_entities):
                    return match.group()
                return PUMPKIN_HTML if rich and not force_plain else '🎃'
            pieces[i] = _UNIT.sub(replacement, piece)
        cursor += len(piece)
    return ''.join(pieces)


def _markup(markup, *, force_plain=False):
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
                changes = {}
                if '🎃' in text and not force_plain:
                    # Telegram supports one leading premium icon per button,
                    # not custom-emoji HTML embedded in a button's text.
                    text = text.replace('🎃', '').strip() or '•'
                    changes['icon_custom_emoji_id'] = PUMPKIN_ID
                elif force_plain and getattr(button, 'icon_custom_emoji_id', None):
                    changes['icon_custom_emoji_id'] = None
                if text != button.text:
                    changes['text'] = text
                if changes:
                    button = button.model_copy(update=changes)
                    changed = True
                updated_row.append(button)
            result.append(updated_row)
        return markup.model_copy(update={field: result}) if changed else markup
    return markup


def _body(model, bot=None, *, force_plain=False):
    changes = {}
    mode = getattr(model, 'parse_mode', None)
    if isinstance(mode, Default):
        mode = getattr(getattr(bot, 'default', None), 'parse_mode', 'HTML')
    for field, entity_field in (('text', 'entities'), ('caption', 'caption_entities')):
        value = getattr(model, field, None)
        if not isinstance(value, str):
            continue
        entities = getattr(model, entity_field, None)
        rich = mode == 'HTML' and not entities
        updated = pumpkin_text(value, rich=rich, force_plain=force_plain,
                               protected_entities=entities or ())
        if updated != value:
            changes[field] = updated
        if force_plain and entities:
            changes[entity_field] = [e for e in entities if e.type != 'custom_emoji']
        elif not rich and hasattr(model, entity_field) and (mode is None or entities):
            # Emoji and RP both occupy two UTF-16 units, so all original
            # offsets/lengths stay valid when adding premium emoji entities.
            result = list(entities or [])
            protected = [(m.start(), m.end()) for m in _PROTECTED.finditer(value)]
            for match in _UNIT.finditer(value):
                if any(start <= match.start() < end for start, end in protected):
                    continue
                offset = len(value[:match.start()].encode('utf-16-le')) // 2
                if any(e.offset <= offset < e.offset + e.length and e.type in {
                    'custom_emoji', 'code', 'pre', 'url', 'mention', 'email'
                } for e in result):
                    continue
                result.append(MessageEntity(type='custom_emoji', offset=offset, length=2,
                                            custom_emoji_id=PUMPKIN_ID))
            if result != list(entities or []):
                changes[entity_field] = sorted(result, key=lambda e: (e.offset, -e.length))
                if entities and mode is not None:
                    changes['parse_mode'] = None
    return changes


def themed_request(method, bot=None, *, force_plain=False):
    if not chat_game_theme.PUMPKIN_MODE:
        return method
    updates = _body(method, bot, force_plain=force_plain)
    for field in ('description', 'short_description'):
        value = getattr(method, field, None)
        updated = pumpkin_text(value)
        if updated != value:
            updates[field] = updated
    markup = getattr(method, 'reply_markup', None)
    if markup is not None:
        updated = _markup(markup, force_plain=force_plain)
        if updated is not markup:
            updates['reply_markup'] = updated
    media = getattr(method, 'media', None)
    if isinstance(media, list):
        updated = [item.model_copy(update=changes) if (changes := _body(item, bot, force_plain=force_plain)) else item
                   for item in media]
        if any(a is not b for a, b in zip(media, updated)):
            updates['media'] = updated
    elif media is not None and hasattr(media, 'caption'):
        changes = _body(media, bot, force_plain=force_plain)
        if changes:
            updates['media'] = media.model_copy(update=changes)
    commands = getattr(method, 'commands', None)
    if isinstance(commands, list):
        updated = [item.model_copy(update={'description': pumpkin_text(item.description)})
                   if pumpkin_text(item.description) != item.description else item for item in commands]
        if any(a is not b for a, b in zip(commands, updated)):
            updates['commands'] = updated
    return method.model_copy(update=updates) if updates else method


class PumpkinDisplayMiddleware(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):
        try:
            return await make_request(bot, themed_request(method, bot))
        except TelegramBadRequest as error:
            if not chat_game_theme.PUMPKIN_MODE or not any(marker in str(error).lower() for marker in ('document_invalid', 'custom emoji', 'custom_emoji')):
                raise
            # Only retry a definite Telegram rejection, never a timeout or an
            # unknown send outcome. Do not let global theming re-add the same
            # rejected premium emoji during the existing text fallback.
            logger.warning('Telegram rejected premium emoji; using plain fallback')
            return await make_request(bot, themed_request(method, bot, force_plain=True))
