#!/usr/bin/env python3
"""Unit tests for webgrab - mocked, no network needed."""

import io
import subprocess
import sys
import urllib.request
from unittest.mock import MagicMock, patch

from webgrab import (
    METHODS,
    extract_text,
    html_to_basic_md,
    log,
    main,
    try_chrome_headless,
    try_jina,
    try_requests,
)

# -- helpers --


def _fake_resp(body: bytes, status: int = 200):
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.code = status
    return resp


def _long_html(n: int = 300) -> str:
    return "<p>" + "x" * n + "</p>"


def _mock_method(html_or_none, err=None):
    return lambda url, timeout=15: (html_or_none, err)


def _run_main(argv):
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    with patch("sys.argv", ["webgrab"] + argv), patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
        try:
            main()
            code = 0
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
    return stdout_buf.getvalue(), stderr_buf.getvalue(), code


# -- try_requests --


class TestTryRequests:
    def test_success(self):
        body = b"<html><body>" + b"Hello World " * 20 + b"</body></html>"
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(body)):
            html, err = try_requests("http://example.com")
        assert html is not None
        assert err is None
        assert "Hello World" in html

    def test_short_response(self):
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(b"hi")):
            html, err = try_requests("http://example.com")
        assert html is None
        assert err == "too short"

    def test_exactly_200_chars_passes(self):
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(b"x" * 200)):
            html, err = try_requests("http://example.com")
        assert html is not None

    def test_199_chars_rejected(self):
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(b"x" * 199)):
            html, err = try_requests("http://example.com")
        assert html is None
        assert err == "too short"

    def test_connection_error(self):
        import urllib.error

        with patch.object(urllib.request, "urlopen", side_effect=urllib.error.URLError("refused")):
            html, err = try_requests("http://example.com")
        assert html is None
        assert "refused" in err

    def test_timeout(self):
        with patch.object(urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
            html, err = try_requests("http://example.com")
        assert html is None

    def test_http_403(self):
        import urllib.error

        with patch.object(
            urllib.request,
            "urlopen",
            side_effect=urllib.error.HTTPError(url="http://x", code=403, msg="Forbidden", hdrs=None, fp=None),
        ):
            html, err = try_requests("http://example.com")
        assert html is None

    def test_unicode_decode(self):
        body = b"\xff\xfe" + b"x" * 250
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(body)):
            html, err = try_requests("http://example.com")
        assert html is not None

    def test_timeout_param(self):
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(b"x" * 300)) as mo:
            try_requests("http://example.com", timeout=5)
            assert mo.call_args[1]["timeout"] == 5

    def test_user_agent(self):
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(b"x" * 300)) as mo:
            try_requests("http://example.com")
            req = mo.call_args[0][0]
            assert "Chrome" in req.headers.get("User-agent", "")


# -- try_cloudscraper --


class TestTryCloudscraper:
    def test_success(self, monkeypatch):
        import importlib

        mock_scraper = MagicMock()
        mock_resp = MagicMock(status_code=200)
        mock_resp.text = "<html><body>CF bypassed " * 15 + "</body></html>"
        mock_scraper.get.return_value = mock_resp
        mock_cs = MagicMock(create_scraper=MagicMock(return_value=mock_scraper))
        monkeypatch.setitem(sys.modules, "cloudscraper", mock_cs)
        importlib.reload(sys.modules["webgrab"])
        html, err = sys.modules["webgrab"].try_cloudscraper("http://example.com")
        assert html is not None
        assert "CF bypassed" in html

    def test_403(self, monkeypatch):
        import importlib

        mock_scraper = MagicMock()
        mock_resp = MagicMock(status_code=403, text="blocked")
        mock_scraper.get.return_value = mock_resp
        mock_cs = MagicMock(create_scraper=MagicMock(return_value=mock_scraper))
        monkeypatch.setitem(sys.modules, "cloudscraper", mock_cs)
        importlib.reload(sys.modules["webgrab"])
        html, err = sys.modules["webgrab"].try_cloudscraper("http://example.com")
        assert html is None
        assert err == "403 forbidden"

    def test_short(self, monkeypatch):
        import importlib

        mock_scraper = MagicMock()
        mock_resp = MagicMock(status_code=200, text="short")
        mock_scraper.get.return_value = mock_resp
        mock_cs = MagicMock(create_scraper=MagicMock(return_value=mock_scraper))
        monkeypatch.setitem(sys.modules, "cloudscraper", mock_cs)
        importlib.reload(sys.modules["webgrab"])
        html, err = sys.modules["webgrab"].try_cloudscraper("http://example.com")
        assert html is None
        assert err == "too short"

    def test_not_installed(self, monkeypatch):
        import importlib

        monkeypatch.setitem(sys.modules, "cloudscraper", None)
        importlib.reload(sys.modules["webgrab"])
        html, err = sys.modules["webgrab"].try_cloudscraper("http://example.com")
        assert html is None
        assert err == "cloudscraper not installed"

    def test_exception(self, monkeypatch):
        import importlib

        mock_cs = MagicMock(create_scraper=MagicMock(side_effect=RuntimeError("boom")))
        monkeypatch.setitem(sys.modules, "cloudscraper", mock_cs)
        importlib.reload(sys.modules["webgrab"])
        html, err = sys.modules["webgrab"].try_cloudscraper("http://example.com")
        assert html is None
        assert "boom" in err


