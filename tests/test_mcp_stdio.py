#!/usr/bin/env python3
"""MCP server integration tests - real stdio protocol communication."""

import asyncio
import json
import sys


async def _start_server():
    """Start webgrab MCP server as subprocess."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "from webgrab import main; main()",
        "--mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    return proc


async def _send(proc, msg: dict, timeout: float = 10) -> dict | None:
    """Send JSON-RPC message and read response."""
    data = json.dumps(msg) + "\n"
    proc.stdin.write(data.encode())
    await proc.stdin.drain()

    try:
        line = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
        if not line:
            return None
        return json.loads(line.decode())
    except TimeoutError:
        return None


async def _send_notification(proc, msg: dict) -> None:
    """Send a JSON-RPC notification (no response expected)."""
    data = json.dumps(msg) + "\n"
    proc.stdin.write(data.encode())
    await proc.stdin.drain()


async def _init_server(proc):
    """Initialize the MCP server (required before other calls)."""
    await _send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        },
    )
    await _send_notification(
        proc,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    )


class TestMCPStdio:
    """Integration tests for MCP server via actual stdio protocol."""

    def test_initialize(self):
        async def _run():
            proc = await _start_server()
            try:
                resp = await _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1.0"},
                        },
                    },
                )
                assert resp is not None, "no response from initialize"
                assert resp["jsonrpc"] == "2.0"
                assert resp["id"] == 1
                assert "capabilities" in resp["result"]
                assert resp["result"]["serverInfo"]["name"] == "webgrab"
            finally:
                proc.terminate()
                await proc.wait()

        asyncio.run(_run())

    def test_initialized_notification(self):
        async def _run():
            proc = await _start_server()
            try:
                await _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "test", "version": "1.0"},
                        },
                    },
                )
                await _send_notification(
                    proc,
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                )
                # Server should still be alive
                await asyncio.sleep(0.5)
                assert proc.returncode is None, "server crashed after initialized"
            finally:
                proc.terminate()
                await proc.wait()

        asyncio.run(_run())

    def test_tools_list(self):
        async def _run():
            proc = await _start_server()
            try:
                await _init_server(proc)
                resp = await _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
                assert resp is not None, "no response from tools/list"
                tools = resp["result"]["tools"]
                names = {t["name"] for t in tools}
                assert "fetch" in names
                assert "extract" in names

                # Fetch schema
                fetch_tool = next(t for t in tools if t["name"] == "fetch")
                props = fetch_tool["inputSchema"]["properties"]
                assert "url" in props
                assert "format" in props
                assert "timeout" in props
                assert "url" in fetch_tool["inputSchema"]["required"]

                # Extract schema
                extract_tool = next(t for t in tools if t["name"] == "extract")
                eprops = extract_tool["inputSchema"]["properties"]
                assert "html_content" in eprops
                assert "format" in eprops
                assert "html_content" in extract_tool["inputSchema"]["required"]
            finally:
                proc.terminate()
                await proc.wait()

        asyncio.run(_run())

    def test_tools_call_extract(self):
        async def _run():
            proc = await _start_server()
            try:
                await _init_server(proc)
                resp = await _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "extract",
                            "arguments": {
                                "html_content": "<h1>Title</h1><p>Hello World</p>",
                                "format": "text",
                            },
                        },
                    },
                )
                assert resp is not None, "no response from tools/call extract"
                text = resp["result"]["content"][0]["text"]
                assert "Title" in text
                assert "Hello World" in text
                assert "<h1>" not in text
            finally:
                proc.terminate()
                await proc.wait()

        asyncio.run(_run())

    def test_tools_call_extract_markdown(self):
        async def _run():
            proc = await _start_server()
            try:
                await _init_server(proc)
                resp = await _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 6,
                        "method": "tools/call",
                        "params": {
                            "name": "extract",
                            "arguments": {
                                "html_content": "<h1>Title</h1><p><strong>Bold</strong></p>",
                                "format": "markdown",
                            },
                        },
                    },
                )
                assert resp is not None
                text = resp["result"]["content"][0]["text"]
                assert "# Title" in text
                assert "**Bold**" in text
            finally:
                proc.terminate()
                await proc.wait()

        asyncio.run(_run())

    def test_tools_call_fetch_real_url(self):
        async def _run():
            proc = await _start_server()
            try:
                await _init_server(proc)
                resp = await _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 4,
                        "method": "tools/call",
                        "params": {
                            "name": "fetch",
                            "arguments": {
                                "url": "http://example.com",
                                "format": "text",
                                "timeout": 10,
                            },
                        },
                    },
                )
                assert resp is not None, "no response from tools/call fetch"
                text = resp["result"]["content"][0]["text"]
                assert "Example Domain" in text
            finally:
                proc.terminate()
                await proc.wait()

        asyncio.run(_run())

    def test_tools_call_fetch_html_format(self):
        async def _run():
            proc = await _start_server()
            try:
                await _init_server(proc)
                resp = await _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 7,
                        "method": "tools/call",
                        "params": {
                            "name": "fetch",
                            "arguments": {
                                "url": "http://example.com",
                                "format": "html",
                                "timeout": 10,
                            },
                        },
                    },
                )
                assert resp is not None
                text = resp["result"]["content"][0]["text"]
                assert "Example Domain" in text
            finally:
                proc.terminate()
                await proc.wait()

        asyncio.run(_run())

    def test_invalid_method(self):
        async def _run():
            proc = await _start_server()
            try:
                await _init_server(proc)
                resp = await _send(
                    proc,
                    {"jsonrpc": "2.0", "id": 99, "method": "nonexistent/method"},
                )
                # Server should respond with error or method not found
                if resp is not None:
                    assert resp.get("id") == 99
                # Either way server should still be alive
                await asyncio.sleep(0.3)
                assert proc.returncode is None
            finally:
                proc.terminate()
                await proc.wait()

        asyncio.run(_run())

    def test_multiple_sequential_calls(self):
        async def _run():
            proc = await _start_server()
            try:
                await _init_server(proc)

                # Call 1: extract
                r1 = await _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 10,
                        "method": "tools/call",
                        "params": {
                            "name": "extract",
                            "arguments": {"html_content": "<p>First</p>", "format": "text"},
                        },
                    },
                )
                assert r1 is not None
                assert "First" in r1["result"]["content"][0]["text"]

                # Call 2: extract
                r2 = await _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 11,
                        "method": "tools/call",
                        "params": {
                            "name": "extract",
                            "arguments": {"html_content": "<p>Second</p>", "format": "text"},
                        },
                    },
                )
                assert r2 is not None
                assert "Second" in r2["result"]["content"][0]["text"]

                # Call 3: fetch
                r3 = await _send(
                    proc,
                    {
                        "jsonrpc": "2.0",
                        "id": 12,
                        "method": "tools/call",
                        "params": {
                            "name": "fetch",
                            "arguments": {
                                "url": "http://example.com",
                                "format": "text",
                                "timeout": 10,
                            },
                        },
                    },
                )
                assert r3 is not None
                assert "Example Domain" in r3["result"]["content"][0]["text"]
            finally:
                proc.terminate()
                await proc.wait()

        asyncio.run(_run())
