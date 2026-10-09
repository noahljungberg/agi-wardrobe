"""Fuzzy matching of what you say ("beige mango cords") to items."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from wardrobe.catalog import Item
from wardrobe.heuristics import canonical_colour, fold

# Words that mean the same thing for matching purposes (English + Swedish).
SYNONYMS: dict[str, str] = {
    "cords": "corduroy", "cord": "corduroy", "manchester": "corduroy", "manchesterbyxa": "corduroy trousers",
    "manchesterbyxor": "corduroy trousers", "byxa": "trousers", "byxor": "trousers", "pants": "trousers",
    "chinos": "trousers", "chino": "trousers", "slacks": "trousers",
    "tee": "t-shirt", "tshirt": "t-shirt", "t-tröja": "t-shirt", "jumper": "sweater", "knit": "sweater",
    "knitted": "sweater", "stickad": "sweater", "tröja": "sweater", "pullover": "sweater",
    "kappa": "coat", "rock": "coat", "jacka": "jacket", "skor": "shoes", "sko": "shoes", "trainers": "sneakers",
    "skjorta": "shirt", "piké": "polo", "pike": "polo", "ull": "wool", "linne": "linen", "bomull": "cotton",
    "kängor": "boots", "stövlar": "boots", "keps": "cap", "mössa": "beanie", "halsduk": "scarf",
    "puffer": "puffer", "dunjacka": "puffer", "täckjacka": "puffer",
    "jeans": "jeans", "denims": "jeans",
}
STOPWORDS = {"my", "the", "a", "an", "and", "with", "on", "today", "i", "have", "wearing", "min", "mina", "mitt", "de", "den", "det", "pair", "of"}


def tokens(text: str) -> list[str]:
    out: list[str] = []
    for raw in re.findall(r"[\wåäöéü-]+", text.lower()):
        if raw in STOPWORDS:
            continue
        expanded = SYNONYMS.get(raw, raw)
        for tok in expanded.split():
            out.append(fold(tok))
        colour = canonical_colour(raw)
        if colour and fold(colour) not in out:
            out.extend(fold(colour).split())
    return out


def item_tokens(item: Item) -> set[str]:
    fields = [item.id.replace("-", " "), item.name, item.brand or "", item.colour or "", item.category,
              str(item.get("type", "")), str(item.get("material", "")), *item.aliases]
    return set(tokens(" ".join(fields)))


def _token_score(query_tok: str, doc: set[str]) -> float:
    if query_tok in doc:
        return 1.0
    best = 0.0
    for d in doc:
        if len(query_tok) >= 4 and (d.startswith(query_tok) or query_tok.startswith(d)) and len(d) >= 4:
            best = max(best, 0.85)
        elif len(query_tok) >= 4:
            ratio = SequenceMatcher(None, query_tok, d).ratio()
            if ratio >= 0.84:
                best = max(best, ratio * 0.9)
    return best


@dataclass
class Match:
    item: Item
    score: float


def search(items: list[Item], query: str, limit: int = 10, min_score: float = 0.34) -> list[Match]:
    q = tokens(query)
    if not q:
        return []
    alias_hits = {i.id for i in items for a in i.aliases if fold(a) and fold(a) in fold(query)}
    results = []
    for item in items:
        doc = item_tokens(item)
        score = sum(_token_score(t, doc) for t in q) / len(q)
        if item.id in alias_hits or fold(query.strip()) == item.id:
            score = max(score, 0.95) + 0.15  # your own name for it beats generic word overlap
        if score >= min_score:
            results.append(Match(item, round(score, 3)))
    results.sort(key=lambda m: (-m.score, m.item.id))
    return results[:limit]


@dataclass
class Resolution:
    phrase: str
    item: Item | None
    candidates: list[Item]


def resolve(items: list[Item], phrase: str) -> Resolution:
    """Map a phrase or id to a single item if it's unambiguous."""
    for item in items:
        if phrase.strip() == item.id:
            return Resolution(phrase, item, [])
    matches = search(items, phrase, limit=5)
    if not matches:
        return Resolution(phrase, None, [])
    top = matches[0]
    runner_up = matches[1].score if len(matches) > 1 else 0.0
    if top.score >= 0.6 and top.score - runner_up >= 0.12:
        return Resolution(phrase, top.item, [])
    if top.score > 1.0 and runner_up <= 1.0:  # matched one of your aliases
        return Resolution(phrase, top.item, [])
    return Resolution(phrase, None, [m.item for m in matches if m.score >= top.score - 0.2])
