# Outfit on you (try-on)

Status: complete (not yet run against a signed-in Codex)

## Purpose

Draws a chosen outfit on the user, from their photo in `me/` and the garment
photos, so "dress me and show me" can show them wearing it. Pictures come from
the owner's signed-in Codex CLI on the home machine: Codex's built-in image
generation (`gpt-image-2`) runs on the ChatGPT subscription, so there is no API
key and no per-picture bill. The owner chose this over a pay-per-image API
(2026-10-11).

## Public API

- `TryOn(cache_dir, renderer, codex, model=None, codex_home=None, timeout=420, run=subprocess.run)`,
  created by `Wardrobe` as `w.tryon` from `WARDROBE_CODEX` / `WARDROBE_CODEX_MODEL`.
- `pick_person(photos) -> list[Path]`: up to two photos of the user, tallest
  first (a full-length photo shows the build; a portrait gives the face).
- `request(person, items, styling="") -> Status`: the cached picture, or start
  or join the job. `Status.state` is `done` (with `path`), `running` (with
  `seconds`) or `failed` (with `error`). A failure is reported once; the next
  call retries.
- `await obtain(person, items, styling="", wait=50) -> Status`: `request`,
  waiting up to `wait` seconds for a running job.
- `executable()`: the resolved Codex path; raises `TryOnError` when it's off or
  missing.
- `build_prompt(n_person, pictured, unpictured, styling)`, `clean(text, limit)`.
- `TryOnError`: a message to show the user as is.

## How a picture is made

1. Photos are copied as JPEGs (person 1536 px, garments 1024 px) into a temporary
   folder: up to 2 of the person and up to 7 garments, ordered outerwear → shoes.
   Garments without a photo are described in words.
2. `codex login status` must not mention an API key or "not logged in".
3. The command is:
   ```
   codex exec --json --ephemeral --skip-git-repo-check --ignore-user-config --ignore-rules
     --sandbox read-only --cd <tmp> --output-last-message <tmp>/last-message.txt [--model M]
     --image person-1.jpg … --image garment-1.jpg …
   ```
   The prompt goes in on stdin: `--image` takes several files and would swallow a
   positional prompt. `OPENAI_API_KEY` and `CODEX_API_KEY` are removed from the
   child's environment.
4. Codex saves the picture to `$CODEX_HOME/generated_images/<thread id>/<call id>.png`
   (Codex source, `ext/image-generation`). The picture is found from the
   `RESULT:` line in the last message, then this thread's folder (the thread id
   comes from the `thread.started` JSON event), then the newest picture made
   since the run started.
5. It is saved as `cache/tryon/<key>.jpg` (1200 px). The key covers the item ids,
   labels, photo files, the person's photos, the styling, the model and
   `PROMPT_VERSION`. Codex's own copy is deleted when it came from this run's folder.

## Implementation files

- `src/wardrobe/tryon.py`

## Dependencies

- Allowed: `catalog` (`Item`), `outfit` (`slot_of`, `SLOTS`), `render`
  (`Renderer` for JPEG conversion), the standard library (`subprocess`, threads).
- Forbidden: `server`, `state`, network libraries (Codex does the network I/O).

## Constraints

- One Codex job at a time, in daemon threads (stopping the service never waits for a
  picture; systemd stops the Codex child with the service). Other outfits queue behind it.
- A job is killed after 7 minutes. Exit codes and usage-limit messages are
  turned into `TryOnError` text, never exceptions in the tool.
- Prompt text from the catalogue (labels) and the chat model (styling) passes
  through `clean()`: letters, digits, spaces and `.,'&()/+%-` only, length-capped.
  Codex also runs read-only, without the owner's config, rules or MCP servers. The
  agent's own reply is only logged on the server, never returned to the chat (a garment
  photo could carry instructions, and a read-only agent can still read files).
- The prompt asks to keep the person's face, hair, skin tone and proportions,
  and not to slim, lengthen or idealise them. The picture is still an
  approximation: tool text and `INSTRUCTIONS` say never to judge fit from it.
- Bump `PROMPT_VERSION` when the prompt changes so cached pictures are redrawn.
- The user's photos go to OpenAI through Codex only when `try_on` is called.

## Tests

- `tests/test_tryon.py` with a fake `codex` script (no network):
  - the command line, flags, stdin prompt, no API key, the full-length photo
    first, cleaning, caching and removal of Codex's copy;
  - finding the picture without a `RESULT:` line;
  - each failure (not signed in, API key, exit code, usage limit, no picture)
    reported once, then retried;
  - a slow job: `running`, then `done`;
  - off/missing Codex, `WARDROBE_CODEX` parsing, prompt text;
  - the `try_on` tool: no photo, link + image, unknown ids.
- The flags were checked against Codex CLI 0.162.1 (`codex exec --help`, and a
  run that reached the 401 for a missing login). A real signed-in run is still
  owed (QUALITY).

## Non-goals

- No API-key image providers (Gemini, OpenAI API). Add them behind the same
  `TryOn` interface if the subscription route stops working.
- No fit judgement, measurements or body editing.
- No automatic pictures for every outfit: they cost subscription usage, so the
  model only asks when the user wants to see it on them.
