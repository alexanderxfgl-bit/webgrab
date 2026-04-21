"""Tests for the HTTP MCP server."""

import pytest

# Skip all tests if fastmcp is not installed
pytest.importorskip("fastmcp", reason="fastmcp not installed")

from webgrab.server_http import extract_content, fetch_url, mcp


class TestFetchUrl:
    """Test fetch_url function."""

    def test_fetch_success(self):
        """Test successful fetch returns correct structure."""
        result = fetch_url("https://example.com", fmt="text", timeout=10)

        assert result["success"] is True
        assert result["url"] == "https://example.com"
        assert "method" in result
        assert "elapsed_seconds" in result
        assert "chars" in result
        assert "content" in result
        assert "execution_log" in result
        assert len(result["execution_log"]) >= 1

        # Check execution log structure
        first_log = result["execution_log"][0]
        assert "method" in first_log
        assert "status" in first_log
        assert "elapsed" in first_log

    def test_fetch_returns_execution_log(self):
        """Test that execution log is returned even on success."""
        result = fetch_url("https://example.com", fmt="text", timeout=10)

        assert "execution_log" in result
        assert len(result["execution_log"]) >= 1

        # First entry should be the successful method
        first = result["execution_log"][0]
        assert first["status"] == "success"
        assert "chars" in first
        assert first["chars"] > 0

    def test_fetch_all_methods_logged(self):
        """Test that failed methods are also logged."""
        # Use a URL that might fail some methods
        result = fetch_url("https://httpbin.org/status/404", fmt="text", timeout=5)

        assert "execution_log" in result
        # Should have entries for methods that were tried
        assert len(result["execution_log"]) >= 1

    def test_fetch_invalid_url(self):
        """Test fetch with invalid URL."""
        result = fetch_url("https://this-domain-does-not-exist-12345.com", fmt="text", timeout=5)

        assert result["success"] is False
        assert "error" in result
        assert "execution_log" in result

        # All methods should have failed
        for log in result["execution_log"]:
            assert log["status"] in ("failed", "error")
            assert "error" in log

    def test_fetch_html_format(self):
        """Test fetch with HTML format."""
        result = fetch_url("https://example.com", fmt="html", timeout=10)

        assert result["success"] is True
        assert result["format"] == "html"
        assert "<" in result["content"]  # Should contain HTML tags

    def test_fetch_markdown_format(self):
        """Test fetch with markdown format."""
        result = fetch_url("https://example.com", fmt="markdown", timeout=10)

        assert result["success"] is True
        assert result["format"] == "markdown"

    def test_fetch_text_format(self):
        """Test fetch with text format."""
        result = fetch_url("https://example.com", fmt="text", timeout=10)

        assert result["success"] is True
        assert result["format"] == "text"
        assert "<" not in result["content"]  # Should not contain HTML tags


class TestExtractContent:
    """Test extract_content function."""

    def test_extract_text(self):
        """Test extracting text from HTML."""
        html = "<html><body><h1>Hello</h1><p>World</p></body></html>"
        result = extract_content(html, fmt="text")

        assert result["success"] is True
        assert result["format"] == "text"
        assert "Hello" in result["content"]
        assert "World" in result["content"]
        assert "<" not in result["content"]

    def test_extract_markdown(self):
        """Test extracting markdown from HTML."""
        html = "<html><body><h1>Hello</h1><p>World</p></body></html>"
        result = extract_content(html, fmt="markdown")

        assert result["success"] is True
        assert result["format"] == "markdown"
        assert "# Hello" in result["content"]

    def test_extract_html(self):
        """Test extracting HTML (passthrough)."""
        html = "<html><body><h1>Hello</h1></body></html>"
        result = extract_content(html, fmt="html")

        assert result["success"] is True
        assert result["format"] == "html"
        assert result["content"] == html


