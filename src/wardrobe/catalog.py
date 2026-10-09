"""The wardrobe folder: items/<id>/item.yaml + photos, inbox/, profile.yaml.

The folder is the source of truth and stays hand-editable. The catalog re-reads
it whenever something changed on disk (checked at most every couple of seconds).
"""

from __future__ import annotations

import re
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from wardrobe.heuristics import CATEGORIES, canonical_colour, fold, infer, layer_for

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ACTIVE_STATUSES = {"owned", "", None}

# Order in which item.yaml keys are written, for readable files.
FIELD_ORDER = [
    "name", "brand", "aliases", "category", "type", "layer", "colour", "pattern", "material", "composition",
    "warmth", "formality", "rain_ok", "size", "bought", "price", "currency", "source_url",
    "status", "needs_review", "notes",
]


@dataclass
class Item:
    id: str
    path: Path
    data: dict[str, Any]
    photos: list[Path]
    inferred: set[str] = field(default_factory=set)

    def get(self, key: str, default: Any = None) -> Any:
        value = self.data.get(key)
        return default if value is None or value == "" else value

    @property
    def name(self) -> str:
        return str(self.get("name", self.id))

    @property
    def brand(self) -> str | None:
        return self.get("brand")

    @property
    def category(self) -> str:
        return str(self.get("category", "other"))

    @property
    def layer(self) -> str | None:
        return self.get("layer")

    @property
    def colour(self) -> str | None:
        return self.get("colour")

    @property
    def warmth(self) -> int | None:
        return _as_int(self.get("warmth"))

    @property
    def formality(self) -> int | None:
        return _as_int(self.get("formality"))

    @property
    def rain_ok(self) -> bool:
        return bool(self.get("rain_ok", False))

    @property
    def status(self) -> str:
        return str(self.get("status", "owned"))

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def aliases(self) -> list[str]:
        value = self.get("aliases", [])
        return [str(v) for v in value] if isinstance(value, list) else [str(value)]

    @property
    def main_photo(self) -> Path | None:
        return self.photos[0] if self.photos else None

    def label(self) -> str:
        """Short human label: 'Mango Corduroy trousers (beige)'."""
        parts = [self.brand, self.name] if self.brand and self.brand.lower() not in self.name.lower() else [self.name]
        text = " ".join(p for p in parts if p)
        return f"{text} ({self.colour})" if self.colour and self.colour.lower() not in text.lower() else text

    def summary(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "name": self.name}
        for key in ("brand", "category", "type", "layer", "colour", "material", "warmth", "formality", "rain_ok", "size", "status"):
            value = self.get(key)
            if value is not None:
                out[key] = value
        if not self.photos:
            out["no_photo"] = True
        if self.get("needs_review"):
            out["needs_review"] = True
        return out


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _natural_key(path: Path) -> tuple:
    return tuple(int(t) if t.isdigit() else t for t in re.split(r"(\d+)", path.name.lower()))


def slugify(text: str) -> str:
    text = fold(text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60].strip("-") or "item"


