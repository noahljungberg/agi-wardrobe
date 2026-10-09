"""Pick weather-appropriate candidates per outfit slot.

The server narrows the wardrobe down; the model (which sees the photos)
makes the actual styling call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from wardrobe.catalog import Item
from wardrobe.weather import DayWeather

SLOTS = ("outerwear", "mid", "base", "bottoms", "shoes", "accessories")
SLOT_TITLES = {
    "outerwear": "Outerwear", "mid": "Mid layer (knits, hoodies, cardigans)", "base": "Tops",
    "bottoms": "Bottoms", "shoes": "Shoes", "accessories": "Accessories",
}
DEFAULT_WARMTH = {"outerwear": 3, "mid": 3, "base": 1, "bottoms": 2, "shoes": 1, "accessories": 2}

OCCASION_FORMALITY = [
    (r"gym|workout|träning|run|löpning|hike|vandring", 1),
    (r"wedding|bröllop|formal|gala|funeral|begravning|black tie", 5),
    (r"interview|intervju|presentation|meeting|möte|client|kund", 4),
    (r"work|office|jobb|kontor|school|skola|uni|class|lecture|föreläsning", 3),
    (r"date|dinner|middag|restaurant|party|fest|bar|drinks", 3),
    (r"casual|chill|home|hemma|weekend|errands|ärenden|shopping|lazy", 2),
]


def slot_of(item: Item) -> str:
    if item.category == "tops":
        return "mid" if item.layer == "mid" else "base"
    return item.category if item.category in SLOTS else "accessories"


def occasion_formality(occasion: str | None) -> int | None:
    if not occasion:
        return None
    low = occasion.lower()
    for pattern, level in OCCASION_FORMALITY:
        if re.search(pattern, low):
            return level
    return None


@dataclass
class Targets:
    outer: str  # "yes" | "optional" | "no"
    outer_warmth: int
    mid: str
    mid_warmth: int
    base_warmth: int
    bottoms_warmth: int
    shoes_warmth: int
    wet: bool
    snow: bool
    formality: int | None
    accessories: list[str] = field(default_factory=list)

    def warmth_for(self, slot: str) -> int:
        return {
            "outerwear": self.outer_warmth, "mid": self.mid_warmth, "base": self.base_warmth,
            "bottoms": self.bottoms_warmth, "shoes": self.shoes_warmth, "accessories": 3,
        }[slot]

    def guidance(self) -> str:
        lines = []
        if self.outer == "yes":
            lines.append(f"outerwear needed (warmth ≈{self.outer_warmth}/5{', rain-proof preferred' if self.wet else ''})")
        elif self.outer == "optional":
            lines.append(f"light outerwear optional (warmth ≈{self.outer_warmth}/5)")
        else:
            lines.append("no outerwear needed")
        if self.mid == "yes":
            lines.append(f"add a mid layer (warmth ≈{self.mid_warmth}/5)")
        elif self.mid == "optional":
            lines.append("a light knit is optional")
        lines.append(f"bottoms warmth ≈{self.bottoms_warmth}/5")
        if self.snow:
            lines.append("snow: boots")
        elif self.wet:
            lines.append("wet: avoid suede, prefer shoes that handle rain")
        if self.accessories:
            lines.append("consider " + ", ".join(self.accessories))
        if self.formality:
            lines.append(f"occasion formality ≈{self.formality}/5")
        return "; ".join(lines)


def compute_targets(weather: DayWeather, occasion: str | None, bias: float = 0.0) -> Targets:
    """`bias` shifts perceived temperature: negative if you run cold."""
    f_min = weather.feels_min + bias
    f_avg = (weather.feels_min + weather.feels_max) / 2 + bias

    def band(value: float, steps: list[tuple[float, int]], last: int) -> int:
        for limit, result in steps:
            if value <= limit:
                return result
        return last

    outer = "yes" if f_min < 15 or (weather.wet and f_min < 22) else ("optional" if f_min < 19 else "no")
    outer_warmth = band(f_min, [(-6, 5), (2, 4), (8, 3), (13, 2)], 1)
    mid = "yes" if f_avg < 12 else ("optional" if f_avg < 17 else "no")
    mid_warmth = band(f_avg, [(0, 4), (8, 3)], 2)
    base_warmth = 0 if f_avg > 25 else 1
    bottoms_warmth = band(f_avg, [(2, 3), (19, 2), (24, 1)], 0)
    shoes_warmth = 3 if (weather.snow or f_min <= 1) else (2 if f_min <= 8 else 1)
    accessories = []
    if f_min <= 4:
        accessories += ["scarf", "beanie"]
    if f_min <= -3:
        accessories.append("gloves")
    return Targets(
        outer=outer, outer_warmth=outer_warmth, mid=mid, mid_warmth=mid_warmth, base_warmth=base_warmth,
        bottoms_warmth=bottoms_warmth, shoes_warmth=shoes_warmth, wet=weather.wet, snow=weather.snow,
        formality=occasion_formality(occasion), accessories=accessories,
    )


RECENCY_PENALTY = {  # slot -> {days since worn: penalty}
    "base": {0: 1.0, 1: 0.45, 2: 0.15},
    "mid": {0: 0.5, 1: 0.2},
    "bottoms": {0: 0.3, 1: 0.1},
}


def score(item: Item, slot: str, t: Targets, today: date, last_worn: dict[str, date]) -> float:
    warmth = item.warmth if item.warmth is not None else DEFAULT_WARMTH[slot]
    s = 1.0 - 0.22 * abs(warmth - t.warmth_for(slot))
    if slot == "accessories":
        type_ = str(item.get("type", "")).lower()
        s = 0.9 if any(a in type_ for a in t.accessories) else 0.5
    material = str(item.get("material", "")).lower()
    type_ = str(item.get("type", "")).lower()
    if t.wet and slot == "outerwear":
        s += 0.25 if item.rain_ok else -0.15
    if t.wet and slot == "shoes":
        if item.rain_ok or "boot" in type_:
            s += 0.15
        if "suede" in material:
            s -= 0.3
    if t.snow and slot == "shoes" and "boot" in type_:
        s += 0.3
    if t.formality and item.formality is not None:
        s -= 0.12 * abs(item.formality - t.formality)
    worn = last_worn.get(item.id)
    if worn is not None:
        days = (today - worn).days
        s -= RECENCY_PENALTY.get(slot, {}).get(days, 0.0)
    return round(s, 3)


@dataclass
class Candidates:
    targets: Targets
    by_slot: dict[str, list[tuple[Item, float]]]
    filled_slots: set[str]


def pick_candidates(
    items: list[Item],
    weather: DayWeather,
    occasion: str | None,
    anchors: list[Item],
    last_worn: dict[str, date],
    today: date,
    bias: float = 0.0,
    per_slot: int = 6,
) -> Candidates:
    t = compute_targets(weather, occasion, bias)
    anchor_ids = {a.id for a in anchors}
    filled = {slot_of(a) for a in anchors}
    by_slot: dict[str, list[tuple[Item, float]]] = {s: [] for s in SLOTS}
    for item in items:
        if item.id in anchor_ids:
            continue
        slot = slot_of(item)
        if slot in filled:
            continue
        by_slot[slot].append((item, score(item, slot, t, today, last_worn)))
    for slot in SLOTS:
        limit = 4 if slot == "accessories" else per_slot
        if slot == "outerwear" and t.outer == "no":
            limit = 2
        if slot == "mid" and t.mid == "no":
            limit = 2
        if slot == "accessories" and not t.accessories:
            limit = 0
        by_slot[slot] = sorted(by_slot[slot], key=lambda p: (-p[1], p[0].id))[:limit]
    return Candidates(targets=t, by_slot=by_slot, filled_slots=filled)


def temperature_bias(profile: dict[str, Any]) -> float:
    """profile.yaml `runs: cold|warm` or `temperature_bias: -2`."""
    if isinstance(profile.get("temperature_bias"), int | float):
        return float(profile["temperature_bias"])
    runs = str(profile.get("runs", "")).lower()
    return -2.5 if "cold" in runs else (2.5 if "warm" in runs or "hot" in runs else 0.0)
