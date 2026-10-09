# Weather and places

Status: complete

## Purpose

Turns a place into "what the day will feel like while you're out": temperature
and feels-like range, rain hours and probability, gusts, conditions, for the
local hours from now (or 07:00) to 22:00. Also geocodes place names.

## Public API

- `WeatherClient(client=None, ttl=900)`
  - `geocode(name) -> Place | None`: accepts "City", "City, Country" or
    "lat,lon"; returns an IANA `tz` when known.
  - `day(place, which="today"|"tomorrow", now=None) -> DayWeather`: Open-Meteo
    first, MET Norway if that fails.
- `Place(lat, lon, name, tz=None)`
- `DayWeather`: `temp_min/max`, `feels_min/max`, `rain_prob_max`, `rain_mm`,
  `rain_hours`, `wind_max` (gusts, m/s), `conditions`, `snow`, `hours`,
  `.wet`, `.text()` ("7–12°C, feels like 3°, showers, rain likely 15–18 (70%)")
- `rows_from_open_meteo(data)`, `rows_from_met(data, offset)`,
  `summarise_rows(rows, place, which, local_now, tz)`: pure functions, tested
  with fixtures.

## Implementation files

- `src/wardrobe/weather.py`

## Dependencies

- Allowed: `httpx`, `zoneinfo`.
- Forbidden: every other `wardrobe` module (layer 0).

## Constraints

- Responses are cached in memory for 15 minutes per URL and params.
- MET Norway requires an identifying `User-Agent` (`USER_AGENT`). Keep it.
- With MET and an unknown time zone, the UTC offset is approximated from
  longitude (no daylight saving time).
- Free APIs, no keys. Open-Meteo rate-limits shared datacenter IPs (429), which
  is why the fallback exists.

## Tests

- `tests/test_weather.py`: Open-Meteo window and rain hours, MET row
  conversion with offset. Tools use `FakeWeather` (`tests/conftest.py`).

## Non-goals

- No multi-day forecasts beyond "tomorrow", no alerts, no UV or pollen.
- No reverse geocoding: the phone sends the city name with its coordinates.
