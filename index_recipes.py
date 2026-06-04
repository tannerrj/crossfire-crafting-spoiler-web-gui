#!/usr/bin/env python3
"""
index_recipes.py  —  Stage 2
Builds forward and reverse indexes from all.json → indexed.json.
Replaces preIndexer.pl.

Each recipe gains:
  index      — integer position in the master list
  nameHash   — filesystem/URL-safe version of the name
  usedBy     — list of recipe indexes that use this item as an ingredient
  minimum    — smallest ingredient count across all recipes that use this item

Ingredient-only items (not themselves recipes) are also added to the list
so that every ingredient has a page.

Usage:
    python3 index_recipes.py [all.json] [indexed.json]
"""

import sys
import json
import re
from pathlib import Path


def make_name_hash(name: str) -> str:
    """Convert a recipe name to a safe ASCII identifier (mirrors s/[-'\\s]/_/g)."""
    return re.sub(r"[-'\s]", '_', name)


def build_index(recipes: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """
    First pass: add every recipe to the master list, handling duplicate names
    by appending a counter suffix (mirrors preIndexer.pl logic).
    Returns (master_list, name_to_index).
    """
    master: list[dict]      = []
    name_to_idx: dict[str, int] = {}

    for recipe in recipes:
        name = recipe['name']

        if name not in name_to_idx:
            recipe['index'] = len(master)
            master.append(recipe)
            name_to_idx[name] = recipe['index']
        else:
            # deduplicate by appending " 01", " 02" …
            counter = 1
            candidate = f"{name} {counter:02d}"
            while candidate in name_to_idx:
                counter += 1
                candidate = f"{name} {counter:02d}"
            recipe['name']  = candidate
            recipe['index'] = len(master)
            master.append(recipe)
            name_to_idx[candidate] = recipe['index']

    return master, name_to_idx


def add_ingredient_only_entries(
    master: list[dict],
    name_to_idx: dict[str, int],
) -> None:
    """
    Second pass: any ingredient that doesn't already have its own recipe entry
    gets a stub entry so it can have a page in the site.
    Mutates master and name_to_idx in place.
    """
    # snapshot length — we'll iterate over entries that existed before this pass
    existing_count = len(master)

    for i in range(existing_count):
        recipe = master[i]
        for ingred in recipe.get('Ingred', []):
            iname = ingred['name']
            if iname not in name_to_idx:
                stub = {'name': iname, 'index': len(master)}
                master.append(stub)
                name_to_idx[iname] = stub['index']


def build_reverse_index(
    master: list[dict],
    name_to_idx: dict[str, int],
) -> None:
    """
    Third pass: populate nameHash on every entry, and usedBy / minimum on
    ingredients.  Mutates master in place.
    """
    # nameHash for every entry
    for recipe in master:
        recipe['nameHash'] = make_name_hash(recipe['name'])

    # usedBy links + nameHash on each ingredient ref
    for recipe in master:
        for ingred in recipe.get('Ingred', []):
            ingred['nameHash'] = make_name_hash(ingred['name'])
            idx = name_to_idx.get(ingred['name'])
            if idx is not None:
                master[idx].setdefault('usedBy', [])
                master[idx]['usedBy'].append(recipe['index'])

    # minimum: smallest count across all recipes that use this ingredient
    for entry in master:
        if 'usedBy' not in entry:
            continue
        min_count = 99999
        for user_idx in entry['usedBy']:
            user = master[user_idx]
            for ingred in user.get('Ingred', []):
                if ingred['name'] == entry['name']:
                    min_count = min(min_count, ingred['count'])
        entry['minimum'] = min_count


def main() -> None:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('all.json')
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('indexed.json')

    if not src.exists():
        sys.exit(f"ERROR: '{src}' not found.")

    print(f"Indexing {src} …", file=sys.stderr)
    recipes = json.loads(src.read_text(encoding='utf-8'))

    master, name_to_idx = build_index(recipes)
    add_ingredient_only_entries(master, name_to_idx)
    build_reverse_index(master, name_to_idx)

    # Serialise both the master list and the name→index map
    payload = {
        'recipes':    master,
        'name_index': name_to_idx,
    }
    dst.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')
    print(
        f"Written → {dst}  "
        f"({len(master)} entries, {len(name_to_idx)} index keys)",
        file=sys.stderr,
    )


if __name__ == '__main__':
    main()
