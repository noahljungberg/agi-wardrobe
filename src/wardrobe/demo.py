"""Generate a demo wardrobe with drawn placeholder photos, for trying the
server before your real folder is ready."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from wardrobe.catalog import Catalog, write_item_yaml

COLOURS = {
    "beige": (214, 196, 168), "off-white": (238, 232, 218), "black": (35, 35, 38), "navy": (38, 50, 82),
    "grey": (150, 150, 152), "light grey": (200, 201, 204), "brown": (115, 80, 55), "olive": (110, 112, 70),
    "white": (246, 246, 244), "blue": (70, 100, 150), "light blue": (170, 195, 220), "charcoal": (70, 70, 74),
}

DEMO_ITEMS = [
    {"name": "Corduroy trousers regular fit", "brand": "Mango", "colour": "beige", "aliases": ["beige cords", "manchester trousers"], "size": "42"},
    {"name": "Corduroy trousers regular fit", "brand": "Mango", "colour": "brown", "size": "42"},
    {"name": "Regular-fit cotton trousers with pleats", "brand": "Mango", "colour": "grey", "size": "42"},
    {"name": "Straight jeans 501", "brand": "Levi's", "colour": "blue", "size": "32/32"},
    {"name": "Slim linen drawstring trousers", "brand": "Mango", "colour": "off-white", "size": "42"},
    {"name": "Ribbed tennis sweater", "brand": "Mango", "colour": "off-white", "size": "M"},
    {"name": "Merino crewneck sweater", "brand": "Uniqlo", "colour": "navy", "size": "M"},
    {"name": "Bombay polo shirt", "brand": "Mango", "colour": "black", "size": "M"},
    {"name": "Basic t-shirt", "brand": "Mango", "colour": "light grey", "size": "M"},
    {"name": "Oxford shirt", "brand": "Uniqlo", "colour": "light blue", "size": "M"},
    {"name": "Wool coat with high collar", "brand": "Mango", "colour": "black", "size": "M"},
    {"name": "Short padded water-repellent jacket", "brand": "Mango", "colour": "olive", "size": "M"},
    {"name": "Hilltop jacket", "brand": "Levi's", "colour": "brown", "size": "M"},
    {"name": "Leather sneakers", "brand": "Nubikk", "colour": "white", "size": "43"},
    {"name": "Suede chelsea boots", "brand": "Filling Pieces", "colour": "brown", "size": "43"},
    {"name": "Wool scarf", "brand": "Acne", "colour": "charcoal"},
]


def _draw(kind: str, colour: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (600, 800), (244, 242, 238))
    d = ImageDraw.Draw(img)
    edge = tuple(max(0, c - 45) for c in colour)
    if kind == "bottoms":
        d.polygon([(190, 120), (410, 120), (440, 720), (330, 720), (300, 300), (270, 720), (160, 720)], fill=colour, outline=edge, width=4)
        d.rectangle([190, 110, 410, 150], fill=colour, outline=edge, width=4)
    elif kind in ("base", "mid"):
        sleeve = 520 if kind == "mid" else 330
        d.polygon([(200, 180), (400, 180), (520, 260), (480, sleeve), (420, sleeve - 40), (420, 640), (180, 640),
                   (180, sleeve - 40), (120, sleeve), (80, 260)], fill=colour, outline=edge, width=4)
        d.ellipse([255, 160, 345, 220], fill=(244, 242, 238), outline=edge, width=4)
    elif kind == "outerwear":
        d.polygon([(190, 140), (410, 140), (530, 230), (500, 640), (440, 620), (440, 740), (160, 740), (160, 620),
                   (100, 640), (70, 230)], fill=colour, outline=edge, width=4)
        d.line([(300, 170), (300, 740)], fill=edge, width=4)
        d.polygon([(220, 140), (300, 320), (380, 140)], fill=edge)
    elif kind == "shoes":
        d.rounded_rectangle([90, 420, 290, 520], radius=45, fill=colour, outline=edge, width=4)
        d.rounded_rectangle([310, 380, 510, 480], radius=45, fill=colour, outline=edge, width=4)
        d.rectangle([90, 500, 290, 530], fill=edge)
        d.rectangle([310, 460, 510, 490], fill=edge)
    else:
        d.rounded_rectangle([150, 200, 450, 280], radius=30, fill=colour, outline=edge, width=4)
        d.rectangle([330, 260, 400, 640], fill=colour, outline=edge, width=4)
    return img


def make_demo(root: Path) -> int:
    catalog = Catalog(root)
    catalog.ensure_layout()
    (root / "profile.yaml").write_text(
        "# About you. Everything here is optional.\n"
        "home: Linköping, Sweden      # fallback when the phone hasn't sent a location\n"
        "runs: neutral                # cold | neutral | warm\n"
        "style: >\n  Clean, relaxed Scandinavian. Neutral colours, regular fits.\n"
        "dislikes:\n  - skinny fits\n",
        encoding="utf-8",
    )
    count = 0
    for spec in DEMO_ITEMS:
        item_id = catalog.new_item_id(spec["name"], spec["brand"], spec["colour"])
        folder = catalog.items_dir / item_id
        folder.mkdir(parents=True, exist_ok=True)
        write_item_yaml(folder / "item.yaml", dict(spec))
        from wardrobe.catalog import load_item

        item = load_item(folder)
        kind = item.layer if item.category == "tops" else item.category
        _draw(kind or "other", COLOURS.get(spec["colour"], (180, 180, 180))).save(folder / "1.jpg", quality=88)
        count += 1
    return count
