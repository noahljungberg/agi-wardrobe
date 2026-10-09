# Matching: what you say → which item

Status: complete

## Purpose

Resolves free-text phrases ("beige mango cords", "my black coat",
"manchester trousers") or ids to items, and searches the wardrobe. Ambiguity is
returned rather than guessed, so the model can ask.

## Public API

- `resolve(items, phrase) -> Resolution(phrase, item | None, candidates)`:
  - an exact id wins;
  - otherwise the top match must score ≥ 0.6 and beat the runner-up by ≥ 0.12;
  - or the top match hit one of the item's `aliases` while the runner-up didn't.
- `search(items, query, limit=10, min_score=0.34) -> list[Match(item, score)]`.
- `tokens(text)`: synonym expansion (`SYNONYMS`), stopwords, colour folding.
- `item_tokens(item)`.

## Implementation files

- `src/wardrobe/matching.py`

## Dependencies

- Allowed: `catalog` (the `Item` type), `heuristics` (`fold`, `canonical_colour`).
- Forbidden: `state`, `server`, network.

## Constraints

- Score = mean over query tokens of the best per-token match (exact 1.0,
  prefix 0.85, fuzzy ≥ 0.84 ratio × 0.9). An alias hit sets the score to at
  least 0.95 + 0.15.
- Matching is deterministic: ties are broken by item id.
- Adding a synonym: map a word to its canonical tokens in `SYNONYMS`
  (Swedish → English is the main use).

## Tests

- `tests/test_matching.py`: phrases from real usage, the alias tie-break
  between two identical corduroys, ambiguity, no-match.

## Non-goals

- No embeddings or semantic search. Wardrobes are small, and the model handles
  vague requests via `find_items`.
- No learning from corrections. The user adds `aliases` instead
  (`save_item(aliases=[...])`).
