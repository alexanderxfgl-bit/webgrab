#!/usr/bin/env python3
"""webgrab HTTP MCP server - runs on remote VM, serves the full cascade over HTTP."""

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastmcp import FastMCP

# Chrome binary
_CHROME_BIN = os.environ.get("WEBGRAB_CHROME", "/usr/local/bin/chrome")

# Disk cache settings
_CACHE_DIR = Path(os.environ.get("WEBGRAB_CACHE_DIR", "/tmp/webgrab-cache"))
_CACHE_MAX_BYTES = int(os.environ.get("WEBGRAB_CACHE_MAX_GB", "10")) * 1024 * 1024 * 1024

# FlareSolverr settings
_FLARESOLVERR_URL = os.environ.get("WEBGRAB_FLARESOLVERR_URL", "http://127.0.0.1:8191/v1")

# Allowed auth token (set via WEBGRAB_TOKEN env var)
_AUTH_TOKEN = os.environ.get("WEBGRAB_TOKEN", "")

# Max response size in chars
MAX_CHARS = int(os.environ.get("WEBGRAB_MAX_CHARS", "200000"))


# ---------------------------------------------------------------------------
# Anti-bot / challenge page detection
# ---------------------------------------------------------------------------
_CHALLENGE_PHRASES = (
    "just a moment",
    "checking your browser",
    "enable javascript and cookies to continue",
    "please verify you are a human",
    "cf-browser-verification",
    "attention required",
    "this page may be requiring captcha",
)


def _is_challenge_page(text: str) -> bool:
    """Check if response is a bot challenge / CAPTCHA page."""
    lower = text[:2000].lower()
    return any(phrase in lower for phrase in _CHALLENGE_PHRASES)


# ---------------------------------------------------------------------------
# LRU Disk Cache
# ---------------------------------------------------------------------------
def _cache_key(url: str, fmt: str) -> str:
    return hashlib.sha256(f"{url}|{fmt}".encode()).hexdigest()


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / key[:2] / key


def _cache_get(url: str, fmt: str) -> dict | None:
    """Get cached result. Returns None on miss."""
    try:
        p = _cache_path(_cache_key(url, fmt))
        if not p.exists():
            return None
        data = json.loads(p.read_text())
        # Update atime for LRU eviction
        p.touch()
        return data
    except Exception:
        return None


def _cache_put(url: str, fmt: str, result: dict) -> None:
    """Store result in cache."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = _cache_key(url, fmt)
        p = _cache_path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result))
    except Exception:
        pass


def _cache_evict_if_needed() -> None:
    """Evict oldest files if cache exceeds max size. LRU by atime."""
    try:
        if not _CACHE_DIR.exists():
            return
        total = sum(f.stat().st_size for f in _CACHE_DIR.rglob("*") if f.is_file())
        if total < _CACHE_MAX_BYTES:
            return
        # Get all cache files sorted by atime (oldest first)
        files = [(f, f.stat().st_atime) for f in _CACHE_DIR.rglob("*") if f.is_file()]
        files.sort(key=lambda x: x[1])
        # Evict oldest until under 80% of limit
        target = int(_CACHE_MAX_BYTES * 0.8)
        for f, _ in files:
            if total <= target:
                break
            total -= f.stat().st_size
            f.unlink(missing_ok=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Fetch methods
# ---------------------------------------------------------------------------
def try_requests(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    """Plain urllib."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                )
            },
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        html = resp.read().decode("utf-8", errors="replace")
        if len(html) < 200:
            return None, "too short"
        if _is_challenge_page(html):
            return None, "challenge page detected"
        return html, None
    except Exception as e:
        return None, str(e)[:200]


