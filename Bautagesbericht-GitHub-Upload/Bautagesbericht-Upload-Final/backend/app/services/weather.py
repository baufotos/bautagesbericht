"""Wetterdaten vom Bright Sky Dienst (DWD-Daten, kein API-Key nötig).

Die Aufbereitung folgt exakt dem HPP-Referenzformat:
  Station    "DWD Hamburg Fuhlsbüttel"        (Bright Sky liefert "Hamburg-Fuhlsbüttel")
  Temp. Max  Maximum der Stundentemperaturen
  Temp. Min  Minimum der Stundentemperaturen
  Regen      Summe des Stundenniederschlags
  Wind Max   Maximum der Windböen, umgerechnet in m/s
  Schnee     Bright Sky liefert keine Schneehöhe -> 0
Stundenwerte werden auf die ungeraden Stunden 01, 03 … 23 verdichtet,
weil die HPP-Vorlage genau zwölf Spalten dafür vorsieht.
"""

import httpx

BRIGHT_SKY_URL = "https://api.brightsky.dev/weather"

# Bright Sky liefert Windgeschwindigkeiten in km/h.
KMH_PER_MS = 3.6

# Spalten der Stundentabelle in der HPP-Vorlage.
REPORT_HOURS = list(range(1, 24, 2))


def _kmh_to_ms(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value / KMH_PER_MS, 1)


def _format_station(name: str) -> str:
    """'Hamburg-Fuhlsbüttel' -> 'DWD Hamburg Fuhlsbüttel'."""
    if not name:
        return ""
    clean = name.replace("-", " ").strip()
    return f"DWD {clean}"


def _hour_of(timestamp: str) -> int | None:
    if "T" not in timestamp:
        return None
    try:
        return int(timestamp.split("T", 1)[1][:2])
    except (ValueError, IndexError):
        return None


async def fetch_weather(lat: float, lon: float, date_str: str) -> dict | None:
    """Tageswetter für einen Standort. Gibt None zurück, wenn keine Daten vorliegen."""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                BRIGHT_SKY_URL,
                params={"lat": lat, "lon": lon, "date": date_str},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    entries = data.get("weather") or []
    if not entries:
        return None

    sources = data.get("sources") or []
    station_name = sources[0].get("station_name", "") if sources else ""

    # Für die Stundentabelle zählen nur die Stunden des angefragten Tages.
    # Bright Sky liefert zusätzlich 00:00 des Folgetags; dieser Randwert gehört
    # zum Tagesfenster und geht in die Extremwerte ein (so rechnet auch HPP).
    by_hour: dict[int, dict] = {}
    for entry in entries:
        ts = entry.get("timestamp", "")
        if not ts.startswith(date_str):
            continue
        hour = _hour_of(ts)
        if hour is not None:
            by_hour[hour] = entry

    if not by_hour:
        return None

    temps = [e["temperature"] for e in entries if e.get("temperature") is not None]
    precip = [e["precipitation"] for e in entries if e.get("precipitation") is not None]
    gusts = [e["wind_gust_speed"] for e in entries if e.get("wind_gust_speed") is not None]
    winds = [e["wind_speed"] for e in entries if e.get("wind_speed") is not None]

    # HPP weist "Wind Max" als Böenmaximum aus; ohne Böendaten fällt es auf den
    # mittleren Wind zurück.
    wind_max_source = gusts or winds

    stundenwerte = []
    for hour in REPORT_HOURS:
        entry = by_hour.get(hour)
        if entry is None:
            stundenwerte.append({"stunde": hour})
            continue
        stundenwerte.append({
            "stunde": hour,
            "temperatur_c": entry.get("temperature"),
            "niederschlag_mm": entry.get("precipitation"),
            "wind_ms": _kmh_to_ms(entry.get("wind_speed")),
            "wind_grad": entry.get("wind_direction"),
            "bewoelkung_prozent": entry.get("cloud_cover"),
            "icon": entry.get("icon"),
        })

    return {
        "station": _format_station(station_name),
        "temp_max_c": round(max(temps), 1) if temps else None,
        "temp_min_c": round(min(temps), 1) if temps else None,
        "regen_mm": round(sum(precip), 1) if precip else None,
        "wind_max_ms": _kmh_to_ms(max(wind_max_source)) if wind_max_source else None,
        "schnee_cm": 0,
        "stundenwerte": stundenwerte,
    }
