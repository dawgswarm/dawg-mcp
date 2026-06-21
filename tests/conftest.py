"""Shared test fixtures and lightweight fakes (no network, no real browser)."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from dawg_sdk import ScrapeResult
from mcp.server.fastmcp import FastMCP

from dawg_mcp.config import Config
from dawg_mcp.tools import register_all


class FakeLocator:
    def __init__(self, selector: str):
        self.selector = selector


class FakePage:
    """Minimal async Page stand-in for snapshot/tool tests."""

    def __init__(
        self,
        url: str = "https://example.com",
        title: str = "Example",
        snapshot: str = '- button "OK" [ref=e3]\n- textbox "Name" [ref=e4]',
    ):
        self.url = url
        self._title = title
        self._snapshot = snapshot

    async def title(self) -> str:
        return self._title

    async def aria_snapshot(self, mode=None, **kwargs) -> str:
        return self._snapshot

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(selector)


class FallbackPage(FakePage):
    """Page whose aria_snapshot rejects mode= (older Playwright)."""

    async def aria_snapshot(self, mode=None, **kwargs) -> str:
        if mode is not None:
            raise TypeError("aria_snapshot() got an unexpected keyword argument 'mode'")
        return "fallback-snapshot"


class FakeSession:
    def __init__(self, session_id: str = "sess-1", browser_id: str = "browser-0"):
        self.session_id = session_id
        self.browser_id = browser_id
        self.page = FakePage()

    def is_connected(self) -> bool:
        return True


class FakeScraper:
    async def scrape(self, url, **kwargs) -> ScrapeResult:
        return ScrapeResult(success=True, url=url, content="hello world", status_code=200)


class FakeManager:
    """Stand-in for SessionManager used by tool smoke tests."""

    def __init__(self):
        self._sessions = [FakeSession()]
        self._scraper = FakeScraper()

    def scraper(self):
        return self._scraper

    def list_sessions(self):
        return list(self._sessions)

    def get(self, session_id=None):
        if not self._sessions:
            raise KeyError("no active browser sessions; call browser_provision first")
        return self._sessions[0]

    async def provision(self, proxy=None, geo=None):
        return self._sessions[0]

    async def release(self, session_id):
        self._sessions = [s for s in self._sessions if s.session_id != session_id]


@pytest.fixture
def test_mcp() -> FastMCP:
    """A FastMCP app whose lifespan yields fakes instead of real resources."""

    @asynccontextmanager
    async def fake_lifespan(_app):
        yield {
            "cfg": Config(api_key="test-key", base_url="https://dawgswarm.ru"),
            "mgr": FakeManager(),
        }

    app = FastMCP("dawg-mcp-test", lifespan=fake_lifespan)
    register_all(app)
    return app
