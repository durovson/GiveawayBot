"""Existing premium-emoji assets, reused by the RP and Arena interfaces."""

TOKEN_MODE = True

EMOJI = {
    "peach": ("🍑", "5258330865674494479"),
    "game": ("🎮", "5258508428212445001"),
    "store": ("🏪", "5983399041197675256"),
    "alarm": ("🚨", "5316575892133132571"),
    "hourglass": ("⌛️", "5296482716567495148"),
    "money": ("💵", "5372874186010158207"),
    "warning": ("❗️", "5258382581375723416"),
    "token": ("🪙", "5318972874726339331"),
}


def emoji(name: str) -> str:
    fallback, emoji_id = EMOJI[name]
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def currency() -> str:
    return emoji("token") if TOKEN_MODE else "RP"
