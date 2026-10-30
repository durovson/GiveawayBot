"""Premium assets scoped to Arena, including its private narration."""
import re

ASSETS = {
    '🚨': ('🚨', '5316575892133132571'),
    '🎯': ('🎯', '6032949275732742941'),
    '💵': ('💵', '5870478797593120516'),
    '⏳': ('⏳', '5373221902267457807'),
    '🏁': ('👾', '5316930493223025689'),
    '🥇': ('🥇', '5961051261204696786'),
    '⚰️': ('📛', '5256054975389247793'),
    '⚡️': ('⚡️', '5316702348855227508'),
    '🍌': ('🍌', '4969786548888275044'),
    '🛡': ('🛡', '6032636795387121097'),
    '👾': ('👾', '5337037846475720165'),
    '📡': ('🏳️', '5253830568876977751'),
    '⚠️': ('⚠️', '5881702736843511327'),
    '🎃': ('🎃', '5368309348739074032'),
    '☠️': ('☠️', '5372865660500067203'),
}
_TOKENS = re.compile('|'.join(re.escape(k) for k in sorted(ASSETS, key=len, reverse=True)))
_PROTECTED = re.compile(r'(<tg-emoji\b[^>]*>.*?</tg-emoji>|<[^>]+>)', re.DOTALL)


def arena_emojis(text):
    parts = _PROTECTED.split(text)
    def replace(match):
        glyph, asset = ASSETS[match.group()]
        return f'<tg-emoji emoji-id="{asset}">{glyph}</tg-emoji>'
    for i in range(0, len(parts), 2):
        parts[i] = _TOKENS.sub(replace, parts[i])
    return ''.join(parts)
