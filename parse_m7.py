#!/usr/bin/env python3
"""
parse_m7.py  —  Stage 1
Parses a Crossfire server m7 CSV dump into a JSON array of recipe dicts.

New CSV format (one header row):
  name,index,num_ingreds,chance,skill,difficulty,exp,cauldron,yield,
  ingredients,ingred_price,result_price

Ingredients field: a quoted comma-separated string where each item is
  [count ]name(object_id)
  e.g. "7 water(3829),pile of salt(1139),3 ruby(2193)"

Usage:
    python3 parse_m7.py [m7.txt] [all.json]
"""

import csv
import sys
import json
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Name normalisation
# The new format retains meaningful underscores and _N suffixes in names
# (mushroom_1, mushroom_2, raw_amethyst_flawless_beauty, etc.) so we only
# apply light cleaning: replace remaining underscores with spaces and
# capitalise, but preserve intentional _N game-item suffixes.
# ---------------------------------------------------------------------------

# Prefix substitutions (applied before general underscore replacement)
_PREFIX_SUBS = [
    (r'^phil_oil\b',   'bottle of philosophical oil'),
    (r'^phil_',        'pile of philosophical '),
    (r'^potion_generic\b', 'potion'),
    (r'^potion_',      'potion of '),
    (r'^dust_generic\b',   'dust'),
    (r'^dust_',        'dust of '),
    (r'^balm_generic\b',   'balm'),
    (r'^balm_',        'balm of '),
    (r'^figurine_generic\b', 'figurine'),
    (r'^figurine_',    'figurine of '),
    (r'^talisman_',    'talisman '),
    (r'^holy_symbol\b', 'holy symbol'),
    (r'^fix_mercury\b', 'mercury'),
    (r'^true_lead\b',  'block of true lead'),
    (r'^major_potion_restoration\b', 'major potion of restoration'),
    (r'^medium_potion_restoration\b', 'medium potion of restoration'),
    (r'^minor_potion_restoration\b',  'minor potion of restoration'),
    (r'^potion_shielding\b', 'potion of shielding'),
    (r'^potion_heroism\b',   'potion of heroism'),
    (r'^potion_cold\b',      'potion of cold'),
    (r'^potion_fire\b',      'potion of fire'),
    (r'^dragon_steak_cooked\b', 'cooked dragon steak'),
    (r'^stew_veg\b',    'vegetable stew'),
    (r'^stew_fish\b',   'fish stew'),
    (r'^stew_mushroom\b', 'mushroom stew'),
    (r'^stew_meat\b',   'meat stew'),
]

def normalise_name(raw: str) -> str:
    name = raw.strip()
    for pattern, repl in _PREFIX_SUBS:
        new = re.sub(pattern, repl, name, flags=re.IGNORECASE)
        if new != name:
            name = new
            break
    # Replace remaining underscores with spaces
    name = name.replace('_', ' ')
    # Collapse multiple spaces
    name = re.sub(r' {2,}', ' ', name).strip()
    # Capitalise first letter only (preserve internal caps like "Sorig", "Ruggilli")
    if name:
        name = name[0].upper() + name[1:]
    return name


# ---------------------------------------------------------------------------
# Ingredient parser
# Each item: [count ]name(object_id)
# ---------------------------------------------------------------------------
INGRED_RE = re.compile(r'^(\d+)\s+(.+?)\(\d+\)\s*$|^(.+?)\(\d+\)\s*$')

def parse_ingredients(raw: str) -> list[dict]:
    """Parse the ingredients CSV field into a list of {name, count} dicts."""
    result = []
    # The field may be quoted by the CSV reader already stripped; split on ','
    # but must be careful — names can contain commas? No: the format uses
    # the object_id parentheses as delimiters, so we split on '),' boundaries.
    # Use a simple regex split: find each "optional_count name(id)" token.
    tokens = re.findall(r'(\d*\s*[^,]+?\(\d+\))', raw)
    for token in tokens:
        token = token.strip()
        m = re.match(r'^(\d+)\s+(.+?)\(\d+\)\s*$', token)
        if m:
            count = int(m.group(1))
            name  = m.group(2).strip()
        else:
            m2 = re.match(r'^(.+?)\(\d+\)\s*$', token)
            if m2:
                count = 1
                name  = m2.group(1).strip()
            else:
                continue
        # ucfirst
        name = name[0].upper() + name[1:] if name else name
        result.append({'name': name, 'count': count})
    result.sort(key=lambda x: x['count'])
    return result


# ---------------------------------------------------------------------------
# Deduplication fingerprint
# ---------------------------------------------------------------------------
def ingredient_fingerprint(ingreds: list[dict]) -> str:
    return ''.join(f"{i['count']:02d}{i['name']}" for i in ingreds)


# ---------------------------------------------------------------------------
# Main parse
# ---------------------------------------------------------------------------
def parse_m7(path: Path) -> list[dict]:
    seen_fps: set[str] = set()
    skip_count = 0
    all_recipes: list[dict] = []

    with open(path, newline='', encoding='utf-8', errors='replace') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            name       = normalise_name(row['name'])
            index      = int(row['index'])
            chance     = int(row['chance'])
            difficulty = int(row['difficulty'])
            exp        = int(row['exp'])
            skill      = row['skill'] if row['skill'] != '(null)' else None
            cauldron   = row['cauldron'] if row['cauldron'] != '(null)' else None
            recipe_yield = int(row['yield'])
            ingred_price  = int(row['ingred_price'])
            result_price  = int(row['result_price'])

            ingreds = parse_ingredients(row['ingredients'])
            fp = ingredient_fingerprint(ingreds)

            if fp in seen_fps:
                skip_count += 1
                print(f"  Skipping duplicate: '{name}'", file=sys.stderr)
                continue
            seen_fps.add(fp)

            recipe: dict = {
                'name':   name,
                'index':  index,
                'chance': chance,
            }
            if skill:
                recipe['skill'] = skill
            if difficulty != 0:
                recipe['Difficulty'] = difficulty
            if exp != 0:
                recipe['Exp'] = exp
            if cauldron:
                recipe['Cauldron'] = cauldron
            if recipe_yield != 0:
                recipe['yield'] = recipe_yield
            if ingred_price >= 0:
                recipe['ingred_price'] = ingred_price
            if result_price > 0:
                recipe['result_price'] = result_price
            if ingreds:
                recipe['Ingred'] = ingreds

            all_recipes.append(recipe)

    print(
        f"  Parsed {len(all_recipes)} recipes  ({skip_count} duplicates skipped)",
        file=sys.stderr,
    )
    all_recipes.sort(key=lambda r: r['name'].lower())
    return all_recipes


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('m7.txt')
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('all.json')

    if not src.exists():
        sys.exit(f"ERROR: '{src}' not found.")

    print(f"Parsing {src} …", file=sys.stderr)
    recipes = parse_m7(src)
    dst.write_text(json.dumps(recipes, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"Written → {dst}", file=sys.stderr)


if __name__ == '__main__':
    main()
