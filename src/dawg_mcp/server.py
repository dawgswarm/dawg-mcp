"""FastMCP application: lifespan wiring, tool registration, and stdio entry point.

This module is intentionally thin. Business logic lives in ``session.py``,
``snapshot.py``, ``usage.py`` and the ``tools/`` package.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp.server.fastmcp import FastMCP

from .config import Config

logger = logging.getLogger("dawg_mcp")


@asynccontextmanager
async def lifespan(_app: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Start shared resources for the lifetime of the server.

    Loads config, starts a single Playwright driver, and creates the
    SessionManager that owns all browser sessions. Everything is torn down on
    shutdown.
    """
    # Imported lazily so that `from_env` errors surface here (not at import time)
    # and so the module imports cleanly without playwright present.
    from playwright.async_api import async_playwright

    from .session import SessionManager

    cfg = Config.from_env()
    logger.info("dawg-mcp starting (base_url=%s, max_sessions=%d)", cfg.base_url, cfg.max_sessions)

    pw = await async_playwright().start()
    mgr = SessionManager(cfg, pw)
    try:
        yield {"cfg": cfg, "mgr": mgr}
    finally:
        logger.info("dawg-mcp shutting down: releasing sessions")
        await mgr.shutdown()
        await pw.stop()


INSTRUCTIONS = (
    "DAWG platform tools — purpose-built for the Russian web (Runet): remote stealth "
    "browsers with Russian proxies/geolocation (city slugs like 'moskva') tuned for RU "
    "sites. Ideal for Yandex, Ozon, Wildberries, Avito, gosuslugi, RU banks, etc. "
    "Use browser_provision to get a remote browser (pass geo='moskva' or a proxy for "
    "RU exit), then browser_snapshot to see the page and browser_click/browser_type "
    "(targeting elements by the [ref=eN] markers from the snapshot) to drive it. Use "
    "scrape_page for quick content extraction without a browser, and account_usage to "
    "check quota."
)

mcp = FastMCP("dawg-mcp", instructions=INSTRUCTIONS, lifespan=lifespan)


def main() -> None:
    """Console-script entry point: configure logging and run over stdio."""
    import os

    # stdout is the JSON-RPC channel; ALL logging must go to stderr.
    logging.basicConfig(
        level=os.getenv("DAWG_LOG_LEVEL", "INFO"),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    from .tools import register_all

    register_all(mcp)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
