"""Погода для world_context и импульсов: OpenWeatherMap или Open-Meteo (без ключа)."""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

logger = logging.getLogger("iskra.sensors.weather")

OWM_URL = "https://api.openweathermap.org/data/2.5/weather"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"

WeatherProvider = Literal["openweather", "open_meteo"]


def classify_weather(main: str, wid: int) -> tuple[dict[str, float], str]:
    """OpenWeatherMap condition → (дельты по переменным состояния, краткая строка для промпта)."""
    m = (main or "").upper()
    if 200 <= wid <= 232 or m == "THUNDERSTORM":
        return {"arousal": 0.20}, "погода: гроза"
    if (
        300 <= wid <= 321
        or 500 <= wid <= 531
        or m in ("DRIZZLE", "RAIN")
    ):
        return {"valence": -0.08, "nostalgia": 0.15}, "погода: дождь или морось"
    if 600 <= wid <= 622 or m == "SNOW":
        return {"nostalgia": 0.10}, "погода: снег"
    if wid == 800 or m == "CLEAR":
        return {"valence": 0.10}, "погода: ясно"
    return {}, "погода: облачно или смешанные условия"


def classify_wmo_weather_code(code: int) -> tuple[dict[str, float], str]:
    """Код погоды WMO (Open-Meteo) → те же семантические классы, что и для OpenWeather."""
    if code in (95, 96, 99):
        return {"arousal": 0.20}, "погода: гроза"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return {"valence": -0.08, "nostalgia": 0.15}, "погода: дождь"
    if code in (51, 53, 55, 56, 57):
        return {"valence": -0.08, "nostalgia": 0.15}, "погода: морось"
    if code in (71, 73, 75, 77, 85, 86):
        return {"nostalgia": 0.10}, "погода: снег"
    if code == 0:
        return {"valence": 0.10}, "погода: ясно"
    return {}, "погода: облачно или смешанные условия"


async def _open_meteo_resolve_coords(
    *,
    city: str | None,
    lat: float | None,
    lon: float | None,
    client: httpx.AsyncClient,
    timeout: float,
) -> tuple[float, float, str] | None:
    if lat is not None and lon is not None:
        return float(lat), float(lon), ""
    q = (city or "Moscow").strip()
    if not q:
        q = "Moscow"
    try:
        r = await client.get(
            OPEN_METEO_GEOCODE,
            params={"name": q, "count": 1, "language": "ru"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        if not results:
            logger.warning("open-meteo geocode: нет результатов для %r", q)
            return None
        hit = results[0]
        plat = float(hit["latitude"])
        plon = float(hit["longitude"])
        label = str(hit.get("name") or q)
        adm = hit.get("admin1")
        cc = hit.get("country_code")
        if adm:
            label = f"{label}, {adm}"
        if cc:
            label = f"{label} ({cc})"
        return plat, plon, label
    except Exception as e:
        logger.warning("open-meteo geocode failed: %s", e)
        return None


async def fetch_openweather_summary(
    *,
    api_key: str,
    city: str | None,
    lat: float | None,
    lon: float | None,
    client: httpx.AsyncClient,
    timeout: float = 12.0,
) -> tuple[dict[str, float], str] | None:
    params: dict[str, Any] = {"appid": api_key, "units": "metric"}
    if lat is not None and lon is not None:
        params["lat"] = lat
        params["lon"] = lon
    else:
        params["q"] = city or "Moscow"

    try:
        r = await client.get(OWM_URL, params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("weather_sensor (OWM): запрос не удался: %s", e)
        return None

    try:
        w0 = (data.get("weather") or [{}])[0]
        main = str(w0.get("main") or "")
        wid = int(w0.get("id") or 0)
        desc = str(w0.get("description") or "")
        place = str(data.get("name") or "")
        deltas, summary = classify_weather(main, wid)
        extra = f"{summary}"
        if desc:
            extra += f" ({desc})"
        if place:
            extra += f", {place}"
        return deltas, extra
    except Exception as e:
        logger.warning("weather_sensor (OWM): разбор JSON: %s", e)
        return None


async def fetch_open_meteo_summary(
    *,
    city: str | None,
    lat: float | None,
    lon: float | None,
    client: httpx.AsyncClient,
    timeout: float = 12.0,
) -> tuple[dict[str, float], str] | None:
    resolved = await _open_meteo_resolve_coords(
        city=city, lat=lat, lon=lon, client=client, timeout=timeout
    )
    if resolved is None:
        return None
    plat, plon, place_hint = resolved
    try:
        r = await client.get(
            OPEN_METEO_FORECAST,
            params={
                "latitude": plat,
                "longitude": plon,
                "current": "temperature_2m,weather_code,relative_humidity_2m",
                "timezone": "auto",
            },
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.warning("weather_sensor (Open-Meteo): запрос не удался: %s", e)
        return None

    try:
        cur = data.get("current") or {}
        code = int(cur.get("weather_code") or -1)
        temp = cur.get("temperature_2m")
        deltas, summary = classify_wmo_weather_code(code)
        parts = [summary]
        if isinstance(temp, (int, float)):
            parts.append(f"{float(temp):.1f}°C")
        if code >= 0:
            parts.append(f"WMO {code}")
        if place_hint:
            parts.append(place_hint)
        return deltas, ", ".join(parts)
    except Exception as e:
        logger.warning("weather_sensor (Open-Meteo): разбор JSON: %s", e)
        return None


async def fetch_weather_summary(
    *,
    provider: WeatherProvider,
    api_key: str,
    city: str | None,
    lat: float | None,
    lon: float | None,
    client: httpx.AsyncClient,
    timeout: float = 12.0,
) -> tuple[dict[str, float], str] | None:
    if provider == "open_meteo":
        return await fetch_open_meteo_summary(
            city=city, lat=lat, lon=lon, client=client, timeout=timeout
        )
    return await fetch_openweather_summary(
        api_key=api_key,
        city=city,
        lat=lat,
        lon=lon,
        client=client,
        timeout=timeout,
    )
