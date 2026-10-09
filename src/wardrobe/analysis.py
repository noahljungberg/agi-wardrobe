"""Wardrobe statistics the model turns into gap and duplicate advice."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from typing import Any

from wardrobe.catalog import Item
from wardrobe.heuristics import NEUTRAL_COLOURS
from wardrobe.outfit import slot_of


def _compatible(a: Item, b: Item) -> bool:
    if a.formality is not None and b.formality is not None and abs(a.formality - b.formality) > 1:
        return False
    ca, cb = a.colour, b.colour
    if not ca or not cb:
        return True
    return ca in NEUTRAL_COLOURS or cb in NEUTRAL_COLOURS or ca == cb


def analyse(
    items: list[Item],
    wear_counts: dict[str, int],
    last_worn: dict[str, date],
    history: list[dict[str, Any]],
    today: date,
) -> dict[str, Any]:
    by_slot: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        by_slot[slot_of(item)].append(item)

    def ids(xs: list[Item]) -> list[str]:
        return [x.id for x in xs]

    logged_days = len({h["day"] for h in history})
    temps = [t for h in history for t in (h.get("temp_min"), h.get("temp_max")) if t is not None]

    # near-duplicates: same slot + type + colour
    groups: dict[tuple, list[Item]] = defaultdict(list)
    for item in items:
        groups[(slot_of(item), str(item.get("type", "")), item.colour)].append(item)
    duplicates = [ids(g) for g in groups.values() if len(g) >= 2]

    # items that combine with few things
    tops = by_slot["base"] + by_slot["mid"]
    orphans = []
    for item in tops + by_slot["bottoms"]:
        partners = by_slot["bottoms"] if item in tops else tops
        n = sum(_compatible(item, p) for p in partners)
        if partners and n <= 1:
            orphans.append({"id": item.id, "pairs_with": n})

    outer = by_slot["outerwear"]
    shoes = by_slot["shoes"]
    checks = {
        "rain_proof_outerwear": ids([o for o in outer if o.rain_ok]),
        "warm_outerwear_4plus": ids([o for o in outer if (o.warmth or 0) >= 4]),
        "boots": ids([s for s in shoes if "boot" in str(s.get("type", "")).lower()]),
        "smart_items_formality_4plus": {
            slot: ids([i for i in by_slot[slot] if (i.formality or 0) >= 4]) for slot in ("base", "mid", "bottoms", "shoes", "outerwear")
        },
        "warm_weather_bottoms": ids([b for b in by_slot["bottoms"] if (b.warmth if b.warmth is not None else 2) <= 1]),
    }

    worn = [(i, wear_counts.get(i.id, 0)) for i in items]
    cost_per_wear = sorted(
        (
            {"id": i.id, "price": i.get("price"), "wears": n, "per_wear": round(float(i.get("price")) / max(n, 1), 1)}
            for i, n in worn
            if isinstance(i.get("price"), int | float)
        ),
        key=lambda x: -x["per_wear"],
    )

    return {
        "items_total": len(items),
        "per_slot": {slot: len(v) for slot, v in sorted(by_slot.items())},
        "colours": dict(Counter(i.colour or "unknown" for i in items).most_common()),
        "warmth_by_slot": {slot: dict(sorted(Counter(i.warmth for i in v if i.warmth is not None).items())) for slot, v in by_slot.items()},
        "formality_by_slot": {slot: dict(sorted(Counter(i.formality for i in v if i.formality is not None).items())) for slot, v in by_slot.items()},
        "coverage": checks,
        "near_duplicates": duplicates,
        "hard_to_combine": orphans,
        "wear_log": {
            "days_logged": logged_days,
            "temperature_range_seen": [min(temps), max(temps)] if temps else None,
            "most_worn": [{"id": i.id, "wears": n} for i, n in sorted(worn, key=lambda p: -p[1])[:5] if n],
            "never_worn": ids([i for i, n in worn if n == 0]) if logged_days >= 14 else "need 14+ logged days",
            "not_worn_60_days": [i.id for i in items if i.id in last_worn and (today - last_worn[i.id]).days >= 60],
        },
        "cost_per_wear_highest": cost_per_wear[:8],
        "housekeeping": {
            "missing_photo": ids([i for i in items if not i.photos]),
            "needs_review": ids([i for i in items if i.get("needs_review")]),
        },
    }
