"""Outfit pictures on the user ("try-on"), drawn by the owner's signed-in Codex CLI.

`codex exec` gets the user's photo and the garment photos attached and is asked to make one
picture with its built-in image generation, which runs on the ChatGPT subscription (no API key,
no per-image bill). Jobs run one at a time in a background thread, so a slow picture never
blocks a request: asking again for the same outfit joins the running job, and finished
pictures are cached by outfit + photos.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from wardrobe.catalog import Item
from wardrobe.outfit import SLOTS, slot_of
from wardrobe.render import Renderer

log = logging.getLogger(__name__)

PROMPT_VERSION = 1
JOB_TIMEOUT = 420
MAX_PERSON_PHOTOS = 2
MAX_GARMENTS = 7
ROLE = {
    "outerwear": "outer layer", "mid": "mid layer", "base": "base layer", "bottoms": "bottoms",
    "shoes": "shoes", "accessories": "accessory",
}


class TryOnError(Exception):
    """A problem to tell the user as is (setup, limits, Codex failures)."""


@dataclass
class Status:
    state: str
    """'done', 'running' or 'failed'."""
    path: Path | None = None
    error: str | None = None
    seconds: float = 0.0


@dataclass
class _Job:
    started: float
    future: Future[Path]


def clean(text: str, limit: int) -> str:
    """Item labels and styling hints go into an agent prompt: plain words only, short."""
    text = " ".join(re.sub(r"[^\w\s.,'&()/+%-]", " ", text).split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_prompt(n_person: int, pictured: list[tuple[str, str]], unpictured: list[tuple[str, str]], styling: str) -> str:
    """The Codex task. `pictured`/`unpictured` are (role, label) in the order the photos are attached."""
    lines = [
        "Use your built-in image generation tool (the $imagegen skill) to make exactly one picture.",
        "Do not run shell commands, edit files or browse the web.",
        "",
        "Attached images, in order:",
    ]
    n = 0
    for _ in range(n_person):
        n += 1
        lines.append(f"{n}. The person (photo of them).")
    for role, label in pictured:
        n += 1
        lines.append(f"{n}. Garment, {role}: {label}.")
    if unpictured:
        lines.append("Also wearing (no photo, follow the description): "
                     + "; ".join(f"{role}: {label}" for role, label in unpictured) + ".")
    lines += [
        "",
        "Make a realistic full-length photo of this same person wearing all of these garments together as one outfit.",
        "- Keep the person's face, hair, skin tone and body proportions as in their photo. Do not slim, "
        "lengthen or idealise the body.",
        "- Copy each garment's colour, fabric texture, pattern, collar, buttons and length from its photo. "
        "Use only the garment from each photo: ignore any model wearing it, and add no logos or text.",
        "- Layer from the outside in: outer layer over the mid layer over the base layer.",
    ]
    if styling:
        lines.append(f"- Styling: {styling}.")
    lines += [
        "- Standing naturally, facing the camera, head to shoes in frame, plain light grey background, "
        "soft even daylight, portrait orientation (2:3).",
        "",
        "When the picture is saved, finish with exactly one line: RESULT: <absolute path of the saved image>",
    ]
    return "\n".join(lines)


class TryOn:
    def __init__(
        self,
        cache_dir: Path,
        renderer: Renderer,
        codex: str | None,
        model: str | None = None,
        codex_home: Path | None = None,
        timeout: float = JOB_TIMEOUT,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    ):
        self.dir = cache_dir / "tryon"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.renderer = renderer
        self.codex = codex
        self.model = model
        self.codex_home = codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        self.timeout = timeout
        self._run = run
        self._one_at_a_time = threading.Lock()
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()

    # ----------------------------------------------------------------- inputs

    def executable(self) -> str:
        if not self.codex:
            raise TryOnError("Outfit pictures are turned off on the server (WARDROBE_CODEX=off).")
        found = shutil.which(self.codex)
        if not found:
            raise TryOnError(f"The Codex CLI ({self.codex!r}) isn't installed or isn't on the server's PATH. "
                             "Install it, run `codex login` once, or set WARDROBE_CODEX to its full path.")
        return found

    def pick_person(self, photos: list[Path]) -> list[Path]:
        """Tallest photos first: a full-length photo shows the build; a portrait still gives the face."""
        def tallness(path: Path) -> float:
            try:
                img = self.renderer.thumbnail(path, 256)
            except Exception:
                return -1.0
            return img.height / max(img.width, 1)

        ranked = sorted(photos, key=tallness, reverse=True)
        return [p for p in ranked if tallness(p) > 0][:MAX_PERSON_PHOTOS]

    def key(self, person: list[Path], items: list[Item], styling: str) -> str:
        def stamp(path: Path | None) -> list[Any]:
            if not path or not path.exists():
                return []
            st = path.stat()
            return [path.name, st.st_mtime_ns, st.st_size]

        raw = json.dumps([
            PROMPT_VERSION, self.model, [stamp(p) for p in person],
            [[i.id, i.label(), stamp(i.main_photo)] for i in items], styling,
        ])
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    # ------------------------------------------------------------------- jobs

    def request(self, person: list[Path], items: list[Item], styling: str = "") -> Status:
        """Cached picture, or start/join the job. A failure is reported once; the next call retries."""
        items = sorted(items, key=lambda i: SLOTS.index(slot_of(i)))[:MAX_GARMENTS]
        styling = clean(styling, 200)
        key = self.key(person, items, styling)
        out = self.dir / f"{key}.jpg"
        if out.exists():
            return Status("done", path=out)
        with self._lock:
            job = self._jobs.get(key)
            if job and job.future.done():
                del self._jobs[key]
                error = job.future.exception()
                if error is None:
                    return Status("done", path=job.future.result())
                message = str(error) if isinstance(error, TryOnError) else f"Unexpected error: {error!r}"
                return Status("failed", error=message)
            if job is None:
                exe = self.executable()
                job = _Job(time.time(), self._start(exe, out, person, items, styling))
                self._jobs[key] = job
            return Status("running", seconds=time.time() - job.started)

    def _start(self, exe: str, out: Path, person: list[Path], items: list[Item], styling: str) -> Future[Path]:
        """Run the job in a daemon thread (stopping the service never waits for Codex), one at a time."""
        future: Future[Path] = Future()

        def work() -> None:
            with self._one_at_a_time:
                future.set_running_or_notify_cancel()
                try:
                    future.set_result(self._generate(exe, out, person, items, styling))
                except BaseException as exc:
                    future.set_exception(exc)

        threading.Thread(target=work, name="tryon", daemon=True).start()
        return future

    async def obtain(self, person: list[Path], items: list[Item], styling: str = "", wait: float = 50) -> Status:
        """Like `request`, but wait up to `wait` seconds for a running job to finish."""
        deadline = time.monotonic() + wait
        status = self.request(person, items, styling)
        while status.state == "running" and time.monotonic() < deadline:
            await asyncio.sleep(min(0.25, max(deadline - time.monotonic(), 0.05)))
            status = self.request(person, items, styling)
        return status

    # ------------------------------------------------------------------ codex

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.pop("OPENAI_API_KEY", None)  # never bill per image: subscription login only
        env.pop("CODEX_API_KEY", None)
        env["CODEX_HOME"] = str(self.codex_home)
        return env

    def _check_login(self, exe: str) -> None:
        try:
            r = self._run([exe, "login", "status"], capture_output=True, text=True, timeout=30, env=self._env())
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TryOnError(f"Couldn't run Codex on the server ({type(exc).__name__}).") from exc
        status = f"{r.stdout}\n{r.stderr}".lower()
        if "api key" in status:
            raise TryOnError("Codex on the server is signed in with an API key, which would bill per picture. "
                             "Run `codex logout`, then `codex login` and choose Sign in with ChatGPT.")
        if r.returncode != 0 or "not logged in" in status:
            raise TryOnError("Codex on the server isn't signed in. On the server, run `codex login` "
                             "(Sign in with ChatGPT) as the user the wardrobe service runs as.")

    def _generate(self, exe: str, out: Path, person: list[Path], items: list[Item], styling: str) -> Path:
        self._check_login(exe)
        with tempfile.TemporaryDirectory(prefix="wardrobe-tryon-") as tmp_name:
            tmp = Path(tmp_name)
            refs: list[Path] = []
            for n, path in enumerate(person, 1):
                refs.append(tmp / f"person-{n}.jpg")
                refs[-1].write_bytes(self.renderer.thumbnail_jpeg(path, 1536, 90))
            pictured, unpictured = [], []
            for n, item in enumerate(items, 1):
                entry = (ROLE[slot_of(item)], clean(item.label(), 90))
                if item.main_photo:
                    refs.append(tmp / f"garment-{n}.jpg")
                    refs[-1].write_bytes(self.renderer.thumbnail_jpeg(item.main_photo, 1024, 90))
                    pictured.append(entry)
                else:
                    unpictured.append(entry)
            prompt = build_prompt(len(person), pictured, unpictured, styling)
            last = tmp / "last-message.txt"
            # No positional prompt: `-i` takes several files, so the prompt goes in on stdin.
            cmd = [exe, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config",
                   "--ignore-rules", "--sandbox", "read-only", "--cd", str(tmp), "--output-last-message", str(last)]
            if self.model:
                cmd += ["--model", self.model]
            for ref in refs:
                cmd += ["--image", str(ref)]
            started = time.time()
            try:
                r = self._run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout,
                              env=self._env(), cwd=tmp)
            except subprocess.TimeoutExpired as exc:
                raise TryOnError(f"Codex took longer than {round(self.timeout / 60)} minutes; try again later.") from exc
            except OSError as exc:
                raise TryOnError(f"Couldn't run Codex on the server ({type(exc).__name__}).") from exc
            output = f"{r.stdout}\n{r.stderr}"
            if r.returncode != 0:
                if "usage limit" in output.lower() or "rate limit" in output.lower():
                    raise TryOnError("Your ChatGPT/Codex usage limit is reached; pictures work again when it resets.")
                tail = " ".join(r.stderr.split())[-300:] if r.stderr else "no error output"
                raise TryOnError(f"Codex failed (exit {r.returncode}): {tail}")
            final = last.read_text(encoding="utf-8", errors="replace") if last.exists() else ""
            png, owned = self._find_image(final, _thread_id(r.stdout), started)
            if png is None:
                # The agent's words stay in the server log: they never go back to the chat.
                log.warning("codex made no picture; last message: %s", " ".join(final.split())[:500])
                raise TryOnError("Codex finished without making a picture; the server log has its reply. Try again.")
            try:
                tmp_out = out.with_suffix(".tmp")
                tmp_out.write_bytes(Renderer.scaled_jpeg(png, 1200, 88))
                tmp_out.replace(out)
            except Exception as exc:
                raise TryOnError("Codex returned a file that isn't a readable image.") from exc
            if owned:  # our job's copy in Codex's folder: don't leave pictures of the user lying around
                png.unlink(missing_ok=True)
                try:
                    png.parent.rmdir()
                except OSError:
                    pass
            return out

    def _find_image(self, final: str, thread_id: str | None, started: float) -> tuple[Path | None, bool]:
        """Where Codex saved the picture: the RESULT line, this run's folder, else the newest new one.

        Returns (path, owned): owned means the file is in this run's own folder and may be removed.
        """
        root = (self.codex_home / "generated_images").resolve()
        thread_dir = (root / _safe(thread_id)).resolve() if thread_id else None
        for line in final.splitlines():
            if line.strip().startswith("RESULT:"):
                path = Path(line.strip()[7:].strip()).expanduser()
                try:
                    path = path.resolve()
                except OSError:
                    continue
                if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and root in path.parents:
                    return path, thread_dir is not None and path.parent == thread_dir
        if thread_dir and thread_dir.is_dir():
            pngs = sorted(thread_dir.glob("*.png"), key=lambda p: p.stat().st_mtime)
            if pngs:
                return pngs[-1], True
        if root.is_dir():
            fresh = [p for p in root.glob("*/*.png") if p.stat().st_mtime >= started - 1]
            if fresh:
                return max(fresh, key=lambda p: p.stat().st_mtime), False
        return None, False


def _thread_id(jsonl: str) -> str | None:
    for line in jsonl.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "thread.started" and event.get("thread_id"):
            return str(event["thread_id"])
    return None


def _safe(value: str) -> str:
    """Codex's own folder-name rule for generated images (ASCII letters, digits, - and _)."""
    return "".join(ch if (ch.isascii() and ch.isalnum()) or ch in "-_" else "_" for ch in value) or "generated_image"
