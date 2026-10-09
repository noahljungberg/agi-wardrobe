from datetime import date, timedelta

from wardrobe.analysis import analyse
from wardrobe.catalog import Catalog


def test_analysis_facts(demo_dir):
    cat = Catalog(demo_dir)
    cat.save_item(None, {"name": "Corduroy trousers regular fit", "brand": "Mango", "colour": "beige", "price": 419})
    items = cat.items()
    today = date(2026, 10, 9)
    result = analyse(items, {"levi-s-straight-jeans-501-blue": 3}, {"levi-s-straight-jeans-501-blue": today - timedelta(days=70)}, [], today)
    assert result["items_total"] == 17
    assert any(len(group) == 2 and all("corduroy-trousers-regular-fit-beige" in i for i in group) for group in result["near_duplicates"])
    assert result["coverage"]["rain_proof_outerwear"] == ["mango-short-padded-water-repellent-jacket-olive"]
    assert result["wear_log"]["never_worn"] == "need 14+ logged days"
    assert result["wear_log"]["not_worn_60_days"] == ["levi-s-straight-jeans-501-blue"]
    assert result["cost_per_wear_highest"][0]["per_wear"] == 419.0


def test_never_worn_after_enough_days(demo_dir):
    items = Catalog(demo_dir).items()
    history = [{"day": f"2026-09-{d:02d}", "temp_min": 5, "temp_max": 12} for d in range(1, 16)]
    result = analyse(items, {items[0].id: 1}, {}, history, date(2026, 10, 9))
    assert items[0].id not in result["wear_log"]["never_worn"]
    assert len(result["wear_log"]["never_worn"]) == len(items) - 1
    assert result["wear_log"]["temperature_range_seen"] == [5, 12]
