# webgrab

Universal web page fetcher with cascading fallback. Tries each method in order and returns on first success.

## Cascade Order

1. **requests** (plain urllib) - fastest, no deps
2. **cloudscraper** - cloudflare bypass (optional)
3. **jina** - Jina Reader API (free, no key)
4. **chrome-headless** - last resort, needs chrome binary

## Install

```bash
uv sync
```

With cloudflare support:
```bash
uv sync --extra cloudflare
```

## Usage

```bash
uv run webgrab https://example.com
uv run webgrab https://example.com --format text
uv run webgrab https://example.com --format html --timeout 10
```

## Dev

```bash
# Lint + type check
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run ty check src/webgrab/__init__.py

# Tests (parallel with xdist)
uv run pytest tests/ -n auto

# Tests with coverage
uv run pytest tests/test_webgrab.py --cov=src --cov-report=term-missing -n auto

# Integration tests (easy + medium)
uv run pytest tests/test_integration.py -m "not slow" -n auto

# Slow / hard URL tests
uv run pytest tests/test_integration.py -m "slow" -n auto
```

## Hooks

- **pre-commit**: ruff (lint + format) + ty + unit tests (90% coverage)
- **pre-push**: unit tests (90% coverage) + integration tests

## CI

GitHub Actions runs lint, unit tests, integration tests, and slow tests on every push/PR.
