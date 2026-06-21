"""Map SDK / Playwright exceptions to clean MCP ToolErrors.

FastMCP surfaces ``ToolError`` message text to the agent while masking other
exceptions, so we translate every known failure into an actionable message.
Full tracebacks are logged to stderr.
"""

from __future__ import annotations

import functools
import logging
from typing import Awaitable, Callable, TypeVar

from dawg_sdk import AuthError, BaasError, BrowserNotReadyError, RateLimitError
from mcp.server.fastmcp.exceptions import ToolError
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("dawg_mcp")

T = TypeVar("T")


def map_errors(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """Decorator: translate known exceptions into ``ToolError`` for tool bodies.

    ``ToolError`` raised inside ``fn`` is passed through unchanged (tools that
    build a richer message, e.g. a stale-ref re-snapshot, raise it directly).
    """

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs) -> T:
        try:
            return await fn(*args, **kwargs)
        except ToolError:
            raise
        except AuthError as exc:
            raise ToolError(
                "Authentication failed: invalid or missing DAWG_API_KEY. "
                "Check the API key in your MCP client env block."
            ) from exc
        except RateLimitError as exc:
            retry = getattr(exc, "retry_after", 60)
            raise ToolError(
                f"Rate limited by DAWG; retry after ~{retry}s."
            ) from exc
        except BrowserNotReadyError as exc:
            raise ToolError(
                f"Browser did not become ready in time ({exc}). "
                "Retry browser_provision; the pool may be saturated."
            ) from exc
        except PlaywrightTimeoutError as exc:
            raise ToolError(
                f"Operation timed out: {exc}. The page may still be loading — "
                "retry, increase timeout_ms, or take a fresh browser_snapshot."
            ) from exc
        except PlaywrightError as exc:
            # Connection dropped, target closed, bad selector, etc.
            logger.warning("Playwright error in %s: %s", fn.__name__, exc)
            raise ToolError(
                f"Browser operation failed: {_first_line(str(exc))}. "
                "If the session was lost, release it and browser_provision again."
            ) from exc
        except BaasError as exc:
            status = getattr(exc, "status_code", None)
            suffix = f" (HTTP {status})" if status else ""
            raise ToolError(f"DAWG API error{suffix}: {exc}.") from exc
        except KeyError as exc:
            # SessionManager.get raises KeyError for unknown/ambiguous session ids.
            raise ToolError(
                f"Session error: {exc}. Call browser_list_sessions or browser_provision first."
            ) from exc
        except (RuntimeError, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _first_line(text: str) -> str:
    """Return the first non-empty line of a multi-line error message."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return text
