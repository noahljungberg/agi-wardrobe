import pytest

from wardrobe.heuristics import canonical_colour, infer


@pytest.mark.parametrize(
    ("name", "category", "type_", "layer"),
    [
        ("Manchesterbyxa regular fit", "bottoms", "trousers", None),
        ("Regular fit-byxa i bomull med pressveck", "bottoms", "trousers", None),
        ("Vadderad jacka krage av fårskinnspäls", "outerwear", "puffer", None),
        ("Kort vadderad vattenavvisande täckjacka", "outerwear", "puffer", None),
        ("Ribbstickad tenniströja", "tops", "knit", "mid"),
        ("Ullkappa med hög krage", "outerwear", "coat", None),
        ("BOMBAY - Piké - black", "tops", "polo", "base"),
        ("T-shirt - bas - ice grey", "tops", "t-shirt", "base"),
        ("Merino crewneck sweater", "tops", "knit", "mid"),
        ("Hilltop Jacket", "outerwear", "jacket", None),
        ("Leather sneakers", "shoes", "sneakers", None),
        ("Suede Chelsea boots", "shoes", "boots", None),
        ("Oxford shirt", "tops", "shirt", "base"),
        ("Skjortjacka i ull", "outerwear", "overshirt", None),
    ],
)
def test_infer_type(name, category, type_, layer):
    out = infer(name)
    assert out["category"] == category
    assert out["type"] == type_
    assert out.get("layer") == layer


def test_materials_adjust_warmth_and_rain():
    assert infer("Ullkappa med hög krage")["material"] == "wool"
    assert infer("Ullkappa med hög krage")["warmth"] == 4
    assert infer("Slim fit-byxa linne dragsko")["material"] == "linen"
    assert infer("Slim fit-byxa linne dragsko")["warmth"] == 1
    assert infer("Kort vadderad vattenavvisande täckjacka")["rain_ok"] is True
    assert infer("Regular fit-byxa i bomull med pressveck")["formality"] == 4


@pytest.mark.parametrize(
    ("text", "colour"),
    [("Piké - beige", "beige"), ("ice grey", "light grey"), ("Ecru", "off-white"), ("svart", "black"),
     ("marinblå", "navy"), ("off white", "off-white"), ("nothing here", None)],
)
def test_colours(text, colour):
    assert canonical_colour(text) == colour
