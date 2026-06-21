"""Browser tools: provision/release a remote stealth Chromium and drive it.

Driving tools operate on the active page of a session (default: the sole active
session). State-changing tools return a fresh AI snapshot so the agent always
sees the up-to-date page. Element targeting uses ``ref`` values from the latest
``browser_snapshot``.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Literal, Optional

from mcp.server.fastmcp import Context, FastMCP, Image
from mcp.server.fastmcp.exceptions import ToolError
from playwright.async_api import Error as PlaywrightError

from ..errors import map_errors
from ..session import BrowserSession, SessionManager
from ..snapshot import locate_ref, snapshot_payload, truncate


def _mgr(ctx: Context) -> SessionManager:
    return ctx.request_context.lifespan_context["mgr"]


def _cfg(ctx: Context):
    return ctx.request_context.lifespan_context["cfg"]


def _brief(sess: BrowserSession) -> dict:
    return {
        "session_id": sess.session_id,
        "browser_id": sess.browser_id,
        "url": sess.page.url,
        "connected": sess.is_connected(),
    }


async def _ref_action(
    sess: BrowserSession, element: str, ref: str, action: Callable[..., Awaitable], cfg
) -> dict:
    """Run a locator action by ref; on failure re-snapshot and raise with guidance."""
    loc = locate_ref(sess.page, ref)
    try:
        await action(loc)
    except PlaywrightError as exc:
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        payload = await snapshot_payload(sess.page, cfg.snapshot_max_chars)
        raise ToolError(
            f"Could not act on {element!r} (ref={ref}): {first}. "
            f"The page may have changed; use this fresh snapshot and re-select an element.\n\n"
            f"{payload['snapshot']}"
        ) from exc
    return await snapshot_payload(sess.page, cfg.snapshot_max_chars)


def register(mcp: FastMCP) -> None:  # noqa: C901 - cohesive tool group
    # -- lifecycle ------------------------------------------------------------

    @mcp.tool()
    @map_errors
    async def browser_provision(
        ctx: Context, proxy: Optional[str] = None, geo: Optional[str] = None
    ) -> dict:
        """Provision a remote stealth Chromium and connect to it.

        Args:
            proxy: Optional proxy URL, e.g. "socks5://user:pass@host:port".
            geo: Optional geolocation — a city slug (e.g. "moskva") or
                "lat,lon" coordinates (e.g. "55.75,37.61").

        Returns session_id (pass it to other browser_* tools), browser_id, the
        current url/title, and an initial AI snapshot.
        """
        cfg = _cfg(ctx)
        sess = await _mgr(ctx).provision(proxy=proxy, geo=geo)
        payload = await snapshot_payload(sess.page, cfg.snapshot_max_chars)
        return {"session_id": sess.session_id, "browser_id": sess.browser_id, **payload}

    @mcp.tool()
    @map_errors
    async def browser_release(ctx: Context, session_id: Optional[str] = None) -> dict:
        """Release a provisioned browser back to the pool."""
        sess = _mgr(ctx).get(session_id)
        sid = sess.session_id
        await _mgr(ctx).release(sid)
        return {"released": sid}

    @mcp.tool()
    @map_errors
    async def browser_list_sessions(ctx: Context) -> dict:
        """List active provisioned browser sessions."""
        return {"sessions": [_brief(s) for s in _mgr(ctx).list_sessions()]}

    # -- navigation -----------------------------------------------------------

    @mcp.tool()
    @map_errors
    async def browser_navigate(
        ctx: Context, url: str, session_id: Optional[str] = None, timeout_ms: Optional[int] = None
    ) -> dict:
        """Navigate the active page to a URL. Returns a fresh AI snapshot."""
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            await sess.page.goto(url, timeout=timeout_ms or cfg.default_nav_timeout_ms)
            return await snapshot_payload(sess.page, cfg.snapshot_max_chars)

    @mcp.tool()
    @map_errors
    async def browser_navigate_back(ctx: Context, session_id: Optional[str] = None) -> dict:
        """Go back in history. Returns a fresh AI snapshot."""
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            await sess.page.go_back()
            return await snapshot_payload(sess.page, cfg.snapshot_max_chars)

    @mcp.tool()
    @map_errors
    async def browser_navigate_forward(ctx: Context, session_id: Optional[str] = None) -> dict:
        """Go forward in history. Returns a fresh AI snapshot."""
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            await sess.page.go_forward()
            return await snapshot_payload(sess.page, cfg.snapshot_max_chars)

    # -- observe --------------------------------------------------------------

    @mcp.tool()
    @map_errors
    async def browser_snapshot(ctx: Context, session_id: Optional[str] = None) -> dict:
        """Capture an AI accessibility snapshot of the active page.

        This is the primary way to "see" the page: it returns an ARIA tree with
        [ref=eN] markers. Use those refs with browser_click / browser_type / etc.
        """
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            return await snapshot_payload(sess.page, cfg.snapshot_max_chars)

    @mcp.tool()
    @map_errors
    async def browser_get_text(
        ctx: Context,
        session_id: Optional[str] = None,
        format: Literal["text", "html"] = "text",
        selector: Optional[str] = None,
    ) -> dict:
        """Get the page's visible text or HTML (optionally scoped to a CSS selector)."""
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            if selector:
                loc = sess.page.locator(selector).first
                raw = await (loc.inner_html() if format == "html" else loc.inner_text())
            else:
                raw = await (sess.page.content() if format == "html" else sess.page.inner_text("body"))
            content, was_truncated = truncate(raw, cfg.snapshot_max_chars)
            return {"content": content, "url": sess.page.url, "truncated": was_truncated}

    @mcp.tool()
    @map_errors
    async def browser_take_screenshot(
        ctx: Context,
        session_id: Optional[str] = None,
        full_page: bool = False,
        ref: Optional[str] = None,
    ) -> Image:
        """Take a PNG screenshot for visual verification.

        To act on elements use browser_snapshot (not this); screenshots are for
        visually confirming what the page looks like. Pass `ref` to shoot a
        single element, or full_page=true for the whole scrollable page.
        """
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            if ref:
                png = await locate_ref(sess.page, ref).screenshot(type="png")
            else:
                png = await sess.page.screenshot(full_page=full_page, type="png")
        return Image(data=png, format="png")

    @mcp.tool()
    @map_errors
    async def browser_evaluate(
        ctx: Context,
        function: str,
        session_id: Optional[str] = None,
        ref: Optional[str] = None,
    ) -> dict:
        """Evaluate a JavaScript function and return its (JSON-serializable) result.

        `function` is a JS function expression, e.g. "() => document.title" or,
        when `ref` is given, "(el) => el.textContent" receiving the element.
        """
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            if ref:
                result = await locate_ref(sess.page, ref).evaluate(function)
            else:
                result = await sess.page.evaluate(function)
            return {"result": result, "url": sess.page.url}

    # -- interact -------------------------------------------------------------

    @mcp.tool()
    @map_errors
    async def browser_click(
        ctx: Context,
        element: str,
        ref: str,
        session_id: Optional[str] = None,
        double: bool = False,
        button: Literal["left", "right", "middle"] = "left",
    ) -> dict:
        """Click an element identified by `ref` from the latest snapshot.

        `element` is a short human description (e.g. "Login button") used for
        diagnostics. Returns a fresh AI snapshot after the click.
        """
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            return await _ref_action(
                sess, element, ref,
                lambda loc: loc.click(button=button, click_count=2 if double else 1),
                cfg,
            )

    @mcp.tool()
    @map_errors
    async def browser_type(
        ctx: Context,
        element: str,
        ref: str,
        text: str,
        session_id: Optional[str] = None,
        submit: bool = False,
        clear: bool = False,
    ) -> dict:
        """Type text into the field identified by `ref`.

        Set clear=true to empty the field first, submit=true to press Enter after.
        Returns a fresh AI snapshot.
        """
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)

        async def _do(loc):
            if clear:
                await loc.fill("")
            await loc.fill(text)
            if submit:
                await loc.press("Enter")

        async with sess.lock:
            return await _ref_action(sess, element, ref, _do, cfg)

    @mcp.tool()
    @map_errors
    async def browser_fill_form(
        ctx: Context, fields: list[dict], session_id: Optional[str] = None
    ) -> dict:
        """Fill multiple form fields in one call.

        `fields` is a list of {"element": desc, "ref": ref, "value": value}.
        Returns a fresh AI snapshot.
        """
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            for f in fields:
                element = f.get("element", "field")
                ref = f["ref"]
                value = f.get("value", "")
                try:
                    await locate_ref(sess.page, ref).fill(value)
                except PlaywrightError as exc:
                    first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
                    payload = await snapshot_payload(sess.page, cfg.snapshot_max_chars)
                    raise ToolError(
                        f"Could not fill {element!r} (ref={ref}): {first}. "
                        f"Use this fresh snapshot and re-select.\n\n{payload['snapshot']}"
                    ) from exc
            return await snapshot_payload(sess.page, cfg.snapshot_max_chars)

    @mcp.tool()
    @map_errors
    async def browser_select_option(
        ctx: Context,
        element: str,
        ref: str,
        values: list[str],
        session_id: Optional[str] = None,
    ) -> dict:
        """Select one or more options in a <select> identified by `ref`."""
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            return await _ref_action(
                sess, element, ref, lambda loc: loc.select_option(values), cfg
            )

    @mcp.tool()
    @map_errors
    async def browser_hover(
        ctx: Context, element: str, ref: str, session_id: Optional[str] = None
    ) -> dict:
        """Hover over an element identified by `ref`. Returns a fresh AI snapshot."""
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            return await _ref_action(sess, element, ref, lambda loc: loc.hover(), cfg)

    @mcp.tool()
    @map_errors
    async def browser_press_key(
        ctx: Context, key: str, session_id: Optional[str] = None
    ) -> dict:
        """Press a keyboard key (e.g. "Enter", "Escape", "ArrowDown", "Control+a")."""
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            await sess.page.keyboard.press(key)
            return await snapshot_payload(sess.page, cfg.snapshot_max_chars)

    @mcp.tool()
    @map_errors
    async def browser_wait_for(
        ctx: Context,
        session_id: Optional[str] = None,
        text: Optional[str] = None,
        text_gone: Optional[str] = None,
        time_ms: Optional[int] = None,
    ) -> dict:
        """Wait for text to appear, text to disappear, or a fixed time.

        Provide exactly one of `text`, `text_gone`, or `time_ms`.
        Returns a fresh AI snapshot.
        """
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            if text is not None:
                await sess.page.get_by_text(text).first.wait_for(state="visible")
            elif text_gone is not None:
                await sess.page.get_by_text(text_gone).first.wait_for(state="hidden")
            elif time_ms is not None:
                await sess.page.wait_for_timeout(time_ms)
            else:
                raise ValueError("Provide one of: text, text_gone, time_ms.")
            return await snapshot_payload(sess.page, cfg.snapshot_max_chars)

    # -- tabs -----------------------------------------------------------------

    @mcp.tool()
    @map_errors
    async def browser_tabs(
        ctx: Context,
        action: Literal["list", "new", "close", "select"] = "list",
        session_id: Optional[str] = None,
        index: Optional[int] = None,
        url: Optional[str] = None,
    ) -> dict:
        """Manage tabs: list, open a new tab (optional url), close, or select by index.

        list returns the tab list; new/select/close return a fresh AI snapshot of
        the now-active tab.
        """
        cfg = _cfg(ctx)
        sess = _mgr(ctx).get(session_id)
        async with sess.lock:
            pages = sess.context.pages
            if action == "list":
                tabs = []
                for i, p in enumerate(pages):
                    tabs.append({"index": i, "url": p.url, "title": await p.title(),
                                 "active": p is sess.page})
                return {"tabs": tabs}

            if action == "new":
                page = await sess.context.new_page()
                page.set_default_navigation_timeout(cfg.default_nav_timeout_ms)
                page.set_default_timeout(cfg.default_action_timeout_ms)
                if url:
                    await page.goto(url)
                sess.page = page
                return await snapshot_payload(sess.page, cfg.snapshot_max_chars)

            if index is None or index < 0 or index >= len(pages):
                raise ValueError(f"index out of range (0..{len(pages) - 1}).")

            if action == "select":
                sess.page = pages[index]
                await sess.page.bring_to_front()
                return await snapshot_payload(sess.page, cfg.snapshot_max_chars)

            # action == "close"
            target = pages[index]
            await target.close()
            remaining = sess.context.pages
            if not remaining:
                raise ToolError("Closed the last tab; provision a new browser or open a tab.")
            if target is sess.page or sess.page not in remaining:
                sess.page = remaining[-1]
            return await snapshot_payload(sess.page, cfg.snapshot_max_chars)
