# Known issues and follow-ups

Non-blocking debt and ideas. Agents: add here instead of fixing out of scope;
remove an entry in the change that fixes it.

## Open

| # | Area | Issue | Notes |
|---|---|---|---|
| 1 | importer | Not yet run against live Mango/Zalando/Levi's pages. All three returned 403 from a cloud IP | Verify from home (`wardrobe import`), adjust parsers with real HTML saved as fixtures |
| 2 | importer | Mango product pages may be JavaScript-rendered | Playwright fallback exists; untested on the real site |
| 3 | outfit card | Rendering in the ChatGPT/Claude **iPhone** apps unverified | First task of the deployment plan |
| 4 | clients | ChatGPT Pro Lite may not offer Developer mode / write tools | Claude is the fallback client; same server |
| 5 | weather | With MET Norway and a location without `tz`, the UTC offset is guessed from longitude (no DST) | The phone Shortcut sends `tz`; geocoded places have it |
| 6 | state | No schema migration mechanism; adding a column needs `ALTER TABLE` handling | Add a `PRAGMA user_version` based migrator when the first change comes |
| 7 | cli | No automated test for `wardrobe serve` / `check` / `import` | Manual start/SIGTERM check done |
| 8 | catalog | Refresh scans every item folder (fine for hundreds of items) | Revisit if a wardrobe grows past ~2000 items |
| 9 | auth | Failed-login lockout is in memory and resets on restart | Acceptable for one user behind a long passphrase |
| 10 | http-api | A urlencoded `/location` body with raw (non-percent-encoded) UTF-8 is decoded as Latin-1 | Shortcuts send JSON, so this doesn't affect them; only hand-made curl calls |
| 11 | render | Own photos (inbox) have messy backgrounds next to clean packshots | Optional background removal (e.g. `rembg`) when saving from the inbox |

## Ideas (not planned)

- Trip packing list: "SF for 5 days" → forecast for each day + wardrobe.
- Rating outfits ("loved it") to tune scoring per user.
- Laundry-aware suggestions via `status: laundry` from a Shortcut.

## Closed

- 2026-10-09: tools used server-local `date.today()`; now `Wardrobe.local_today()`.
- 2026-10-09: dead code (`State.oauth_delete_where`, `DayWeather.as_dict`,
  `EDITABLE_FIELDS`) removed.
