# Outfit candidates

Status: complete

## Purpose

Narrows the wardrobe to a few good candidates per slot for the day's weather,
the occasion and what was worn recently. It does **not** pick the final outfit:
the model sees the candidates' photos and decides.

## Public API

- `SLOTS = (outerwear, mid, base, bottoms, shoes, accessories)`, `SLOT_TITLES`
- `slot_of(item)`: tops map to `base` or `mid` by `layer`.
- `compute_targets(weather, occasion, bias=0.0) -> Targets`: target warmth per
  slot, whether outerwear and a mid layer are `yes|optional|no`, wet/snow,
  formality from the occasion, suggested accessories. `Targets.guidance()` is
  the line shown to the model.
- `score(item, slot, targets, today, last_worn) -> float`
- `pick_candidates(items, weather, occasion, anchors, last_worn, today, bias, per_slot=6) -> Candidates`:
  anchors (what you already have on) fill their slots, and those slots get no
  candidates.
- `occasion_formality(text)`, `temperature_bias(profile)`: `runs: cold` gives
  −2.5 °C, `runs: warm` gives +2.5 °C, or an explicit `temperature_bias`.

## Implementation files

- `src/wardrobe/outfit.py`

## Dependencies

- Allowed: `catalog` (`Item`), `weather` (`DayWeather`).
- Forbidden: `state` (last-worn dates are passed in), `render`, `server`, network.

## Constraints

- Thresholds use **feels-like** temperature: the minimum for outerwear and
  shoes, the average for layers and bottoms.
- Score = 1 − 0.22·|warmth − target|, then:
  - rain: ±0.25 for rain-ok outerwear, +0.15 for shoes that handle rain,
    −0.3 for suede;
  - snow: boots +0.3;
  - formality: −0.12 per step off the occasion;
  - recently worn: penalties in `RECENCY_PENALTY` (base layers are penalised most).
- Items without warmth use `DEFAULT_WARMTH[slot]`.
- At most 6 per slot and 4 accessories; fewer when a slot isn't needed.

## Tests

- `tests/test_outfit.py`: cold/wet vs hot targets, rain-proof outerwear
  first, an anchor's slot skipped, recently worn tops dropping.

## Non-goals

- No colour-harmony scoring (the model judges looks from the photos; stored
  preferences go to the model as text).
- No "complete outfit" generation, and no learning from ratings.
