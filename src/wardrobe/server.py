"""The MCP server: tools, the outfit view, and the public/private HTTP apps."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from mcp.server.apps import Apps, ResourceCsp
from mcp.server.auth.handlers.metadata import MetadataHandler
from mcp.server.auth.routes import build_metadata, cors_middleware
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.resources import TextResource
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, ImageContent, TextContent, ToolAnnotations
from pydantic import Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from wardrobe import importer
from wardrobe.analysis import analyse
from wardrobe.auth import SCOPE, PassphraseOAuthProvider
from wardrobe.catalog import CATEGORIES, IMAGE_EXTS, Catalog, Item
from wardrobe.config import Config
from wardrobe.heuristics import layer_for
from wardrobe.matching import resolve, search
from wardrobe.outfit import SLOT_TITLES, SLOTS, pick_candidates, slot_of, temperature_bias
from wardrobe.render import Renderer
from wardrobe.state import State
from wardrobe.weather import DayWeather, Place, WeatherClient

log = logging.getLogger(__name__)

OUTFIT_UI = "ui://wardrobe/outfit.html"
OUTFIT_UI_OPENAI = "ui://wardrobe/outfit-openai.html"
LOCATION_MAX_AGE = 36 * 3600

INSTRUCTIONS = """\
You are the user's personal stylist with access to their real wardrobe (every item has photos).

