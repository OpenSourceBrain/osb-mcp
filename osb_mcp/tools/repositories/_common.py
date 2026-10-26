#!/usr/bin/env python3
"""
Shared helpers for the repository source tools.

File: osb_mcp/tools/repositories/_common.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import httpx

_http_client: "httpx.AsyncClient | None" = None


def _session(ctx=None):
    """Return a lazily created HTTP client for repository downloads.

    The client is acquired locally and is not read from the MCP lifespan, so
    the download tools do not depend on the application lifespan providing a
    shared session.  The ``ctx`` argument is accepted for backwards
    compatibility with existing callers.
    """
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient()
    return _http_client


async def close_session() -> None:
    """Close the shared HTTP client, if one was created."""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None
