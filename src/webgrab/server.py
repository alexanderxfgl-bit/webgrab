#!/usr/bin/env python3
"""webgrab MCP server - exposes web fetching as MCP tools."""

import asyncio

from mcp.server.fastmcp import FastMCP

from webgrab import (
    extract_text,
    html_to_basic_md,
    try_chrome_headless,
    try_cloudscraper,
    try_cloudscraper_js,
    try_jina,
    try_nodriver,
    try_requests,
    try_zendriver,
)

mcp = FastMCP(
    "webgrab",
    instructions=(
        "Universal web page fetcher with cascading fallback. "
        "Tries requests > cloudscraper > cloudscraper-js > jina > nodriver > zendriver > chrome-headless."
    ),
)


async def _fetch(url: str, timeout: int = 15) -> tuple[str | None, str | None, str | None]:
    """Try each method, return (content, error, method_used)."""
    methods = [
        ("requests", try_requests),
        ("cloudscraper", try_cloudscraper),
        ("cloudscraper-js", try_cloudscraper_js),
        ("jina", try_jina),
        ("nodriver", try_nodriver),
        ("zendriver", try_zendriver),
        ("chrome-headless", try_chrome_headless),
    ]
    for name, fn in methods:
        try:
            html, err = await asyncio.get_event_loop().run_in_executor(None, fn, url, timeout)
            if html:
                return html, None, name
        except Exception:
            continue
    return None, "all methods failed", None


@mcp.tool()
async def fetch(url: str, format: str = "text", timeout: int = 15) -> str:
    """Fetch a web page and return content in the specified format.

    Args:
        url: The URL to fetch.
        format: Output format - "html", "text" (strip tags), or "markdown" (basic conversion). Defaults to "text".
        timeout: Timeout in seconds for each fetch method. Defaults to 15.
    """
    html, err, method = await _fetch(url, timeout)

    if html is None:
        return f"Error: Failed to fetch {url} - {err}"

    if format == "html":
        return html
    elif format == "text":
        return extract_text(html)
    else:
        return html_to_basic_md(html)


@mcp.tool()
async def extract(html_content: str, format: str = "text") -> str:
    """Extract readable text or markdown from raw HTML content.

    Args:
        html_content: Raw HTML string to process.
        format: "text" (strip tags) or "markdown" (basic conversion). Defaults to "text".
    """
    if format == "text":
        return extract_text(html_content)
    else:
        return html_to_basic_md(html_content)


if __name__ == "__main__":
    mcp.run(transport="stdio")
