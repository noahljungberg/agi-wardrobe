"""Images: cached thumbnails, a numbered contact sheet for the model, and the
outfit collage you see on your phone."""

from __future__ import annotations

import base64
import hashlib
import io
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from wardrobe.catalog import Item

try:  # iPhone photos are HEIC by default
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

BG = (250, 248, 245)
TILE = (243, 241, 237)
INK = (34, 31, 28)
MUTED = (120, 113, 105)
ACCENT = (34, 31, 28)

FONT_PATHS = {
    "regular": [
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ],
    "bold": [
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    ],
}


@lru_cache(maxsize=32)
def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in FONT_PATHS[weight]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def open_image(src: Path | io.BytesIO) -> Image.Image:
    img = Image.open(src)
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, (255, 255, 255))
        flat.paste(img, mask=img.split()[-1])
        return flat
    return img.convert("RGB")


class Renderer:
    def __init__(self, cache_dir: Path):
        self.thumb_dir = cache_dir / "thumbs"
        self.out_dir = cache_dir / "renders"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- thumbnails

    def thumbnail(self, path: Path, size: int) -> Image.Image:
        """The photo scaled to fit a size×size box (aspect kept), cached on disk."""
        stat = path.stat()
        key = hashlib.sha1(f"{path}:{stat.st_mtime_ns}:{size}".encode()).hexdigest()[:20]
        cached = self.thumb_dir / f"{key}.jpg"
        if cached.exists():
            return Image.open(cached).convert("RGB")
        img = open_image(path)
        img.thumbnail((size, size), Image.Resampling.LANCZOS)
        img.save(cached, "JPEG", quality=85)
        return img

    def thumbnail_jpeg(self, path: Path, size: int, quality: int = 78) -> bytes:
        buf = io.BytesIO()
        self.thumbnail(path, size).save(buf, "JPEG", quality=quality)
        return buf.getvalue()

    def data_uri(self, path: Path, size: int = 360) -> str:
        return "data:image/jpeg;base64," + base64.b64encode(self.thumbnail_jpeg(path, size)).decode()

    # ---------------------------------------------------------- contact sheet

    def contact_sheet(self, entries: list[tuple[str, Item]], cols: int = 5, cell: int = 190) -> bytes:
        """Numbered grid of item photos so the model can see candidates.

        `entries` are (label, item); the label (e.g. '3') is drawn on the tile.
        """
        entries = entries[:40]
        rows = max(1, math.ceil(len(entries) / cols))
        caption_h = 34
        pad = 8
        w = cols * (cell + pad) + pad
        h = rows * (cell + caption_h + pad) + pad
        sheet = Image.new("RGB", (w, h), BG)
        draw = ImageDraw.Draw(sheet)
        for idx, (label, item) in enumerate(entries):
            x = pad + (idx % cols) * (cell + pad)
            y = pad + (idx // cols) * (cell + caption_h + pad)
            draw.rectangle([x, y, x + cell, y + cell], fill=TILE)
            if item.main_photo:
                try:
                    thumb = self.thumbnail(item.main_photo, cell - 10)
                    sheet.paste(thumb, (x + (cell - thumb.width) // 2, y + (cell - thumb.height) // 2))
                except Exception:
                    draw.text((x + 10, y + cell // 2), "photo error", fill=MUTED, font=font(14))
            else:
                draw.text((x + 10, y + cell // 2), "no photo", fill=MUTED, font=font(14))
            badge_w = 18 + 11 * len(label)
            draw.rounded_rectangle([x + 4, y + 4, x + 4 + badge_w, y + 30], radius=12, fill=ACCENT)
            draw.text((x + 4 + badge_w / 2, y + 17), label, fill=(255, 255, 255), font=font(18, "bold"), anchor="mm")
            draw.text((x + 2, y + cell + 6), _fit(draw, item.label(), font(13), cell - 4), fill=INK, font=font(13))
        buf = io.BytesIO()
        sheet.save(buf, "JPEG", quality=80)
        return buf.getvalue()

    # ----------------------------------------------------------------- collage

    def collage(self, items: list[Item], title: str, subtitle: str = "", note: str = "") -> Path:
        """Phone-friendly outfit image (1080 px wide). Returns the file path."""
        width, margin, gap = 1080, 40, 24
        cols = 2 if len(items) > 1 else 1
        cell_w = (width - 2 * margin - (cols - 1) * gap) // cols
        img_h = int(cell_w * 1.12) if cols == 2 else 760
        caption_h = 92
        rows = math.ceil(len(items) / cols)

        header_h = 150 if subtitle else 110
        probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        note_lines = _wrap(probe, note, font(26), width - 2 * margin) if note else []
        note_h = (len(note_lines) * 36 + 30) if note_lines else 0
        height = header_h + rows * (img_h + caption_h + gap) + note_h + margin

        canvas = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((margin, 40), _fit(draw, title, font(44, "bold"), width - 2 * margin), fill=INK, font=font(44, "bold"))
        if subtitle:
            draw.text((margin, 98), _fit(draw, subtitle, font(26), width - 2 * margin), fill=MUTED, font=font(26))

        for idx, item in enumerate(items):
            row, col = divmod(idx, cols)
            in_row = min(cols, len(items) - row * cols)
            row_offset = (cols - in_row) * (cell_w + gap) // 2  # centre a lone last tile
            x = margin + row_offset + col * (cell_w + gap)
            y = header_h + row * (img_h + caption_h + gap)
            draw.rounded_rectangle([x, y, x + cell_w, y + img_h], radius=22, fill=TILE)
            if item.main_photo:
                try:
                    photo = open_image(item.main_photo)
                    photo.thumbnail((cell_w - 36, img_h - 36), Image.Resampling.LANCZOS)
                    canvas.paste(photo, (x + (cell_w - photo.width) // 2, y + (img_h - photo.height) // 2))
                except Exception:
                    draw.text((x + 24, y + img_h // 2), "photo error", fill=MUTED, font=font(24))
            else:
                draw.text((x + 24, y + img_h // 2), "no photo yet", fill=MUTED, font=font(24))
            name_font, meta_font = font(28, "bold"), font(23)
            draw.text((x + 4, y + img_h + 14), _fit(draw, item.name, name_font, cell_w - 8), fill=INK, font=name_font)
            meta = " · ".join(p for p in (item.brand, item.colour) if p)
            if meta:
                draw.text((x + 4, y + img_h + 52), _fit(draw, meta, meta_font, cell_w - 8), fill=MUTED, font=meta_font)

        if note_lines:
            y = header_h + rows * (img_h + caption_h + gap) + 10
            for line in note_lines:
                draw.text((margin, y), line, fill=INK, font=font(26))
                y += 36

        digest = hashlib.sha1(f"{title}|{subtitle}|{note}|{[i.id for i in items]}".encode()).hexdigest()[:16]
        out = self.out_dir / f"outfit-{digest}.jpg"
        canvas.save(out, "JPEG", quality=86)
        return out

    @staticmethod
    def scaled_jpeg(path: Path, max_width: int, quality: int = 80) -> bytes:
        img = open_image(path)
        if img.width > max_width:
            img = img.resize((max_width, round(img.height * max_width / img.width)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()


def _fit(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int) -> str:
    if draw.textlength(text, font=fnt) <= max_w:
        return text
    while text and draw.textlength(text + "…", font=fnt) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def _wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int, max_lines: int = 4) -> list[str]:
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=fnt) <= max_w:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit(draw, lines[-1] + " …", fnt, max_w)
    return lines
