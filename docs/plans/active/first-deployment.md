# Plan: first deployment and real-world verification

Status: in progress
Owner: repository owner (steps needing the phone/home machine) + agent (fixes)
Goal: the server runs on the Arch machine, ChatGPT (or Claude) on the iPhone
uses it, and the real wardrobe is loaded.

Agents: do the next unchecked task only, record the result in the progress
log, and stop. Tasks marked 👤 need the owner's devices; for those, prepare
anything you can and then ask.

## Tasks

- [ ] 1. 👤 **Install and run on Arch** ([guides/setup.md](../../guides/setup.md) §1–4)
  - Acceptance: `systemctl --user status wardrobe` is active;
    `scripts/verify.sh` passes on the machine.
- [ ] 2. 👤 **Expose with Tailscale** (setup §5)
  - Acceptance: the public URL (443 or 10000) opened on the phone **with
    Tailscale off, on mobile data** returns the hello text; `:8443/health`
    works only on the tailnet.
  - If the MCP endpoint answers 421 or "Invalid Host header": Funnel sends a
    different Host than expected. Add it to `allowed_hosts` in
    `build_public_app`, add a test, and record it in
    [http-api.md](../../design/http-api.md).
- [ ] 3. 👤 **Connect ChatGPT** (setup §6). If Developer mode isn't available on
  Pro Lite, connect Claude instead (§7).
  - Acceptance: the login page appears, the passphrase is accepted, and
    "what should I wear?" triggers `dress_me`.
- [ ] 4. 👤 **Check how the outfit shows on the iPhone** with the demo wardrobe
  - Record for each app: inline card renders? image inside the tool block?
    link opens?
  - Acceptance: results written in the decision log below and in
    [outfit-card.md](../../design/outfit-card.md); QUALITY row updated.
- [ ] 5. 👤 **Location Shortcut** ([guides/shortcuts.md](../../guides/shortcuts.md) §1)
  - Acceptance: after opening ChatGPT,
    `dress_me` says "from your phone, just now".
- [ ] 6. **Real links import** (owner collects links, including the Mango orders
  from July/August and Mango Outlet 2025)
  - Run `wardrobe import --file links.txt` on the home machine.
  - For each failing shop: save the page HTML as a test fixture (without
    personal data), fix the parser, add a test (`add-shop-parser` skill).
  - Acceptance: ≥90% of links import with a photo; failures are listed in
    known-issues with a reason.
- [ ] 7. 👤 **Fill gaps**: BestSecret items and in-store buys via the Photos
  share Shortcut → "check my inbox".
  - Acceptance: `wardrobe check` shows no `NO PHOTO` items.
- [ ] 8. **One week of real use**, then tune `outfit.py` thresholds from
  feedback.
  - Acceptance: thresholds changed only with a test row per change; QUALITY
    updated.

## Decision log

- 2026-10-09: The display method on iPhone is unknown, so `show_outfit`
  returns all three (MCP Apps card, image content, collage link). Keep all
  three until task 4 shows which ones render.

## Progress log

- 2026-10-09: v0.1 built and pushed; plan created.
- 2026-10-09: Task 3 attempt (Claude web). `…ts.net:8443` is the private
  port, unreachable for Claude by design. `…ts.net:10000/mcp` → "couldn't reach
  this address": Funnel isn't answering from the internet yet (owner to check
  `tailscale funnel status`, certs, policy). Fixed in code: public Host
  checks now accept the Funnel hostname with or without port, so `:10000`
  works once Funnel serves. Setup guide now says which URL goes where and how
  to test from outside the tailnet.
- 2026-10-09: Second attempt: `:10000/mcp` answers `invalid_token` in the
  owner's browser (server and Funnel port OK, at least from the tailnet), but
  Claude still says "couldn't reach". Open: confirm reachability from outside
  the tailnet and that `WARDROBE_PUBLIC_URL` includes `:10000`. Also found that
  Claude defaults to CIMD, which the server didn't support; added (auth.md).
- 2026-10-09: **Connected in ChatGPT.** `dress_me` and `show_outfit` work on the
  real wardrobe; the collage link opens. The outfit card was an empty frame
  stuck on "Opening Show outfit": the card skipped the MCP Apps handshake
  because `window.openai` existed. Fixed (always handshake) and covered by a
  test. The model also embedded the collage as an image (grey box), so the
  instructions now say link only. Next: pull, restart, re-check the card
  (task 4).
