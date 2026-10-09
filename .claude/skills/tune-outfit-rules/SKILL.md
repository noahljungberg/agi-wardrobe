---
name: tune-outfit-rules
description: Adjust how the wardrobe server picks candidates for the weather and occasion (warmth targets, rain, formality, recently-worn penalties) or how items get guessed attributes. Use when feedback is like "it suggests coats when it's mild", "it ignores rain", "my knit is treated as a t-shirt".
---

# Tune outfit and attribute rules

Read first: [docs/design/outfit.md](../../../docs/design/outfit.md); for a wrong
category or warmth on an item, [docs/design/heuristics.md](../../../docs/design/heuristics.md).

## Decide which knob

| Symptom | Knob |
|---|---|
| One item has the wrong warmth/category/formality | Not a rule problem: fix that item (`save_item` or its item.yaml) |
| Many items with a naming pattern are misread | `heuristics._TYPE_RULES` / `_MATERIALS` |
| Outerwear/mid layer suggested at the wrong temperatures | `outfit.compute_targets` bands |
| Rain or snow ignored | rain/snow terms in `outfit.score` |
| Same top suggested too often | `outfit.RECENCY_PENALTY` |
| The owner runs cold or warm overall | `profile.yaml` `runs:` / `temperature_bias`, not code |

## Steps

1. Reproduce with a test first: build a `DayWeather` like `_weather(...)` in
   `tests/test_outfit.py` (or a name row in `tests/test_heuristics.py`) that
   shows the current wrong behaviour.
2. Change **one** threshold or rule. Keep rule order specific → general.
3. Run `scripts/verify.sh --quick` and check that the other cases still hold.
4. Record the change and the feedback that motivated it in the active plan's
   decision log, and update the constraints in `docs/design/outfit.md` if the
   numbers there changed.

## Don't

- Don't add colour-harmony scoring or "complete outfit" picking to the server.
  The model chooses from photos (see the non-goals).
