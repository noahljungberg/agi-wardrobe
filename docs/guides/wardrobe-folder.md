# The wardrobe folder

The folder (`WARDROBE_DIR`) is the source of truth. Edit it by hand whenever you
like; the server notices changes within a couple of seconds.

```
wardrobe/
├── items/
│   ├── mango-corduroy-trousers-beige/
│   │   ├── item.yaml
│   │   ├── 1.jpg          ← main photo (the first file, in natural order)
│   │   └── 2.jpg          ← optional extra angles
│   └── levis-hilltop-jacket/
│       ├── item.yaml
│       └── 1.jpg
├── me/                    ← how you look (for the stylist)
│   ├── about.yaml
│   └── 1.jpg              ← first photo is shown next to suggestions
├── inbox/                 ← new photos waiting to become items
└── profile.yaml           ← about you (optional)
```

The folder name is the item's id. Photos can be `.jpg`, `.png`, `.webp` or
`.heic` (iPhone).

## item.yaml

Only `name` is needed. Anything you leave out is guessed from the name (English
or Swedish, e.g. "Manchesterbyxa", "Ullkappa"), and anything you write wins.

```yaml
name: Corduroy trousers, regular fit
brand: Mango
aliases: [beige cords, manchester trousers]   # what you call it
category: bottoms     # outerwear | tops | bottoms | shoes | accessories | other
type: trousers        # t-shirt, shirt, polo, knit, hoodie, cardigan, jeans, coat, puffer, sneakers, boots…
colour: beige
material: corduroy
warmth: 3             # 0 very light … 5 deep winter
formality: 3          # 1 gym … 5 suit
rain_ok: false        # handles rain (outerwear/shoes)
size: "42"
bought: 2026-01-23
price: 419
currency: SEK
source_url: https://shop.mango.com/...
status: owned         # owned | laundry (temporarily out) | retired (gone) | wishlist (want to buy)
favourite: true       # one you especially like; suggested a little more often
needs_review: true    # set by the importer; cleared when you or the assistant confirm
notes: ""
```

Tops are split into **base** layers (t-shirts, shirts, polos) and **mid** layers
(knits, hoodies, cardigans). This happens automatically from `type`.

## profile.yaml

```yaml
home: Linköping, Sweden    # fallback location
runs: neutral              # cold | neutral | warm (shifts how warm it dresses you)
style: >
  Clean, relaxed Scandinavian. Neutral colours, regular fits.
likes: [corduroy, knitwear]
dislikes: [skinny fits, logos]
```

## me/: how you look

Your colouring and build matter for styling: which colours flatter you near
your face, and which fits suit you. Save this once in the web UI's **Me**
tab, or just tell the assistant ("I have blonde hair and blue eyes").

```yaml
# me/about.yaml
hair: blonde
eyes: blue
skin: fair               # fair | light | medium | olive | tan | brown | deep
undertone: cool          # cool | neutral | warm (if you know it)
height_cm: 185
build: slim
fit_notes: regular fit, not skinny
notes: short beard
photo_in_suggestions: true   # send your first photo along with outfit suggestions
```

Photos of you go in `me/` as well: one face photo in daylight and one
full-length. They're only sent to ChatGPT/Claude inside wardrobe answers,
never through a public link. Set `photo_in_suggestions: false` to keep the
photo out of everyday suggestions (`about_me` still uses it when you ask).

## Adding things

| How | Good for |
|---|---|
| `uv run wardrobe import <link>…` or `--file links.txt` | Online purchases (Mango, Zalando, Levi's, …) |
| Tell the assistant "import these links: …" | Same, from your phone |
| Safari → Share → **Add to wardrobe** | Pages that block the importer |
| Photos → Share → **Add photo to wardrobe**, then "check my inbox" | Things without a link |
| Make a folder by hand | Anything |

Imported items get `needs_review: true`, and the assistant may confirm details
with you when one comes up.
