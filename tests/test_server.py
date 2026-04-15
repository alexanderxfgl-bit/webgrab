#!/usr/bin/env python3
"""Tests for webgrab MCP server."""

import asyncio
from unittest.mock import patch


class TestFetchTool:
    """Test the fetch MCP tool."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_fetch_success_text(self):
        from webgrab.server import fetch

        html = "<html><body><p>Hello World</p></body></html>" * 20
        with patch("webgrab.server.try_requests", return_value=(html, None)):
            result = self._run(fetch("http://example.com", format="text"))
        assert "Hello World" in result
        assert "<html>" not in result

    def test_fetch_success_markdown(self):
        from webgrab.server import fetch

        html = "<h1>Title</h1><p>Content</p>" * 20
        with patch("webgrab.server.try_requests", return_value=(html, None)):
            result = self._run(fetch("http://example.com", format="markdown"))
        assert "# Title" in result

    def test_fetch_success_html(self):
        from webgrab.server import fetch

        html = "<html><body><p>Hello</p></body></html>" * 20
        with patch("webgrab.server.try_requests", return_value=(html, None)):
            result = self._run(fetch("http://example.com", format="html"))
        assert "<html>" in result

    def test_fetch_all_fail(self):
        from webgrab.server import fetch

        with (
            patch("webgrab.server.try_requests", return_value=(None, "blocked")),
            patch("webgrab.server.try_cloudscraper", return_value=(None, "403")),
            patch("webgrab.server.try_jina", return_value=(None, "err")),
            patch("webgrab.server.try_chrome_headless", return_value=(None, "no chrome")),
        ):
            result = self._run(fetch("http://example.com"))
        assert "Error" in result
        assert "all methods failed" in result

    def test_fetch_cascade_falls_through(self):
        from webgrab.server import fetch

        html = "<p>from jina</p>" * 30
        call_log = []

        def fake_requests(*a, **k):
            call_log.append("req")
            return None, "fail"

        def fake_cloudscraper(*a, **k):
            call_log.append("cs")
            return None, "fail"

        def fake_jina(*a, **k):
            call_log.append("jina")
            return html, None

        with (
            patch("webgrab.server.try_requests", side_effect=fake_requests),
            patch("webgrab.server.try_cloudscraper", side_effect=fake_cloudscraper),
            patch("webgrab.server.try_jina", side_effect=fake_jina),
            patch("webgrab.server.try_chrome_headless") as chrome_mock,
        ):
            result = self._run(fetch("http://example.com"))
        assert "from jina" in result
        assert call_log == ["req", "cs", "jina"]
        chrome_mock.assert_not_called()

    def test_fetch_exception_caught(self):
        from webgrab.server import fetch

        def boom(*a, **k):
            raise RuntimeError("kaboom")

        html = "<p>ok</p>" * 30
        with (
            patch("webgrab.server.try_requests", side_effect=boom),
            patch("webgrab.server.try_cloudscraper", return_value=(html, None)),
        ):
            result = self._run(fetch("http://example.com"))
        assert "ok" in result

    def test_fetch_timeout_param(self):
        from webgrab.server import fetch

        html = "<p>x</p>" * 30
        with patch("webgrab.server.try_requests", return_value=(html, None)) as mo:
            self._run(fetch("http://example.com", timeout=5))
        mo.assert_called_once_with("http://example.com", 5)

    def test_fetch_default_format_text(self):
        from webgrab.server import fetch

        html = "<html><body><p>Default</p></body></html>" * 20
        with patch("webgrab.server.try_requests", return_value=(html, None)) as mo:
            self._run(fetch("http://example.com"))
        mo.assert_called_once_with("http://example.com", 15)


class TestExtractTool:
    """Test the extract MCP tool."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_extract_text(self):
        from webgrab.server import extract

        html = "<html><body><script>drop</script><p>Keep this</p></body></html>"
        result = self._run(extract(html, format="text"))
        assert "Keep this" in result
        assert "drop" not in result
        assert "<p>" not in result

    def test_extract_markdown(self):
        from webgrab.server import extract

        html = "<h1>Title</h1><p><strong>Bold</strong> text</p>"
        result = self._run(extract(html, format="markdown"))
        assert "# Title" in result
        assert "**Bold**" in result

    def test_extract_default_text(self):
        from webgrab.server import extract

        result = self._run(extract("<p>hello</p>"))
        assert "hello" in result


class TestServerSetup:
    """Test MCP server is configured correctly."""

    def test_server_name(self):
        from webgrab.server import mcp

        assert mcp.name == "webgrab"

    def test_server_has_tools(self):
        from webgrab.server import mcp

        tools = mcp._tool_manager.list_tools()
        names = [t.name for t in tools]
        assert "fetch" in names
        assert "extract" in names

    def test_fetch_tool_has_description(self):
        from webgrab.server import mcp

        tools = mcp._tool_manager.list_tools()
        fetch_tool = next(t for t in tools if t.name == "fetch")
        assert fetch_tool.description is not None
        assert len(fetch_tool.description) > 20

    def test_extract_tool_has_description(self):
        from webgrab.server import mcp

        tools = mcp._tool_manager.list_tools()
        extract_tool = next(t for t in tools if t.name == "extract")
        assert extract_tool.description is not None
