"""The single REST call not covered by the SDK: GET /api/v1/usage.

Mirrors the SDK's auth header, base_url default, error mapping and the
``{success, data}`` envelope unwrapping for consistent behavior.
"""

from __future__ import annotations

import httpx
from dawg_sdk import AuthError, BaasError, RateLimitError

from .config import DEFAULT_BASE_URL


async def get_usage(api_key: str, base_url: str = DEFAULT_BASE_URL) -> dict:
    """Fetch current account usage and plan for the given API key."""
    async with httpx.AsyncClient(headers={"X-API-Key": api_key}, timeout=30) as client:
        try:
            resp = await client.get(f"{base_url.rstrip('/')}/api/v1/usage")
        except httpx.RequestError as exc:
            raise BaasError(f"Connection failed: {exc}") from exc

    if resp.status_code == 401:
        raise AuthError("Invalid API key", status_code=401)
    if resp.status_code == 429:
        data = resp.json() if resp.text else {}
        retry = data.get("detail", {}).get("retry_after_seconds", 60)
        raise RateLimitError("Rate limit exceeded", retry_after=retry, status_code=429)
    if resp.status_code >= 400:
        raise BaasError(f"API error: {resp.status_code}", status_code=resp.status_code)

    body = resp.json() if resp.text else {}
    # Unwrap the standard {success, data} envelope, same as the SDK.
    return body.get("data", body) if isinstance(body, dict) else {"data": body}
