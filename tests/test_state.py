import time
from datetime import date, timedelta
from pathlib import Path

from wardrobe.state import State


def test_wear_log_same_day_replaces(tmp_path: Path):
    s = State(tmp_path)
    today = date(2026, 10, 9)
    s.log_wear(["a", "b"], today, "Linköping", 3, 8)
    s.log_wear(["a"], today)  # said again: not a second wear
    s.log_wear(["a"], today - timedelta(days=2))
    assert s.wear_counts() == {"a": 2, "b": 1}
    assert s.last_worn()["a"] == today
    recent = s.recent_outfits(today - timedelta(days=1))
    assert {tuple(sorted(r["items"])) for r in recent} == {("a",), ("b",)}


def test_prefs(tmp_path: Path):
    s = State(tmp_path)
    pid = s.add_pref("  never black with brown ")
    assert s.prefs() == [{"id": pid, "text": "never black with brown"}]
    assert s.remove_pref(pid) and not s.remove_pref(pid)


def test_location_is_single_row(tmp_path: Path):
    s = State(tmp_path)
    assert s.location() is None
    s.set_location(1, 2, "A", "phone")
    s.set_location(3, 4, "B", "phone", "Europe/Stockholm")
    loc = s.location()
    assert (loc.lat, loc.name, loc.tz) == (3, "B", "Europe/Stockholm")
    assert loc.age_text() == "just now"
    assert s._exec("SELECT COUNT(*) FROM location").fetchone()[0] == 1


def test_render_tokens_expire(tmp_path: Path):
    s = State(tmp_path)
    f = tmp_path / "x.jpg"
    f.write_bytes(b"x")
    live = s.add_render(f)
    dead = s.add_render(f, ttl=-1)
    assert s.render_path(live) == f
    assert s.render_path(dead) is None
    assert s.render_path("nope") is None


def test_oauth_expiry_and_secret_stable(tmp_path: Path):
    s = State(tmp_path)
    s.oauth_put("code", "c1", {"x": 1}, time.time() - 1)
    s.oauth_put("client", "k", {"y": 2}, None)
    assert s.oauth_get("code", "c1") is None
    assert s.oauth_get("client", "k") == {"y": 2}
    assert s.secret("images") == State(tmp_path).secret("images")
