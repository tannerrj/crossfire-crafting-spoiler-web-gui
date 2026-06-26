# CLAUDE.md — Crossfire Crafting Spoiler Web GUI

Developer guide for AI assistants and contributors working on this codebase.

---

## What this project does

Generates a static HTML reference site for crafting recipes in the
[Crossfire](https://crossfire.real-time.com/) MMORPG. The source data is a
server dump produced with the `-m7` switch.

The pipeline has three stages:

```
m7.txt  →  parse_m7.py  →  all.json
                               ↓
                       index_recipes.py  →  indexed.json
                                                 ↓
                                         build_site.py  →  site/
```

The output is a self-contained flat directory of HTML files that can be served
from any static host or browsed directly from disk (`file://`).

---

## Repository layout

```
crossfire-m7/
├── m7.txt                  Source data (server dump, 521 lines)
├── parse_m7.py             Stage 1: CSV parser
├── index_recipes.py        Stage 2: forward/reverse indexer
├── build_site.py           Stage 3: site builder
├── Makefile                Orchestrates all three stages
├── templates/
│   ├── base.html.j2        Shared layout, nav, and CSS variables
│   ├── index.html.j2       Sortable/searchable recipe list
│   └── recipe.html.j2      Individual recipe page + SVG graph
├── intro.txt               Original author's note (Mark Munro, 2016)
├── README.md               GitHub-facing project description
├── CLAUDE.md               This file
├── .gitignore
├── all.json                Stage 1 output  (generated, not committed)
├── indexed.json            Stage 2 output  (generated, not committed)
└── site/                   Final HTML site (generated, not committed)
```

Generated files (`all.json`, `indexed.json`, `site/`) are listed in `.gitignore` and should not be committed.

---

## Quick start

```bash
# Install dependencies (Ubuntu Noble / Debian)
sudo apt install python3 python3-jinja2 graphviz

# Full build
cd crossfire-m7
make

# Fast build — skips graphviz SVG rendering, much quicker
make fast

# Force a full rebuild of all HTML pages (ignores existing files)
make rebuild

# Wipe all generated artefacts
make clean
```

You can also run each stage individually:

```bash
python3 parse_m7.py   [m7.txt]      [all.json]
python3 index_recipes.py [all.json] [indexed.json]
python3 build_site.py [indexed.json] [site/] [--no-graphs] [--force]
```

All paths are optional; the defaults match the Makefile.

---

## Dependencies

| Package | apt/dnf name | Purpose |
|---|---|---|
| Python 3.12+ | `python3` | Runtime |
| Jinja2 | `python3-jinja2` | HTML templating |
| graphviz (binary) | `graphviz` | Renders `dot` → SVG |

**Ubuntu / Debian / Linux Mint**
```bash
sudo apt install python3 python3-jinja2 graphviz
```

**Fedora**
```bash
sudo dnf install python3 python3-jinja2 graphviz
```

No pip / virtualenv needed — all packages are available in the standard
distribution repos.

`graphviz` is optional. Without it the site builds fine; recipe pages just
omit the dependency graph. `build_site.py --no-graphs` skips it explicitly.

---

## Data model

### Input format — `m7.txt`

A CSV file with a header row:

```
name,index,num_ingreds,chance,skill,difficulty,exp,cauldron,yield,ingredients,ingred_price,result_price
```

The `ingredients` field is a quoted comma-separated string where each item is
`[count ]name(object_id)`, e.g.:

```
"7 water(3829),pile of salt(1139),3 ruby(2193)"
```

Rows with `skill` or `cauldron` of `(null)` are transformation/splitting
recipes with no associated crafting skill.

### Stage 1 output — `all.json`

An array of recipe objects, sorted A–Z by name. Each object has:

```json
{
  "name":         "Water of the wise",
  "index":        3829,
  "chance":       30,
  "skill":        "alchemy",
  "Difficulty":   8,
  "Exp":          1000,
  "Cauldron":     "cauldron",
  "yield":        7,
  "ingred_price": 140,
  "result_price": 200,
  "Ingred": [
    { "name": "Water", "count": 7 }
  ]
}
```

Fields with zero/null values are omitted (`skill`, `Cauldron`, `Difficulty`,
`Exp`, `yield`, `result_price`). `Ingred` is always sorted by `count`
ascending. Duplicate recipes (identical ingredient fingerprint) are dropped
with a stderr warning; 77 are skipped from the current dataset.

### Stage 2 output — `indexed.json`

A JSON object with two keys:

```json
{
  "recipes":    [ /* enriched recipe objects */ ],
  "name_index": { "Water of the wise": 0, … }
}
```

Each recipe gains:

| Field | Type | Description |
|---|---|---|
| `index` | int | Position in `recipes` array |
| `nameHash` | str | URL/filename-safe name (`[-'\s]` → `_`) |
| `usedBy` | int[] | Indexes of recipes that use this item as an ingredient |
| `minimum` | int | Smallest ingredient count across all `usedBy` recipes |

Ingredient-only items (things used in recipes but not themselves craftable)
get stub entries with only `name`, `index`, `nameHash`, `usedBy`, and
`minimum`. They have no `Ingred` key. The site generates a page for them too.

**Current dataset sizes:** 442 full recipes, 268 ingredient stubs = 710 total
entries, producing 886 HTML pages (plus 4 index pages). The page count exceeds
the entry count because case-collision nameHashes (see Known Quirks) produce
two separate files for 24 name pairs. Skills: `alchemy`, `bowyer`, `jeweler`,
`smithery`, `thaumaturgy`, `woodsman`. Cauldrons: `cauldron`, `forge`,
`jeweler_bench`, `stove`, `tanbench`, `thaumaturg_desk`, `workbench`.
Exp range: 100–500,000. Difficulty range: -35–50 (negative difficulties
exist for some smelting recipes).

### Recipe page context

`build_site.py` adds one more field before rendering:

| Field | Type | Description |
|---|---|---|
| `ancestors` | list | `[{name, nameHash}]` built from `usedBy` indexes |

The template also computes and displays a **Profit** row (`result_price -
ingred_price`) coloured green when positive, red when negative.

---

## Templates

Templates live in `templates/` and use Jinja2 syntax. All three extend
`base.html.j2` via `{% extends %}`.

### `base.html.j2`

Contains the full `<head>`, CSS custom properties (dark theme colour palette),
sticky header, and nav links. Blocks exposed: `title`, `extra_head`, `content`.

The colour palette lives entirely in `:root` CSS variables — change colours
here, nowhere else:

```css
:root {
  --bg, --surface, --surface2, --border,
  --accent, --accent2, --text, --text-muted,
  --green, --purple, --gold, --red
}
```

Skill badge colours are defined as `.badge-<skillname>` classes. Current
skills: `alchemy`, `bowyer`, `jeweler`, `smithery`, `thaumaturgy`, `woodsman`.
Add a new `.badge-<name>` class here if a new skill appears in a future dataset.

### `index.html.j2`

Renders the four index pages (`index.html`, `by_exp.html`, `by_difficulty.html`,
`by_skill.html`). All four use the same template; `build_site.py` passes
pre-sorted lists and the parameters `sort_label`, `default_sort_col` (int),
and `default_sort_dir` (`"asc"` | `"desc"`).

Client-side JS handles live filtering (`<input id="search">`) and
click-to-sort columns. No framework — plain vanilla JS in a self-contained
IIFE at the bottom of the template. The JS reads `data-name`,
`data-skill`, and `data-cauldron` attributes on each `<tr>`.

### `recipe.html.j2`

Two rendering paths controlled by `{% if recipe.Ingred is defined %}`:

- **Full recipe** — shows stat pills (Exp, Difficulty, Exp/Diff ratio),
  details table, ingredient list, "used by" list, and the inline SVG graph.
- **Ingredient stub** — shows a notice, "used by" list, and minimum quantity.

The `svg_content` variable holds the raw SVG string with the XML declaration
stripped. It is passed through Jinja2's `| safe` filter. If graphviz is
unavailable or `--no-graphs` is set, `svg_content` is an empty string and the
graph card is omitted entirely.

---

## Graph generation

`build_site.py` builds a DOT graph for each full recipe via `build_dot()`,
then renders it to SVG by shelling out to `dot -Tsvg` via `subprocess.run`.

Node colours in DOT source:

| Colour | Meaning |
|---|---|
| `#4e9af1` (blue) | The recipe being viewed |
| `#4caf7d` (green) | Ingredients |
| `#b06af4` (purple) | Recipes that use this item (`usedBy`) |

The raw SVG has its `width` and `height` attributes stripped so CSS controls
sizing. The graph card in `recipe.html.j2` constrains it to `max-height: 520px`.

SVG node labels are clickable links (`URL=` attribute in DOT → `xlink:href` in
SVG). This works when served over HTTP; it may not work from `file://` in some
browsers.

---

## Known quirks in the source data

**Case-collision nameHashes.** Some ingredient-only stubs and their recipe
counterparts produce nameHashes that differ only in case (e.g.
`Amulet_of_Aethereality` vs `amulet_of_aethereality`). Both get separate
pages. This affects 24 name pairs and is inherited from the source data.
Do not "fix" this without verifying cross-links still resolve.

**Duplicate recipes.** 77 entries share an identical ingredient fingerprint
with an earlier entry and are skipped in `parse_m7.py` with a stderr warning.

**Negative difficulties.** Some smelting recipes (e.g. `smallnugget`,
`ring`) have negative `difficulty` values (down to -35). These are stored as-is
and displayed correctly. The Exp/Diff ratio stat pill is suppressed when
`difficulty <= 0`.

**`(null)` skill and cauldron.** Seven rows have `skill=(null)` and
`cauldron=(null)`. These are item-splitting/transformation recipes (e.g.
`lead`, `zinc_filings`, `apple_eighth`). They are included in the site but
have no skill badge and no equipment row on their page.

**`fix_mercury` normalises to `mercury`.** The entry `fix_mercury` is renamed
to `mercury` by the prefix substitution table in `normalise_name()`. Since
a `mercury` entry also exists, `index_recipes.py` appends a counter suffix
to produce `mercury` and `mercury 01`. Both pages exist in the site.

**Name normalisation.** `parse_m7.py:normalise_name()` applies a prefix
substitution table then replaces remaining underscores with spaces. The new
CSV format preserves more meaningful names than the old tab-delimited format,
so the substitution table is shorter. If a future dataset introduces new
prefixes that produce ugly names, extend `_PREFIX_SUBS` in `parse_m7.py` —
it is the single source of truth for naming.

---

## Adding a new data source

To use a different or updated `m7.txt`:

1. Replace `m7.txt`.
2. `make clean && make` — all three stages will rerun.
3. Check stderr output from `parse_m7.py` for new duplicate warnings.
4. If new skills appear, add `.badge-<skillname>` CSS to `base.html.j2`
   and a Jinja2 condition in the badge macro in `index.html.j2` and
   `recipe.html.j2`.

---

## Extending the site

**Add a new index sort** (e.g. by yield): add a new `write_index()` call
in `build_site.py`, add a nav link in `base.html.j2`, and optionally adjust
the JS default sort in the new page's template call.

**Add a new field to recipe pages**: add it to the `info-table` block in
`recipe.html.j2`. Fields not present on a recipe are safely absent from the
dict — use `{% if recipe.fieldname is defined %}` guards.

**Change the theme**: edit the `:root` block in `base.html.j2` only.
All colours are CSS custom properties; nothing is hardcoded elsewhere in the
templates.

**Serve over HTTP**: any static file server works.
```bash
python3 -m http.server 8080 --directory site/
# → http://localhost:8080/index.html
```
SVG graph node links will work correctly over HTTP but may be blocked
by some browsers when opened via `file://`.