# -- try_chrome_headless --


class TestTryChromeHeadless:
    def test_success(self):
        mock_result = MagicMock(stdout="<html><body>Chrome content</body></html>" * 20)
        with patch("os.path.exists", return_value=True), patch.object(subprocess, "run", return_value=mock_result):
            html, err = try_chrome_headless("http://example.com")
        assert html is not None
        assert "Chrome content" in html

    def test_not_found(self):
        with patch("os.path.exists", return_value=False):
            html, err = try_chrome_headless("http://example.com")
        assert html is None
        assert err == "chrome binary not found"

    def test_timeout(self):
        with (
            patch("os.path.exists", return_value=True),
            patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("chrome", 5)),
        ):
            html, err = try_chrome_headless("http://example.com")
        assert html is None
        assert err == "timeout"

    def test_short(self):
        mock_result = MagicMock(stdout="short")
        with patch("os.path.exists", return_value=True), patch.object(subprocess, "run", return_value=mock_result):
            html, err = try_chrome_headless("http://example.com")
        assert html is None
        assert err == "too short"

    def test_exception(self):
        with patch("os.path.exists", return_value=True), patch.object(subprocess, "run", side_effect=OSError("perm")):
            html, err = try_chrome_headless("http://example.com")
        assert html is None
        assert "perm" in err

    def test_timeout_param(self):
        mock_result = MagicMock(stdout="x" * 300)
        with (
            patch("os.path.exists", return_value=True),
            patch.object(subprocess, "run", return_value=mock_result) as mo,
        ):
            try_chrome_headless("http://example.com", timeout=10)
            assert mo.call_args[1]["timeout"] == 10

    def test_flags(self):
        mock_result = MagicMock(stdout="x" * 300)
        with (
            patch("os.path.exists", return_value=True),
            patch.object(subprocess, "run", return_value=mock_result) as mo,
        ):
            try_chrome_headless("http://example.com")
            cmd = mo.call_args[0][0]
            for flag in ("--headless", "--no-sandbox", "--disable-gpu", "--dump-dom"):
                assert flag in cmd

    def test_env_var_chrome_path(self):
        mock_result = MagicMock(stdout="x" * 300)
        with (
            patch.dict("os.environ", {"WEBGRAB_CHROME": "/custom/chrome"}),
            patch("os.path.exists", return_value=True),
            patch.object(subprocess, "run", return_value=mock_result) as mo,
        ):
            try_chrome_headless("http://example.com")
            assert "/custom/chrome" in mo.call_args[0][0][0]


# -- try_jina --


class TestTryJina:
    def test_success(self):
        with patch.object(
            urllib.request,
            "urlopen",
            return_value=_fake_resp(b"# Hello\nWorld content here " * 5),
        ):
            html, err = try_jina("http://example.com")
        assert html is not None
        assert "Hello" in html

    def test_short(self):
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(b"ok")):
            html, err = try_jina("http://example.com")
        assert html is None
        assert err == "too short"

    def test_error(self):
        import urllib.error

        with patch.object(urllib.request, "urlopen", side_effect=urllib.error.URLError("fail")):
            html, err = try_jina("http://example.com")
        assert html is None
        assert "fail" in err

    def test_url_format(self):
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(b"x" * 100)) as mo:
            try_jina("http://example.com")
            assert "r.jina.ai" in mo.call_args[0][0].full_url

    def test_accept_header(self):
        with patch.object(urllib.request, "urlopen", return_value=_fake_resp(b"x" * 100)) as mo:
            try_jina("http://example.com")
            assert mo.call_args[0][0].headers.get("Accept") == "text/plain"


