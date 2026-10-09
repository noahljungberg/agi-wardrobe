import base64
import json

import pytest
from mcp import Client

from conftest import FakeWeather
from wardrobe.server import Wardrobe, build_mcp


@pytest.fixture
def wardrobe(config):
    return Wardrobe(config, weather=FakeWeather())


@pytest.fixture
def connect(wardrobe):
    """`async with connect() as client:` (an async-generator fixture would cross anyio task scopes)."""
    return lambda: Client(build_mcp(wardrobe))


def texts(result):
    return "\n".join(b.text for b in result.content if b.type == "text")


def images(result):
    return [b for b in result.content if b.type == "image"]


async def test_tool_list_and_annotations(connect):
    async with connect() as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        assert {"dress_me", "show_outfit", "log_wear", "find_items", "save_item", "review_inbox", "import_links",
                "wardrobe_analysis", "remember", "forget", "set_location"} <= set(tools)
        assert tools["dress_me"].annotations.read_only_hint is True
        assert tools["log_wear"].annotations.read_only_hint is False
        assert tools["show_outfit"].meta["ui"]["resourceUri"] == "ui://wardrobe/outfit.html"
        resources = {r.uri: r.mime_type for r in (await client.list_resources()).resources}
        assert resources["ui://wardrobe/outfit.html"] == "text/html;profile=mcp-app"


async def test_dress_me_uses_home_and_anchor(connect, wardrobe):
    async with connect() as client:
        wardrobe.catalog.root.joinpath("profile.yaml").write_text("home: Linköping, Sweden\n")
        r = await client.call_tool("dress_me", {"wearing": ["beige mango cords"], "occasion": "office"})
        text = texts(r)
        assert "Linköping" in text and "home" in text
        assert "A1 `mango-corduroy-trousers-regular-fit-beige`" in text
        assert "**Bottoms**" not in text  # slot already filled by what they're wearing
        assert "rain-proof preferred" in text
        sheet = images(r)[0]
        assert sheet.mime_type == "image/jpeg" and len(base64.b64decode(sheet.data)) > 5000


async def test_dress_me_without_location_asks(connect, wardrobe):
    (wardrobe.catalog.root / "profile.yaml").unlink()
    async with connect() as client:
        r = await client.call_tool("dress_me", {})
        assert "Ask which city" in texts(r)


async def test_phone_location_wins(connect, wardrobe):
    async with connect() as client:
        wardrobe.state.set_location(37.77, -122.42, "San Francisco", "from your phone", "America/Los_Angeles")
        r = await client.call_tool("dress_me", {})
        assert "San Francisco (from your phone" in texts(r)


async def test_show_outfit_payloads(connect, wardrobe):
    async with connect() as client:
        wardrobe.state.set_location(58.41, 15.62, "Linköping", "from your phone", "Europe/Stockholm")
        r = await client.call_tool("show_outfit", {
            "item_ids": ["nubikk-leather-sneakers-white", "beige cords", "mango-wool-coat-with-high-collar-black"],
            "note": "Coat for the showers.",
        })
        s = r.structured_content
        assert [i["id"] for i in s["items"]][0] == "mango-wool-coat-with-high-collar-black"  # slot order
        assert s["title"] == "Today · Linköping"
        assert s["collage_url"].startswith(wardrobe.config.public_url + "/img/r/")
        assert set(r.meta["wardrobe/thumbs"]) == {i["id"] for i in s["items"]}
        assert r.meta["wardrobe/thumbs"]["nubikk-leather-sneakers-white"].startswith("data:image/jpeg;base64,")
        assert images(r)
        token = s["collage_url"].rsplit("/", 1)[1].removesuffix(".jpg")
        assert wardrobe.state.render_path(token).exists()


async def test_log_wear_and_recency(connect, wardrobe):
    async with connect() as client:
        r = await client.call_tool("log_wear", {"items": ["beige cords", "ecru knit"]})
        assert "Logged for" in texts(r)
        r = await client.call_tool("log_wear", {"items": ["corduroy trousers"], "day": "yesterday"})
        assert "could be" in texts(r)
        r = await client.call_tool("find_items", {"query": "knit"})
        assert "worn today" in texts(r)


async def test_save_item_from_inbox_and_review(connect, wardrobe):
    async with connect() as client:
        inbox = wardrobe.catalog.inbox_dir
        (inbox / "IMG_0001.jpg").write_bytes((wardrobe.catalog.items_dir / "nubikk-leather-sneakers-white/1.jpg").read_bytes())
        r = await client.call_tool("review_inbox", {})
        assert "IMG_0001.jpg" in texts(r) and images(r)
        r = await client.call_tool("save_item", {"name": "Grey hoodie", "category": "tops", "type": "hoodie", "colour": "grey", "from_inbox": ["IMG_0001.jpg"]})
        assert "Saved `grey-hoodie-grey`" in texts(r)
        item = wardrobe.catalog.get("grey-hoodie-grey")
        assert item.layer == "mid" and item.photos
        r = await client.call_tool("save_item", {"item_id": "nope"})
        assert r.is_error


async def test_preferences_and_analysis(connect):
    async with connect() as client:
        r = await client.call_tool("remember", {"note": "never black with brown"})
        assert "[1]" in texts(r)
        data = json.loads(texts(await client.call_tool("wardrobe_analysis", {})))
        assert data["items_total"] == 16 and data["remembered_preferences"] == ["never black with brown"]
        assert data["coverage"]["rain_proof_outerwear"]
        assert "Forgotten" in texts(await client.call_tool("forget", {"pref_id": 1}))


async def test_set_location(connect, wardrobe):
    async with connect() as client:
        assert "San Francisco" in texts(await client.call_tool("set_location", {"place": "San Francisco"}))
        assert wardrobe.state.location().name.startswith("San Francisco")
        assert "Couldn't find" in texts(await client.call_tool("set_location", {"place": "Nowhere"}))


async def test_geocoder_outage_falls_back(connect, wardrobe):
    import httpx

    async def broken(name):
        raise httpx.ConnectError("down")

    wardrobe.weather.geocode = broken
    async with connect() as client:
        r = await client.call_tool("dress_me", {})
        assert "Ask which city" in texts(r)
        r = await client.call_tool("set_location", {"place": "Paris"})
        assert "unreachable" in texts(r)
