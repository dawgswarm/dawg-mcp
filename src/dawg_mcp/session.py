"""Browser session registry and lifecycle over the DAWG SDK + Playwright.

Each provisioned browser is one ``AsyncBaas`` instance (the SDK holds a single
browser per client) paired with a live Playwright CDP connection. The
``SessionManager`` owns them all, keyed by ``session_id``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional, Union

from dawg_sdk import AsyncBaas, AsyncScraper

from .config import Config

if TYPE_CHECKING:  # pragma: no cover - type hints only
    from playwright.async_api import Browser, BrowserContext, Page, Playwright

logger = logging.getLogger("dawg_mcp")


def parse_geo(geo: Optional[str]) -> Optional[Union[str, tuple[float, float]]]:
    """Convert a geo string into the SDK's expected form.

    ``"55.75,37.61"`` -> ``(55.75, 37.61)`` (explicit coordinates);
    anything else (e.g. ``"moskva"``) is treated as a city slug.
    """
    if not geo:
        return None
    parts = geo.split(",")
    if len(parts) == 2:
        try:
            return (float(parts[0].strip()), float(parts[1].strip()))
        except ValueError:
            pass
    return geo


@dataclass
class BrowserSession:
    """A single provisioned remote browser and its Playwright state."""

    session_id: str
    browser_id: str
    baas: AsyncBaas
    browser: "Browser"
    context: "BrowserContext"
    page: "Page"
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def is_connected(self) -> bool:
        try:
            return self.browser.is_connected()
        except Exception:
            return False


class SessionManager:
    """Owns all browser sessions plus a shared, lazily-created scraper client."""

    def __init__(self, cfg: Config, pw: "Playwright") -> None:
        self.cfg = cfg
        self.pw = pw
        self._sessions: dict[str, BrowserSession] = {}
        self._provision_lock = asyncio.Lock()
        self._scraper: Optional[AsyncScraper] = None

    # -- scraper ---------------------------------------------------------------

    def scraper(self) -> AsyncScraper:
        """Return the shared AsyncScraper, creating it on first use."""
        if self._scraper is None:
            self._scraper = AsyncScraper(
                self.cfg.api_key, self.cfg.base_url, timeout=self.cfg.default_action_timeout_ms / 1000 + 60
            )
        return self._scraper

    # -- browser sessions ------------------------------------------------------

    async def provision(
        self, proxy: Optional[str] = None, geo: Optional[str] = None
    ) -> BrowserSession:
        """Provision a remote browser and connect Playwright to it over CDP."""
        async with self._provision_lock:
            if len(self._sessions) >= self.cfg.max_sessions:
                raise RuntimeError(
                    f"Max concurrent browsers reached ({self.cfg.max_sessions}). "
                    "Release one with browser_release first."
                )

        baas = AsyncBaas(
            self.cfg.api_key,
            self.cfg.base_url,
            timeout=self.cfg.provision_timeout,
            poll_interval=self.cfg.poll_interval,
        )
        # create() provisions, polls until ready, and returns a CDP ws_url with
        # an ephemeral token (or apiKey fallback) baked in.
        ws_url = await baas.create(proxy=proxy, geo=parse_geo(geo))
        try:
            browser = await self.pw.chromium.connect_over_cdp(ws_url)
        except Exception:
            # Don't leak the remote browser if the local CDP connect fails.
            await baas.release()
            await baas.close()
            raise

        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_navigation_timeout(self.cfg.default_nav_timeout_ms)
        page.set_default_timeout(self.cfg.default_action_timeout_ms)

        sess = BrowserSession(
            session_id=baas.session_id or "",
            browser_id=baas.browser_id or "",
            baas=baas,
            browser=browser,
            context=context,
            page=page,
        )
        # Newest tab/popup becomes the active page.
        context.on("page", lambda p: self._on_new_page(sess, p))
        self._sessions[sess.session_id] = sess
        logger.info("Provisioned session %s (browser %s)", sess.session_id, sess.browser_id)
        return sess

    def _on_new_page(self, sess: BrowserSession, page: "Page") -> None:
        page.set_default_navigation_timeout(self.cfg.default_nav_timeout_ms)
        page.set_default_timeout(self.cfg.default_action_timeout_ms)
        sess.page = page

    def get(self, session_id: Optional[str]) -> BrowserSession:
        """Resolve a session by id, defaulting to the sole session if unambiguous."""
        if session_id is None:
            if len(self._sessions) == 1:
                return next(iter(self._sessions.values()))
            if not self._sessions:
                raise KeyError("no active browser sessions; call browser_provision first")
            raise KeyError("session_id required: more than one active session")
        sess = self._sessions.get(session_id)
        if sess is None:
            raise KeyError(f"unknown session_id {session_id!r}")
        return sess

    def list_sessions(self) -> list[BrowserSession]:
        return list(self._sessions.values())

    async def release(self, session_id: str) -> None:
        """Release one session: close the CDP connection and the remote browser."""
        sess = self._sessions.pop(session_id, None)
        if sess is None:
            return
        try:
            await sess.browser.close()
        except Exception as exc:  # connection may already be gone
            logger.debug("browser.close() during release failed: %s", exc)
        try:
            await sess.baas.release()
        finally:
            await sess.baas.close()
        logger.info("Released session %s", session_id)

    async def shutdown(self) -> None:
        """Release all sessions and close the shared scraper client."""
        for sid in list(self._sessions):
            try:
                await self.release(sid)
            except Exception as exc:
                logger.warning("error releasing %s on shutdown: %s", sid, exc)
        if self._scraper is not None:
            try:
                await self._scraper.close()
            except Exception:
                pass
            self._scraper = None
