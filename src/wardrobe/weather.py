"""Weather from Open-Meteo (free, no API key) and place-name geocoding."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
MET_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
USER_AGENT = "agi-wardrobe/0.1 (+https://github.com/noahljungberg/agi-wardrobe)"

log = logging.getLogger(__name__)

# WMO weather codes -> words
WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "showers", 81: "showers", 82: "heavy showers", 85: "snow showers", 86: "snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}
SNOW_CODES = {71, 73, 75, 77, 85, 86}


@dataclass
class Place:
    lat: float
    lon: float
    name: str | None
    tz: str | None = None


@dataclass
class DayWeather:
    place: str
    day: date
    hours: tuple[int, int]
    temp_min: float
    temp_max: float
    feels_min: float
    feels_max: float
    rain_prob_max: int
    rain_mm: float
    rain_hours: list[int]
    wind_max: float
    conditions: str
    snow: bool
    timezone: str = "UTC"
    hourly: list[dict[str, Any]] = field(default_factory=list)

    @property
    def wet(self) -> bool:
        return self.rain_prob_max >= 45 or self.rain_mm >= 1.0

    def text(self) -> str:
        parts = [f"{self.temp_min:.0f}–{self.temp_max:.0f}°C"]
        if self.feels_min < self.temp_min - 1.5:
            parts.append(f"feels like {self.feels_min:.0f}°")
        parts.append(self.conditions)
        if self.rain_hours:
            parts.append(f"{'snow' if self.snow else 'rain'} likely {_span(self.rain_hours)} ({self.rain_prob_max}%)")
        elif self.rain_prob_max >= 25:
            parts.append(f"{self.rain_prob_max}% chance of rain")
        if self.wind_max >= 12:
            parts.append(f"windy, gusts around {self.wind_max:.0f} m/s")
        return ", ".join(parts)



def _span(hours: list[int]) -> str:
    """[15, 16, 17] -> '15–18'."""
    if not hours:
        return ""
    ranges, start, prev = [], hours[0], hours[0]
    for h in hours[1:]:
        if h != prev + 1:
            ranges.append((start, prev))
            start = h
        prev = h
    ranges.append((start, prev))
    return ", ".join(f"{a:02d}–{b + 1:02d}" for a, b in ranges)



# MET Norway symbol codes -> the closest WMO code, so both sources summarise alike.
MET_SYMBOLS = [
    ("thunder", 95), ("heavysnow", 75), ("snowshowers", 85), ("snow", 73), ("sleet", 66),
    ("heavyrain", 65), ("rainshowers", 80), ("lightrain", 61), ("rain", 63), ("fog", 45),
    ("cloudy", 3), ("partlycloudy", 2), ("fair", 1), ("clearsky", 0),
]


def _met_code(symbol: str | None) -> int | None:
    if not symbol:
        return None
    for key, code in MET_SYMBOLS:
        if key in symbol:
            return code
    return None


def _offset_for(place: Place, when: datetime) -> timedelta:
    if place.tz:
        try:
            return when.astimezone(ZoneInfo(place.tz)).utcoffset() or timedelta(0)
        except ZoneInfoNotFoundError:
            pass
    return timedelta(hours=round(place.lon / 15))  # rough, no DST; only if the zone is unknown


class WeatherClient:
    """Open-Meteo first; MET Norway (api.met.no) if Open-Meteo fails."""

    def __init__(self, client: httpx.AsyncClient | None = None, ttl: float = 900):
        self._client = client
        self._ttl = ttl
        self._cache: dict[tuple, tuple[float, Any]] = {}

    async def _get(self, url: str, params: dict[str, Any]) -> Any:
        key = (url, tuple(sorted(params.items())))
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self._ttl:
            return hit[1]
        client = self._client or httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT})
        try:
            resp = await client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            data = resp.json()
        finally:
            if self._client is None:
                await client.aclose()
        self._cache[key] = (time.monotonic(), data)
        return data

    async def geocode(self, name: str) -> Place | None:
        """'San Francisco', 'Linköping, Sweden' or '58.41,15.62' -> Place."""
        name = name.strip()
        try:
            lat_s, lon_s = (p.strip() for p in name.split(","))
            return Place(float(lat_s), float(lon_s), None)
        except ValueError:
            pass
        query, _, country = name.partition(",")
        data = await self._get(GEOCODE_URL, {"name": query.strip(), "count": 5, "format": "json"})
        results = data.get("results") or []
        if country.strip():
            wanted = country.strip().lower()
            preferred = [
                r for r in results
                if wanted in (str(r.get("country", "")) + " " + str(r.get("country_code", ""))).lower()
                or wanted in str(r.get("admin1", "")).lower()
            ]
            results = preferred or results
        if not results:
            return None
        r = results[0]
        label = ", ".join(str(p) for p in (r.get("name"), r.get("country")) if p)
        return Place(float(r["latitude"]), float(r["longitude"]), label, r.get("timezone"))

    async def day(self, place: Place, which: str = "today", now: datetime | None = None) -> DayWeather:
        now = now or datetime.now(timezone.utc)
        label = place.name or f"{place.lat:.2f},{place.lon:.2f}"
        try:
            data = await self._get(
                FORECAST_URL,
                {
                    "latitude": round(place.lat, 2),
                    "longitude": round(place.lon, 2),
                    "hourly": "temperature_2m,apparent_temperature,precipitation_probability,precipitation,weather_code,wind_gusts_10m",
                    "wind_speed_unit": "ms",
                    "timezone": "auto",
                    "forecast_days": 3,
                },
            )
            rows, offset, tz = rows_from_open_meteo(data)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            log.warning("Open-Meteo failed (%r); using MET Norway", exc)
            data = await self._get(MET_URL, {"lat": round(place.lat, 2), "lon": round(place.lon, 2)})
            offset = _offset_for(place, now)
            rows, tz = rows_from_met(data, offset), place.tz or "UTC"
        return summarise_rows(rows, label, which, now.astimezone(timezone(offset)).replace(tzinfo=None), tz)


def rows_from_open_meteo(data: dict[str, Any]) -> tuple[list[dict[str, Any]], timedelta, str]:
    h = data["hourly"]
    rows = []
    for i, ts in enumerate(h["time"]):
        rows.append({
            "time": datetime.fromisoformat(ts),
            "temp": h["temperature_2m"][i],
            "feels": h["apparent_temperature"][i],
            "rain_prob": h["precipitation_probability"][i] or 0,
            "rain": h["precipitation"][i] or 0.0,
            "code": h["weather_code"][i],
            "gust": h["wind_gusts_10m"][i] or 0.0,
        })
    return rows, timedelta(seconds=int(data.get("utc_offset_seconds", 0))), str(data.get("timezone", "UTC"))


def rows_from_met(data: dict[str, Any], offset: timedelta) -> list[dict[str, Any]]:
    rows = []
    for entry in data["properties"]["timeseries"]:
        one_hour = entry["data"].get("next_1_hours")
        if not one_hour:
            continue  # beyond ~2.5 days MET only has 6-hour blocks
        inst = entry["data"]["instant"]["details"]
        details = one_hour.get("details", {})
        utc = datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
        rows.append({
            "time": (utc + offset).replace(tzinfo=None),
            "temp": inst.get("air_temperature"),
            "feels": inst.get("apparent_air_temperature", inst.get("air_temperature")),
            "rain_prob": details.get("probability_of_precipitation") or 0,
            "rain": details.get("precipitation_amount") or 0.0,
            "code": _met_code(one_hour.get("summary", {}).get("symbol_code")),
            "gust": inst.get("wind_speed_of_gust") or inst.get("wind_speed") or 0.0,
        })
    return rows


def summarise_rows(
    rows: list[dict[str, Any]], place_name: str, which: str, local_now: datetime, tz: str = "UTC"
) -> DayWeather:
    """Summarise the hours you're out: from now (or 07:00) until 22:00."""
    target = local_now.date() + timedelta(days=1 if which == "tomorrow" else 0)
    start_hour = 7 if which == "tomorrow" else max(7, min(local_now.hour, 21))
    end_hour = 22
    if which != "tomorrow" and local_now.hour >= 21:
        start_hour, end_hour = local_now.hour, 24
    rows = [
        {**r, "hour": r["time"].hour}
        for r in rows
        if r["time"].date() == target and start_hour <= r["time"].hour < end_hour and r["temp"] is not None
    ]
    if not rows:
        raise ValueError("no forecast hours for the requested day")
    for r in rows:
        if r["feels"] is None:
            r["feels"] = r["temp"]
    codes = [r["code"] for r in rows if r["code"] is not None]
    worst = max(codes, key=lambda c: (c >= 51, c)) if codes else 3
    rain_hours = [r["hour"] for r in rows if r["rain_prob"] >= 50 or r["rain"] >= 0.5]
    return DayWeather(
        place=place_name,
        day=target,
        hours=(rows[0]["hour"], rows[-1]["hour"] + 1),
        temp_min=min(r["temp"] for r in rows),
        temp_max=max(r["temp"] for r in rows),
        feels_min=min(r["feels"] for r in rows),
        feels_max=max(r["feels"] for r in rows),
        rain_prob_max=int(max(r["rain_prob"] for r in rows)),
        rain_mm=float(sum(r["rain"] for r in rows)),
        rain_hours=rain_hours,
        wind_max=float(max(r["gust"] for r in rows)),
        conditions=WMO.get(worst, "mixed"),
        snow=worst in SNOW_CODES,
        timezone=tz,
        hourly=[{k: v for k, v in r.items() if k != "time"} for r in rows],
    )
