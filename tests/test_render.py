import io

from PIL import Image

from wardrobe.catalog import Catalog
from wardrobe.render import Renderer, open_image


def test_contact_sheet_and_collage(demo_dir, tmp_path):
    items = Catalog(demo_dir).items()
    r = Renderer(tmp_path / "cache")
    sheet = Image.open(io.BytesIO(r.contact_sheet([(str(n), i) for n, i in enumerate(items, 1)])))
    assert sheet.format == "JPEG" and sheet.width == 5 * (190 + 8) + 8
    path = r.collage(items[:4], "Today · Linköping", "7–12°C", "A note")
    img = Image.open(path)
    assert img.width == 1080 and img.height > 1000
    assert r.collage(items[:4], "Today · Linköping", "7–12°C", "A note") == path  # same outfit, same file


def test_missing_photo_does_not_raise(demo_dir, tmp_path):
    cat = Catalog(demo_dir)
    item = cat.get("acne-wool-scarf-charcoal")
    for p in item.photos:
        p.unlink()
    cat.refresh(force=True)
    item = cat.get("acne-wool-scarf-charcoal")
    r = Renderer(tmp_path / "cache")
    assert r.contact_sheet([("1", item)])
    assert r.collage([item], "t").exists()


def test_open_image_flattens_transparency(tmp_path):
    p = tmp_path / "t.png"
    Image.new("RGBA", (10, 10), (255, 0, 0, 0)).save(p)
    img = open_image(p)
    assert img.mode == "RGB" and img.getpixel((0, 0)) == (255, 255, 255)


def test_open_image_heic(tmp_path):
    import pytest

    pillow_heif = pytest.importorskip("pillow_heif")
    p = tmp_path / "photo.heic"
    try:
        pillow_heif.from_pillow(Image.new("RGB", (64, 48), (10, 20, 30))).save(p)
    except Exception as exc:  # encoder not built into this wheel
        pytest.skip(f"no HEIC encoder: {exc}")
    assert open_image(p).size == (64, 48)