How to behave:
- When they ask what to wear, or say what they already have on, call `dress_me` first (pass what \
they're wearing in `wearing`). It returns the weather where they are and photo-numbered candidates. \
Look at the photos, choose one complete outfit (outerwear if needed, top/mid layer, bottoms, shoes), \
then call `show_outfit` with the chosen item ids. Mention the weather in a few words and why the outfit works.
- When they say they're wearing something (now or "yesterday"), call `log_wear` without asking. \
If they accept a suggested outfit ("ok", "wearing that"), log those items.
- Keep replies short: they read on a phone. One clarifying question at most, and only if truly needed.
- After `show_outfit`, also give the image link as a markdown link, e.g. [Outfit](url), in case the card doesn't render.
- Use `find_items` for questions about what they own, `wardrobe_analysis` for gaps, duplicates and \
shopping advice (judge gaps against their climate, style notes and what they actually wear).
- Items marked needs_review were added automatically; if one comes up, you may confirm its details \
with the user and fix them with `save_item`.
- `remember` stores lasting preferences ("never black with brown"); respect stored preferences.
- New photos in the inbox: call `review_inbox`, describe each item and save it with `save_item` (from_inbox).
"""


class LocationUnknown(Exception):
    pass


class Wardrobe:
    """Services shared by the tools and HTTP routes."""

    def __init__(self, config: Config, weather: WeatherClient | None = None):
        self.config = config
        self.catalog = Catalog(config.wardrobe_dir)
        self.catalog.ensure_layout()
        self.state = State(config.state_dir)
        self.renderer = Renderer(self.state.cache_dir)
        self.weather = weather or WeatherClient()
        self._image_key = self.state.secret("image-signing").encode()

    # ------------------------------------------------------------ signed URLs

    def _sig(self, message: str) -> str:
        return base64.urlsafe_b64encode(hmac.new(self._image_key, message.encode(), hashlib.sha256).digest()[:18]).decode()

    def item_image_url(self, item: Item, size: int = 600, ttl: int = 7 * 86400) -> str | None:
        if not item.main_photo:
            return None
        exp = int(time.time()) + ttl
        path = f"/img/i/{item.id}/{size}"
        return f"{self.config.public_url}{path}?exp={exp}&sig={self._sig(f'{path}:{exp}')}"

    def verify_image(self, path: str, exp: str, sig: str) -> bool:
        try:
            if int(exp) < time.time():
                return False
        except ValueError:
            return False
        return hmac.compare_digest(self._sig(f"{path}:{exp}"), sig)

    def render_url(self, path: Path) -> str:
        return f"{self.config.public_url}/img/r/{self.state.add_render(path)}.jpg"

    # ------------------------------------------------------------ location

    async def place(self, override: str | None = None) -> tuple[Place, str]:
        if override:
            try:
                found = await self.weather.geocode(override)
            except httpx.HTTPError as exc:
                raise LocationUnknown(f"place lookup failed ({type(exc).__name__})") from exc
            if not found:
                raise LocationUnknown(f"couldn't find a place called {override!r}")
            return found, "as you said"
        loc = self.state.location()
        if loc and time.time() - loc.updated_at < LOCATION_MAX_AGE:
            return Place(loc.lat, loc.lon, loc.name, loc.tz), f"{loc.source}, {loc.age_text()}"
        home = self.catalog.profile().get("home") or self.config.home
        if home:
            try:
                found = await self.weather.geocode(str(home))
            except httpx.HTTPError as exc:
                log.warning("geocoding home failed: %r", exc)
                found = None
            if found:
                return found, "home (no recent location from your phone)"
        if loc:
            return Place(loc.lat, loc.lon, loc.name, loc.tz), f"last known location, {loc.age_text()}"
        raise LocationUnknown("no location yet")

    def local_today(self, place: Place | None = None) -> date:
        """The user's calendar day: from `place`, else the last known location, else the server's."""
        if place is None:
            loc = self.state.location()
            place = Place(loc.lat, loc.lon, loc.name, loc.tz) if loc else None
        if place and place.tz:
            try:
                return datetime.now(ZoneInfo(place.tz)).date()
            except ZoneInfoNotFoundError:
                pass
        if place:
            return (datetime.now(timezone.utc) + timedelta(hours=round(place.lon / 15))).date()
        return date.today()

    async def day_weather(self, place: Place, which: str) -> DayWeather | None:
        try:
            return await self.weather.day(place, which)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("weather unavailable: %r", exc)
            return None


def _neutral_weather(place: str, day: date) -> DayWeather:
    """Stand-in when no forecast is reachable: mild, dry."""
    return DayWeather(
        place=place, day=day, hours=(8, 22), temp_min=12, temp_max=16, feels_min=11, feels_max=16,
        rain_prob_max=0, rain_mm=0, rain_hours=[], wind_max=0, conditions="weather unavailable", snow=False,
    )


def _days_ago(day: date | None, today: date) -> str:
    if day is None:
        return "not worn yet"
    n = (today - day).days
    return "worn today" if n == 0 else ("worn yesterday" if n == 1 else f"worn {n}d ago")


def _item_line(label: str, item: Item, last: date | None, today: date) -> str:
    bits = []
    if item.warmth is not None:
        bits.append(f"warmth {item.warmth}")
    if item.formality is not None:
        bits.append(f"formality {item.formality}")
    for key in ("material", "type"):
        if item.get(key):
            bits.append(str(item.get(key)))
    if item.rain_ok:
        bits.append("rain-ok")
    if not item.photos:
        bits.append("NO PHOTO")
    if item.get("needs_review"):
        bits.append("needs review")
    return f"{label} `{item.id}` — {item.label()} · {', '.join(bits)} · {_days_ago(last, today)}"


def _image(data: bytes) -> ImageContent:
    return ImageContent(type="image", data=base64.b64encode(data).decode(), mime_type="image/jpeg")


def _text(text: str) -> TextContent:
    return TextContent(type="text", text=text)


def _resolve_many(items: list[Item], phrases: list[str]) -> tuple[list[Item], list[str]]:
    found, problems = [], []
    for phrase in phrases:
        r = resolve(items, phrase)
        if r.item:
            if r.item not in found:
                found.append(r.item)
        elif r.candidates:
            problems.append(f"'{phrase}' could be: " + ", ".join(f"`{c.id}` ({c.label()})" for c in r.candidates[:5]))
        else:
            problems.append(f"'{phrase}': no matching item")
    return found, problems


def _parse_day(value: str | None, today: date) -> date:
    if not value or value == "today":
        return today
    if value == "yesterday":
        return today - timedelta(days=1)
    return date.fromisoformat(value)


def build_mcp(w: Wardrobe) -> MCPServer:
    config = w.config
    auth_kwargs: dict[str, Any] = {}
    if config.auth == "oauth":
        assert config.passphrase
        provider = PassphraseOAuthProvider(w.state, config.public_url, config.passphrase)
        auth_kwargs = {
            "auth_server_provider": provider,
            "auth": AuthSettings(
                issuer_url=config.public_url,
                resource_server_url=f"{config.public_url}/mcp",
                required_scopes=[SCOPE],
                client_registration_options=ClientRegistrationOptions(enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]),
                revocation_options=RevocationOptions(enabled=True),
                validate_token_resource=False,
            ),
        }

    apps = Apps()

    # ------------------------------------------------------------- show_outfit

    @apps.tool(
        resource_uri=OUTFIT_UI,
        title="Show outfit",
        annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False),
        meta={
            "openai/outputTemplate": OUTFIT_UI_OPENAI,
            "openai/toolInvocation/invoking": "Putting the outfit together…",
            "openai/toolInvocation/invoked": "Here's the outfit",
        },
    )
    async def show_outfit(
        item_ids: Annotated[list[str], Field(description="Ids of every item in the outfit (outerwear, tops, bottoms, shoes, accessories).")],
        title: Annotated[str | None, Field(description="Short title, e.g. 'Office, rainy afternoon'. Defaults to day + place.")] = None,
        note: Annotated[str | None, Field(description="One or two sentences on why it works, shown under the photos.")] = None,
        day: Literal["today", "tomorrow"] = "today",
    ) -> CallToolResult:
        """Show the user the outfit as photos (inline card where supported, plus an image link)."""
        items = w.catalog.items(include_inactive=True)
        chosen, problems = _resolve_many(items, item_ids)
        if not chosen:
            return CallToolResult(content=[_text("None of those ids matched. " + "; ".join(problems))], is_error=True)
        chosen.sort(key=lambda i: SLOTS.index(slot_of(i)))
        weather_text = ""
        heading = title
        try:
            where, _ = await w.place(None)
            weather = await w.day_weather(where, day)
            if weather:
                weather_text = weather.text()
            heading = heading or f"{day.capitalize()} · {(where.name or '').split(',')[0]}".rstrip(" ·")
        except LocationUnknown:
            heading = heading or day.capitalize()
        collage = w.renderer.collage(chosen, heading or "Outfit", weather_text, note or "")
        url = w.render_url(collage)
        structured = {
            "title": heading,
            "weather": weather_text,
            "note": note,
            "collage_url": url,
            "items": [
                {"id": i.id, "name": i.name, "brand": i.brand, "colour": i.colour, "category": i.category, "image": w.item_image_url(i)}
                for i in chosen
            ],
        }
        thumbs = {i.id: w.renderer.data_uri(i.main_photo, 420) for i in chosen if i.main_photo}
        text = f"Outfit shown ({len(chosen)} items). Full image (valid 24 h): {url}"
        if problems:
            text += "\nSkipped: " + "; ".join(problems)
        return CallToolResult(
            content=[_text(text), _image(w.renderer.scaled_jpeg(collage, 640, 75))],
            structured_content=structured,
            meta={"wardrobe/thumbs": thumbs},
        )

    html = files("wardrobe").joinpath("ui/outfit.html").read_text(encoding="utf-8")
    csp = ResourceCsp(resource_domains=[config.public_url])
    apps.add_html_resource(OUTFIT_UI, html, name="Outfit", description="Outfit card with photos", csp=csp, prefers_border=False)

    mcp = MCPServer(
        "wardrobe",
        title="Wardrobe",
        description="Your wardrobe with photos, the weather where you are, and outfit suggestions.",
        instructions=INSTRUCTIONS,
        version="0.1.0",
        extensions=[apps],
        **auth_kwargs,
    )
    mcp.add_resource(
        TextResource(
            uri=OUTFIT_UI_OPENAI,
            name="Outfit (ChatGPT)",
            mime_type="text/html+skybridge",
            text=html,
            meta={
                "openai/widgetDescription": "Shows the chosen outfit as photos with the day's weather.",
                "openai/widgetPrefersBorder": False,
                "openai/widgetCSP": {"resource_domains": [config.public_url], "connect_domains": []},
            },
        )
    )

    if config.auth == "oauth":
        mcp.custom_route("/login", methods=["GET", "POST"], include_in_schema=False)(auth_kwargs["auth_server_provider"].login_page)

    read_only = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
    writes = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

    # ---------------------------------------------------------------- dress_me

    @mcp.tool(title="Dress me", annotations=read_only)
    async def dress_me(
        wearing: Annotated[list[str] | None, Field(description="Items the user already has on or wants to wear, in their words or as ids, e.g. ['beige mango cords'].")] = None,
        occasion: Annotated[str | None, Field(description="What the day involves, e.g. 'office', 'dinner date', 'gym'.")] = None,
        place: Annotated[str | None, Field(description="Only if the user names a place different from where they are now.")] = None,
        day: Annotated[Literal["today", "tomorrow"], Field(description="Which day to dress for.")] = "today",
    ) -> CallToolResult:
        """Weather where the user is + photo-numbered outfit candidates from their wardrobe. Call before suggesting any outfit."""
        items = w.catalog.items()
        if not items:
            return CallToolResult(content=[_text("The wardrobe is empty. Add items to the wardrobe folder (items/<name>/item.yaml + photo) or import product links with import_links.")])
        anchors, problems = _resolve_many(items, wearing or [])
        try:
            where, source = await w.place(place)
        except LocationUnknown as exc:
            return CallToolResult(content=[_text(f"I don't know where the user is ({exc}). Ask which city they're in, then call dress_me again with `place`.")])
        weather = await w.day_weather(where, day)
        today = w.local_today(where)
        target_day = today + timedelta(days=1 if day == "tomorrow" else 0)
        if weather is None:
            weather = _neutral_weather(where.name or "your location", target_day)
        profile = w.catalog.profile()
        last_worn = w.state.last_worn()
        cands = pick_candidates(items, weather, occasion, anchors, last_worn, target_day, temperature_bias(profile))

        entries: list[tuple[str, Item]] = []
        lines = [
            f"**Weather** — {weather.place} ({source}), {day} {weather.hours[0]:02d}–{weather.hours[1]:02d}: {weather.text()}",
            f"**Guidance** — {cands.targets.guidance()}",
        ]
        if anchors:
            lines.append("**Already chosen** (photos A1…):")
            for n, a in enumerate(anchors, 1):
                entries.append((f"A{n}", a))
                lines.append(_item_line(f"A{n}", a, last_worn.get(a.id), today))
        if problems:
            lines.append("**Couldn't pin down**: " + "; ".join(problems) + " — ask the user which one, or pick the most likely.")
        n = 0
        for slot in SLOTS:
            pairs = cands.by_slot.get(slot) or []
            if not pairs:
                continue
            lines.append(f"**{SLOT_TITLES[slot]}**")
            for item, _score in pairs:
                n += 1
                entries.append((str(n), item))
                lines.append(_item_line(f"#{n}", item, last_worn.get(item.id), today))
        prefs = w.state.prefs()
        style = {k: profile[k] for k in ("style", "dislikes", "likes", "runs") if profile.get(k)}
        if style:
            lines.append("**Profile** — " + json.dumps(style, ensure_ascii=False))
        if prefs:
            lines.append("**Remembered preferences** — " + "; ".join(f"[{p['id']}] {p['text']}" for p in prefs))
        recent = w.state.recent_outfits(today - timedelta(days=4))
        if recent:
            lines.append("**Recent outfits** — " + "; ".join(f"{r['day']}: {', '.join(r['items'])}" for r in recent[:5]))
        lines.append("Next: pick one outfit (include the already-chosen items) and call `show_outfit` with the ids.")
        content: list[Any] = [_text("\n".join(lines))]
        if entries:
            content.append(_image(w.renderer.contact_sheet(entries)))
        return CallToolResult(content=content)

    # ---------------------------------------------------------------- log_wear

    @mcp.tool(title="Log what I'm wearing", annotations=writes)
    async def log_wear(
        items: Annotated[list[str], Field(description="Item ids or descriptions, e.g. ['beige cords', 'ecru knit'].")],
        day: Annotated[str, Field(description="'today', 'yesterday' or YYYY-MM-DD.")] = "today",
        note: str | None = None,
    ) -> str:
        """Record what the user wore. Call whenever they say what they have on or accept an outfit."""
        all_items = w.catalog.items(include_inactive=True)
        found, problems = _resolve_many(all_items, items)
        try:
            where, _ = await w.place(None)
        except LocationUnknown:
            where = None
        today = w.local_today(where)
        try:
            when = _parse_day(day, today)
        except ValueError:
            return f"Couldn't read the day {day!r}; use today, yesterday or YYYY-MM-DD."
        if not found:
            return "Nothing logged. " + "; ".join(problems)
        temp_min = temp_max = None
        if where and when == today:
            weather = await w.day_weather(where, "today")
            if weather:
                temp_min, temp_max = weather.temp_min, weather.temp_max
        w.state.log_wear([i.id for i in found], when, where.name if where else None, temp_min, temp_max, note)
        msg = f"Logged for {when.isoformat()}: " + ", ".join(i.label() for i in found) + "."
        if problems:
            msg += " Not logged: " + "; ".join(problems)
        return msg

    # -------------------------------------------------------------- find_items

    @mcp.tool(title="Find items", annotations=read_only)
    async def find_items(
        query: Annotated[str, Field(description="Words like 'navy knit' or 'shoes'; empty lists everything.")] = "",
        category: Annotated[str | None, Field(description=f"One of {', '.join(CATEGORIES)}.")] = None,
        include_retired: bool = False,
    ) -> CallToolResult:
        """Search the wardrobe. Returns matches with a numbered photo sheet."""
        items = w.catalog.items(include_inactive=include_retired)
        if category:
            items = [i for i in items if i.category == category]
        matches = [m.item for m in search(items, query, limit=40)] if query.strip() else sorted(items, key=lambda i: (SLOTS.index(slot_of(i)), i.id))
        if not matches:
            return CallToolResult(content=[_text(f"No items match {query!r}.")])
        last_worn, counts = w.state.last_worn(), w.state.wear_counts()
        today = w.local_today()
        lines = [f"{len(matches)} item(s):"]
        for n, item in enumerate(matches[:40], 1):
            lines.append(_item_line(f"#{n}", item, last_worn.get(item.id), today) + f" · worn {counts.get(item.id, 0)}×" + ("" if item.active else f" · {item.status}"))
        if len(matches) > 40:
            lines.append(f"…and {len(matches) - 40} more; narrow the query.")
        sheet = w.renderer.contact_sheet([(str(n), i) for n, i in enumerate(matches[:40], 1)])
        return CallToolResult(content=[_text("\n".join(lines)), _image(sheet)])

    # --------------------------------------------------------------- save_item

    @mcp.tool(title="Add or edit an item", annotations=writes)
    async def save_item(
        item_id: Annotated[str | None, Field(description="Existing item id to edit; omit to create a new item.")] = None,
        name: str | None = None,
        brand: str | None = None,
        category: Annotated[str | None, Field(description=f"One of {', '.join(CATEGORIES)}.")] = None,
        type: Annotated[str | None, Field(description="e.g. t-shirt, shirt, polo, knit, hoodie, cardigan, jeans, trousers, coat, jacket, sneakers, boots.")] = None,
        colour: str | None = None,
        material: str | None = None,
        warmth: Annotated[int | None, Field(ge=0, le=5, description="0 = very light … 5 = deep winter")] = None,
        formality: Annotated[int | None, Field(ge=1, le=5, description="1 = gym … 5 = suit")] = None,
        rain_ok: bool | None = None,
        size: str | None = None,
        aliases: Annotated[list[str] | None, Field(description="What the user calls it, e.g. ['beige cords']. Replaces the list.")] = None,
        notes: str | None = None,
        status: Annotated[Literal["owned", "retired", "laundry"] | None, Field(description="retired = gone (sold, returned, worn out); laundry = temporarily unavailable.")] = None,
        from_inbox: Annotated[list[str] | None, Field(description="Inbox photo filenames to attach (they move into the item folder).")] = None,
    ) -> CallToolResult:
        """Create or update an item in the wardrobe folder. Saving also clears the 'needs review' flag."""
        if category and category not in CATEGORIES:
            return CallToolResult(content=[_text(f"category must be one of {', '.join(CATEGORIES)}")], is_error=True)
        fields: dict[str, Any] = {
            k: v for k, v in {
                "name": name, "brand": brand, "category": category, "type": type, "colour": colour,
                "material": material, "warmth": warmth, "formality": formality, "rain_ok": rain_ok,
                "size": size, "aliases": aliases, "notes": notes, "status": status,
            }.items() if v is not None
        }
        if category == "tops" and type:
            fields["layer"] = layer_for("tops", type)
        if item_id is not None and w.catalog.get(item_id) is None:
            return CallToolResult(content=[_text(f"No item with id {item_id!r}.")], is_error=True)
        photos: list[Path] = []
        for filename in from_inbox or []:
            path = w.catalog.inbox_dir / Path(filename).name
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTS:
                return CallToolResult(content=[_text(f"No inbox photo called {filename!r}.")], is_error=True)
            photos.append(path)
        fields["needs_review"] = None
        try:
            item = w.catalog.save_item(item_id, fields, add_photos=photos)
        except ValueError as exc:
            return CallToolResult(content=[_text(str(exc))], is_error=True)
        content: list[Any] = [_text(f"Saved `{item.id}`: " + json.dumps(item.summary(), ensure_ascii=False))]
        if item.main_photo:
            content.append(_image(w.renderer.thumbnail_jpeg(item.main_photo, 480)))
        return CallToolResult(content=content)

    # ------------------------------------------------------------ review_inbox

    @mcp.tool(title="Review new photos", annotations=read_only)
    async def review_inbox() -> CallToolResult:
        """Photos the user dropped in the inbox, waiting to become items. Describe each, then save_item(from_inbox=[...])."""
        pending = w.catalog.inbox_files()
        if not pending:
            return CallToolResult(content=[_text("The inbox is empty.")])
        content: list[Any] = [_text(f"{len(pending)} photo(s) in the inbox" + (" (showing the first 6)" if len(pending) > 6 else "") + ":")]
        for path in pending[:6]:
            content.append(_text(f"File: {path.name}"))
            content.append(_image(w.renderer.thumbnail_jpeg(path, 768)))
        return CallToolResult(content=content)

    # ------------------------------------------------------------ import_links

    @mcp.tool(title="Import product links", annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True))
    async def import_links(
        urls: Annotated[list[str], Field(description="Product page links (Mango, Zalando, Levi's, …) with the right colour selected.")],
    ) -> CallToolResult:
        """Add items from shop links: downloads product photos and prefills details (marked needs_review)."""
        results = [await importer.import_url(w.catalog, url, chromium=config.chromium) for url in urls[:25]]
        lines, new_items = [], []
        for r in results:
            if r.existing and r.item:
                lines.append(f"• already in wardrobe: `{r.item.id}`")
            elif r.item:
                new_items.append(r.item)
                lines.append(f"• added `{r.item.id}` — {r.item.label()}" + (f" ({r.error})" if r.error else ""))
            else:
                lines.append(f"• failed {r.url}: {r.error}")
        if len(urls) > 25:
            lines.append(f"Only the first 25 links were imported; send the remaining {len(urls) - 25} again.")
        content: list[Any] = [_text("\n".join(lines))]
        if new_items:
            content.append(_image(w.renderer.contact_sheet([(str(n), i) for n, i in enumerate(new_items, 1)])))
        return CallToolResult(content=content)

    # ------------------------------------------------------- wardrobe_analysis

    @mcp.tool(title="Wardrobe analysis", annotations=read_only)
    async def wardrobe_analysis() -> str:
        """Counts, coverage, near-duplicates, hard-to-combine items and wear statistics, for gap and shopping advice."""
        result = analyse(
            w.catalog.items(), w.state.wear_counts(), w.state.last_worn(), w.state.wear_history(), w.local_today()
        )
        profile = w.catalog.profile()
        result["profile"] = {k: profile[k] for k in ("home", "style", "likes", "dislikes", "runs") if profile.get(k)}
        result["remembered_preferences"] = [p["text"] for p in w.state.prefs()]
        return json.dumps(result, ensure_ascii=False, indent=1)

    # -------------------------------------------------------- remember / forget

    @mcp.tool(title="Remember a preference", annotations=writes)
    async def remember(note: Annotated[str, Field(description="A lasting preference, e.g. 'never black with brown'.")]) -> str:
        """Store a lasting style preference that future suggestions must respect."""
        pref_id = w.state.add_pref(note)
        return f"Remembered [{pref_id}]: {note}"

    @mcp.tool(title="Forget a preference", annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False))
    async def forget(pref_id: int) -> str:
        """Remove a remembered preference by its id."""
        return "Forgotten." if w.state.remove_pref(pref_id) else f"No preference with id {pref_id}."

    # ------------------------------------------------------------ set_location

    @mcp.tool(title="Set my location", annotations=writes)
    async def set_location(place: Annotated[str, Field(description="City (optionally ', country'), e.g. 'San Francisco'.")]) -> str:
        """Use when the user says they're somewhere new and their phone hasn't reported it."""
        try:
            found = await w.weather.geocode(place)
        except httpx.HTTPError:
            return "The place lookup service is unreachable right now; try again in a minute."
        if not found:
            return f"Couldn't find {place!r}."
        w.state.set_location(found.lat, found.lon, found.name, "you said", found.tz)
        return f"Location set to {found.name}."

    # ------------------------------------------------------------ HTTP routes

    @mcp.custom_route("/img/r/{token}.jpg", methods=["GET"], include_in_schema=False)
    async def render_image(request: Request) -> Response:
        path = w.state.render_path(request.path_params["token"])
        if not path or not path.exists():
            return PlainTextResponse("Expired or unknown image", status_code=404)
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})

    @mcp.custom_route("/img/i/{item_id}/{size:int}", methods=["GET"], include_in_schema=False)
    async def item_image(request: Request) -> Response:
        item_id, size = request.path_params["item_id"], request.path_params["size"]
        path = f"/img/i/{item_id}/{size}"
        if not w.verify_image(path, request.query_params.get("exp", ""), request.query_params.get("sig", "")):
            return PlainTextResponse("Forbidden", status_code=403)
        item = w.catalog.get(item_id)
        if not item or not item.main_photo or size not in (240, 420, 600, 900):
            return PlainTextResponse("Not found", status_code=404)
        return Response(w.renderer.thumbnail_jpeg(item.main_photo, size, 82), media_type="image/jpeg",
                        headers={"Cache-Control": "private, max-age=86400"})

    @mcp.custom_route("/", methods=["GET"], include_in_schema=False)
    async def index(request: Request) -> Response:
        return PlainTextResponse("Wardrobe MCP server. Add it to your AI app with this URL + /mcp\n")

    return mcp


def build_public_app(w: Wardrobe, mcp: MCPServer) -> Starlette:
    config = w.config
    port = config.public_port
    # Funnel may forward the Host with or without its port (443, 8443 or 10000), so accept both.
    hostname = config.public_host.rsplit(":", 1)[0]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[hostname, f"{hostname}:*", f"127.0.0.1:{port}", f"localhost:{port}"],
        allowed_origins=[config.public_url, "https://chatgpt.com", "https://claude.ai", f"http://127.0.0.1:{port}", f"http://localhost:{port}"],
    )
    app = mcp.streamable_http_app(stateless_http=True, json_response=True, transport_security=security, host=config.bind)
    if mcp.settings.auth:
        _advertise_client_metadata_documents(app, mcp.settings.auth)
    return app


def _advertise_client_metadata_documents(app: Starlette, auth: AuthSettings) -> None:
    """The SDK's metadata route doesn't announce CIMD support; replace it with one that does.

    Claude recommends CIMD ("use Claude's published identity") and only uses it when the
    authorization server metadata says `client_id_metadata_document_supported: true`.
    """
    metadata = build_metadata(
        auth.issuer_url,
        auth.service_documentation_url,
        auth.client_registration_options or ClientRegistrationOptions(),
        auth.revocation_options or RevocationOptions(),
    )
    metadata.client_id_metadata_document_supported = True
    metadata.token_endpoint_auth_methods_supported = ["none", "client_secret_post", "client_secret_basic"]
    path = "/.well-known/oauth-authorization-server"
    for i, route in enumerate(app.router.routes):
        if getattr(route, "path", None) == path:
            app.router.routes[i] = Route(path, endpoint=cors_middleware(MetadataHandler(metadata).handle, ["GET", "OPTIONS"]),
                                         methods=["GET", "OPTIONS"])
            return
    raise RuntimeError(f"{path} route not found; did the MCP SDK change?")


# -------------------------------------------------------------- private API


def build_private_app(w: Wardrobe) -> Starlette:
    """Tailnet-only endpoints for iOS Shortcuts: location, share-sheet import, inbox upload."""

    def authorised(request: Request) -> bool:
        token = w.config.device_token
        if not token:
            return True  # only reachable inside your tailnet; set WARDROBE_DEVICE_TOKEN for defence in depth
        header = request.headers.get("authorization", "")
        supplied = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token", "")
        return hmac.compare_digest(supplied.encode(), token.encode())

    async def health(request: Request) -> Response:
        return JSONResponse({"ok": True, "items": len(w.catalog.items()), "errors": w.catalog.errors})

    async def location(request: Request) -> Response:
        if not authorised(request):
            return JSONResponse({"error": "unauthorised"}, status_code=401)
        data = await _body(request)
        try:
            lat = float(data.get("lat", data.get("latitude")))
            lon = float(data.get("lon", data.get("longitude")))
        except (TypeError, ValueError):
            return JSONResponse({"error": "send lat and lon"}, status_code=400)
        name = str(data.get("name") or data.get("city") or "").strip() or None
        tz = str(data.get("tz") or "").strip() or None
        if tz:
            try:
                ZoneInfo(tz)
            except (ZoneInfoNotFoundError, ValueError):
                tz = None
        w.state.set_location(lat, lon, name, "from your phone", tz)
        return JSONResponse({"ok": True, "name": name})

    async def import_page(request: Request) -> Response:
        if not authorised(request):
            return JSONResponse({"error": "unauthorised"}, status_code=401)
        data = await _body(request)
        url = str(data.get("url") or "").strip()
        if not url.startswith("http"):
            return JSONResponse({"error": "send url"}, status_code=400)
        payload = data if (data.get("jsonld") or data.get("meta") or data.get("images")) else None
        result = await importer.import_url(w.catalog, url, payload=payload, chromium=w.config.chromium)
        if result.item is None:
            return JSONResponse({"ok": False, "error": result.error}, status_code=422)
        message = f"Already in wardrobe: {result.item.label()}" if result.existing else f"Added {result.item.label()}"
        if result.error:
            message += f" ({result.error})"
        return JSONResponse({"ok": True, "id": result.item.id, "message": message})

    async def inbox(request: Request) -> Response:
        if not authorised(request):
            return JSONResponse({"error": "unauthorised"}, status_code=401)
        form = await request.form(max_part_size=40 * 1024 * 1024)
        saved = []
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for n, (_key, value) in enumerate(form.multi_items(), 1):
            if not hasattr(value, "read"):
                continue
            data = await value.read()
            if not data:
                continue
            try:
                jpeg = importer.image_bytes_to_jpeg(data)
            except Exception:
                continue
            path = w.catalog.inbox_dir / f"{stamp}-{n}.jpg"
            path.write_bytes(jpeg)
            saved.append(path.name)
        if not saved:
            return JSONResponse({"ok": False, "error": "no images received"}, status_code=400)
        return JSONResponse({"ok": True, "saved": saved, "message": f"{len(saved)} photo(s) in the inbox. Ask your assistant to review the inbox."})

    return Starlette(routes=[
        Route("/health", health, methods=["GET"]),
        Route("/location", location, methods=["POST", "GET"]),
        Route("/import", import_page, methods=["POST"]),
        Route("/inbox", inbox, methods=["POST"]),
    ])


async def _body(request: Request) -> dict[str, Any]:
    if request.method == "GET":
        return dict(request.query_params)
    ctype = request.headers.get("content-type", "")
    if "form" not in ctype:  # JSON, or a Shortcuts dictionary sent without a content type
        try:
            data = json.loads(await request.body() or b"{}")
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}
    form = await request.form()
    return {k: v for k, v in form.items() if isinstance(v, str)}