class TestChallengeDetection:
    """Test _is_challenge_page helper."""

    def test_detects_just_a_moment(self):
        from webgrab.server_http import _is_challenge_page

        assert _is_challenge_page("<html><body>Just a moment...</body></html>")

    def test_detects_checking_browser(self):
        from webgrab.server_http import _is_challenge_page

        assert _is_challenge_page("<html><body>Checking your browser</body></html>")

    def test_allows_normal_page(self):
        from webgrab.server_http import _is_challenge_page

        assert not _is_challenge_page("<html><body><h1>Hello World</h1></body></html>")


class TestDiskCache:
    """Test disk cache functions."""

    def test_cache_miss(self, tmp_path):
        from webgrab.server_http import _cache_get, _CACHE_DIR
        import webgrab.server_http as mod

        old = _CACHE_DIR
        mod._CACHE_DIR = tmp_path
        try:
            assert _cache_get("https://example.com", "markdown") is None
        finally:
            mod._CACHE_DIR = old

    def test_cache_put_and_get(self, tmp_path):
        from webgrab.server_http import _cache_get, _cache_put, _CACHE_DIR
        import webgrab.server_http as mod

        old = _CACHE_DIR
        mod._CACHE_DIR = tmp_path
        try:
            data = {"success": True, "content": "hello"}
            _cache_put("https://example.com", "markdown", data)
            result = _cache_get("https://example.com", "markdown")
            assert result is not None
            assert result["content"] == "hello"
        finally:
            mod._CACHE_DIR = old

    def test_cache_eviction(self, tmp_path):
        from webgrab.server_http import _cache_put, _cache_evict_if_needed, _CACHE_DIR, _CACHE_MAX_BYTES
        import webgrab.server_http as mod

        old_dir = _CACHE_DIR
        old_max = _CACHE_MAX_BYTES
        mod._CACHE_DIR = tmp_path
        mod._CACHE_MAX_BYTES = 1000  # 1KB limit
        try:
            # Write enough data to exceed limit
            for i in range(20):
                _cache_put(f"https://example.com/{i}", "md", {"data": "x" * 200})
            _cache_evict_if_needed()
            # Some files should have been evicted
            files = list(tmp_path.rglob("*"))
            files = [f for f in files if f.is_file()]
            assert len(files) < 20
        finally:
            mod._CACHE_DIR = old_dir
            mod._CACHE_MAX_BYTES = old_max


class TestFlareSolverr:
    """Test flaresolverr method (integration - requires service)."""

    def test_flaresolverr_not_running(self):
        from webgrab.server_http import try_flaresolverr

        result, err = try_flaresolverr("https://example.com", timeout=5)
        # Should fail gracefully when flaresolverr isn't running
        assert result is None
        assert err is not None


class TestFetchWithCache:
    """Test that fetch_url uses and populates cache."""

    def test_second_fetch_is_cached(self, tmp_path):
        import webgrab.server_http as mod

        old = mod._CACHE_DIR
        mod._CACHE_DIR = tmp_path
        try:
            result1 = mod.fetch_url("https://example.com", fmt="text", timeout=10)
            if result1["success"]:
                result2 = mod.fetch_url("https://example.com", fmt="text", timeout=10)
                assert result2.get("from_cache") is True
        finally:
            mod._CACHE_DIR = old


class TestMCPServer:
    """Test MCP server setup."""

    def test_server_name(self):
        """Test server has correct name."""
        assert mcp.name == "webgrab"

    @pytest.mark.skip(reason="fastmcp 3.x API differs - tools registered differently")
    def test_server_has_tools(self):
        """Test server has fetch and extract tools."""
        pass

    @pytest.mark.skip(reason="fastmcp 3.x API differs - tools registered differently")
    def test_fetch_tool_exists(self):
        """Test fetch tool is registered."""
        pass

    @pytest.mark.skip(reason="fastmcp 3.x API differs - tools registered differently")
    def test_extract_tool_exists(self):
        """Test extract tool is registered."""
        pass
