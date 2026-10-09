from datetime import datetime, timedelta

from wardrobe.weather import rows_from_met, rows_from_open_meteo, summarise_rows


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
