.PHONY: help install install-dev test lint format typecheck clean build dist tag-release run tui

PY ?= python3
VENV ?= .venv
PYTHON = $(VENV)/bin/python
PIP    = $(VENV)/bin/pip

help:  ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/python:
	$(PY) -m venv $(VENV)
	$(PIP) install --upgrade pip

install: $(VENV)/bin/python  ## Install the package in editable mode (runtime deps only)
	$(PIP) install -e .
	$(PYTHON) -m playwright install chromium

install-dev: $(VENV)/bin/python  ## Install runtime + dev deps and Playwright Chromium
	$(PIP) install -e ".[dev]"
	$(PYTHON) -m playwright install chromium

test:  ## Run the test suite
	$(PYTHON) -m pytest

lint:  ## Lint with ruff
	$(PYTHON) -m ruff check src tests

format:  ## Auto-format with black + ruff --fix
	$(PYTHON) -m black src tests
	$(PYTHON) -m ruff check --fix src tests

typecheck:  ## Run mypy on src
	$(PYTHON) -m mypy src

clean:  ## Remove build artifacts and caches
	rm -rf build dist *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
	find . -type d -name .mypy_cache -prune -exec rm -rf {} +

build: clean  ## Build sdist + wheel into dist/
	$(PYTHON) -m pip install --upgrade build
	$(PYTHON) -m build

dist: build  ## Alias for `build`
	@ls -la dist/

run:  ## Run the CLI from source (PYTHONPATH=src)
	PYTHONPATH=src $(PYTHON) -m jobcli.cli.main $(ARGS)

tui:  ## Run the interactive TUI from source
	PYTHONPATH=src $(PYTHON) -m jobcli.cli.entry

tag-release:  ## Tag the current commit with the version from pyproject.toml
	@VERSION=$$(grep -E '^version = ' pyproject.toml | head -1 | sed 's/.*"\(.*\)".*/\1/'); \
	echo "Tagging v$$VERSION"; \
	git tag -a "v$$VERSION" -m "Release v$$VERSION"; \
	echo "Push with: git push origin v$$VERSION"
