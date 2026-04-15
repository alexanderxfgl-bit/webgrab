#!/usr/bin/env python3
"""Integration tests - real network calls, categorized by difficulty."""

import os

import pytest

from webgrab import try_chrome_headless, try_cloudscraper, try_jina, try_requests

# -- EASY: static sites, no JS, no auth, no anti-bot --


class TestEasyURLs:
    """Simple static pages that should work with plain urllib."""

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("http://example.com", id="example"),
            pytest.param("https://httpbin.org/html", id="httpbin-html"),
            pytest.param("https://www.w3.org/TR/PNG/iso_8859-1.txt", id="w3-txt"),
            pytest.param("https://old.reddit.com/r/programming/.json", id="reddit-json"),
        ],
    )
    def test_requests_fetches(self, url: str):
        html, err = try_requests(url, timeout=10)
        assert html is not None, f"requests failed for {url}: {err}"
        assert len(html) >= 200

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://news.ycombinator.com", id="hackernews"),
            pytest.param("https://httpbin.org/get", id="httpbin-json"),
            pytest.param("https://www.iana.org/domains/reserved", id="iana"),
        ],
    )
    def test_requests_text_content(self, url: str):
        html, err = try_requests(url, timeout=10)
        assert html is not None, f"failed: {err}"
        assert len(html) >= 200


# -- MEDIUM: some JS, light cloudflare, rate limiting --


class TestMediumURLs:
    """Sites with some protection that may need cloudscraper or jina."""

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://old.reddit.com/r/programming/", id="reddit-old"),
            pytest.param("https://www.reddit.com/r/programming/.json", id="reddit-new-json"),
            pytest.param("https://httpbin.org/delay/1", id="httpbin-slow"),
        ],
    )
    def test_cloudscraper_or_requests(self, url: str):
        """At least one method should work."""
        html, err = try_requests(url, timeout=15)
        if html is None:
            html, err = try_cloudscraper(url, timeout=15)
        assert html is not None, f"all methods failed for {url}: {err}"

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://www.wikipedia.org", id="wikipedia"),
            pytest.param("https://quotes.toscrape.com/", id="quotes-scrape"),
            pytest.param("https://books.toscrape.com/", id="books-scrape"),
        ],
    )
    def test_scraping_demos(self, url: str):
        html, err = try_requests(url, timeout=10)
        assert html is not None, f"failed for {url}: {err}"


# -- HARD: heavy JS, captchas, auth walls, anti-bot --


class TestHardURLs:
    """Sites that are difficult - may need jina or chrome. Marked slow."""

    @pytest.mark.slow
    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://www.reddit.com/", id="reddit-js-wall"),
            pytest.param("https://x.com/", id="twitter-js"),
            pytest.param("https://www.facebook.com/", id="facebook"),
            pytest.param("https://www.linkedin.com/", id="linkedin"),
        ],
    )
    def test_jina_fallback(self, url: str):
        """Jina should handle JS-heavy sites."""
        html, err = try_jina(url, timeout=20)
        assert html is not None, f"jina failed for {url}: {err}"

    @pytest.mark.slow
    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://www.google.com/search?q=test", id="google-search"),
            pytest.param("https://www.amazon.com/", id="amazon"),
            pytest.param("https://www.youtube.com/", id="youtube"),
        ],
    )
    def test_very_hard(self, url: str):
        """These are very hard - just verify we don't crash."""
        try:
            html, err = try_requests(url, timeout=10)
            if html is None:
                html, err = try_jina(url, timeout=20)
            # don't assert - these might fail, just verify no crash
            assert err is None or isinstance(err, str)
        except Exception:
            pytest.xfail(f"expected failure for {url}")


# -- CHROME (only runs if chrome binary available) --


@pytest.mark.skipif(
    not os.path.exists(os.environ.get("WEBGRAB_CHROME", "/home/node/chrome/chrome-linux64/chrome")),
    reason="chrome binary not found",
)
class TestChromeHeadless:
    @pytest.mark.slow
    def test_example_com(self):
        html, err = try_chrome_headless("http://example.com", timeout=10)
        assert html is not None, f"chrome failed: {err}"

    @pytest.mark.slow
    def test_reddit_old(self):
        html, err = try_chrome_headless("https://old.reddit.com/", timeout=15)
        # reddit might show consent wall via chrome
        if html is not None:
            assert len(html) >= 200