# -- extract_text --


class TestExtractText:
    def test_strips_tags(self):
        r = extract_text("<html><body><p>Hello <b>World</b></p></body></html>")
        assert "Hello" in r
        assert "World" in r
        assert "<p>" not in r

    def test_removes_script(self):
        r = extract_text('<p>Visible</p><script>alert("x")</script><p>Also</p>')
        assert "Visible" in r
        assert "alert" not in r

    def test_removes_style(self):
        r = extract_text("<p>Text</p><style>body{color:red}</style><p>More</p>")
        assert "Text" in r
        assert "color" not in r

    def test_collapse_whitespace(self):
        r = extract_text("<p>one   two    three</p>")
        assert "one two three" in r
        assert "   " not in r

    def test_max_chars(self):
        r = extract_text("<p>" + "x" * 100000 + "</p>", max_chars=1000)
        assert len(r) <= 1000

    def test_empty(self):
        assert extract_text("") == ""

    def test_multiline_script(self):
        r = extract_text("<p>before</p>\n<script>\nvar x = 1;\n</script>\n<p>after</p>")
        assert "before" in r
        assert "after" in r
        assert "var x" not in r

    def test_whitespace_only(self):
        assert extract_text("<p>   </p>") == ""

    def test_nested_tags(self):
        r = extract_text("<div><p><span>deep</span></p></div>")
        assert "deep" in r


# -- html_to_basic_md --


class TestHtmlToBasicMd:
    def test_h1(self):
        assert "# Title" in html_to_basic_md("<h1>Title</h1>")

    def test_h2(self):
        assert "## Sub" in html_to_basic_md("<h2>Sub</h2>")

    def test_h3(self):
        assert "### S" in html_to_basic_md("<h3>S</h3>")

    def test_h4(self):
        assert "#### X" in html_to_basic_md("<h4>X</h4>")

    def test_link(self):
        r = html_to_basic_md('<a href="http://example.com">Click</a>')
        assert "[Click](http://example.com)" in r

    def test_link_with_attrs(self):
        r = html_to_basic_md('<a class="foo" href="/link" target="_blank">Go</a>')
        assert "[Go](/link)" in r

    def test_bold(self):
        r = html_to_basic_md("<strong>bold</strong> and <b>also</b>")
        assert "**bold**" in r
        assert "**also**" in r

    def test_italic(self):
        r = html_to_basic_md("<em>it</em> and <i>too</i>")
        assert "*it*" in r
        assert "*too*" in r

    def test_list_items(self):
        r = html_to_basic_md("<ul><li>a</li><li>b</li></ul>")
        assert "- a" in r
        assert "- b" in r

    def test_br(self):
        r = html_to_basic_md("a<br>b<br/>c")
        assert "a" in r

    def test_blockquote(self):
        r = html_to_basic_md("<blockquote>line1\nline2</blockquote>")
        assert "> line1" in r
        assert "> line2" in r

    def test_script_removed(self):
        r = html_to_basic_md("<p>keep</p><script>drop</script>")
        assert "keep" in r
        assert "drop" not in r

    def test_style_removed(self):
        r = html_to_basic_md("<p>keep</p><style>.x{}</style>")
        assert "keep" in r

    def test_max_chars(self):
        r = html_to_basic_md("<p>" + "x" * 100000 + "</p>", max_chars=500)
        assert len(r) <= 500

    def test_empty(self):
        assert html_to_basic_md("") == ""

    def test_complex(self):
        html = "<h1>T</h1><p><strong>B</strong> <a href='/l'>link</a></p><ul><li>1</li></ul><blockquote>q</blockquote>"
        r = html_to_basic_md(html)
        assert "# T" in r
        assert "**B**" in r
        assert "[link](/l)" in r
        assert "- 1" in r
        assert "> q" in r

    def test_h5_h6_no_header(self):
        r = html_to_basic_md("<h5>five</h5><h6>six</h6>")
        assert "# five" not in r
        assert "five" in r


# -- log --


