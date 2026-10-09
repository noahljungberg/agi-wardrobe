"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    wardrobe_dir: Path
    state_dir: Path
    public_url: str
    """Public base URL (Tailscale Funnel), e.g. https://box.tailnet.ts.net. No trailing slash."""
    auth: str
    """'oauth' (default) or 'none' (local testing only)."""
    passphrase: str | None
    device_token: str | None
    bind: str
    public_port: int
    private_port: int
    home: str | None
    """Fallback location when the phone hasn't reported one: a place name or 'lat,lon'."""
    chromium: str | None

    @property
    def public_host(self) -> str:
        return urlparse(self.public_url).netloc

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        env = dict(os.environ if env is None else env)

        def get(name: str, default: str | None = None) -> str | None:
            value = env.get(name, "").strip()
            return value or default

        wardrobe_dir = get("WARDROBE_DIR")
        if not wardrobe_dir:
            raise ConfigError("WARDROBE_DIR is not set (the folder with items/, inbox/, profile.yaml)")
        state_dir = get("WARDROBE_STATE_DIR") or str(Path.home() / ".local/state/wardrobe")
        public_port = int(get("WARDROBE_PUBLIC_PORT", "8765"))
        public_url = (get("WARDROBE_PUBLIC_URL") or f"http://127.0.0.1:{public_port}").rstrip("/")
        auth = (get("WARDROBE_AUTH", "oauth") or "oauth").lower()
        if auth not in ("oauth", "none"):
            raise ConfigError("WARDROBE_AUTH must be 'oauth' or 'none'")
        passphrase = get("WARDROBE_PASSPHRASE")
        if auth == "oauth" and (not passphrase or len(passphrase) < 8):
            raise ConfigError("WARDROBE_PASSPHRASE must be set (8+ characters) when WARDROBE_AUTH=oauth")

        return cls(
            wardrobe_dir=Path(wardrobe_dir).expanduser(),
            state_dir=Path(state_dir).expanduser(),
            public_url=public_url,
            auth=auth,
            passphrase=passphrase,
            device_token=get("WARDROBE_DEVICE_TOKEN"),
            bind=get("WARDROBE_BIND", "127.0.0.1") or "127.0.0.1",
            public_port=public_port,
            private_port=int(get("WARDROBE_PRIVATE_PORT", "8766")),
            home=get("WARDROBE_HOME"),
            chromium=get("WARDROBE_CHROMIUM"),
        )
