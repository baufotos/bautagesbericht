import httpx

from app.config import settings

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


async def geocode_address(adresse: str) -> tuple[float | None, float | None]:
    if not adresse.strip():
        return None, None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                NOMINATIM_URL,
                params={"q": adresse, "format": "json", "limit": 1},
                headers={"User-Agent": settings.nominatim_user_agent},
            )
            resp.raise_for_status()
            data = resp.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    return None, None
