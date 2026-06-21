"""Accessibility snapshots for AI agents.

Playwright's ``page.aria_snapshot(mode="ai")`` returns an ARIA tree annotated
with ``[ref=eN]`` markers — the same representation the official @playwright/mcp
server uses. Agents read the snapshot, then target elements by ``ref`` which we
resolve through Playwright's ``aria-ref=`` selector engine.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from playwright.async_api import Locator, Page


async def take_snapshot(page: "Page") -> str:
    """Return an AI-optimized ARIA snapshot with ``[ref=eN]`` markers.

    Falls back to the default aria snapshot (no refs) if the running Playwright
    build does not support ``mode="ai"``.
    """
    try:
        return await page.aria_snapshot(mode="ai")
    except TypeError:
        # Older Playwright without the `mode` kwarg.
        return await page.aria_snapshot()


def truncate(text: str, limit: int) -> tuple[str, bool]:
    """Cap text length, returning ``(text, was_truncated)``."""
    if len(text) <= limit:
        return text, False
    omitted = len(text) - limit
    return text[:limit] + f"\n... [truncated, {omitted} chars omitted]", True


def locate_ref(page: "Page", ref: str) -> "Locator":
    """Resolve a snapshot ``ref`` (e.g. ``e7``) to a Playwright Locator."""
    return page.locator(f"aria-ref={ref}")


async def snapshot_payload(page: "Page", max_chars: int) -> dict:
    """Standard ``{url, title, snapshot}`` result returned by browser tools."""
    snap, was_truncated = truncate(await take_snapshot(page), max_chars)
    return {
        "url": page.url,
        "title": await page.title(),
        "snapshot": snap,
        "snapshot_truncated": was_truncated,
    }
