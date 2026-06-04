#!/usr/bin/env python3
"""
build_site.py  —  Stage 3
Reads indexed.json, renders Jinja2 templates, and writes the static site.
Replaces buildSite.pl.

Requires:
    apt install python3-jinja2 python3-graphviz graphviz

Usage:
    python3 build_site.py [indexed.json] [output_dir]

Options:
    --no-graphs     Skip graphviz rendering (fast mode, text-only pages)
    --force         Regenerate all pages even if up to date
"""

import sys
import json
import re
import shutil
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

try:
    import jinja2
except ImportError:
    sys.exit("ERROR: jinja2 not found.  Run: sudo apt install python3-jinja2")


# ---------------------------------------------------------------------------
# Graphviz DOT builder
# ---------------------------------------------------------------------------

def _dot_id(name_hash: str) -> str:
    """Ensure the DOT node ID is a valid identifier."""
    return re.sub(r'[^A-Za-z0-9_]', '_', name_hash)


def build_dot(recipe: dict, recipes: list[dict], name_index: dict) -> str:
    """
    Build a DOT graph string for one recipe, mirroring the plotThis /
    plotUsedBy logic in buildSite.pl.
    Returns the DOT source as a string.
    """
    nodes: dict[str, dict] = {}   # nameHash → {label, colour, url}
    edges: list[tuple]     = []   # (from_hash, to_hash, count_label)

    trap1: set[int] = set()
    trap2: set[int] = set()

    def plot_this(idx: int, plot_all: bool) -> None:
        if idx in trap1:
            return
        trap1.add(idx)
        item = recipes[idx]
        nh   = item['nameHash']
        nodes[nh] = dict(label=item['name'], colour='#4e9af1',
                         url=f"{nh}.html")

        sub: list[int] = []
        for ing in item.get('Ingred', []):
            ing_nh = ing['nameHash']
            sub_idx = name_index.get(ing['name'])
            if sub_idx is not None:
                sub.append(sub_idx)
            if ing_nh not in nodes:
                nodes[ing_nh] = dict(label=ing['name'], colour='#4caf7d',
                                     url=f"{ing_nh}.html")
            edges.append((ing_nh, nh, str(ing['count']) if ing['count'] > 1 else ''))

        for si in sub:
            plot_this(si, False)

        if plot_all:
            for used_idx in item.get('usedBy', []):
                plot_used_by(nh, used_idx)

    def plot_used_by(parent_nh: str, idx: int) -> None:
        if idx in trap2:
            return
        trap2.add(idx)
        item = recipes[idx]
        nh   = item['nameHash']
        nodes[nh] = dict(label=item['name'], colour='#b06af4',
                         url=f"{nh}.html")
        edges.append((parent_nh, nh, ''))
        for used_idx in item.get('usedBy', []):
            plot_used_by(nh, used_idx)

    plot_this(recipe['index'], True)

    lines = [
        'digraph recipes {',
        '  bgcolor="transparent";',
        '  rankdir=LR;',
        '  splines=true;',
        '  node [fontname="sans-serif" fontsize=11 style=filled '
        '        fillcolor="#1a1f2e" fontcolor="#d4daf0" color="#2e3550"];',
        '  edge [fontname="sans-serif" fontsize=9 color="#6b7494" fontcolor="#6b7494"];',
    ]
    for nh, attr in nodes.items():
        nid   = _dot_id(nh)
        col   = attr['colour']
        label = attr['label'].replace('"', '\\"')
        url   = attr.get('url', '')
        url_part = f' URL="{url}"' if url else ''
        lines.append(
            f'  {nid} [label="{label}" color="{col}"{url_part}];'
        )
    for frm, to, lbl in edges:
        fid = _dot_id(frm)
        tid = _dot_id(to)
        lbl_part = f' [label="{lbl}"]' if lbl else ''
        lines.append(f'  {fid} -> {tid}{lbl_part};')
    lines.append('}')
    return '\n'.join(lines)


