"""Environment-based configuration for the dawg-mcp server.

All settings are read once at startup. The only required value is ``DAWG_API_KEY``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "https://dawgswarm.ru"


@dataclass(frozen=True)
class Config:
    """Immutable server configuration, populated from environment variables."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    provision_timeout: float = 120.0
    poll_interval: float = 2.0
    default_nav_timeout_ms: int = 30000
    default_action_timeout_ms: int = 15000
    snapshot_max_chars: int = 60000
    max_sessions: int = 4
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        """Build a Config from environment variables.

        Raises:
            RuntimeError: if ``DAWG_API_KEY`` is not set.
        """
        api_key = os.environ.get("DAWG_API_KEY")
        if not api_key:
            raise RuntimeError(
                "DAWG_API_KEY is required. Set it in the env block of your MCP client "
                "configuration (Claude Code .mcp.json or Codex config.toml)."
            )
        return cls(
            api_key=api_key,
            base_url=os.getenv("DAWG_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
            provision_timeout=float(os.getenv("DAWG_PROVISION_TIMEOUT", "120")),
            poll_interval=float(os.getenv("DAWG_POLL_INTERVAL", "2")),
            default_nav_timeout_ms=int(os.getenv("DAWG_DEFAULT_NAV_TIMEOUT_MS", "30000")),
            default_action_timeout_ms=int(os.getenv("DAWG_DEFAULT_ACTION_TIMEOUT_MS", "15000")),
            snapshot_max_chars=int(os.getenv("DAWG_SNAPSHOT_MAX_CHARS", "60000")),
            max_sessions=int(os.getenv("DAWG_MAX_SESSIONS", "4")),
            log_level=os.getenv("DAWG_LOG_LEVEL", "INFO"),
        )
