from datetime import date, timedelta

from wardrobe.catalog import Catalog
from wardrobe.outfit import compute_targets, occasion_formality, pick_candidates, slot_of, temperature_bias
from wardrobe.weather import DayWeather


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


def test_occasion_and_bias():
    assert occasion_formality("dinner date") == 3
    assert occasion_formality("job interview") == 4
    assert occasion_formality("gym") == 1
    assert occasion_formality(None) is None
    assert temperature_bias({"runs": "cold"}) == -2.5
    assert temperature_bias({"temperature_bias": 1}) == 1.0
    assert temperature_bias({}) == 0.0
