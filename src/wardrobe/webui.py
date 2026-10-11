"""The wardrobe in a browser: browse every item, see what's available, what's
missing and what needs attention, and make small edits.

Served on the private (tailnet-only) app at `/ui`, for a computer on the
tailnet. Not exposed through Funnel. Writes go through `Catalog.save_item`,
like everything else.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import tempfile
import time
from collections import deque
from collections.abc import Callable
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from wardrobe import importer
from wardrobe.analysis import analyse
from wardrobe.catalog import CATEGORIES, IMAGE_EXTS, STATUSES, Catalog, Item
from wardrobe.config import Config
from wardrobe.outfit import slot_of
from wardrobe.render import Renderer
from wardrobe.state import State

COOKIE = "wardrobe_ui"
SESSION_TTL = 30 * 86400
PHOTO_SIZES = (240, 480, 960)
CSRF_HEADER = "x-wardrobe"  # fetch() from the page sets it; a cross-site form can't
EDITABLE = {
    "name": str, "brand": str, "category": str, "type": str, "colour": str, "material": str,
    "size": str, "notes": str, "status": str, "warmth": int, "formality": int, "rain_ok": bool,
    "favourite": bool, "aliases": list, "price": float, "currency": str, "source_url": str,
}
SAFE_NAME = re.compile(r"^[\w.\-]+$")


class WebUI:
    def __init__(
        self,
        catalog: Catalog,
        state: State,
        renderer: Renderer,
        config: Config,
        today: Callable[[], date] = date.today,
    ):
        self.catalog = catalog
        self.state = state
        self.renderer = renderer
        self.config = config
        self.today = today
        self._key = state.secret("ui-session").encode()
        self._failures: deque[float] = deque()

    # ------------------------------------------------------------ session

    @property
    def secret(self) -> str | None:
        """What you type to log in: the passphrase, else the device token, else nothing (open)."""
        return self.config.passphrase or self.config.device_token

    def _sign(self, exp: int) -> str:
        return base64.urlsafe_b64encode(hmac.new(self._key, f"ui:{exp}".encode(), hashlib.sha256).digest()[:18]).decode()

    def _session_ok(self, request: Request) -> bool:
        if not self.secret:
            return True
        exp_s, _, sig = request.cookies.get(COOKIE, "").partition(".")
        try:
            exp = int(exp_s)
        except ValueError:
            return False
        return exp > time.time() and hmac.compare_digest(self._sign(exp), sig)

    def _guard(self, request: Request, write: bool = False) -> Response | None:
        if not self._session_ok(request):
            return JSONResponse({"error": "log in at /ui"}, status_code=401)
        if write and request.headers.get(CSRF_HEADER) != "1":
            return JSONResponse({"error": "missing X-Wardrobe header"}, status_code=403)
        return None

    async def page(self, request: Request) -> Response:
        if not self._session_ok(request):
            return HTMLResponse(_login_page(), headers=_PAGE_HEADERS)
        html = files("wardrobe").joinpath("ui/catalog.html").read_text(encoding="utf-8")
        return HTMLResponse(html, headers=_PAGE_HEADERS)

    async def login(self, request: Request) -> Response:
        form = await request.form()
        cutoff = time.time() - 900
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()
        if len(self._failures) >= 10:
            return HTMLResponse(_login_page("Too many attempts. Wait 15 minutes."), status_code=429, headers=_PAGE_HEADERS)
        supplied = str(form.get("passphrase", ""))
        if self.secret and not hmac.compare_digest(supplied.encode(), self.secret.encode()):
            self._failures.append(time.time())
            return HTMLResponse(_login_page("Wrong passphrase."), status_code=401, headers=_PAGE_HEADERS)
        exp = int(time.time()) + SESSION_TTL
        resp = RedirectResponse("/ui", status_code=303)
        resp.set_cookie(COOKIE, f"{exp}.{self._sign(exp)}", max_age=SESSION_TTL, httponly=True,
                        samesite="strict", secure=request.url.scheme == "https")
        return resp

    async def logout(self, request: Request) -> Response:
        resp = RedirectResponse("/ui", status_code=303)
        resp.delete_cookie(COOKIE)
        return resp

    # ------------------------------------------------------------ reading

    def item_json(self, item: Item, wears: dict[str, int], last: dict[str, date]) -> dict[str, Any]:
        keys = ("brand", "type", "colour", "material", "warmth", "formality", "size", "price", "currency",
                "source_url", "notes", "bought")
        out: dict[str, Any] = {
            "id": item.id, "name": item.name, "category": item.category, "slot": slot_of(item),
            "status": item.status if item.status in STATUSES else "owned",
            "favourite": item.favourite, "rain_ok": item.rain_ok, "aliases": item.aliases,
            "needs_review": bool(item.get("needs_review")), "photos": len(item.photos),
            "wears": wears.get(item.id, 0), "last_worn": last[item.id].isoformat() if item.id in last else None,
            "guessed": sorted(item.inferred),
        }
        for key in keys:
            value = item.get(key)
            if value is not None:
                out[key] = value if isinstance(value, int | float | bool) else str(value)
        return out

    async def items(self, request: Request) -> Response:
        if denied := self._guard(request):
            return denied
        wears, last = self.state.wear_counts(), self.state.last_worn()
        all_items = sorted(self.catalog.items(include_inactive=True), key=lambda i: (i.category, i.name.lower()))
        return JSONResponse({
            "items": [self.item_json(i, wears, last) for i in all_items],
            "inbox": [p.name for p in self.catalog.inbox_files()],
            "errors": self.catalog.errors,
            "categories": list(CATEGORIES),
            "statuses": list(STATUSES),
        })

    async def analysis(self, request: Request) -> Response:
        if denied := self._guard(request):
            return denied
        result = analyse(self.catalog.items(), self.state.wear_counts(), self.state.last_worn(),
                         self.state.wear_history(), self.today())
        return JSONResponse(result)

    async def photo(self, request: Request) -> Response:
        if denied := self._guard(request):
            return denied
        item = self.catalog.get(request.path_params["item_id"])
        n, size = request.path_params["n"], request.path_params["size"]
        if not item or size not in PHOTO_SIZES or not 0 <= n < len(item.photos):
            return Response(status_code=404)
        return Response(self.renderer.thumbnail_jpeg(item.photos[n], size, 82), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=3600"})

    async def inbox_photo(self, request: Request) -> Response:
        if denied := self._guard(request):
            return denied
        name, size = request.path_params["name"], request.path_params["size"]
        path = self.catalog.inbox_dir / name
        if not SAFE_NAME.match(name) or size not in PHOTO_SIZES or not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
            return Response(status_code=404)
        return Response(self.renderer.thumbnail_jpeg(path, size, 82), media_type="image/jpeg")

    # ------------------------------------------------------------ writing

    async def create(self, request: Request) -> Response:
        if denied := self._guard(request, write=True):
            return denied
        body = await _json(request)
        fields, error = _clean_fields(body)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        if not fields.get("name"):
            return JSONResponse({"error": "name is required"}, status_code=400)
        photos: list[Path] = []
        for name in body.get("from_inbox") or []:
            path = self.catalog.inbox_dir / str(name)
            if not SAFE_NAME.match(str(name)) or not path.is_file():
                return JSONResponse({"error": f"no inbox photo {name!r}"}, status_code=400)
            photos.append(path)
        fields.setdefault("status", "owned")
        if fields["status"] != "wishlist":
            # Added by hand with few details: flag it so the assistant offers to complete it.
            fields.setdefault("needs_review", True)
        item = self.catalog.save_item(None, fields, add_photos=photos)
        return JSONResponse(self.item_json(item, {}, {}), status_code=201)

    async def update(self, request: Request) -> Response:
        if denied := self._guard(request, write=True):
            return denied
        item_id = request.path_params["item_id"]
        if self.catalog.get(item_id) is None:
            return JSONResponse({"error": "no such item"}, status_code=404)
        body = await _json(request)
        fields, error = _clean_fields(body)
        if error:
            return JSONResponse({"error": error}, status_code=400)
        if body.get("needs_review") is False:
            fields["needs_review"] = None  # reviewed: remove the flag
        item = self.catalog.save_item(item_id, fields)
        return JSONResponse(self.item_json(item, self.state.wear_counts(), self.state.last_worn()))

    async def upload_photo(self, request: Request) -> Response:
        if denied := self._guard(request, write=True):
            return denied
        item_id = request.path_params["item_id"]
        if self.catalog.get(item_id) is None:
            return JSONResponse({"error": "no such item"}, status_code=404)
        form = await request.form(max_part_size=40 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for n, (_key, value) in enumerate(form.multi_items(), 1):
                if not hasattr(value, "read"):
                    continue
                try:
                    jpeg = importer.image_bytes_to_jpeg(await value.read())
                except Exception:
                    return JSONResponse({"error": "not an image"}, status_code=400)
                path = Path(tmp) / f"upload-{n}.jpg"
                path.write_bytes(jpeg)
                paths.append(path)
            if not paths:
                return JSONResponse({"error": "no image received"}, status_code=400)
            item = self.catalog.save_item(item_id, {}, add_photos=paths)
        return JSONResponse(self.item_json(item, self.state.wear_counts(), self.state.last_worn()))

    async def import_link(self, request: Request) -> Response:
        if denied := self._guard(request, write=True):
            return denied
        url = str((await _json(request)).get("url") or "").strip()
        if not url.startswith("http"):
            return JSONResponse({"error": "paste a product link"}, status_code=400)
        result = await importer.import_url(self.catalog, url, chromium=self.config.chromium)
        if result.item is None:
            return JSONResponse({"error": result.error or "import failed"}, status_code=422)
        return JSONResponse({"item": self.item_json(result.item, {}, {}), "existing": result.existing,
                             "warning": result.error})

    def routes(self) -> list[Route]:
        return [
            Route("/", lambda request: RedirectResponse("/ui"), methods=["GET"]),
            Route("/ui", self.page, methods=["GET"]),
            Route("/ui/login", self.login, methods=["POST"]),
            Route("/ui/logout", self.logout, methods=["POST"]),
            Route("/ui/api/items", self.items, methods=["GET"]),
            Route("/ui/api/items", self.create, methods=["POST"]),
            Route("/ui/api/items/{item_id}", self.update, methods=["PATCH"]),
            Route("/ui/api/items/{item_id}/photos", self.upload_photo, methods=["POST"]),
            Route("/ui/api/analysis", self.analysis, methods=["GET"]),
            Route("/ui/api/import", self.import_link, methods=["POST"]),
            Route("/ui/photo/{item_id}/{n:int}/{size:int}", self.photo, methods=["GET"]),
            Route("/ui/inbox/{name}/{size:int}", self.inbox_photo, methods=["GET"]),
        ]


async def _json(request: Request) -> dict[str, Any]:
    try:
        data = json.loads(await request.body() or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _clean_fields(body: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Keep known fields with the right types; '' or null removes a field."""
    fields: dict[str, Any] = {}
    for key, kind in EDITABLE.items():
        if key not in body:
            continue
        value = body[key]
        if value is None or value == "":
            fields[key] = None
            continue
        try:
            if kind is bool:
                value = bool(value)
            elif kind is int:
                value = int(value)
            elif kind is float:
                value = float(value)
            elif kind is list:
                value = [str(v).strip() for v in (value if isinstance(value, list) else str(value).split(",")) if str(v).strip()]
            else:
                value = str(value).strip()
        except (TypeError, ValueError):
            return {}, f"{key} has the wrong type"
        fields[key] = value
    if fields.get("category") and fields["category"] not in CATEGORIES:
        return {}, f"category must be one of {', '.join(CATEGORIES)}"
    if fields.get("status") and fields["status"] not in STATUSES:
        return {}, f"status must be one of {', '.join(STATUSES)}"
    if fields.get("warmth") is not None and not 0 <= fields["warmth"] <= 5:
        return {}, "warmth is 0–5"
    if fields.get("formality") is not None and not 1 <= fields["formality"] <= 5:
        return {}, "formality is 1–5"
    if fields.get("name") is None and "name" in fields:
        return {}, "an item needs a name"
    return fields, None


