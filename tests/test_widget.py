"""Render the outfit card in Chromium, through both the MCP Apps bridge and ChatGPT's window.openai.

Skipped when Playwright or a Chromium binary isn't available.
"""

import json
import os
import shutil
from pathlib import Path

import pytest
from conftest import FakeWeather
from mcp import Client

from wardrobe.server import Wardrobe, build_mcp

playwright = pytest.importorskip("playwright.async_api")
CHROMIUM = os.environ.get("WARDROBE_CHROMIUM") or next(
    (p for p in ("/opt/pw-browsers/chromium", shutil.which("chromium") or "") if p and Path(p).exists()), None
)
pytestmark = pytest.mark.skipif(CHROMIUM is None, reason="no chromium binary")

HOST = """<!doctype html><html><body><iframe id="f" style="border:0;width:390px"></iframe><script>
const f = document.getElementById('f'); window.log = [];
window.addEventListener('message', (e) => {
  const m = e.data; window.log.push(m.method || 'response');
  if (m.method === 'ui/initialize') f.contentWindow.postMessage({jsonrpc:'2.0', id:m.id, result:{protocolVersion:'2026-01-26', hostCapabilities:{}, hostInfo:{name:'test'}, hostContext:{theme:'dark'}}}, '*');
  if (m.method === 'ui/notifications/initialized') f.contentWindow.postMessage({jsonrpc:'2.0', method:'ui/notifications/tool-result', params: window.__RESULT}, '*');
});
f.srcdoc = window.__HTML;
</script></body></html>"""


async def _outfit(config):
    w = Wardrobe(config, weather=FakeWeather())
    w.state.set_location(58.41, 15.62, "Linköping", "from your phone", "Europe/Stockholm")
    async with Client(build_mcp(w)) as c:
        html = (await c.read_resource("ui://wardrobe/outfit.html")).contents[0].text
        r = await c.call_tool("show_outfit", {"item_ids": ["beige cords", "nubikk-leather-sneakers-white", "ecru knit"], "note": "Easy."})
    return html, r.model_dump(by_alias=True, exclude_none=True)


async def test_card_renders_via_mcp_apps_bridge(config, tmp_path):
    html, result = await _outfit(config)
    async with playwright.async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROMIUM)
        page = await browser.new_page()
        await page.add_init_script(f"window.__RESULT = {json.dumps(result)}; window.__HTML = {json.dumps(html)};")
        (tmp_path / "host.html").write_text(HOST)
        await page.goto((tmp_path / "host.html").as_uri())
        frame = page.frame_locator("#f")
        await frame.locator(".item img").first.wait_for(timeout=5000)
        assert await frame.locator(".item img").count() == 3
        assert await frame.locator("html").get_attribute("data-theme") == "dark"
        log = await page.evaluate("window.log")
        assert log[0] == "ui/initialize" and "ui/notifications/initialized" in log and "ui/notifications/size-changed" in log
        await browser.close()


async def test_card_renders_via_openai_globals(config, tmp_path):
    html, result = await _outfit(config)
    async with playwright.async_playwright() as pw:
        browser = await pw.chromium.launch(executable_path=CHROMIUM)
        page = await browser.new_page()
        await page.add_init_script(
            "window.openai = {toolOutput: %s, toolResponseMetadata: %s, openExternal: (x) => { window.opened = x.href }};"
            % (json.dumps(result["structuredContent"]), json.dumps(result["_meta"]))
        )
        (tmp_path / "widget.html").write_text(html)
        await page.goto((tmp_path / "widget.html").as_uri())
        assert await page.locator(".item img").count() == 3
        assert "Today · Linköping" in await page.inner_text("h1")
        await page.click("#open")
        assert (await page.evaluate("window.opened")).startswith(config.public_url + "/img/r/")
        await browser.close()
