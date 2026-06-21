"""Tool registration entry point."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register_all(mcp: FastMCP) -> None:
    """Register every tool group on the FastMCP app."""
    from . import account, browser, scraper

    browser.register(mcp)
    scraper.register(mcp)
    account.register(mcp)
