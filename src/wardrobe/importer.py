"""Turn a product link into an item folder with photos and a prefilled item.yaml.

Shops block datacenter IPs, so this is meant to run from your home connection.
It tries a plain request first and falls back to headless Chromium
(`uv sync --extra browser`) when the page is blocked or rendered by JavaScript.
Pages can also arrive pre-extracted from the iPhone share sheet (see
docs/SHORTCUTS.md), which sidesteps blocking entirely.
"""

from __future__ import annotations

import io
import json
import logging
import re
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

import httpx
from PIL import Image

from wardrobe.catalog import Catalog, Item
from wardrobe.heuristics import canonical_colour, infer
from wardrobe.render import open_image

log = logging.getLogger(__name__)

BROWSER_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}
MAX_PHOTOS = 3


@dataclass
class PageParts:
    url: str
    title: str = ""
    jsonld: list[str] = field(default_factory=list)
    meta: dict[str, list[str]] = field(default_factory=dict)
    images: list[str] = field(default_factory=list)


@dataclass
class ProductInfo:
    url: str
    name: str | None = None
    brand: str | None = None
    colour: str | None = None
    images: list[str] = field(default_factory=list)
    material: str | None = None
    description: str | None = None
    sku: str | None = None
    price: float | None = None
    currency: str | None = None

    @property
    def usable(self) -> bool:
        return bool(self.name and self.images)


@dataclass
class ImportResult:
    url: str
    item: Item | None = None
    error: str | None = None
    existing: bool = False


# ---------------------------------------------------------------- parsing


class _Collector(HTMLParser):
    def __init__(self, parts: PageParts):
        super().__init__(convert_charrefs=True)
        self.parts = parts
        self._in_ld = False
        self._in_title = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = a.get("property") or a.get("name") or a.get("itemprop")
            if key and a.get("content"):
                self.parts.meta.setdefault(key.lower(), []).append(a["content"])
        elif tag == "script" and "ld+json" in a.get("type", ""):
            self._in_ld, self._buf = True, []
        elif tag == "title":
            self._in_title = True
        elif tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            if src and not src.startswith("data:"):
                self.parts.images.append(src)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_ld:
            self.parts.jsonld.append("".join(self._buf))
            self._in_ld = False
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_ld:
            self._buf.append(data)
        elif self._in_title:
            self.parts.title += data


def extract_parts(html: str, url: str) -> PageParts:
    parts = PageParts(url=url)
    _Collector(parts).feed(html)
    parts.title = parts.title.strip()
    return parts


def _types(obj: dict[str, Any]) -> set[str]:
    t = obj.get("@type", [])
    return {str(x) for x in (t if isinstance(t, list) else [t])}


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for key in ("@graph", "hasVariant", "isVariantOf", "mainEntity", "itemListElement"):
            if key in node:
                yield from _walk(node[key])
    elif isinstance(node, list):
        for x in node:
            yield from _walk(x)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return _text(value.get("name") or value.get("@value"))
    if isinstance(value, list):
        return _text(value[0]) if value else None
    text = str(value).strip()
    return text or None


