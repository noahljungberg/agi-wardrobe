# Setup on the home machine (Arch Linux)

About 20 minutes, once. You end up with:

- the server running as a systemd user service,
- `https://<machine>.<tailnet>.ts.net/mcp` reachable by ChatGPT/Claude (Tailscale Funnel, behind a login),
- `https://<machine>.<tailnet>.ts.net:8443` reachable only from your own devices (for the iPhone Shortcuts).

## 1. Install

```sh
sudo pacman -S --needed git python uv chromium tailscale
git clone https://github.com/noahljungberg/agi-wardrobe.git ~/agi-wardrobe
cd ~/agi-wardrobe
uv sync --extra browser          # the extra is Playwright, used by the link importer
uv run pytest -q                 # optional: everything should pass
```

`chromium` from pacman is what the importer drives (Playwright's own browser
download doesn't officially support Arch). Point `WARDROBE_CHROMIUM` at it below.

## 2. Wardrobe folder

Pick a folder, e.g. `~/wardrobe`. Want to try things before you've added your
own clothes? Generate a demo with drawn placeholder photos:

```sh
uv run wardrobe demo ~/wardrobe-demo
```

The format is described in [wardrobe-folder.md](wardrobe-folder.md). Once you
have links, import them from the command line:

```sh
uv run wardrobe import --file links.txt     # one link per line, # comments ok
uv run wardrobe check                       # summary, missing photos, guesses
```

## 3. Configuration

```sh
mkdir -p ~/.config/wardrobe
cp deploy/wardrobe.env.example ~/.config/wardrobe/wardrobe.env
chmod 600 ~/.config/wardrobe/wardrobe.env
uv run wardrobe secret           # run twice: passphrase and device token
$EDITOR ~/.config/wardrobe/wardrobe.env
```

`WARDROBE_PUBLIC_URL` is your machine's Tailscale name; `tailscale status --self`
or the admin console shows it (e.g. `https://homebox.tail1234.ts.net`).

## 4. Run it as a service

```sh
mkdir -p ~/.config/systemd/user
cp deploy/wardrobe.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now wardrobe
sudo loginctl enable-linger "$USER"   # keep running when you're not logged in
journalctl --user -u wardrobe -f      # logs
```

The unit assumes the repo is at `~/agi-wardrobe`; edit the paths if not.

## 5. Tailscale: public MCP endpoint + private Shortcuts endpoint

```sh
sudo systemctl enable --now tailscaled
sudo tailscale up
```

In the Tailscale admin console:

- **DNS → HTTPS Certificates**: enable.
- **Access controls**: Funnel must be allowed for this machine. The first
  `tailscale funnel` command prints a link that enables it if it isn't.

Then:

```sh
# Public, for ChatGPT/Claude's servers: https://<machine>.<tailnet>.ts.net → 127.0.0.1:8765
sudo tailscale funnel --bg 8765

# Tailnet only, for your iPhone Shortcuts: https://<machine>.<tailnet>.ts.net:8443 → 127.0.0.1:8766
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8766

tailscale funnel status
```

What's public on port 443:

- `/mcp` (requires the OAuth login),
- the OAuth endpoints and the one-page login,
- `/img/...`: outfit images with random, expiring links and item photos with
  signed, expiring links.

Location, import and inbox upload are on 8443, which only your own devices can
reach.

Quick check from another device on your tailnet:

```sh
curl https://<machine>.<tailnet>.ts.net/                 # "Wardrobe MCP server…"
curl -H "Authorization: Bearer <device token>" https://<machine>.<tailnet>.ts.net:8443/health
```

## 6. Connect ChatGPT

OpenAI moves these settings around, so the labels may differ slightly.

1. On **chatgpt.com** (web), go to **Settings → Apps & Connectors → Advanced**
   and turn on **Developer mode**.
2. **Create** a connector:
   - Name: `Wardrobe`
   - MCP server URL: `https://<machine>.<tailnet>.ts.net/mcp`
   - Authentication: **OAuth**
3. A login page opens. Type your `WARDROBE_PASSPHRASE` and tap **Allow**.
4. In a chat, enable the Wardrobe connector (the **+** / tools menu) and ask
   "what should I wear today?". After this the connector also works in the
   iPhone app.

If Developer mode isn't offered on your plan, use Claude for now (below); the
server is the same.

## 7. Connect Claude (optional)

1. On **claude.ai**, go to **Settings → Connectors → Add custom connector**.
2. Enter the URL `https://<machine>.<tailnet>.ts.net/mcp`.
3. Log in with your passphrase.

The connector then shows up in the Claude iPhone app as well.

## 8. iPhone Shortcuts

See [shortcuts.md](shortcuts.md):

- location on app open (needed for weather where you are),
- "Add to wardrobe" from Safari,
- "Add photo to wardrobe" from Photos.

## Troubleshooting

| Symptom | Check |
|---|---|
| ChatGPT/Claude can't connect | `tailscale funnel status`; `curl https://<machine>…/` from mobile data (not Wi-Fi) |
| Login loops / "invalid redirect" | `WARDROBE_PUBLIC_URL` must exactly match the Funnel URL (https, no trailing slash) |
| Weather always "home" | The location Shortcut isn't reaching `:8443`. Is the Tailscale VPN on on the phone? |
| Import fails with 403 | Try the Safari share-sheet Shortcut; it reads the page in your own browser |
| Need to log out every app | Stop the service, delete `oauth` rows: `sqlite3 ~/.local/state/wardrobe/state.db "delete from oauth"` |