def render_svg(dot_source: str) -> str | None:
    """Run graphviz dot and return SVG string, or None on failure."""
    try:
        result = subprocess.run(
            ['dot', '-Tsvg'],
            input=dot_source,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f"  dot error: {result.stderr[:200]}", file=sys.stderr)
            return None
        svg = result.stdout
        # Strip the XML declaration and DOCTYPE so it embeds cleanly in HTML
        svg = re.sub(r'<\?xml[^>]+\?>', '', svg)
        svg = re.sub(r'<!DOCTYPE[^>]+>', '', svg)
        # Remove fixed width/height so CSS can control sizing
        svg = re.sub(r'\s+width="[^"]+"', '', svg)
        svg = re.sub(r'\s+height="[^"]+"', '', svg)
        return svg.strip()
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        print("  dot timed out", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Site builder
# ---------------------------------------------------------------------------

def build_site(
    indexed_path: Path,
    output_dir: Path,
    templates_dir: Path,
    no_graphs: bool = False,
    force: bool = False,
) -> None:

    # ── Load data ────────────────────────────────────────────────
    payload    = json.loads(indexed_path.read_text(encoding='utf-8'))
    recipes    = payload['recipes']
    name_index = payload['name_index']

    # ── Jinja2 env ───────────────────────────────────────────────
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        autoescape=jinja2.select_autoescape(['html']),
    )

    # ── Output directory ─────────────────────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Check graphviz availability once ─────────────────────────
    has_graphviz = (not no_graphs) and (shutil.which('dot') is not None)
    if not no_graphs and not has_graphviz:
        print("WARNING: 'dot' not found — graphs will be skipped.",
              file=sys.stderr)
        print("         Install with: sudo apt install graphviz", file=sys.stderr)

    # ── Render individual recipe pages ───────────────────────────
    recipe_tmpl = env.get_template('recipe.html.j2')
    total = len(recipes)

    for i, recipe in enumerate(recipes):
        html_path = output_dir / f"{recipe['nameHash']}.html"

        if not force and html_path.exists():
            continue

        # Populate ancestors list for "used by" section
        if 'usedBy' in recipe:
            recipe['ancestors'] = [
                {'name': recipes[j]['name'], 'nameHash': recipes[j]['nameHash']}
                for j in recipe['usedBy']
                if j < len(recipes)
            ]

        # Build inline SVG graph
        svg_content = ''
        if has_graphviz and recipe.get('Ingred'):
            dot_src     = build_dot(recipe, recipes, name_index)
            svg_content = render_svg(dot_src) or ''

        html = recipe_tmpl.render(
            recipe=recipe,
            svg_content=svg_content,
        )
        html_path.write_text(html, encoding='utf-8')

        if (i + 1) % 50 == 0 or (i + 1) == total:
            print(f"  Pages: {i+1}/{total}", file=sys.stderr)

    # ── Index pages (all four sort views use the same template) ──
    index_tmpl = env.get_template('index.html.j2')

    full_recipes = [r for r in recipes if r.get('Ingred')]

    def write_index(filename, items, sort_label, default_col, default_dir):
        path = output_dir / filename
        html = index_tmpl.render(
            recipes=items,
            sort_label=sort_label,
            default_sort_col=default_col,
            default_sort_dir=default_dir,
        )
        path.write_text(html, encoding='utf-8')
        print(f"  Index → {path.name}", file=sys.stderr)

    # A–Z
    az = sorted(full_recipes, key=lambda r: r['name'].lower())
    write_index('index.html', az, 'All Recipes (A–Z)', 3, 'asc')

    # By Exp
    by_exp = sorted(
        [r for r in full_recipes if 'Exp' in r],
        key=lambda r: (r['Exp'], r['name']),
    )
    write_index('by_exp.html', by_exp, 'Recipes by Experience', 0, 'asc')

    # By Difficulty
    by_diff = sorted(
        [r for r in full_recipes if 'Difficulty' in r],
        key=lambda r: (r['Difficulty'], r.get('Exp', 0), r['name']),
    )
    write_index('by_difficulty.html', by_diff, 'Recipes by Difficulty', 1, 'asc')

    # By Skill
    by_skill = sorted(
        [r for r in full_recipes if 'skill' in r],
        key=lambda r: (r['skill'], r['name']),
    )
    write_index('by_skill.html', by_skill, 'Recipes by Skill', 2, 'asc')

    print(f"\nDone. Site written to: {output_dir}/", file=sys.stderr)
    print(f"Open: {output_dir}/index.html", file=sys.stderr)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description='Build the Crossfire recipe site.')
    parser.add_argument('indexed',    nargs='?', default='indexed.json',
                        help='Path to indexed.json  (default: indexed.json)')
    parser.add_argument('output_dir', nargs='?', default='site',
                        help='Output directory       (default: site/)')
    parser.add_argument('--no-graphs', action='store_true',
                        help='Skip graphviz graph rendering')
    parser.add_argument('--force', action='store_true',
                        help='Regenerate all pages (ignore existing files)')
    args = parser.parse_args()

    indexed_path  = Path(args.indexed)
    output_dir    = Path(args.output_dir)
    templates_dir = Path(__file__).parent / 'templates'

    if not indexed_path.exists():
        sys.exit(f"ERROR: '{indexed_path}' not found.")
    if not templates_dir.exists():
        sys.exit(f"ERROR: templates directory '{templates_dir}' not found.")

    build_site(
        indexed_path  = indexed_path,
        output_dir    = output_dir,
        templates_dir = templates_dir,
        no_graphs     = args.no_graphs,
        force         = args.force,
    )


if __name__ == '__main__':
    main()