def _image_urls(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return _image_urls(value.get("contentUrl") or value.get("url"))
    if isinstance(value, list):
        return [u for v in value for u in _image_urls(v)]
    return []


def _colour_code(url: str) -> str | None:
    """Mango puts the colour variant in ?c=08 (sometimes 'color=')."""
    qs = parse_qs(urlparse(url).query)
    for key in ("c", "color", "colour"):
        if qs.get(key):
            return qs[key][0]
    return None


def _clean_title(title: str, brand: str | None) -> str:
    title = re.split(r"\s+[|–—]\s+", title)[0].strip()
    if brand:
        title = re.sub(rf"\s*[-–]\s*{re.escape(brand)}\b.*$", "", title, flags=re.I).strip()
        title = re.sub(rf"^{re.escape(brand)}\s*[-–:]?\s*", "", title, flags=re.I).strip()
    return title


def parse_parts(parts: PageParts) -> ProductInfo:
    info = ProductInfo(url=parts.url)
    products: list[dict[str, Any]] = []
    for block in parts.jsonld:
        try:
            data = json.loads(block.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        products += [o for o in _walk(data) if _types(o) & {"Product", "ProductGroup", "IndividualProduct"}]

    colour_code = _colour_code(parts.url)
    chosen: dict[str, Any] | None = None
    if products:
        variants = [p for p in products if "Product" in _types(p) and "ProductGroup" not in _types(p)]
        if colour_code:
            for p in variants or products:
                blob = json.dumps(p)
                if re.search(rf"[_\-/=]{re.escape(colour_code)}(?:[_.\-?&\"]|$)", blob):
                    chosen = p
                    break
        chosen = chosen or (variants or products)[0]
        group = next((p for p in products if "ProductGroup" in _types(p)), {})
        info.name = _text(chosen.get("name")) or _text(group.get("name"))
        info.brand = _text(chosen.get("brand")) or _text(group.get("brand"))
        info.colour = _text(chosen.get("color")) or _text(chosen.get("colour"))
        info.material = _text(chosen.get("material")) or _text(group.get("material"))
        info.description = _text(chosen.get("description")) or _text(group.get("description"))
        info.sku = _text(chosen.get("sku")) or _text(chosen.get("productID"))
        info.images = _image_urls(chosen.get("image")) or _image_urls(group.get("image"))
        offers = chosen.get("offers") or group.get("offers")
        offer = offers[0] if isinstance(offers, list) and offers else offers
        if isinstance(offer, dict):
            try:
                info.price = float(str(offer.get("price") or offer.get("lowPrice")).replace(",", "."))
            except (TypeError, ValueError):
                pass
            info.currency = _text(offer.get("priceCurrency"))

    meta = {k: v[0] for k, v in parts.meta.items()}
    info.brand = info.brand or meta.get("product:brand") or meta.get("og:brand")
    info.name = info.name or _clean_title(meta.get("og:title") or parts.title, info.brand) or None
    info.colour = info.colour or meta.get("product:color")
    info.description = info.description or meta.get("og:description") or meta.get("description")
    if info.price is None:
        try:
            info.price = float((meta.get("product:price:amount") or meta.get("og:price:amount") or "").replace(",", "."))
        except ValueError:
            pass
    info.currency = info.currency or meta.get("product:price:currency") or meta.get("og:price:currency")
    if not info.images:
        info.images = parts.meta.get("og:image", []) + parts.meta.get("og:image:secure_url", [])
    if not info.colour:
        # "Mango Piké - beige" style titles
        info.colour = canonical_colour(meta.get("og:title", "") or parts.title)
    if info.name and info.brand:
        info.name = _clean_title(info.name, info.brand)

    info.images = _pick_images(info.images or parts.images, parts.url, colour_code)
    return info


def _pick_images(urls: list[str], page_url: str, colour_code: str | None) -> list[str]:
    seen, out = set(), []
    for raw in urls:
        url = urljoin(page_url, raw.strip())
        if not url.startswith("http"):
            continue
        host = urlparse(url).netloc
        if "ztat.net" in host:  # Zalando: ask for the large packshot
            parsed = urlparse(url)
            url = urlunparse(parsed._replace(query="imwidth=1200&filter=packshot"))
        key = urlparse(url)._replace(query="").geturl()
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
    if colour_code:
        matching = [u for u in out if re.search(rf"_{re.escape(colour_code)}(?:[_.\-]|$)", urlparse(u).path)]
        out = matching or out
    return out[: MAX_PHOTOS * 2]


def parse_product(html: str, url: str) -> ProductInfo:
    return parse_parts(extract_parts(html, url))


def parts_from_payload(payload: dict[str, Any]) -> PageParts:
    """Page data posted by the iOS share-sheet Shortcut."""
    meta: dict[str, list[str]] = {}
    for k, v in (payload.get("meta") or {}).items():
        meta.setdefault(str(k).lower(), []).extend(v if isinstance(v, list) else [str(v)])
    return PageParts(
        url=str(payload["url"]),
        title=str(payload.get("title") or ""),
        jsonld=[str(x) for x in payload.get("jsonld") or []],
        meta=meta,
        images=[str(x) for x in payload.get("images") or []],
    )


# ---------------------------------------------------------------- fetching


async def fetch_html(url: str, chromium: str | None = None) -> str:
    """Plain HTTP first; headless Chromium if that's blocked or yields no product."""
    error: str | None = None
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=25) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            html = resp.text
            if parse_product(html, str(resp.url)).usable:
                return html
            error = "page has no product data (probably rendered by JavaScript)"
        else:
            error = f"HTTP {resp.status_code}"
    except httpx.HTTPError as exc:
        error = f"{type(exc).__name__}: {exc}"
    log.info("plain fetch of %s failed (%s); trying headless browser", url, error)
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(f"{error}; install the browser extra (uv sync --extra browser) to fetch pages like a real browser") from None
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, executable_path=chromium or None)
        try:
            context = await browser.new_context(user_agent=BROWSER_UA, locale="sv-SE", viewport={"width": 1280, "height": 900})
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)
            return await page.content()
        finally:
            await browser.close()


