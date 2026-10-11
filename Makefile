# sportsticker developer and deploy shortcuts. Run `make` or `make help`.
#
# PY      python used for local targets (activate your venv, or override:
#         make PY=.venv/bin/python dev)
# PI      Raspberry Pi to deploy to over SSH
# TIMEOUT `timeout` binary used by `profile` (macOS: brew install coreutils,
#         then make profile TIMEOUT=gtimeout)

PY ?= python3
PI ?= charlie@ticker.local
TIMEOUT ?= timeout
LEAGUES ?=
OUT ?= snapshots/fixtures-$(shell date +%Y-%m-%d)

.DEFAULT_GOAL := help
.PHONY: help install dev dev-replay snapshot site logos fixtures test lint format \
	enclosure enclosure-check \
	check-config profile deploy logs

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-14s %s\n", $$1, $$2}'

install: ## Install the package with dev and emulator extras (editable)
	$(PY) -m pip install -e '.[dev,emulator]'

dev: ## Run on the emulator with live ESPN data (http://localhost:8888)
	$(PY) -m sportsticker run --config config.yaml --backend emulator

dev-replay: ## Run on the emulator with recorded games and simulated scoring
	$(PY) -m sportsticker run --backend emulator --replay --fake-live

snapshot: ## Render every slide to snapshots/ (live data, with site/gallery)
	$(PY) -m sportsticker snapshot --out snapshots --site

site: ## Build the public-page snapshot into site/ (no logos)
	$(PY) -m sportsticker snapshot --no-logos --site --out site

logos: ## Pre-fetch team logos into the cache (LEAGUES=nfl,nba to limit)
	$(PY) -m sportsticker logos $(if $(LEAGUES),--leagues $(LEAGUES))

fixtures: ## Save current ESPN scoreboards as replay fixtures (OUT=dir)
	$(PY) -m sportsticker fixtures --out $(OUT)

test: ## Run the test suite
	$(PY) -m pytest -q

lint: ## Check lint and formatting (ruff)
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format: ## Apply ruff fixes and formatting
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

enclosure: ## Rebuild the enclosure STLs and preview PNGs (needs openscad)
	enclosure/export.sh
	OUT=stl/two_panel enclosure/export.sh -D panels=2
	enclosure/render.sh

enclosure-check: ## Run the enclosure collision checks (needs openscad)
	enclosure/check.sh

check-config: ## Validate config.yaml and exit
	$(PY) -m sportsticker run --config config.yaml --check-config

profile: ## Profile the replay loop headless for 60 seconds
	-$(TIMEOUT) -s INT 60 $(PY) -m sportsticker run --replay --fake-live --profile --backend headless

deploy: ## Pull, reinstall and restart the service on the Pi (PI=user@host)
	ssh $(PI) 'cd ~/sportsticker && git pull --ff-only && sudo /home/charlie/ticker-venv/bin/pip install -q -e . && sudo systemctl restart ticker && systemctl --no-pager status ticker | head -5'

logs: ## Follow the service log on the Pi
	ssh $(PI) 'journalctl -u ticker -f'
