"""The browser UI on the private app: login, the JSON API it uses, and a real browser run."""

import io
import os
import shutil
from pathlib import Path

import pytest
import yaml
from conftest import FakeWeather
from PIL import Image
from starlette.testclient import TestClient

from wardrobe import importer
from wardrobe.config import Config
from wardrobe.server import Wardrobe, build_private_app

W = {"X-Wardrobe": "1"}


def make_client(tmp_path: Path, demo_dir: Path, **env) -> tuple[TestClient, Wardrobe]:
    config = Config.from_env({"WARDROBE_DIR": str(demo_dir), "WARDROBE_STATE_DIR": str(tmp_path / "state"),
                              "WARDROBE_AUTH": "none", **env})
    w = Wardrobe(config, weather=FakeWeather())
    return TestClient(build_private_app(w), follow_redirects=False), w


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), (30, 60, 120)).save(buf, "PNG")
    return buf.getvalue()


def test_login_gate(tmp_path, demo_dir):
    client, _ = make_client(tmp_path, demo_dir, WARDROBE_PASSPHRASE="correct horse")
    assert "Passphrase" in client.get("/ui").text
    assert client.get("/ui/api/items").status_code == 401
    assert client.get("/ui/photo/levi-s-hilltop-jacket-brown/0/240").status_code == 401
    assert client.post("/ui/login", data={"passphrase": "nope"}).status_code == 401
    ok = client.post("/ui/login", data={"passphrase": "correct horse"})
    assert ok.status_code == 303 and "wardrobe_ui" in ok.cookies
    assert 'id="view"' in client.get("/ui").text
    assert len(client.get("/ui/api/items").json()["items"]) == 16
    client.post("/ui/logout")
    client.cookies.clear()
    assert client.get("/ui/api/items").status_code == 401


def test_open_without_secrets_and_root_redirect(tmp_path, demo_dir):
    client, _ = make_client(tmp_path, demo_dir)
    assert client.get("/").headers["location"] == "/ui"
    data = client.get("/ui/api/items").json()
    assert {"items", "inbox", "categories", "statuses"} <= set(data)
    item = next(i for i in data["items"] if i["id"] == "mango-corduroy-trousers-regular-fit-beige")
    assert item["slot"] == "bottoms" and item["photos"] == 1 and item["status"] == "owned" and "warmth" in item["guessed"]


def test_edits_write_the_folder(tmp_path, demo_dir):
    client, w = make_client(tmp_path, demo_dir)
    url = "/ui/api/items/uniqlo-oxford-shirt-light-blue"
    assert client.patch(url, json={"status": "laundry"}).status_code == 403  # no X-Wardrobe header
    r = client.patch(url, json={"status": "laundry", "favourite": True, "aliases": "blue oxford, work shirt"}, headers=W)
    assert r.status_code == 200 and r.json()["status"] == "laundry" and r.json()["favourite"] is True
    data = yaml.safe_load((demo_dir / "items/uniqlo-oxford-shirt-light-blue/item.yaml").read_text())
    assert data["status"] == "laundry" and data["favourite"] is True and data["aliases"] == ["blue oxford", "work shirt"]
    assert "uniqlo-oxford-shirt-light-blue" not in {i.id for i in w.catalog.items()}  # not suggested while in the laundry
    assert client.patch(url, json={"category": "hats"}, headers=W).status_code == 400
    assert client.patch(url, json={"warmth": 9}, headers=W).status_code == 400
    assert client.patch(url, json={"name": ""}, headers=W).status_code == 400
    assert client.patch("/ui/api/items/nope", json={}, headers=W).status_code == 404


def test_quick_add_wishlist_and_review(tmp_path, demo_dir):
    client, w = make_client(tmp_path, demo_dir)
    r = client.post("/ui/api/items", json={"name": "White linen shirt", "category": "tops", "colour": "vit"}, headers=W)
    assert r.status_code == 201
    stub = r.json()
    assert stub["needs_review"] is True and stub["photos"] == 0 and stub["colour"] == "white"
    wish = client.post("/ui/api/items", json={"name": "Rain jacket", "category": "outerwear", "status": "wishlist"}, headers=W).json()
    assert wish["status"] == "wishlist" and wish["needs_review"] is False
    assert "rain-jacket" not in {i.id for i in w.catalog.items()}
    reviewed = client.patch(f"/ui/api/items/{stub['id']}", json={"needs_review": False}, headers=W).json()
    assert reviewed["needs_review"] is False
    assert client.post("/ui/api/items", json={"category": "tops"}, headers=W).status_code == 400


def test_photos_upload_serve_and_inbox(tmp_path, demo_dir):
    client, w = make_client(tmp_path, demo_dir)
    item_id = client.post("/ui/api/items", json={"name": "Grey hoodie", "category": "tops"}, headers=W).json()["id"]
    up = client.post(f"/ui/api/items/{item_id}/photos", files={"photo": ("a.png", png_bytes(), "image/png")}, headers=W)
    assert up.status_code == 200 and up.json()["photos"] == 1
    bad = client.post(f"/ui/api/items/{item_id}/photos", files={"photo": ("a.txt", b"not an image", "text/plain")}, headers=W)
    assert bad.status_code == 400
    img = client.get(f"/ui/photo/{item_id}/0/480")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert client.get(f"/ui/photo/{item_id}/5/480").status_code == 404
    assert client.get(f"/ui/photo/{item_id}/0/123").status_code == 404

    (w.catalog.inbox_dir / "IMG_1.png").write_bytes(png_bytes())
    assert client.get("/ui/api/items").json()["inbox"] == ["IMG_1.png"]
    assert client.get("/ui/inbox/IMG_1.png/240").status_code == 200
    assert client.get("/ui/inbox/..%2Fprofile.yaml/240").status_code == 404
    made = client.post("/ui/api/items", json={"name": "Navy cap", "category": "accessories", "from_inbox": ["IMG_1.png"]}, headers=W)
    assert made.status_code == 201 and made.json()["photos"] == 1 and not w.catalog.inbox_files()
    assert client.post("/ui/api/items", json={"name": "x", "from_inbox": ["../profile.yaml"]}, headers=W).status_code == 400


