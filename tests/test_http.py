"""End to end over real HTTP: OAuth login, MCP calls with the token, image links, Shortcuts API."""

import asyncio
import base64
import hashlib
import io
import secrets
import socket
from urllib.parse import parse_qs, urlparse

import httpx
import httpx2
import pytest
import uvicorn
from conftest import FakeWeather
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from PIL import Image

from wardrobe.config import Config
from wardrobe.server import Wardrobe, build_mcp, build_private_app, build_public_app

PASSPHRASE = "correct horse battery"
REDIRECT = "https://chatgpt.com/connector_platform_oauth_redirect"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def start(app, port):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    return server, task


async def stop(server, task):
    server.should_exit = True
    await task


@pytest.fixture
async def running(tmp_path, demo_dir):
    pub, priv = free_port(), free_port()
    config = Config.from_env({
        "WARDROBE_DIR": str(demo_dir), "WARDROBE_STATE_DIR": str(tmp_path / "state"),
        "WARDROBE_PUBLIC_URL": f"http://127.0.0.1:{pub}", "WARDROBE_PUBLIC_PORT": str(pub),
        "WARDROBE_PRIVATE_PORT": str(priv), "WARDROBE_PASSPHRASE": PASSPHRASE, "WARDROBE_DEVICE_TOKEN": "phone-token",
    })
    w = Wardrobe(config, weather=FakeWeather())
    w.state.set_location(58.41, 15.62, "Linköping", "from your phone", "Europe/Stockholm")
    servers = [await start(build_public_app(w, build_mcp(w)), pub), await start(build_private_app(w), priv)]
    yield w, f"http://127.0.0.1:{pub}", f"http://127.0.0.1:{priv}"
    for s in servers:
        await stop(*s)


async def oauth_login(http: httpx.AsyncClient, base: str) -> dict:
    meta = (await http.get(f"{base}/.well-known/oauth-authorization-server")).json()
    reg = await http.post(meta["registration_endpoint"], json={
        "redirect_uris": [REDIRECT], "token_endpoint_auth_method": "none", "client_name": "ChatGPT",
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
    })
    assert reg.status_code == 201, reg.text
    client_id = reg.json()["client_id"]
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    auth = await http.get(meta["authorization_endpoint"], params={
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT, "state": "s1",
        "code_challenge": challenge, "code_challenge_method": "S256", "scope": "wardrobe", "resource": f"{base}/mcp",
    })
    assert auth.status_code == 302, auth.text
    login_url = auth.headers["location"]
    assert login_url.startswith(f"{base}/login?req=")
    page = await http.get(login_url)
    assert "ChatGPT wants to use your wardrobe" in page.text
    req = parse_qs(urlparse(login_url).query)["req"][0]
    bad = await http.post(f"{base}/login", data={"req": req, "passphrase": "nope"})
    assert bad.status_code == 401
    good = await http.post(f"{base}/login", data={"req": req, "passphrase": PASSPHRASE})
    assert good.status_code == 302
    back = urlparse(good.headers["location"])
    q = parse_qs(back.query)
    assert back.netloc == "chatgpt.com" and q["state"] == ["s1"]
    token = await http.post(meta["token_endpoint"], data={
        "grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": REDIRECT,
        "client_id": client_id, "code_verifier": verifier,
    })
    assert token.status_code == 200, token.text
    return {**token.json(), "client_id": client_id, "token_endpoint": meta["token_endpoint"]}


async def test_oauth_and_mcp_over_http(running):
    w, base, _ = running
    async with httpx.AsyncClient(follow_redirects=False) as http:
        unauth = await http.post(f"{base}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert unauth.status_code == 401
        assert "resource_metadata" in unauth.headers.get("www-authenticate", "")
        prm = (await http.get(f"{base}/.well-known/oauth-protected-resource/mcp")).json()
        assert prm["authorization_servers"][0].rstrip("/") == base

        tokens = await oauth_login(http, base)

        headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        async with httpx2.AsyncClient(headers=headers, timeout=30) as h2:
            async with Client(streamable_http_client(f"{base}/mcp", http_client=h2)) as client:
                names = {t.name for t in (await client.list_tools()).tools}
                assert "dress_me" in names
                r = await client.call_tool("dress_me", {"wearing": ["beige cords"]})
                assert "Linköping (from your phone" in r.content[0].text
                shown = await client.call_tool("show_outfit", {"item_ids": ["beige cords", "nubikk-leather-sneakers-white"]})
                collage_url = shown.structured_content["collage_url"]
                item_url = shown.structured_content["items"][0]["image"]

        img = await http.get(collage_url)
        assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
        assert Image.open(io.BytesIO(img.content)).width == 1080
        assert (await http.get(item_url)).status_code == 200
        assert (await http.get(item_url.replace("sig=", "sig=x"))).status_code == 403
        assert (await http.get(f"{base}/img/r/not-a-token.jpg")).status_code == 404

        refreshed = await http.post(tokens["token_endpoint"], data={
            "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": tokens["client_id"],
        })
        assert refreshed.status_code == 200, refreshed.text
        reused = await http.post(tokens["token_endpoint"], data={
            "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"], "client_id": tokens["client_id"],
        })
        assert reused.status_code == 400  # rotated
        old = await http.post(f"{base}/mcp", headers={"Authorization": f"Bearer {tokens['access_token']}"},
                              json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert old.status_code == 401


async def test_shortcuts_api(running):
    w, _, private = running
    async with httpx.AsyncClient() as http:
        assert (await http.post(f"{private}/location", json={"lat": 1, "lon": 2})).status_code == 401
        ok = await http.post(f"{private}/location", headers={"Authorization": "Bearer phone-token"},
                             json={"latitude": "37.77", "longitude": "-122.42", "city": "San Francisco", "tz": "America/Los_Angeles"})
        assert ok.status_code == 200
        loc = w.state.location()
        assert loc.name == "San Francisco" and loc.tz == "America/Los_Angeles"

        buf = io.BytesIO()
        Image.new("RGB", (800, 1000), (40, 60, 90)).save(buf, "PNG")
        up = await http.post(f"{private}/inbox", headers={"Authorization": "Bearer phone-token"},
                             files=[("photo", ("IMG_1.png", buf.getvalue(), "image/png"))])
        assert up.status_code == 200, up.text
        assert len(w.catalog.inbox_files()) == 1

        health = (await http.get(f"{private}/health")).json()
        assert health["items"] == 16