class Catalog:
    def __init__(self, root: Path, refresh_interval: float = 2.0):
        self.root = root
        self.items_dir = root / "items"
        self.inbox_dir = root / "inbox"
        self.refresh_interval = refresh_interval
        self._lock = threading.RLock()
        self._items: dict[str, Item] = {}
        self._profile: dict[str, Any] = {}
        self._signature: tuple | None = None
        self._checked_at = 0.0
        self.errors: list[str] = []

    # ---------------------------------------------------------------- loading

    def ensure_layout(self) -> None:
        self.items_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

    def _scan_signature(self) -> tuple:
        entries = []
        if self.items_dir.is_dir():
            for d in sorted(self.items_dir.iterdir()):
                if not d.is_dir() or d.name.startswith("."):
                    continue
                files = tuple(sorted((f.name, f.stat().st_mtime_ns) for f in d.iterdir() if f.is_file()))
                entries.append((d.name, files))
        profile = self.root / "profile.yaml"
        return (tuple(entries), profile.stat().st_mtime_ns if profile.exists() else 0)

    def refresh(self, force: bool = False) -> None:
        with self._lock:
            now = time.monotonic()
            if not force and now - self._checked_at < self.refresh_interval:
                return
            self._checked_at = now
            signature = self._scan_signature()
            if signature == self._signature and not force:
                return
            self._signature = signature
            self._load()

    def _load(self) -> None:
        items: dict[str, Item] = {}
        errors: list[str] = []
        if self.items_dir.is_dir():
            for d in sorted(self.items_dir.iterdir()):
                if not d.is_dir() or d.name.startswith("."):
                    continue
                try:
                    items[d.name] = load_item(d)
                except Exception as exc:  # a broken file must not take the server down
                    errors.append(f"{d.name}: {exc}")
        profile: dict[str, Any] = {}
        profile_path = self.root / "profile.yaml"
        if profile_path.exists():
            try:
                profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
            except yaml.YAMLError as exc:
                errors.append(f"profile.yaml: {exc}")
        self._items, self._profile, self.errors = items, profile, errors

    # ---------------------------------------------------------------- queries

    def items(self, include_inactive: bool = False) -> list[Item]:
        self.refresh()
        with self._lock:
            return [i for i in self._items.values() if include_inactive or i.active]

    def get(self, item_id: str) -> Item | None:
        self.refresh()
        with self._lock:
            return self._items.get(item_id)

    def profile(self) -> dict[str, Any]:
        self.refresh()
        with self._lock:
            return dict(self._profile)

    def inbox_files(self) -> list[Path]:
        if not self.inbox_dir.is_dir():
            return []
        files = [f for f in self.inbox_dir.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
        return sorted(files, key=lambda f: f.stat().st_mtime)

    # ---------------------------------------------------------------- writing

    def new_item_id(self, name: str, brand: str | None = None, colour: str | None = None) -> str:
        base = slugify(" ".join(p for p in (brand, name, colour) if p))
        candidate, n = base, 2
        while (self.items_dir / candidate).exists():
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def save_item(
        self,
        item_id: str | None,
        fields: dict[str, Any],
        add_photos: list[Path] | None = None,
        move_photos: bool = True,
    ) -> Item:
        """Create or update an item. `fields` with value None are removed."""
        with self._lock:
            if item_id is None:
                if not fields.get("name"):
                    raise ValueError("a new item needs a name")
                item_id = self.new_item_id(fields["name"], fields.get("brand"), fields.get("colour"))
            folder = self.items_dir / item_id
            if folder.resolve().parent != self.items_dir.resolve():
                raise ValueError(f"invalid item id: {item_id!r}")
            folder.mkdir(parents=True, exist_ok=True)
            yaml_path = folder / "item.yaml"
            data: dict[str, Any] = {}
            if yaml_path.exists():
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            for key, value in fields.items():
                if value is None:
                    data.pop(key, None)
                else:
                    data[key] = value
            if "colour" in fields and fields["colour"]:
                data["colour"] = canonical_colour(str(fields["colour"])) or fields["colour"]
            write_item_yaml(yaml_path, data)
            existing = sorted((p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS), key=_natural_key)
            next_n = len(existing) + 1
            for src in add_photos or []:
                dest = _free_photo_path(folder, next_n, src.suffix.lower())
                if move_photos:
                    shutil.move(str(src), dest)
                else:
                    shutil.copyfile(src, dest)
                next_n += 1
            self._checked_at = 0.0
        self.refresh(force=True)
        item = self.get(item_id)
        assert item is not None
        return item


def _free_photo_path(folder: Path, n: int, suffix: str) -> Path:
    suffix = suffix if suffix in IMAGE_EXTS else ".jpg"
    while True:
        candidate = folder / f"{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def write_item_yaml(path: Path, data: dict[str, Any]) -> None:
    ordered = {k: data[k] for k in FIELD_ORDER if k in data}
    ordered.update({k: v for k, v in data.items() if k not in ordered})
    for key, value in list(ordered.items()):
        if isinstance(value, date):
            ordered[key] = value.isoformat()
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(ordered, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)


def load_item(folder: Path) -> Item:
    yaml_path = folder / "item.yaml"
    data: dict[str, Any] = {}
    if yaml_path.exists():
        loaded = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        if loaded is not None and not isinstance(loaded, dict):
            raise ValueError("item.yaml must be a mapping")
        data = loaded or {}
    data.setdefault("name", folder.name.replace("-", " ").capitalize())
    photos = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS), key=_natural_key)

    inferred: set[str] = set()
    guess = infer(str(data.get("name", "")), " ".join(str(data.get(k, "")) for k in ("type", "material", "notes")))
    for key, value in guess.items():
        if data.get(key) in (None, ""):
            data[key] = value
            inferred.add(key)
    if data.get("category") not in CATEGORIES:
        if data.get("category"):
            guess_cat = infer(str(data["category"])).get("category")
            data["category"] = guess_cat or "other"
        else:
            data["category"] = "other"
    if data.get("colour"):
        data["colour"] = canonical_colour(str(data["colour"])) or str(data["colour"]).lower()
    if data["category"] == "tops" and not data.get("layer"):
        data["layer"] = layer_for("tops", data.get("type")) or "base"
    return Item(id=folder.name, path=folder, data=data, photos=photos, inferred=inferred)
