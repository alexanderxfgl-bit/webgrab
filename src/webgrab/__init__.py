#!/usr/bin/env python3
"""webgrab - Universal web page fetcher with cascading fallback."""

import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

# Chrome binary setup
_CHROME_BIN = os.environ.get(
    "WEBGRAB_CHROME",
    "/home/node/chrome/chrome-linux64/chrome",
)
_CHROME_WRAPPER = os.path.join(os.path.dirname(_CHROME_BIN), "chrome-launch.sh")
# If wrapper exists, use it (sets LD_LIBRARY_PATH for chrome)
if os.path.exists(_CHROME_WRAPPER):
    _CHROME_BIN = _CHROME_WRAPPER


def log(msg: str) -> None:
    """Print to stderr."""
    print(msg, file=sys.stderr, flush=True)


def try_requests(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    """Plain urllib - no special deps, fastest method."""
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
        return None, str(e)[:100]


def try_cloudscraper(url: str, timeout: int = 15) -> tuple[str | None, str | None]:
    """cloudscraper normal mode - bypasses basic cloudflare challenges."""
    try:
        import cloudscraper  # type: ignore[import-untyped]

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
        return None, str(e)[:100]


def try_cloudscraper_js(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    """cloudscraper JS mode - solves cloudflare JS challenges using Node.js interpreter."""
    try:
        import cloudscraper  # type: ignore[import-untyped]

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
        return None, str(e)[:100]


def try_jina(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    """Jina Reader API - free, no key needed for basic use."""
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
        return text, None
    except Exception as e:
        return None, str(e)[:100]


def try_nodriver(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    """nodriver (undetected chrome) - bypasses bot detection, JS rendering."""
    if not os.path.exists(_CHROME_BIN):
        return None, "chrome binary not found"
    try:
        import asyncio

        import nodriver as nd  # type: ignore[import-untyped]

        result: str | None = None

        async def _fetch() -> None:
            nonlocal result
            browser = await nd.start(
                browser_executable_path=_CHROME_BIN,
                no_sandbox=True,
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
        return None, str(e)[:100]


def try_zendriver(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    """zendriver - CDP-based browser automation, headless JS rendering."""
    if not os.path.exists(_CHROME_BIN):
        return None, "chrome binary not found"
    try:
        import asyncio

        import zendriver  # type: ignore[import-untyped]

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
        return None, str(e)[:100]


def try_chrome_headless(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    """Chrome headless --dump-dom (last resort, needs chrome binary)."""
    if not os.path.exists(_CHROME_BIN):
        return None, "chrome binary not found"
    try:
        result = subprocess.run(
            [_CHROME_BIN, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom", url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        html = result.stdout
        if len(html) < 200:
            return None, "too short"
        return html, None
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)[:100]


def extract_text(html: str, max_chars: int = 50000) -> str:
    """Strip HTML tags, remove script/style blocks."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = text.strip()
    return text[:max_chars]


def html_to_basic_md(html: str, max_chars: int = 50000) -> str:
    """Rough HTML to markdown - headers, links, bold, italic, lists, blockquotes."""
    # Remove script/style
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Headers
    html = re.sub(r"<h1[^>]*>(.*?)</h1>", r"# \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<h2[^>]*>(.*?)</h2>", r"## \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<h3[^>]*>(.*?)</h3>", r"### \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<h4[^>]*>(.*?)</h4>", r"#### \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    # Links
    html = re.sub(
        r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
        r"[\2](\1)",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Bold/italic
    html = re.sub(
        r"<(strong|b)[^>]*>(.*?)</\1>",
        r"**\2**",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    html = re.sub(
        r"<(em|i)[^>]*>(.*?)</\1>",
        r"*\2*",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # List items
    html = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", html, flags=re.DOTALL | re.IGNORECASE)
    # Br to newlines
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    # Blockquotes
    html = re.sub(
        r"<blockquote[^>]*>(.*?)</blockquote>",
        lambda m: "\n" + "\n".join(f"> {line}" for line in m.group(1).split("\n")) + "\n",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Remaining tags
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    html = html.strip()
    return html[:max_chars]


METHODS: list[tuple[str, Any]] = [
    ("requests", try_requests),
    ("cloudscraper", try_cloudscraper),
    ("cloudscraper-js", try_cloudscraper_js),
    ("jina", try_jina),
    ("nodriver", try_nodriver),
    ("zendriver", try_zendriver),
    ("chrome-headless", try_chrome_headless),
]


def _fetch_url(url: str, fmt: str, timeout: int) -> None:
    """Fetch a URL and print output."""
    import time

    log(f"webgrab: fetching {url} (format={fmt})")
    start = time.time()
    html: str | None = None
    method_used: str | None = None

    for name, fn in METHODS:
        log(f"  trying {name}...")
        try:
            result, err = fn(url, timeout=timeout)  # noqa: B023
            if result:
                elapsed = time.time() - start
                log(f"  {name} succeeded in {elapsed:.1f}s ({len(result)} bytes)")
                html = result
                method_used = name
                break
            else:
                log(f"  {name} failed: {err}")
        except Exception as e:
            log(f"  {name} error: {e}")

    if html is None:
        log("  ALL METHODS FAILED")
        sys.exit(1)

    if fmt == "html":
        output = html
    elif fmt == "text":
        output = extract_text(html)
    else:
        output = html_to_basic_md(html)

    print(output)
    log(f"method={method_used} format={fmt} chars={len(output)}")


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="webgrab",
        description="Universal web page fetcher with cascading fallback",
    )
    parser.add_argument("url", nargs="?", help="URL to fetch")
    parser.add_argument("--format", choices=["text", "markdown", "html"], default="markdown")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--mcp", action="store_true", help="Start MCP server on stdio")

    args = parser.parse_args()

    if args.mcp:
        from webgrab.server import mcp

        mcp.run(transport="stdio")
        return

    if not args.url:
        parser.print_help(sys.stderr)
        sys.exit(2)

    _fetch_url(args.url, args.format, args.timeout)


if __name__ == "__main__":
    main()
