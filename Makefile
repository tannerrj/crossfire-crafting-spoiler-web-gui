# Crossfire recipe site builder
# Requires: python3  python3-jinja2  graphviz
#
# Targets:
#   make           — full build (all three stages)
#   make parse     — stage 1 only: m7.txt → all.json
#   make index     — stage 2 only: all.json → indexed.json
#   make site      — stage 3 only: indexed.json → site/
#   make fast      — full build, skip graph images
#   make clean     — remove intermediate + output files
#   make distclean — clean + remove m7.txt

PYTHON   := python3
M7       := m7.txt
ALL_JSON := all.json
IDX_JSON := indexed.json
SITE_DIR := site

.PHONY: all parse index site fast clean distclean

all: $(SITE_DIR)/index.html

# ── Stage 1 ──────────────────────────────────────────────────
$(ALL_JSON): $(M7) parse_m7.py
	$(PYTHON) parse_m7.py $(M7) $(ALL_JSON)

parse: $(ALL_JSON)

# ── Stage 2 ──────────────────────────────────────────────────
$(IDX_JSON): $(ALL_JSON) index_recipes.py
	$(PYTHON) index_recipes.py $(ALL_JSON) $(IDX_JSON)

index: $(IDX_JSON)

# ── Stage 3 ──────────────────────────────────────────────────
$(SITE_DIR)/index.html: $(IDX_JSON) build_site.py templates/*.html.j2
	$(PYTHON) build_site.py $(IDX_JSON) $(SITE_DIR)

site: $(SITE_DIR)/index.html

# ── Fast build (no graphs) ────────────────────────────────────
fast: $(IDX_JSON)
	$(PYTHON) build_site.py --no-graphs $(IDX_JSON) $(SITE_DIR)

# ── Force full rebuild ────────────────────────────────────────
rebuild: $(IDX_JSON)
	$(PYTHON) build_site.py --force $(IDX_JSON) $(SITE_DIR)

# ── Clean ─────────────────────────────────────────────────────
clean:
	rm -rf $(ALL_JSON) $(IDX_JSON) $(SITE_DIR)

distclean: clean
	rm -f $(M7)
