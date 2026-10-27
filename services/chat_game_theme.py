"""Presentation only: the economy always stores RP, never a second currency."""

PUMPKIN_MODE = False

EMOJI = {
    "peach": ("🍑", "5258330865674494479"),
    "game": ("🎮", "5258508428212445001"),
    "alarm": ("🚨", "5316575892133132571"),
    "hourglass": ("⌛️", "5296482716567495148"),
    "money": ("💵", "5372874186010158207"),
    "warning": ("❗️", "5258382581375723416"),
    "pumpkin": ("🎃", "5368309348739074032"),
}


def emoji(name: str) -> str:
    fallback, emoji_id = EMOJI[name]
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def currency() -> str:
    return emoji("pumpkin") if PUMPKIN_MODE else "RP"