class TestLog:
    def test_writes_stderr(self):
        buf = io.StringIO()
        with patch("sys.stderr", buf):
            log("test")
        assert "test" in buf.getvalue()


# -- main --


class TestMain:
    def test_no_args_exits_2(self):
        _, _, code = _run_main([])
        assert code == 2

    def test_all_fail_exits_1(self):
        fake = [
            ("a", _mock_method(None, "f")),
            ("b", _mock_method(None, "f")),
            ("c", _mock_method(None, "f")),
            ("d", _mock_method(None, "f")),
        ]
        with patch("webgrab.METHODS", fake):
            _, _, code = _run_main(["http://x.com"])
        assert code == 1

    def test_success_exits_0(self):
        fake = [("req", _mock_method(_long_html()))]
        with patch("webgrab.METHODS", fake):
            _, _, code = _run_main(["http://x.com"])
        assert code == 0

    def test_html_format(self):
        html = "<html><body>hi</body></html>" * 20
        fake = [("req", _mock_method(html))]
        with patch("webgrab.METHODS", fake):
            out, _, code = _run_main(["http://x.com", "--format", "html"])
        assert code == 0
        assert "<html>" in out

    def test_text_format(self):
        html = "<html><body><p>Hello World</p></body></html>" * 20
        fake = [("req", _mock_method(html))]
        with patch("webgrab.METHODS", fake):
            out, _, code = _run_main(["http://x.com", "--format", "text"])
        assert code == 0
        assert "Hello World" in out
        assert "<html>" not in out

    def test_markdown_default(self):
        html = "<h1>Title</h1>" * 20
        fake = [("req", _mock_method(html))]
        with patch("webgrab.METHODS", fake):
            out, _, code = _run_main(["http://x.com"])
        assert code == 0
        assert "# Title" in out

    def test_timeout_flag(self):
        call_log: list[int] = []

        def spy(url, timeout=15):
            call_log.append(timeout)
            return _long_html(), None

        fake = [("req", spy)]
        with patch("webgrab.METHODS", fake):
            _run_main(["http://x.com", "--timeout", "5"])
        assert call_log == [5]

    def test_cascade_stops_on_first(self):
        call_log: list[str] = []

        def fail(*a, **k):
            call_log.append("req")
            return None, "f"

        def succeed(*a, **k):
            call_log.append("cs")
            return _long_html(), None

        fake = [("req", fail), ("cs", succeed), ("jina", fail)]
        with patch("webgrab.METHODS", fake):
            _run_main(["http://x.com"])
        assert call_log == ["req", "cs"]

    def test_cascade_falls_through(self):
        call_log: list[str] = []

        def fail1(*a, **k):
            call_log.append("req")
            return None, "f"

        def succeed1(*a, **k):
            call_log.append("cs")
            return _long_html(), None

        def never(*a, **k):
            call_log.append("jina")
            return None, "f"

        fake = [("req", fail1), ("cs", succeed1), ("jina", never)]
        with patch("webgrab.METHODS", fake):
            _run_main(["http://x.com"])
        assert call_log == ["req", "cs"]

    def test_unknown_flag_ignored(self):
        fake = [("req", _mock_method(_long_html()))]
        with patch("webgrab.METHODS", fake):
            _, _, code = _run_main(["http://x.com", "--bogus", "val"])
        assert code == 0

    def test_stderr_logging(self):
        fake = [("req", _mock_method(_long_html()))]
        with patch("webgrab.METHODS", fake):
            _, err, _ = _run_main(["http://x.com"])
        assert "webgrab" in err

    def test_exception_caught(self):
        def boom(*a, **k):
            raise RuntimeError("kaboom")

        fake = [("req", boom), ("cs", _mock_method(_long_html()))]
        with patch("webgrab.METHODS", fake):
            _, _, code = _run_main(["http://x.com"])
        assert code == 0


# -- module checks --


class TestModule:
    def test_public_api(self):
        for name in (
            "try_requests",
            "try_cloudscraper",
            "try_jina",
            "try_chrome_headless",
            "extract_text",
            "html_to_basic_md",
            "log",
            "main",
        ):
            assert callable(getattr(sys.modules["webgrab"], name)), f"{name} not callable"

    def test_methods_count(self):
        assert len(METHODS) == 4

    def test_method_names(self):
        assert [m[0] for m in METHODS] == [
            "requests",
            "cloudscraper",
            "jina",
            "chrome-headless",
        ]
