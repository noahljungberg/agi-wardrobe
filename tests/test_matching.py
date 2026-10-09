from wardrobe.catalog import Catalog
from wardrobe.matching import resolve, search


def test_resolve_phrases(demo_dir):
    items = Catalog(demo_dir).items()
    assert resolve(items, "beige mango cords").item.id == "mango-corduroy-trousers-regular-fit-beige"
    # alias written in item.yaml wins over the identical brown pair
    assert resolve(items, "manchester trousers").item.id == "mango-corduroy-trousers-regular-fit-beige"
    assert resolve(items, "my black coat").item.id == "mango-wool-coat-with-high-collar-black"
    assert resolve(items, "navy knit").item.id == "uniqlo-merino-crewneck-sweater-navy"
    assert resolve(items, "nubikk-leather-sneakers-white").item.id == "nubikk-leather-sneakers-white"


def test_ambiguous_gives_candidates(demo_dir):
    items = Catalog(demo_dir).items()
    r = resolve(items, "corduroy trousers")
    assert r.item is None
    assert {c.id for c in r.candidates} >= {"mango-corduroy-trousers-regular-fit-beige", "mango-corduroy-trousers-regular-fit-brown"}


def test_no_match(demo_dir):
    items = Catalog(demo_dir).items()
    assert resolve(items, "tuxedo").item is None
    assert search(items, "") == []
