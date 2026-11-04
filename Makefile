.DEFAULT_GOAL := help
DJANGO_SETTINGS_MODULE ?= config.settings.dev
MANAGE := uv run python manage.py

.PHONY: help install run test lint format typecheck migrate makemigrations seed reseed seed-staff catalogue-template catalogue-export catalogue-import shell superuser check deploy

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Sync the virtualenv from uv.lock
	uv sync

run: ## Start the development server
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) runserver

test: ## Run the test suite with coverage
	uv run pytest

lint: ## Check formatting and lint rules
	uv run ruff format --check .
	uv run ruff check .

format: ## Apply formatting and safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .

typecheck: ## Run mypy
	uv run mypy .

migrate: ## Apply migrations and create the cache table over the direct connection
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) migrate --database=direct
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) createcachetable --database=direct

makemigrations: ## Generate migrations
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) makemigrations

seed: ## Populate a development catalogue and order history (DEBUG only)
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) seed_demo
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) seed_orders

reseed: ## Delete the seeded rows and seed again. Orders go first: they PROTECT the catalogue
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) seed_orders --flush-only
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) seed_demo --flush
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) seed_orders

seed-staff: ## Create or reset the demo staff login from DEMO_STAFF_EMAIL (DEBUG only)
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) seed_staff

catalogue-template: OUT ?= catalogue-template.xlsx
catalogue-template: ## Write the blank catalogue workbook to OUT (default catalogue-template.xlsx)
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) export_catalogue "$(OUT)" --template

catalogue-export: OUT ?= catalogue-export.xlsx
catalogue-export: ## Write the database's catalogue to OUT (default catalogue-export.xlsx)
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) export_catalogue "$(OUT)"

catalogue-import: ## Load FILE=<workbook> [IMAGES=<folder>] [ARGS="--dry-run --replace-images"]
	@test -n "$(FILE)" || (echo 'Usage: make catalogue-import FILE=<workbook.xlsx> [IMAGES=<folder>] [ARGS=--dry-run]' && exit 2)
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) import_catalogue "$(FILE)" $(if $(IMAGES),--images "$(IMAGES)") $(ARGS)

shell: ## Open the Django shell
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) shell

superuser: ## Create a superuser
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) createsuperuser

check: ## Run Django system checks
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) check

# On the cPanel host only (docs/features/deployment.md). Passenger runs the virtualenv
# cPanel's "Setup Python App" created, so uv syncs into that active environment
# rather than into .venv, and every command after the sync must not re-sync it.
DEPLOY_MANAGE := DJANGO_SETTINGS_MODULE=config.settings.production uv run --active --no-sync python manage.py

deploy: ## On the cPanel host, inside the app's virtualenv: install, migrate, seed, collect static, restart
	@test -n "$$VIRTUAL_ENV" -a "$$VIRTUAL_ENV" != "$(CURDIR)/.venv" || (echo 'Activate the cPanel app virtualenv first: source ~/virtualenv/<app root>/3.12/bin/activate' && exit 2)
	uv sync --active --frozen --no-dev
	$(DEPLOY_MANAGE) migrate --database=direct
	$(DEPLOY_MANAGE) createcachetable --database=direct
	$(DEPLOY_MANAGE) seed_staff --deploy
	$(DEPLOY_MANAGE) seed_demo --deploy
	$(DEPLOY_MANAGE) seed_orders --deploy
	$(DEPLOY_MANAGE) collectstatic --noinput
	mkdir -p tmp && touch tmp/restart.txt
