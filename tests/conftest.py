from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from wardrobe.config import Config
from wardrobe.demo import make_demo
from wardrobe.weather import DayWeather, Place, WeatherClient


class FakeWeather(WeatherClient):
    """Fixed forecast so tests don't touch the network."""

    def __init__(self, temp: float = 7, feels: float = 3, rain_prob: int = 70):
        super().__init__()
        self.temp, self.feels, self.rain_prob = temp, feels, rain_prob

    async def geocode(self, name: str) -> Place | None:
        if "nowhere" in name.lower():
            return None
        if "san francisco" in name.lower():
            return Place(37.77, -122.42, "San Francisco, United States", "America/Los_Angeles")
        return Place(58.41, 15.62, "Linköping, Sweden", "Europe/Stockholm")

    async def day(self, place: Place, which: str = "today", now: datetime | None = None) -> DayWeather:
        return DayWeather(
            place=place.name or "here", day=date.today(), hours=(8, 22),
            temp_min=self.temp, temp_max=self.temp + 5, feels_min=self.feels, feels_max=self.feels + 5,
            rain_prob_max=self.rain_prob, rain_mm=3.0 if self.rain_prob > 50 else 0.0,
            rain_hours=[15, 16, 17] if self.rain_prob > 50 else [], wind_max=6,
            conditions="showers" if self.rain_prob > 50 else "partly cloudy", snow=False,
        )


@pytest.fixture
def demo_dir(tmp_path: Path) -> Path:
    make_demo(tmp_path / "wardrobe")
    return tmp_path / "wardrobe"


@pytest.fixture
def config(tmp_path: Path, demo_dir: Path) -> Config:
    return Config.from_env({
        "WARDROBE_DIR": str(demo_dir),
        "WARDROBE_STATE_DIR": str(tmp_path / "state"),
        "WARDROBE_AUTH": "none",
    })
