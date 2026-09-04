import html
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


MOSCOW_TZ = ZoneInfo("Europe/Moscow")
UTC_TZ = ZoneInfo("UTC")

_TIME_RE = r"(?P<hour>[01]?\d|2[0-3])[:.](?P<minute>[0-5]\d)"
_DATE_RE = r"(?P<day>0?[1-9]|[12]\d|3[01])[.\-/](?P<month>0?[1-9]|1[0-2])(?:[.\-/](?P<year>\d{2}|\d{4}))?"
_TIME_DATE = re.compile(rf"^\s*{_TIME_RE}(?:\s+|\s*,\s*){_DATE_RE}\s*$")
_DATE_TIME = re.compile(rf"^\s*{_DATE_RE}(?:\s+|\s*,\s*){_TIME_RE}\s*$")
_TIME_ONLY = re.compile(rf"^\s*{_TIME_RE}\s*$")
_URL_RE = re.compile(r"https?://[^\s,]+", re.IGNORECASE)


def parse_moscow_giveaway_time(value: str, now: datetime | None = None) -> datetime | None:
    """Parse a user-entered Moscow time and return the corresponding UTC instant."""
    if not isinstance(value, str):
        return None
    now_moscow = (now or datetime.now(MOSCOW_TZ)).astimezone(MOSCOW_TZ)
    match = _TIME_ONLY.fullmatch(value)
    explicit_date = False
    if not match:
        match = _TIME_DATE.fullmatch(value) or _DATE_TIME.fullmatch(value)
        explicit_date = match is not None
    if not match:
        return None

    parts = match.groupdict()
    try:
        if explicit_date:
            year_text = parts.get("year")
            year = now_moscow.year if not year_text else int(year_text)
            if year < 100:
                year += 2000
            local = datetime(
                year, int(parts["month"]), int(parts["day"]),
                int(parts["hour"]), int(parts["minute"]), tzinfo=MOSCOW_TZ,
            )
            if local <= now_moscow:
                return None
        else:
            local = now_moscow.replace(
                hour=int(parts["hour"]), minute=int(parts["minute"]),
                second=0, microsecond=0,
            )
            if local <= now_moscow:
                local += timedelta(days=1)
        return local.astimezone(UTC_TZ)
    except ValueError:
        return None


def format_prize_html(prize: object) -> str:
    """Embed the first URL into the text immediately preceding it."""
    raw = str(prize)
    match = _URL_RE.search(raw)
    if not match:
        return html.escape(raw)
    label = raw[:match.start()].strip()
    url = match.group(0)
    remainder = raw[match.end():]
    if not label:
        label = url
    return (
        f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>'
        f'{html.escape(remainder)}'
    )


def format_prizes_html(prizes: list[object], separator: str = ", ") -> str:
    return separator.join(format_prize_html(prize) for prize in prizes)


def format_moscow_datetime(value: datetime | str | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return html.escape(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC_TZ)
    return value.astimezone(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M MSK")
