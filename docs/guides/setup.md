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
#   …or, if port 443 is already used on this machine, on Funnel's other allowed port:
#   sudo tailscale funnel --bg --https=10000 http://127.0.0.1:8765

# Tailnet only, for your iPhone Shortcuts: https://<machine>.<tailnet>.ts.net:8443 → 127.0.0.1:8766
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8766

tailscale funnel status
```

`tailscale funnel status` must list the public port with **`(Funnel on)`** and
the proxy to `http://127.0.0.1:8765`. `:8443` must **not** say Funnel on.

Funnel only allows ports **443, 8443 and 10000**. The port you choose becomes
part of every public URL, so it must also be in `WARDROBE_PUBLIC_URL` (e.g.
`https://<machine>.<tailnet>.ts.net:10000`). Restart the service after you
change it.

What's public:

- `/mcp` (requires the OAuth login),
- the OAuth endpoints and the one-page login,
- `/img/...`: outfit images with random, expiring links and item photos with
  signed, expiring links.

Location, import and inbox upload are on 8443, which only your own devices can
reach. **Never give 8443 to ChatGPT/Claude**: their servers aren't in your
tailnet.

### Check it from the internet, not from your tailnet

A check from a device that's on Tailscale proves nothing about Funnel: on the
tailnet the name resolves privately. Turn **Tailscale off** on the phone, use
**mobile data**, and open in Safari:

```
https://<machine>.<tailnet>.ts.net/            (or …ts.net:10000/)
```

You should see `Wardrobe MCP server…`. `…/mcp` should answer with an
"unauthorized" error (that's correct: it wants the login). If the page doesn't
load at all, Funnel isn't serving yet; see Troubleshooting. It can take a few
minutes after Funnel is first enabled for DNS and the certificate to be ready.

Private check, from a device **on** the tailnet:

```sh
curl -H "Authorization: Bearer <device token>" https://<machine>.<tailnet>.ts.net:8443/health
```

### Which URL goes where

| Where | URL |
|---|---|
| ChatGPT / Claude connector | `https://<machine>.<tailnet>.ts.net/mcp` (or `…ts.net:10000/mcp`) |
| `WARDROBE_PUBLIC_URL` | `https://<machine>.<tailnet>.ts.net` (or `…ts.net:10000`), with no `/mcp` and no trailing slash |
| iPhone Shortcuts | `https://<machine>.<tailnet>.ts.net:8443/...` |

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
2. Enter the URL `https://<machine>.<tailnet>.ts.net/mcp` (with `:10000`
   before `/mcp` if you used that Funnel port). Never use `:8443`.
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
| Connector says "couldn't reach this address" / "Kunde inte nå den här adressen" | The public URL doesn't answer from the internet. Check: `systemctl --user status wardrobe` is active; `curl http://127.0.0.1:8765/` on the machine prints the hello; `tailscale funnel status` shows the port **(Funnel on)** proxying to `http://127.0.0.1:8765`; HTTPS certificates are enabled in the admin console; Funnel is allowed by the tailnet policy (the `funnel` node attribute); the URL uses the Funnel port, not `:8443`. Then test from the phone with Tailscale off on mobile data. Right after enabling, wait a few minutes. |
| Connector reaches the server but MCP returns 421 "Invalid Host header" | `WARDROBE_PUBLIC_URL` doesn't match the Funnel name; fix it and restart |
| Login loops / "invalid redirect" | `WARDROBE_PUBLIC_URL` must exactly match the Funnel URL (https, no trailing slash) |
| Weather always "home" | The location Shortcut isn't reaching `:8443`. Is the Tailscale VPN on on the phone? |
| Import fails with 403 | Try the Safari share-sheet Shortcut; it reads the page in your own browser |
| Need to log out every app | Stop the service, delete `oauth` rows: `sqlite3 ~/.local/state/wardrobe/state.db "delete from oauth"` |
