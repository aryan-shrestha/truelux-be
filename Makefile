.DEFAULT_GOAL := help
DJANGO_SETTINGS_MODULE ?= config.settings.local
MANAGE := uv run python manage.py

.PHONY: help install run test lint format typecheck migrate makemigrations seed reseed seed-staff shell superuser check

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

shell: ## Open the Django shell
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) shell

superuser: ## Create a superuser
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) createsuperuser

check: ## Run Django system checks
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) $(MANAGE) check