def try_cloudscraper(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    """cloudscraper normal mode."""
    try:
        import cloudscraper

        s = cloudscraper.create_scraper(interpreter="native")
        s.headers["User-Agent"] = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        r = s.get(url, timeout=timeout)
        if r.status_code == 403:
            return None, "403 forbidden"
        if len(r.text) < 200:
            return None, "too short"
        if _is_challenge_page(r.text):
            return None, "challenge page detected"
        return r.text, None
    except ImportError:
        return None, "cloudscraper not installed"
    except Exception as e:
        return None, str(e)[:200]


def try_cloudscraper_js(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    """cloudscraper JS mode - solves CF JS challenges."""
    try:
        import cloudscraper

        s = cloudscraper.create_scraper(interpreter="nodejs")
        s.headers["User-Agent"] = (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        r = s.get(url, timeout=timeout)
        if r.status_code == 403:
            return None, "403 forbidden"
        if len(r.text) < 200:
            return None, "too short"
        if _is_challenge_page(r.text):
            return None, "challenge page detected"
        return r.text, None
    except ImportError:
        return None, "cloudscraper not installed"
    except Exception as e:
        return None, str(e)[:200]


def try_jina(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    """Jina Reader API."""
    try:
        jina_url = f"https://r.jina.ai/{url}"
        req = urllib.request.Request(
            jina_url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/plain"},
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        text = resp.read().decode("utf-8", errors="replace")
        if len(text) < 50:
            return None, "too short"
        # reject if jina warns about errors
        if "403" in text[:200] or "error" in text[:200].lower():
            return None, "jina returned error content"
        if _is_challenge_page(text):
            return None, "challenge page detected"
        return text, None
    except Exception as e:
        return None, str(e)[:200]


def try_chrome_headless(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    """Chrome headless --dump-dom."""
    import subprocess

    if not os.path.exists(_CHROME_BIN):
        return None, "chrome binary not found"
    try:
        result = subprocess.run(
            [
                _CHROME_BIN,
                "--headless",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--dump-dom",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        html = result.stdout
        if len(html) < 200:
            return None, "too short"
        if _is_challenge_page(html):
            return None, "challenge page detected"
        return html, None
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)[:200]


def try_nodriver(url: str, timeout: int = 30) -> tuple[str | None, str | None]:
    """nodriver - undetected chrome."""
    if not os.path.exists(_CHROME_BIN):
        return None, "chrome binary not found"
    try:
        import asyncio

        import nodriver as nd

        result: str | None = None

        async def _fetch() -> None:
            nonlocal result
            browser = await nd.start(
                browser_executable_path=_CHROME_BIN,
                sandbox=False,
                headless=True,
            )
            page = await browser.get(url)
            result = page.get_content()
            await browser.stop()

        asyncio.run(_fetch())
        if result and len(result) >= 200:
            if _is_challenge_page(result):
                return None, "challenge page detected"
            return result, None
        return None, "too short"
    except ImportError:
        return None, "nodriver not installed"
    except Exception as e:
        return None, str(e)[:200]


def try_zendriver(url: str, timeout: int = 30) -> tuple[str | None, str | None]:
    """zendriver - CDP browser automation."""
    if not os.path.exists(_CHROME_BIN):
        return None, "chrome binary not found"
    try:
        import asyncio

        import zendriver

        result: str | None = None

        async def _fetch() -> None:
            nonlocal result
            browser = await zendriver.start(
                browser_executable_path=_CHROME_BIN,
                headless=True,
                sandbox=False,
                browser_connection_timeout=timeout,
            )
            page = browser.main_tab
            if page is None:
                return
            await page.get(url)
            result = page.get_content()
            browser.stop()

        asyncio.run(_fetch())
        if result and len(result) >= 200:
            if _is_challenge_page(result):
                return None, "challenge page detected"
            return result, None
        return None, "too short"
    except ImportError:
        return None, "zendriver not installed"
    except Exception as e:
        return None, str(e)[:200]


def try_flaresolverr(url: str, timeout: int = 60) -> tuple[str | None, str | None]:
    """FlareSolverr proxy - solves Cloudflare challenges via dedicated browser."""
    try:
        payload = json.dumps(
            {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": timeout * 1000,
            }
        ).encode()
        req = urllib.request.Request(
            _FLARESOLVERR_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=timeout + 10)
        data = json.loads(resp.read().decode())
        if data.get("status") != "ok":
            return None, f"flaresolverr error: {data.get('message', 'unknown')}"
        solution = data.get("solution", {})
        html = solution.get("response", "")
        if len(html) < 200:
            return None, "too short"
        if _is_challenge_page(html):
            return None, "challenge page detected"
        return html, None
    except urllib.error.URLError:
        return None, "flaresolverr not running"
    except Exception as e:
        return None, str(e)[:200]


# ---------------------------------------------------------------------------
# HTML processing
# ---------------------------------------------------------------------------
def extract_text(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()[:MAX_CHARS]


def html_to_basic_md(html: str) -> str:
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<h1[^>]*>(.*?)</h1>", r"# \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<h2[^>]*>(.*?)</h2>", r"## \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<h3[^>]*>(.*?)</h3>", r"### \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<h4[^>]*>(.*?)</h4>", r"#### \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(
        r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
        r"[\2](\1)",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    html = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()[:MAX_CHARS]


# ---------------------------------------------------------------------------
# Cascade order: cheap/fast first, expensive/undetectable last
# ---------------------------------------------------------------------------
METHODS = [
    ("requests", try_requests),
    ("cloudscraper", try_cloudscraper),
    ("cloudscraper-js", try_cloudscraper_js),
    ("jina", try_jina),
    ("chrome-headless", try_chrome_headless),
    ("nodriver", try_nodriver),
    ("zendriver", try_zendriver),
    ("flaresolverr", try_flaresolverr),
]


def fetch_url(url: str, fmt: str = "markdown", timeout: int = 30) -> dict:
    """Fetch a URL using the full cascade with disk cache. Returns dict with result or error."""
    # Check cache first
    cached = _cache_get(url, fmt)
    if cached is not None:
        cached["from_cache"] = True
        return cached

    # Evict if cache is full
    _cache_evict_if_needed()

    start = time.time()
    method_used = None
    execution_log = []

    for name, fn in METHODS:
        method_start = time.time()
        try:
            result, err = fn(url, timeout=timeout)
            method_elapsed = time.time() - method_start
            if result:
                elapsed = time.time() - start
                method_used = name
                if fmt == "html":
                    output = result[:MAX_CHARS]
                elif fmt == "text":
                    output = extract_text(result)
                else:
                    output = html_to_basic_md(result)
                execution_log.append(
                    {
                        "method": name,
                        "status": "success",
                        "elapsed": round(method_elapsed, 2),
                        "chars": len(result),
                    }
                )
                resp = {
                    "success": True,
                    "url": url,
                    "method": method_used,
                    "format": fmt,
                    "elapsed_seconds": round(elapsed, 2),
                    "chars": len(output),
                    "content": output,
                    "execution_log": execution_log,
                }
                # Cache successful result
                _cache_put(url, fmt, resp)
                return resp
            else:
                execution_log.append(
                    {
                        "method": name,
                        "status": "failed",
                        "elapsed": round(method_elapsed, 2),
                        "error": err,
                    }
                )
        except Exception as e:
            method_elapsed = time.time() - method_start
            execution_log.append(
                {
                    "method": name,
                    "status": "error",
                    "elapsed": round(method_elapsed, 2),
                    "error": str(e)[:200],
                }
            )

    return {
        "success": False,
        "url": url,
        "error": "All methods failed",
        "execution_log": execution_log,
    }


def extract_content(html_content: str, fmt: str = "markdown") -> dict:
    """Extract content from HTML string."""
    if fmt == "text":
        output = extract_text(html_content)
    elif fmt == "html":
        output = html_content[:MAX_CHARS]
    else:
        output = html_to_basic_md(html_content)
    return {
        "success": True,
        "format": fmt,
        "chars": len(output),
        "content": output,
    }


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="webgrab",
    version="2.2.0",
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint for deploy verification."""
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok", "version": "2.2.0"})


@mcp.tool()
def fetch(url: str, format: str = "markdown", timeout: int = 30) -> str:
    """Fetch a URL and return its content. Uses a cascading fallback with disk cache:
    requests -> cloudscraper -> cloudscraper-js -> jina -> chrome-headless -> nodriver -> zendriver -> flaresolverr.

    Args:
        url: The URL to fetch
        format: Output format - 'markdown', 'text', or 'html'
        timeout: Request timeout in seconds

    Returns:
        The page content in the requested format, or error details if all methods fail
    """
    result = fetch_url(url, format, timeout)
    return json.dumps(result, indent=2)


@mcp.tool()
def extract(html_content: str, format: str = "markdown") -> str:
    """Extract and convert HTML content to text or markdown.

    Args:
        html_content: Raw HTML content to process
        format: Output format - 'markdown', 'text', or 'html'

    Returns:
        Processed content in the requested format
    """
    result = extract_content(html_content, format)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    port = int(os.environ.get("WEBGRAB_PORT", "8721"))
    # Run as streamable-http on all interfaces
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port, stateless_http=True)
