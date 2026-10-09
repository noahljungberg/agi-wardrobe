# Heuristics: attributes from product names

Status: complete

## Purpose

Guesses `category, type, layer, warmth, formality, material, rain_ok, colour`
from a product name in English or Swedish ("Ullkappa med hög krage" → outerwear
coat, wool, warmth 4, formality 4). The guesses fill gaps so imported or
hand-made items work immediately. User-written values always win.

## Public API

- `infer(name, extra="") -> dict`: the name decides the type; `extra`
  (description, material) is the fallback.
- `canonical_colour(text) -> str | None`: maps spellings in many languages to
  one of the canonical colours ("ecru" → "off-white", "marinblå" → "navy").
- `layer_for(category, type) -> "base" | "mid" | None`.
- `fold(text)`: lowercase and strip accents, for matching.
- `CATEGORIES`, `NEUTRAL_COLOURS`.

## Implementation files

- `src/wardrobe/heuristics.py`: the rule tables `_TYPE_RULES`, `_MATERIALS`,
  `_COLOURS` and the functions above.

## Dependencies

- Allowed: standard library only.
- Forbidden: every other `wardrobe` module (layer 0).

## Constraints

- `_TYPE_RULES` is **first match**: specific before general (`overshirt` before
  `jacket`, `t-shirt` before `shirt`).
- Swedish compounds match as substrings; short English words use `\b`.
- Material shifts warmth by its delta (wool +1, linen −1), but only for tops,
  bottoms and outerwear.
- Trousers get +1 formality for pressed/pleated/tailored, −1 for
  drawstring/cargo.

## Tests

- `tests/test_heuristics.py`: a parametrised table of real product names
  (Mango, Zalando, Levi's), materials, colours. **Every new rule adds a row.**

## Non-goals

- No ML or LLM calls. The model in the chat corrects mistakes through
  `save_item`.
- No brand-specific knowledge (fit, sizing).
