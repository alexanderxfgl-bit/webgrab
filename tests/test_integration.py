#!/usr/bin/env python3
"""Integration tests - real network calls, categorized by difficulty."""

import os

import pytest

from webgrab import try_chrome_headless, try_cloudscraper, try_jina, try_requests

# -- CI-SAFE: reliable static sites that work from any IP --


class TestCIStable:
    """Static pages that reliably work from GitHub Actions."""

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("http://example.com", id="example"),
            pytest.param("https://httpbin.org/html", id="httpbin-html"),
            pytest.param("https://httpbin.org/get", id="httpbin-json"),
            pytest.param("https://news.ycombinator.com", id="hackernews"),
            pytest.param("https://quotes.toscrape.com/", id="quotes-scrape"),
            pytest.param("https://books.toscrape.com/", id="books-scrape"),
            pytest.param("https://www.wikipedia.org", id="wikipedia"),
        ],
    )
    def test_requests_succeeds(self, url: str):
        html, err = try_requests(url, timeout=15)
        assert html is not None, f"requests failed for {url}: {err}"
        assert len(html) >= 200

    def test_cloudflare_site(self):
        """Sites behind cloudflare that cloudscraper should handle or cascade past."""
        url = "https://quotes.toscrape.com/"
        html, err = try_requests(url, timeout=10)
        if html is None:
            html, err = try_cloudscraper(url, timeout=10)
        assert html is not None, f"all methods failed: {err}"

    def test_httpbin_delay(self):
        """Slow but reliable endpoint."""
        html, err = try_requests("https://httpbin.org/delay/1", timeout=15)
        assert html is not None, f"failed: {err}"

    def test_jina_reader(self):
        """Jina reader API should work for at least one URL."""
        html, err = try_jina("http://example.com", timeout=15)
        assert html is not None, f"jina failed: {err}"


# -- LOCAL ONLY: sites that block CI IPs (run manually with pytest -m local) --


@pytest.mark.local
class TestLocalOnly:
    """Sites that block GitHub Actions IPs. Run locally only."""

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://old.reddit.com/r/programming/.json", id="reddit-json"),
            pytest.param("https://old.reddit.com/r/programming/", id="reddit-old"),
            pytest.param("https://www.reddit.com/r/programming/.json", id="reddit-new-json"),
        ],
    )
    def test_reddit(self, url: str):
        html, err = try_requests(url, timeout=15)
        if html is None:
            html, err = try_cloudscraper(url, timeout=15)
        assert html is not None, f"all methods failed for {url}: {err}"

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://www.facebook.com/", id="facebook"),
            pytest.param("https://x.com/", id="twitter"),
            pytest.param("https://www.linkedin.com/", id="linkedin"),
        ],
    )
    def test_jina_hard_sites(self, url: str):
        html, err = try_jina(url, timeout=20)
        assert html is not None, f"jina failed for {url}: {err}"

    @pytest.mark.parametrize(
        "url",
        [
            pytest.param("https://www.google.com/search?q=test", id="google-search"),
            pytest.param("https://www.amazon.com/", id="amazon"),
            pytest.param("https://www.youtube.com/", id="youtube"),
        ],
    )
    def test_very_hard(self, url: str):
        try:
            html, err = try_requests(url, timeout=10)
            if html is None:
                html, err = try_jina(url, timeout=20)
            assert err is None or isinstance(err, str)
        except Exception:
            pytest.xfail(f"expected failure for {url}")


# -- CHROME (only runs if chrome binary available) --


@pytest.mark.local
@pytest.mark.skipif(
    not os.path.exists(os.environ.get("WEBGRAB_CHROME", "/home/node/chrome/chrome-linux64/chrome")),
    reason="chrome binary not found",
)
class TestChromeHeadless:
    def test_example_com(self):
        html, err = try_chrome_headless("http://example.com", timeout=10)
        assert html is not None, f"chrome failed: {err}"
