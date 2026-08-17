import os


def _int_set(value: str) -> set[int]:
    result = set()
    for item in (value or "").split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.add(int(item))
        except ValueError:
            continue
    return result


DEFAULT_ADMIN_IDS = {786080766, 734720997}
ADMIN_IDS = _int_set(os.getenv("ADMIN_IDS", "")) or DEFAULT_ADMIN_IDS
PRIMARY_ADMIN_ID = int(os.getenv("PRIMARY_ADMIN_ID", "786080766"))
HOLDER_CHAT_ID = int(os.getenv("HOLDER_CHAT_ID", "-1001944951957"))
