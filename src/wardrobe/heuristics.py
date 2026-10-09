"""Guess item attributes from a product name (English and Swedish).

These guesses only fill gaps: anything written in item.yaml wins, and the
assistant is asked to confirm imported items.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

CATEGORIES = ("outerwear", "tops", "bottoms", "shoes", "accessories", "other")

# (pattern, fields). First match wins, so specific patterns come first.
# Patterns run on lowercased text; Swedish compounds (ullkappa, manchesterbyxa)
# are why most patterns are plain substrings rather than whole words.
_TYPE_RULES: list[tuple[str, dict[str, Any]]] = [
    (r"t-?shirt|t-?tröja|\btee\b|tshirt", {"category": "tops", "type": "t-shirt", "layer": "base", "warmth": 1, "formality": 1}),
    (r"polo|piké|\bpike\b", {"category": "tops", "type": "polo", "layer": "base", "warmth": 1, "formality": 3}),
    (r"overshirt|skjortjacka|shacket", {"category": "outerwear", "type": "overshirt", "warmth": 2, "formality": 2}),
    (r"blazer|kavaj|kostymjacka", {"category": "outerwear", "type": "blazer", "warmth": 2, "formality": 4}),
    (r"trench", {"category": "outerwear", "type": "trench coat", "warmth": 2, "formality": 4, "rain_ok": True}),
    (r"parka", {"category": "outerwear", "type": "parka", "warmth": 5, "formality": 2}),
    (r"puffer|dunjacka|täckjacka|vadderad|padded|quilted|down jacket", {"category": "outerwear", "type": "puffer", "warmth": 4, "formality": 2}),
    (r"coat|kappa|\brock\b|överrock", {"category": "outerwear", "type": "coat", "warmth": 3, "formality": 4}),
    (r"jacket|jacka|bomber|blouson|anorak|windbreaker", {"category": "outerwear", "type": "jacket", "warmth": 3, "formality": 2}),
    (r"gilet|väst|vest", {"category": "outerwear", "type": "vest", "warmth": 2, "formality": 2}),
    (r"hoodie|huvtröja|hooded", {"category": "tops", "type": "hoodie", "layer": "mid", "warmth": 3, "formality": 1}),
    (r"sweatshirt|collegetröja|crewneck sweat(?!er)", {"category": "tops", "type": "sweatshirt", "layer": "mid", "warmth": 3, "formality": 1}),
    (r"cardigan|kofta", {"category": "tops", "type": "cardigan", "layer": "mid", "warmth": 3, "formality": 3}),
    (r"sweater|jumper|pullover|knit|stickad|tröja|turtleneck|polokrage", {"category": "tops", "type": "knit", "layer": "mid", "warmth": 3, "formality": 3}),
    (r"shirt|skjorta|oxford", {"category": "tops", "type": "shirt", "layer": "base", "warmth": 1, "formality": 3}),
    (r"tank|singlet", {"category": "tops", "type": "tank top", "layer": "base", "warmth": 0, "formality": 1}),
    (r"jeans|denim", {"category": "bottoms", "type": "jeans", "warmth": 2, "formality": 2}),
    (r"shorts", {"category": "bottoms", "type": "shorts", "warmth": 0, "formality": 1}),
    (r"jogger|sweatpants|mjukisbyxor", {"category": "bottoms", "type": "joggers", "warmth": 2, "formality": 1}),
    (r"chino|trousers|byxa|byxor|pants|slacks|kostymbyxa", {"category": "bottoms", "type": "trousers", "warmth": 2, "formality": 3}),
    (r"boot|känga|kängor|stövel|stövlar|chelsea", {"category": "shoes", "type": "boots", "warmth": 3, "formality": 3}),
    (r"loafer|mockasin", {"category": "shoes", "type": "loafers", "warmth": 1, "formality": 4}),
    (r"derby|brogue|oxfordsko|dress shoe|finsko", {"category": "shoes", "type": "dress shoes", "warmth": 1, "formality": 5}),
    (r"sandal|slides|flip.?flop", {"category": "shoes", "type": "sandals", "warmth": 0, "formality": 1}),
    (r"sneaker|trainer|tennisskor|löparsko|runner", {"category": "shoes", "type": "sneakers", "warmth": 1, "formality": 2}),
    (r"\bskor\b|\bsko\b|shoes?\b", {"category": "shoes", "type": "shoes", "warmth": 1, "formality": 2}),
    (r"scarf|halsduk", {"category": "accessories", "type": "scarf", "warmth": 3, "formality": 3}),
    (r"beanie|mössa|\bhat\b|hatt|keps|\bcap\b", {"category": "accessories", "type": "hat", "warmth": 2, "formality": 2}),
    (r"glove|handskar|vantar", {"category": "accessories", "type": "gloves", "warmth": 3, "formality": 3}),
    (r"belt|bälte|skärp", {"category": "accessories", "type": "belt", "formality": 3}),
    (r"\bbag\b|väska|ryggsäck|backpack|tote", {"category": "accessories", "type": "bag", "formality": 2}),
]

_MATERIALS: list[tuple[str, str, int]] = [
    # (pattern, material, warmth delta)
    (r"cashmere|kashmir", "cashmere", 1),
    (r"merino", "merino wool", 1),
    (r"\bwool|\bull|ullkappa|ullblandning|ulltröja|wool-blend|lammull|lambswool", "wool", 1),
    (r"shearling|fårskinn|sherpa|teddy", "shearling", 1),
    (r"fleece", "fleece", 1),
    (r"corduroy|manchester", "corduroy", 1),
    (r"linen|linne", "linen", -1),
    (r"seersucker", "cotton seersucker", -1),
    (r"suede|mocka", "suede", 0),
    (r"leather|läder|skinn", "leather", 0),
    (r"lyocell|tencel", "lyocell", 0),
    (r"cotton|bomull", "cotton", 0),
]

_RAIN = r"waterproof|water-?repellent|vattenavvisande|vattentät|gore-?tex|rain|regn"
_DRESSY = r"pressveck|pleat|pleated|tailored|kostym|suit|wool trousers|ullbyxa"
_CASUAL = r"dragsko|drawstring|cargo|relaxed|oversize"

# canonical colour -> spellings (English, Swedish, store names)
_COLOURS: dict[str, list[str]] = {
    "off-white": ["off-white", "offwhite", "off white", "ecru", "cream", "kräm", "natur", "ivory", "benvit", "écru"],
    "white": ["white", "vit", "vitt", "vita"],
    "black": ["black", "svart", "svarta"],
    "light grey": ["light grey", "light gray", "ljusgrå", "ice grey", "ice gray"],
    "charcoal": ["charcoal", "antracit", "anthracite", "dark grey", "dark gray", "mörkgrå"],
    "grey": ["grey", "gray", "grå", "gråmelerad", "melange"],
    "navy": ["navy", "marinblå", "marin", "dark blue", "mörkblå"],
    "light blue": ["light blue", "ljusblå", "sky blue"],
    "blue": ["blue", "blå", "indigo", "denim"],
    "beige": ["beige", "sand", "stone", "camel", "taupe", "khaki beige"],
    "brown": ["brown", "brun", "chocolate", "choklad", "tobacco", "cognac", "rust brown"],
    "olive": ["olive", "oliv", "khaki", "army", "military green"],
    "green": ["green", "grön", "forest", "bottle green", "sage", "mint"],
    "burgundy": ["burgundy", "vinröd", "bordeaux", "wine", "maroon"],
    "red": ["red", "röd"],
    "pink": ["pink", "rosa"],
    "yellow": ["yellow", "gul", "mustard", "senap"],
    "orange": ["orange", "rust", "terracotta"],
    "purple": ["purple", "lila", "violet"],
}

NEUTRAL_COLOURS = {"off-white", "white", "black", "light grey", "charcoal", "grey", "navy", "beige", "brown", "olive", "blue", "light blue"}


def fold(text: str) -> str:
    """Lowercase and strip accents, keeping Swedish å/ä/ö recognisable as a/a/o."""
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def canonical_colour(text: str | None) -> str | None:
    if not text:
        return None
    low = text.lower()
    # Longest spellings first so "light grey" beats "grey" and "off-white" beats "white".
    candidates = sorted(((s, c) for c, spellings in _COLOURS.items() for s in spellings), key=lambda p: -len(p[0]))
    for spelling, colour in candidates:
        if re.search(rf"(?<![a-zåäö]){re.escape(spelling)}(?![a-zåäö])", low):
            return colour
    return None


def infer(name: str, extra: str = "") -> dict[str, Any]:
    """Best-effort attributes for an item called `name` (`extra` = description etc.)."""
    text = f"{name} {extra}".lower()
    out: dict[str, Any] = {}
    # The name decides the type; the description is only a fallback.
    for source in (name.lower(), extra.lower()):
        for pattern, fields in _TYPE_RULES:
            if re.search(pattern, source):
                out.update(fields)
                break
        if out:
            break
    for pattern, material, delta in _MATERIALS:
        if re.search(pattern, text):
            out["material"] = material
            if "warmth" in out and out.get("category") in ("tops", "bottoms", "outerwear"):
                out["warmth"] = max(0, min(5, out["warmth"] + delta))
            break
    if re.search(_RAIN, text):
        out["rain_ok"] = True
    if out.get("category") == "bottoms" and "formality" in out:
        if re.search(_DRESSY, text):
            out["formality"] = min(5, out["formality"] + 1)
        elif re.search(_CASUAL, text):
            out["formality"] = max(1, out["formality"] - 1)
    colour = canonical_colour(name) or canonical_colour(extra)
    if colour:
        out["colour"] = colour
    return out


def layer_for(category: str | None, type_: str | None) -> str | None:
    if category != "tops":
        return None
    for pattern, fields in _TYPE_RULES:
        if fields.get("category") == "tops" and type_ and re.search(pattern, type_.lower()):
            return fields.get("layer")
    return "base"
