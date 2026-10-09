import time

import yaml

from wardrobe.catalog import Catalog


def test_load_infers_missing_fields(demo_dir):
    cat = Catalog(demo_dir)
    item = cat.get("mango-wool-coat-with-high-collar-black")
    assert item.category == "outerwear"
    assert item.photos and item.photos[0].name == "1.jpg"
    assert "category" in item.inferred


def test_hand_edits_are_picked_up(demo_dir):
    cat = Catalog(demo_dir, refresh_interval=0)
    path = demo_dir / "items/levi-s-hilltop-jacket-brown/item.yaml"
    data = yaml.safe_load(path.read_text())
    data["warmth"] = 5
    time.sleep(0.01)
    path.write_text(yaml.safe_dump(data))
    assert cat.get("levi-s-hilltop-jacket-brown").warmth == 5


def test_save_new_item_with_inbox_photo(demo_dir):
    cat = Catalog(demo_dir)
    photo = demo_dir / "inbox" / "IMG_1.jpg"
    photo.write_bytes((demo_dir / "items/nubikk-leather-sneakers-white/1.jpg").read_bytes())
    item = cat.save_item(None, {"name": "Navy overshirt", "brand": "Arket", "colour": "marinblå"}, add_photos=[photo])
    assert item.id == "arket-navy-overshirt-marinbla"
    assert item.colour == "navy"
    assert item.category == "outerwear"
    assert not photo.exists() and item.photos


def test_broken_yaml_does_not_break_catalog(demo_dir):
    (demo_dir / "items/broken").mkdir()
    (demo_dir / "items/broken/item.yaml").write_text("name: [unclosed")
    cat = Catalog(demo_dir)
    assert len(cat.items()) == 16
    assert cat.errors and cat.errors[0].startswith("broken")


def test_retired_items_hidden(demo_dir):
    cat = Catalog(demo_dir)
    cat.save_item("acne-wool-scarf-charcoal", {"status": "retired"})
    assert "acne-wool-scarf-charcoal" not in {i.id for i in cat.items()}
    assert "acne-wool-scarf-charcoal" in {i.id for i in cat.items(include_inactive=True)}
