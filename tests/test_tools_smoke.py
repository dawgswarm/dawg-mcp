"""In-process tool calls against fakes via the MCP in-memory transport."""

import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session


@pytest.mark.asyncio
async def test_all_tools_registered(test_mcp):
    async with create_connected_server_and_client_session(test_mcp) as client:
        await client.initialize()
        tools = await client.list_tools()
        names = {t.name for t in tools.tools}
        assert len(names) == 24
        assert {"browser_provision", "browser_snapshot", "browser_click",
                "scrape_page", "account_usage"} <= names
        # ctx must never leak into a tool's input schema
        for t in tools.tools:
            assert "ctx" not in (t.inputSchema or {}).get("properties", {})


@pytest.mark.asyncio
async def test_browser_list_sessions_returns_fake(test_mcp):
    async with create_connected_server_and_client_session(test_mcp) as client:
        await client.initialize()
        res = await client.call_tool("browser_list_sessions", {})
        assert res.isError is False
        data = json.loads(res.content[0].text)
        assert data["sessions"][0]["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_scrape_page_through_fake_scraper(test_mcp):
    async with create_connected_server_and_client_session(test_mcp) as client:
        await client.initialize()
        res = await client.call_tool("scrape_page", {"url": "https://example.com"})
        assert res.isError is False
        data = json.loads(res.content[0].text)
        assert data["success"] is True
        assert data["content"] == "hello world"


@pytest.mark.asyncio
async def test_account_usage_maps_auth_error(test_mcp, monkeypatch):
    from dawg_sdk import AuthError

    async def boom(api_key, base_url):
        raise AuthError("Invalid API key", status_code=401)

    monkeypatch.setattr("dawg_mcp.tools.account.get_usage", boom)
    async with create_connected_server_and_client_session(test_mcp) as client:
        await client.initialize()
        res = await client.call_tool("account_usage", {})
        assert res.isError is True
        assert "DAWG_API_KEY" in res.content[0].text