async def download_images(urls: list[str], referer: str, dest: Path, limit: int = MAX_PHOTOS) -> list[Path]:
    saved: list[Path] = []
    async with httpx.AsyncClient(
        headers={**HEADERS, "Referer": referer, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"},
        follow_redirects=True,
        timeout=25,
    ) as client:
        for url in urls:
            if len(saved) >= limit:
                break
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                img = open_image_bytes(resp.content)
            except Exception as exc:
                log.info("skipping image %s: %s", url, exc)
                continue
            if min(img.size) < 200:
                continue  # icons, swatches
            img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            path = dest / f"{len(saved) + 1}.jpg"
            img.save(path, "JPEG", quality=90)
            saved.append(path)
    return saved


def open_image_bytes(data: bytes) -> Image.Image:
    return open_image(io.BytesIO(data))


def normalise_url(url: str) -> str:
    """Drop tracking parameters but keep the ones that pick a variant."""
    parsed = urlparse(url.strip())
    keep = {k: v for k, v in parse_qs(parsed.query).items() if k in ("c", "color", "colour", "size")}
    query = "&".join(f"{k}={v[0]}" for k, v in sorted(keep.items()))
    return urlunparse(parsed._replace(query=query, fragment=""))


async def import_url(
    catalog: Catalog,
    url: str,
    payload: dict[str, Any] | None = None,
    chromium: str | None = None,
    extra: dict[str, Any] | None = None,
) -> ImportResult:
    """Import one product link. `payload` = page data from the share sheet."""
    clean = normalise_url(url)
    for item in catalog.items(include_inactive=True):
        if item.get("source_url") and normalise_url(str(item.get("source_url"))) == clean:
            return ImportResult(url, item=item, existing=True)
    try:
        if payload:
            info = parse_parts(parts_from_payload({**payload, "url": url}))
        else:
            info = parse_product(await fetch_html(url, chromium), url)
    except Exception as exc:
        return ImportResult(url, error=str(exc))
    if not info.name:
        return ImportResult(url, error="couldn't find the product name on the page")

    guess = infer(info.name, " ".join(filter(None, [info.material, info.description])))
    fields: dict[str, Any] = {k: v for k, v in guess.items() if k != "layer"}
    fields.update({
        "name": info.name,
        "brand": info.brand,
        "colour": canonical_colour(info.colour or "") or (info.colour.lower() if info.colour else guess.get("colour")),
        "material": guess.get("material") or info.material,
        "composition": info.material if info.material and info.material != guess.get("material") else None,
        "price": info.price,
        "currency": info.currency,
        "source_url": clean,
        "status": "owned",
        "needs_review": True,
    })
    fields.update({k: v for k, v in (extra or {}).items() if v is not None})
    fields = {k: v for k, v in fields.items() if v not in (None, "")}

    with tempfile.TemporaryDirectory() as tmp:
        photos = await download_images(info.images, url, Path(tmp))
        item = catalog.save_item(None, fields, add_photos=photos)
    if not photos:
        return ImportResult(url, item=item, error="imported without a photo (images were blocked); add one to the item folder")
    return ImportResult(url, item=item)


def image_bytes_to_jpeg(data: bytes, max_side: int = 2000) -> bytes:
    img = open_image_bytes(data)
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()