_PAGE_HEADERS = {"X-Frame-Options": "DENY", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _login_page(error: str = "") -> str:
    msg = f'<p class="err">{error}</p>' if error else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Wardrobe</title>
<style>
:root {{ color-scheme: light dark; --bg:#faf8f5; --fg:#221f1c; --muted:#786f69; --line:#e2ddd6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#171513; --fg:#f2eee9; --muted:#a59d95; --line:#3a3530; }} }}
body {{ margin:0; min-height:100vh; display:grid; place-items:center; background:var(--bg); color:var(--fg);
  font:16px/1.45 -apple-system, system-ui, sans-serif; }}
main {{ width:min(340px, calc(100vw - 32px)); }}
h1 {{ font-size:26px; margin:0 0 4px; letter-spacing:-.02em; }} p {{ color:var(--muted); margin:0 0 20px; }}
input {{ width:100%; box-sizing:border-box; font:inherit; padding:13px 14px; border-radius:12px; border:1px solid var(--line);
  background:transparent; color:inherit; margin-bottom:12px; }}
button {{ width:100%; font:inherit; font-weight:600; padding:13px; border:0; border-radius:12px; background:var(--fg); color:var(--bg); cursor:pointer; }}
.err {{ color:#c0392b; }}
</style></head><body><main><h1>Wardrobe</h1><p>Your clothes, in one place.</p>{msg}
<form method="post" action="/ui/login"><input type="password" name="passphrase" placeholder="Passphrase" autofocus required>
<button type="submit">Open</button></form></main></body></html>"""
