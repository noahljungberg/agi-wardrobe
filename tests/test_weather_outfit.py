from datetime import date, datetime, timedelta, timezone

from wardrobe.catalog import Catalog
from wardrobe.outfit import compute_targets, pick_candidates, slot_of
from wardrobe.weather import DayWeather, rows_from_met, rows_from_open_meteo, summarise_rows


def _open_meteo(day: str, temps, probs):
    hours = [f"{day}T{h:02d}:00" for h in range(24)]
    return {
        "utc_offset_seconds": 7200, "timezone": "Europe/Stockholm",
        "hourly": {
            "time": hours, "temperature_2m": temps, "apparent_temperature": [t - 3 for t in temps],
            "precipitation_probability": probs, "precipitation": [0.8 if p >= 60 else 0 for p in probs],
            "weather_code": [80 if p >= 60 else 3 for p in probs], "wind_gusts_10m": [5] * 24,
        },
    }


def test_summarise_open_meteo_window_and_rain():
    temps = [5 + h * 0.3 for h in range(24)]
    probs = [70 if 15 <= h < 18 else 10 for h in range(24)]
    rows, offset, tz = rows_from_open_meteo(_open_meteo("2026-10-09", temps, probs))
    now = datetime(2026, 10, 9, 7, 30)  # local
    w = summarise_rows(rows, "Linköping", "today", now, tz)
    assert w.hours == (7, 22)
    assert w.rain_hours == [15, 16, 17]
    assert "rain likely 15–18" in w.text()
    assert w.wet and w.conditions == "showers"


def test_met_rows_use_offset():
    data = {"properties": {"timeseries": [
        {"time": "2026-10-09T10:00:00Z", "data": {
            "instant": {"details": {"air_temperature": 8.0, "apparent_air_temperature": 5.0, "wind_speed_of_gust": 9.0}},
            "next_1_hours": {"summary": {"symbol_code": "lightrainshowers_day"}, "details": {"precipitation_amount": 0.6, "probability_of_precipitation": 60}}}},
    ]}}
    rows = rows_from_met(data, timedelta(hours=2))
    assert rows[0]["time"].hour == 12 and rows[0]["code"] == 80 and rows[0]["feels"] == 5.0


def _weather(feels_min, feels_max, rain=0):
    return DayWeather("x", date.today(), (8, 22), feels_min + 2, feels_max + 2, feels_min, feels_max, rain,
                      2.0 if rain > 50 else 0, [15] if rain > 50 else [], 4, "x", False)


def test_targets_cold_wet_vs_hot():
    cold = compute_targets(_weather(-2, 4, rain=80), "office")
    assert cold.outer == "yes" and cold.outer_warmth == 4 and cold.mid == "yes" and cold.wet
    assert cold.formality == 3 and "scarf" in cold.accessories
    hot = compute_targets(_weather(24, 30), None)
    assert hot.outer == "no" and hot.mid == "no" and hot.bottoms_warmth == 0


def test_candidates_prefer_rainproof_and_skip_anchor_slot(demo_dir):
    items = Catalog(demo_dir).items()
    anchor = next(i for i in items if i.id == "mango-corduroy-trousers-regular-fit-beige")
    c = pick_candidates(items, _weather(4, 9, rain=80), None, [anchor], {}, date.today())
    assert c.by_slot["bottoms"] == []
    assert c.by_slot["outerwear"][0][0].rain_ok
    assert all(slot_of(i) == "shoes" for i, _ in c.by_slot["shoes"])


def test_recently_worn_tops_drop(demo_dir):
    items = Catalog(demo_dir).items()
    today = date.today()
    fresh = pick_candidates(items, _weather(14, 18), None, [], {}, today)
    top = fresh.by_slot["base"][0][0]
    worn = pick_candidates(items, _weather(14, 18), None, [], {top.id: today - timedelta(days=1)}, today)
    assert worn.by_slot["base"][0][0].id != top.id
