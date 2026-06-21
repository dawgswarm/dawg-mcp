"""Account tools: current usage and plan."""

from __future__ import annotations

from mcp.server.fastmcp import Context, FastMCP

from ..errors import map_errors
from ..usage import get_usage


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    @map_errors
    async def account_usage(ctx: Context) -> dict:
        """Get the current account usage and tariff plan for the configured API key.

        Returns minute/token consumption, limits and the active plan so the agent
        can reason about remaining quota before running expensive operations.
        """
        cfg = ctx.request_context.lifespan_context["cfg"]
        return await get_usage(cfg.api_key, cfg.base_url)
