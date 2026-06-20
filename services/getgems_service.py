import os
import aiohttp

COLLECTION_ADDRESS = "EQDwLDJcRXegHyvvRHXouGrUODuF0eagnWzLvUMUSTw8tv3Y"

GETGEMS_API_KEY = os.getenv("GETGEMS_API_KEY")

API_URL = (
    f"https://api.getgems.io/public-api/v1/collection/stats/"
    f"{COLLECTION_ADDRESS}"
)


def format_floor(value):
    try:
        return f"{int(float(value))}"
    except Exception:
        return "0"


def format_volume(value):
    try:
        value = float(value)

        if value >= 1000:
            return f"{value / 1000:.1f}K"

        return f"{value:.0f}"

    except Exception:
        return "0"


async def get_collection_stats():
    headers = {
        "accept": "application/json"
    }
    if GETGEMS_API_KEY:
        headers["Authorization"] = GETGEMS_API_KEY

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                API_URL,
                headers=headers,
                timeout=10
            ) as response:

                data = await response.json()

                stats = data["response"]

                return {
                    "floor": format_floor(
                        stats["floorPrice"]
                    ),
                    "volume": format_volume(
                        stats["totalVolumeSold"]
                    )
                }

    except Exception:
        return {
            "floor": "?",
            "volume": "?"
        }
