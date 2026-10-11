import time

import pytest
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


def test_me_appearance_and_photos(demo_dir):
    import pytest

    cat = Catalog(demo_dir)
    assert cat.me() == {"photos": []}
    photo = demo_dir / "inbox" / "selfie.jpg"
    photo.write_bytes((demo_dir / "items/nubikk-leather-sneakers-white/1.jpg").read_bytes())
    me = cat.save_me({"hair": "blonde", "eyes": "blue"}, add_photos=[photo])
    assert me["hair"] == "blonde" and [p.name for p in me["photos"]] == ["1.jpg"] and not photo.exists()
    assert "eyes" not in cat.save_me({"eyes": None})
    with pytest.raises(ValueError):
        cat.save_me({"shoe_size": 43})
    assert not cat.remove_me_photo("../profile.yaml")
    assert cat.remove_me_photo("1.jpg") and cat.me()["photos"] == []


@pytest.mark.parametrize("replacement", [False, True])
def test_archive_selected_photos_preserves_other_photos(demo_dir, replacement):
    cat = Catalog(demo_dir)
    item = cat.get("acne-wool-scarf-charcoal")
    original = item.main_photo
    original_bytes = original.read_bytes()
    untouched = original.with_name("3.jpg")
    untouched.write_bytes(original_bytes)
    source = cat.inbox_dir / "replacement.jpg"
    source.write_bytes(original_bytes)
    result = cat.save_item(item.id, {"notes": "reviewed"},
                           archive_photos=[original],
                           add_photos=[source] if replacement else None,
                           move_photos=False)
    assert not original.exists()
    assert (item.path / ".photo-archive" / original.name).read_bytes() == original_bytes
    assert untouched in result.photos and untouched.read_bytes() == original_bytes
    assert len(result.photos) == (2 if replacement else 1)
    assert result.data["notes"] == "reviewed"
    assert source.exists()
    assert Catalog(demo_dir).get(item.id).photos == result.photos


def test_archive_all_photos_and_repeat_preserves_originals(demo_dir):
    cat = Catalog(demo_dir)
    item = cat.get("acne-wool-scarf-charcoal")
    original_bytes = item.main_photo.read_bytes()
    result = cat.save_item(item.id, {}, archive_photos=item.photos)
    assert result.photos == [] and result.main_photo is None
    source = cat.inbox_dir / "replacement.jpg"
    source.write_bytes(original_bytes)
    result = cat.save_item(item.id, {}, add_photos=[source], move_photos=False)
    result = cat.save_item(item.id, {}, archive_photos=result.photos, add_photos=[source])
    archive = item.path / ".photo-archive"
    assert sorted(p.name for p in archive.iterdir()) == ["1-2.jpg", "1.jpg"]
    assert all(p.read_bytes() == original_bytes for p in archive.iterdir())
    assert len(result.photos) == 1


@pytest.mark.parametrize("bad_target", ["missing", "outside", "traversal", "nested", "symlink", "yaml", "archive_symlink", "archive_file", "replacement_missing", "replacement_selected", "replacement_symlink", "item_symlink"])
def test_archive_validation_makes_no_changes(demo_dir, bad_target):
    cat = Catalog(demo_dir)
    item = cat.get("acne-wool-scarf-charcoal")
    original = item.main_photo
    target = original
    item_id = item.id
    additions = []
    if bad_target == "missing":
        target = item.path / "missing.jpg"
    elif bad_target == "outside":
        target = cat.get("nubikk-leather-sneakers-white").main_photo
    elif bad_target == "traversal":
        target = item.path / ".." / item.id / original.name
    elif bad_target == "nested":
        (item.path / "nested").mkdir()
        target = item.path / "nested" / "image.jpg"
        target.write_bytes(b"nested")
    elif bad_target == "symlink":
        target = item.path / "linked.jpg"
        target.symlink_to(original)
    elif bad_target == "yaml":
        target = item.path / "item.yaml"
    elif bad_target == "archive_symlink":
        (item.path / ".photo-archive").symlink_to(cat.inbox_dir, target_is_directory=True)
    elif bad_target == "archive_file":
        (item.path / ".photo-archive").write_bytes(b"keep")
    elif bad_target == "replacement_missing":
        additions = [cat.inbox_dir / "missing.jpg"]
    elif bad_target == "replacement_selected":
        additions = [original]
    elif bad_target == "replacement_symlink":
        source = cat.inbox_dir / "linked.jpg"
        source.symlink_to(original)
        additions = [source]
    elif bad_target == "item_symlink":
        (cat.items_dir / "alias").symlink_to(item.path, target_is_directory=True)
        item_id = "alias"
    before = {str(p.relative_to(demo_dir)): p.read_bytes()
              for p in demo_dir.rglob("*") if p.is_file()}
    with pytest.raises(ValueError):
        cat.save_item(item_id, {"notes": "must not save"},
                      archive_photos=[original, target], add_photos=additions)
    after = {str(p.relative_to(demo_dir)): p.read_bytes()
             for p in demo_dir.rglob("*") if p.is_file()}
    assert before == after
    assert not (item.path / ".photo-archive").exists() or bad_target in {"archive_symlink", "archive_file"}


def test_archive_replacement_skips_existing_number_and_broken_symlinks(demo_dir):
    cat = Catalog(demo_dir)
    item = cat.get("acne-wool-scarf-charcoal")
    original = item.main_photo
    second = item.path / "2.jpg"
    second.write_bytes(original.read_bytes())
    source = cat.inbox_dir / "new.jpg"
    source.write_bytes(b"replacement")
    broken = item.path / "3.jpg"
    broken.symlink_to(cat.inbox_dir / "missing.jpg")
    archive = item.path / ".photo-archive"
    archive.mkdir()
    archived_link = archive / original.name
    archived_link.symlink_to(cat.inbox_dir / "missing-archive.jpg")
    result = cat.save_item(item.id, {}, archive_photos=[original], add_photos=[source])
    assert second.read_bytes() != b"replacement"
    assert (item.path / "4.jpg").read_bytes() == b"replacement"
    assert broken.is_symlink() and archived_link.is_symlink()
    assert (archive / "1-2.jpg").read_bytes() == second.read_bytes()
    assert second in result.photos
