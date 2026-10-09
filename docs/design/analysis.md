# Wardrobe analysis

Status: complete

## Purpose

Computes the facts the model needs to give gap, duplicate and shopping advice.
It doesn't produce advice itself: the model combines these numbers with the
profile, climate and the user's question.

## Public API

- `analyse(items, wear_counts, last_worn, history, today) -> dict` with keys:
  - `items_total`, `per_slot`, `colours`, `warmth_by_slot`, `formality_by_slot`
  - `coverage`: rain-proof outerwear, warm outerwear (≥4), boots, smart items
    (formality ≥4) per slot, warm-weather bottoms
  - `near_duplicates`: same slot, type and colour
  - `hard_to_combine`: tops/bottoms with ≤1 compatible partner
  - `wear_log`: days logged, temperature range seen, most worn, never worn
    (only after 14+ logged days), not worn in 60 days
  - `cost_per_wear_highest`, `housekeeping` (missing photo, needs review)

## Implementation files

- `src/wardrobe/analysis.py`

## Dependencies

- Allowed: `catalog`, `heuristics` (`NEUTRAL_COLOURS`), `outfit` (`slot_of`).
- Forbidden: `state` (data is passed in), `server`, network.

## Constraints

- Compatibility rule: formality within 1, and either colour neutral or both the
  same.
- The output is serialised as JSON for the model. Keep it compact: lists of
  ids, not item dumps.

## Tests

- `tests/test_analysis.py`: duplicates, coverage, the never-worn threshold,
  cost per wear.
- `tests/test_server.py::test_preferences_and_analysis`: the tool wrapper.

## Non-goals

- No product recommendations or shopping links (the chat model can search the
  web itself).
