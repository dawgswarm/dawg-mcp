import pytest

from dawg_mcp.snapshot import locate_ref, snapshot_payload, take_snapshot, truncate
from conftest import FakePage, FallbackPage


def test_truncate_under_limit():
    text, was = truncate("hello", 100)
    assert text == "hello" and was is False


def test_truncate_over_limit():
    text, was = truncate("x" * 200, 50)
    assert was is True
    assert text.startswith("x" * 50)
    assert "truncated" in text


def test_locate_ref_builds_aria_ref_selector():
    page = FakePage()
    loc = locate_ref(page, "e7")
    assert loc.selector == "aria-ref=e7"


@pytest.mark.asyncio
async def test_take_snapshot_ai_mode():
    snap = await take_snapshot(FakePage(snapshot="- button [ref=e1]"))
    assert "[ref=e1]" in snap


@pytest.mark.asyncio
async def test_take_snapshot_fallback_when_no_mode():
    snap = await take_snapshot(FallbackPage())
    assert snap == "fallback-snapshot"


@pytest.mark.asyncio
async def test_snapshot_payload_shape():
    payload = await snapshot_payload(FakePage(), max_chars=60000)
    assert set(payload) == {"url", "title", "snapshot", "snapshot_truncated"}
    assert payload["url"] == "https://example.com"
    assert payload["snapshot_truncated"] is False
