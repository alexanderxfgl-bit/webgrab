#!/usr/bin/env python3
"""webgrab - Universal web page fetcher with cascading fallback."""

import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


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
    """cloudscraper for cloudflare bypass (optional dep)."""
    try:
        import cloudscraper  # type: ignore[import-untyped]

        s = cloudscraper.create_scraper()
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


def try_chrome_headless(url: str, timeout: int = 20) -> tuple[str | None, str | None]:
    """Chrome headless --dump-dom (last resort, needs chrome binary)."""
    import os

    chrome = os.environ.get("WEBGRAB_CHROME", "/home/node/chrome/chrome-linux64/chrome")
    if not os.path.exists(chrome):
        return None, "chrome binary not found"
    try:
        result = subprocess.run(
            [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom", url],
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
    ("jina", try_jina),
    ("chrome-headless", try_chrome_headless),
]


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: webgrab <url> [--format text|markdown|html] [--timeout 30]", file=sys.stderr)
        sys.exit(2)

    url = sys.argv[1]
    fmt = "markdown"
    timeout = 30

    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--format":
            fmt = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--timeout":
            timeout = int(sys.argv[i + 1])
            i += 2
        else:
            i += 1

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


if __name__ == "__main__":
    main()
