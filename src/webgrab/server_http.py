#!/usr/bin/env python3
"""webgrab HTTP MCP server - runs on remote VM, serves the full cascade over HTTP."""

import os
import re
import time
import urllib.error
import urllib.request

from fastmcp import FastMCP

# Chrome binary
_CHROME_BIN = os.environ.get("WEBGRAB_CHROME", "/usr/local/bin/chrome")

# Allowed auth token (set via WEBGRAB_TOKEN env var)
_AUTH_TOKEN = os.environ.get("WEBGRAB_TOKEN", "")

# Max response size in chars
MAX_CHARS = int(os.environ.get("WEBGRAB_MAX_CHARS", "200000"))


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
            [_CHROME_BIN, "--headless", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage", "--dump-dom", url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        html = result.stdout
        if len(html) < 200:
            return None, "too short"
        # Detect Cloudflare challenge pages
        lower = html.lower()
        if (
            "just a moment" in lower
            or "checking your browser" in lower
            or "enable javascript and cookies to continue" in lower
        ):
            return None, "cloudflare challenge page"
        return html, None
    except subprocess.TimeoutExpired:
        return None, "timeout"
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
            return result, None
        return None, "too short"
    except ImportError:
        return None, "zendriver not installed"
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
            return result, None
        return None, "too short"
    except ImportError:
        return None, "nodriver not installed"
    except Exception as e:
        return None, str(e)[:200]


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
    html = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r"[\2](\1)", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()[:MAX_CHARS]


METHODS = [
    ("requests", try_requests),
    ("cloudscraper", try_cloudscraper),
    ("cloudscraper-js", try_cloudscraper_js),
    ("jina", try_jina),
    ("nodriver", try_nodriver),
    ("zendriver", try_zendriver),
    ("chrome-headless", try_chrome_headless),
]


def fetch_url(url: str, fmt: str = "markdown", timeout: int = 30) -> dict:
    """Fetch a URL using the full cascade. Returns dict with result or error."""
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
                    {"method": name, "status": "success", "elapsed": round(method_elapsed, 2), "chars": len(result)}
                )
                return {
                    "success": True,
                    "url": url,
                    "method": method_used,
                    "format": fmt,
                    "elapsed_seconds": round(elapsed, 2),
                    "chars": len(output),
                    "content": output,
                    "execution_log": execution_log,
                }
            else:
                execution_log.append(
                    {"method": name, "status": "failed", "elapsed": round(method_elapsed, 2), "error": err}
                )
        except Exception as e:
            method_elapsed = time.time() - method_start
            execution_log.append(
                {"method": name, "status": "error", "elapsed": round(method_elapsed, 2), "error": str(e)[:200]}
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


# FastMCP server
mcp = FastMCP(
    name="webgrab",
    version="2.1.0",
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint for deploy verification."""
    from starlette.responses import JSONResponse

    return JSONResponse({"status": "ok", "version": "2.1.0"})


@mcp.tool()
def fetch(url: str, format: str = "markdown", timeout: int = 30) -> str:
    """Fetch a URL and return its content. Uses a cascading fallback: requests -> cloudscraper -> cloudscraper-js -> jina -> chrome-headless -> nodriver -> zendriver.

    Args:
        url: The URL to fetch
        format: Output format - 'markdown', 'text', or 'html'
        timeout: Request timeout in seconds

    Returns:
        The page content in the requested format, or error details if all methods fail
    """
    import json

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
    import json

    result = extract_content(html_content, format)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    port = int(os.environ.get("WEBGRAB_PORT", "8721"))
    # Run as streamable-http on all interfaces
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port, stateless_http=True)
