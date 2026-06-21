"""End-to-end smoke test for dawg-mcp.

Drives the REAL MCP tools (over the in-memory transport, with the real server
lifespan) against the live DAWG platform. Requires a valid DAWG_API_KEY.

Run (from the repo root):
    DAWG_API_KEY=... uv run python examples/smoke_test.py
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import sys

from mcp.shared.memory import create_connected_server_and_client_session


def _data(result):
    """Extract a tool's dict payload (structuredContent or JSON text)."""
    if getattr(result, "structuredContent", None):
        return result.structuredContent
    return json.loads(result.content[0].text)


async def main() -> int:
    if not os.environ.get("DAWG_API_KEY"):
        print("DAWG_API_KEY is required for the smoke test.", file=sys.stderr)
        return 2

    from dawg_mcp.server import mcp
    from dawg_mcp.tools import register_all

    register_all(mcp)

    async with create_connected_server_and_client_session(mcp) as client:
        await client.initialize()
        tools = await client.list_tools()
        print(f"[1] {len(tools.tools)} tools available")

        prov = _data(await client.call_tool("browser_provision", {}))
        session_id = prov["session_id"]
        print(f"[2] provisioned session={session_id} browser={prov['browser_id']}")

        nav = _data(await client.call_tool("browser_navigate", {"url": "https://example.com"}))
        print(f"[3] navigated -> {nav['url']} | title={nav['title']!r}")
        assert "[ref=" in nav["snapshot"], "snapshot has no [ref=] markers"

        snap = _data(await client.call_tool("browser_snapshot", {}))
        refs = re.findall(r"\[ref=([^\]]+)\]", snap["snapshot"])
        print(f"[4] snapshot refs: {refs[:8]}")

        # Click the first link/element ref (example.com has a 'More information' link)
        link_ref = None
        for line in snap["snapshot"].splitlines():
            if "link" in line:
                m = re.search(r"\[ref=([^\]]+)\]", line)
                if m:
                    link_ref = m.group(1)
                    break
        if link_ref:
            clicked = await client.call_tool(
                "browser_click", {"element": "More information link", "ref": link_ref}
            )
            print(f"[5] clicked ref={link_ref} isError={clicked.isError}")

        # Stale-ref should produce a clean error + fresh snapshot
        stale = await client.call_tool(
            "browser_click", {"element": "bogus", "ref": "e99999"}
        )
        print(f"[6] stale-ref click isError={stale.isError} (expected True)")

        shot = await client.call_tool("browser_take_screenshot", {})
        img = next((c for c in shot.content if getattr(c, "type", "") == "image"), None)
        if img is not None:
            png = base64.b64decode(img.data)
            with open("smoke_screenshot.png", "wb") as fh:
                fh.write(png)
            print(f"[7] screenshot saved ({len(png)} bytes)")

        scraped = _data(await client.call_tool("scrape_page", {"url": "https://example.com"}))
        print(f"[8] scrape_page success={scraped['success']} len={len(scraped.get('content',''))}")

        usage = _data(await client.call_tool("account_usage", {}))
        print(f"[9] account_usage keys={list(usage)[:8]}")

        rel = _data(await client.call_tool("browser_release", {"session_id": session_id}))
        print(f"[10] released {rel['released']}")

    print("\nSMOKE TEST OK ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
