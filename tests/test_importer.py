import json
from pathlib import Path

from PIL import Image

from wardrobe import importer
from wardrobe.catalog import Catalog

MANGO_LIKE = """<html><head><title>Manchesterbyxa regular fit - Herr | Mango Sverige</title>
<meta property="og:title" content="Manchesterbyxa regular fit - Herr | Mango Sverige">
<script type="application/ld+json">%s</script></head><body></body></html>""" % json.dumps({
    "@context": "https://schema.org", "@type": "ProductGroup", "name": "Manchesterbyxa regular fit",
    "brand": {"@type": "Brand", "name": "Mango"}, "material": "100% bomull",
    "hasVariant": [
        {"@type": "Product", "name": "Manchesterbyxa regular fit", "color": "Svart",
         "image": ["https://shop.mango.com/assets/rcs/pics/static/T1/fotos/S20/17007889_99.jpg"],
         "offers": {"@type": "Offer", "price": "419.00", "priceCurrency": "SEK"}},
        {"@type": "Product", "name": "Manchesterbyxa regular fit", "color": "Beige",
         "image": ["https://shop.mango.com/assets/rcs/pics/static/T1/fotos/S20/17007889_08.jpg",
                   "https://shop.mango.com/assets/rcs/pics/static/T1/fotos/outfit/S20/17007889_08-99999999_01.jpg"],
         "offers": {"@type": "Offer", "price": "419.00", "priceCurrency": "SEK"}},
    ],
})

ZALANDO_LIKE = """<html><head>
<meta property="og:title" content="Mango Piké - beige - Zalando.se">
<meta property="og:image" content="https://img01.ztat.net/article/spp-media-p1/abc/def.jpg?imwidth=300">
<meta property="product:brand" content="Mango"></head></html>"""


def test_parse_mango_variant_by_colour_code():
    info = importer.parse_product(MANGO_LIKE, "https://shop.mango.com/se/sv/p/herr/byxor/manchesterbyxa_17007889?c=08&utm_source=x")
    assert info.name == "Manchesterbyxa regular fit"
    assert info.brand == "Mango"
    assert info.colour == "Beige"
    assert info.price == 419.0 and info.currency == "SEK"
    assert all("_08" in u for u in info.images)


def test_parse_zalando_og():
    info = importer.parse_product(ZALANDO_LIKE, "https://www.zalando.se/mango-pike-beige-m9122q11z-b11.html")
    assert info.brand == "Mango"
    assert info.name.startswith("Piké")
    assert info.colour == "beige"
    assert info.images == ["https://img01.ztat.net/article/spp-media-p1/abc/def.jpg?imwidth=1200&filter=packshot"]


def test_normalise_url_keeps_variant():
    assert importer.normalise_url("https://x.se/p/1?c=08&utm_source=mail#top") == "https://x.se/p/1?c=08"


async def test_import_url_with_share_sheet_payload(demo_dir, monkeypatch, tmp_path):
    async def fake_download(urls, referer, dest: Path, limit=3):
        path = dest / "1.jpg"
        Image.new("RGB", (400, 500), (200, 180, 150)).save(path)
        return [path]

    monkeypatch.setattr(importer, "download_images", fake_download)
    cat = Catalog(demo_dir)
    url = "https://shop.mango.com/se/sv/p/herr/byxor/manchesterbyxa_17007889?c=08"
    payload = {"title": "Manchesterbyxa", "jsonld": [MANGO_LIKE.split("ld+json\">")[1].split("</script>")[0]], "meta": {}, "images": []}
    result = await importer.import_url(cat, url, payload=payload)
    assert result.error is None
    item = result.item
    assert item.colour == "beige" and item.category == "bottoms" and item.get("material") == "corduroy"
    assert item.get("needs_review") is True and item.photos
    again = await importer.import_url(cat, url + "&utm_campaign=y", payload=payload)
    assert again.existing and again.item.id == item.id


async def test_import_reports_fetch_errors(demo_dir, monkeypatch):
    async def blocked(url, chromium=None):
        raise RuntimeError("HTTP 403")

    monkeypatch.setattr(importer, "fetch_html", blocked)
    result = await importer.import_url(Catalog(demo_dir), "https://www.zalando.se/x.html")
    assert result.item is None and "403" in result.error