def test_import_and_analysis(tmp_path, demo_dir, monkeypatch):
    client, w = make_client(tmp_path, demo_dir)

    async def fake_import(catalog, url, payload=None, chromium=None, extra=None):
        item = catalog.save_item(None, {"name": "Oxford shirt", "brand": "Arket", "colour": "white", "source_url": url})
        return importer.ImportResult(url, item=item)

    monkeypatch.setattr(importer, "import_url", fake_import)
    r = client.post("/ui/api/import", json={"url": "https://www.arket.com/x.html"}, headers=W)
    assert r.status_code == 200 and r.json()["item"]["brand"] == "Arket"
    assert client.post("/ui/api/import", json={"url": "nope"}, headers=W).status_code == 400
    a = client.get("/ui/api/analysis").json()
    assert a["items_total"] == 17 and "coverage" in a


def test_me_page_api(tmp_path, demo_dir):
    client, w = make_client(tmp_path, demo_dir, WARDROBE_PASSPHRASE="correct horse")
    assert client.get("/ui/api/me").status_code == 401
    client.post("/ui/login", data={"passphrase": "correct horse"})
    assert client.get("/ui/api/me").json() == {"photos": []}
    assert client.patch("/ui/api/me", json={"hair": "blonde"}).status_code == 403  # no X-Wardrobe header
    me = client.patch("/ui/api/me", json={"hair": "blonde", "eyes": "blue", "height_cm": "185", "bogus": 1}, headers=W).json()
    assert me == {"hair": "blonde", "eyes": "blue", "height_cm": 185, "photos": []}
    assert client.patch("/ui/api/me", json={"height_cm": 20}, headers=W).status_code == 400
    me = client.post("/ui/api/me/photos", files={"photo": ("me.png", png_bytes(), "image/png")}, headers=W).json()
    assert me["photos"] == ["1.jpg"]
    assert client.get("/ui/me/1.jpg/480").headers["content-type"] == "image/jpeg"
    assert client.get("/ui/me/..%2Fprofile.yaml/480").status_code == 404
    (w.catalog.inbox_dir / "selfie.png").write_bytes(png_bytes())
    assert client.post("/ui/api/me/from-inbox", json={"name": "selfie.png"}, headers=W).json()["photos"] == ["1.jpg", "2.png"]
    assert client.delete("/ui/api/me/photos/1.jpg", headers=W).json()["photos"] == ["2.png"]
    assert client.delete("/ui/api/me/photos/1.jpg", headers=W).status_code == 404
    assert client.patch("/ui/api/me", json={"photo_in_suggestions": False}, headers=W).json()["photo_in_suggestions"] is False


# ---------------------------------------------------------------- real browser

CHROMIUM = os.environ.get("WARDROBE_CHROMIUM") or next(
    (p for p in ("/opt/pw-browsers/chromium", shutil.which("chromium") or "") if p and Path(p).exists()), None
)


@pytest.mark.skipif(CHROMIUM is None, reason="no chromium binary")
async def test_browse_edit_and_add_in_a_browser(tmp_path, demo_dir):
    playwright = pytest.importorskip("playwright.async_api")
    from test_http import free_port, start, stop

    port = free_port()
    config = Config.from_env({"WARDROBE_DIR": str(demo_dir), "WARDROBE_STATE_DIR": str(tmp_path / "state"), "WARDROBE_AUTH": "none"})
    w = Wardrobe(config, weather=FakeWeather())
    server = await start(build_private_app(w), port)
    try:
        async with playwright.async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=CHROMIUM)
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            await page.goto(f"http://127.0.0.1:{port}/ui")
            await page.wait_for_selector(".card")
            assert await page.locator(".card").count() == 16

            await page.click('[data-id="uniqlo-oxford-shirt-light-blue"]')
            await page.wait_for_selector(".drawer.on h2")
            await page.click('.seg [data-status="laundry"]')
            await page.wait_for_timeout(300)
            assert w.catalog.get("uniqlo-oxford-shirt-light-blue").status == "laundry"
            await page.keyboard.press("Escape")
            assert await page.locator(".card").count() == 15  # "Available now" hides laundry

            await page.click("#add-btn")
            await page.fill('#add-form [name="name"]', "Striped shirt")
            await page.select_option('#add-form [name="category"]', "tops")
            await page.click("#add-go")
            await page.wait_for_selector(".drawer.on h2:text('Striped shirt')")
            assert w.catalog.get("striped-shirt") is not None

            await page.keyboard.press("Escape")
            await page.click('[data-view="insights"]')
            await page.wait_for_selector(".gap")
            assert "What's missing" in await page.inner_text("#view")

            await page.click('[data-view="me"]')
            await page.fill('#me-form [name="hair"]', "blonde")
            await page.fill('#me-form [name="eyes"]', "blue")
            assert await page.inner_text("#me-reads") == "blonde hair, blue eyes"
            await page.click('#me-form button[type="submit"]')
            await page.wait_for_timeout(300)
            assert w.catalog.me()["hair"] == "blonde"
            assert errors == []
            await browser.close()
    finally:
        await stop(*server)
