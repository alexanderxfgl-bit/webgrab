# webgrab

Universal web page fetcher with cascading fallback. Tries each method in order and returns on first success.

## Cascade Order

1. **requests** (plain urllib) - fastest, no deps
2. **cloudscraper** - cloudflare bypass (native interpreter) - REQUIRED
3. **cloudscraper-js** - cloudflare bypass (nodejs interpreter) - REQUIRED
4. **jina** - Jina Reader API (free, no key)
5. **nodriver** - undetectable chrome via CDP
6. **zendriver** - CDP browser automation
7. **chrome-headless** - last resort, needs chrome binary

## Install

### From source

```bash
git clone https://github.com/alexanderxfgl-bit/webgrab.git
cd webgrab
uv sync --extra dev
```

### Via uvx (recommended - no install needed)

```bash
# One-liner - auto-installs from git
uvx --from git+https://github.com/alexanderxfgl-bit/webgrab.git webgrab https://example.com

# Help
uvx --from git+https://github.com/alexanderxfgl-bit/webgrab.git webgrab --help
```

### As a global CLI tool

```bash
cd webgrab
uv tool install .
webgrab https://example.com
```

## CLI Usage

```bash
# Fetch a URL (defaults to markdown format)
webgrab https://example.com

# Choose output format
webgrab https://example.com --format text
webgrab https://example.com --format html
webgrab https://example.com --format markdown

# Set timeout per attempt (default 30s)
webgrab https://example.com --timeout 10

# Help
webgrab --help
```

## MCP Server

Start as a stdio MCP server that any MCP client can connect to:

```bash
# From project dir
uv run webgrab --mcp

# Via uvx
uvx --from webgrab webgrab --mcp
```

### MCP Tools

**fetch** - Fetch a web page and return content
- `url` (string, required): The URL to fetch
- `format` (string, optional): "text", "html", or "markdown" (default: "text")
- `timeout` (integer, optional): Timeout in seconds per method (default: 15)

**extract** - Extract readable text from raw HTML
- `html_content` (string, required): Raw HTML to process
- `format` (string, optional): "text" or "markdown" (default: "text")

### MCP Client Config

```json
{
  "mcpServers": {
    "webgrab": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/alexanderxfgl-bit/webgrab.git", "webgrab", "--mcp"]
    }
  }
}
```

## Browser Dependencies

For **nodriver**, **zendriver**, and **chrome-headless** methods to work, Chrome/Chromium must be available.

### Linux (Debian/Ubuntu)

```bash
sudo apt-get update
sudo apt-get install -y chromium-browser
```

### macOS

```bash
# Already installed on most Macs at /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome
```

### Docker/Custom Paths

If Chrome is installed in a non-standard location, set `CHROME_BIN` env var:

```bash
export CHROME_BIN=/path/to/chrome
webgrab https://example.com
```

The `chrome-launch.sh` wrapper in the repo sets `LD_LIBRARY_PATH` for bundled Chrome builds in containers.

## Dev

```bash
# Lint + format + type check
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run ty check src/webgrab/__init__.py

# Unit tests with coverage (parallel)
uv run pytest tests/test_webgrab.py tests/test_server.py --cov=src --cov-report=term-missing -n auto

# Integration tests (CI-safe)
uv run pytest tests/test_integration.py -m "not local" -n auto

# All tests
uv run pytest tests/ -m "not local" --cov=src --cov-fail-under=90 -n auto

# Local-only tests (sites that block CI IPs)
uv run pytest tests/test_integration.py -m "local" -n auto
```

## Hooks

- **pre-commit**: ruff (lint + format) + ty + full test suite (90% coverage)
- **pre-push**: full test suite (90% coverage)

## CI

GitHub Actions runs lint, tests, and integration tests on every push/PR. Only CI-safe tests run in CI; flaky external sites are marked `local` and run manually.
