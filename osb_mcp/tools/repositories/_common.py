#!/usr/bin/env python3
"""
Shared helpers for the repository source tools.

File: osb_mcp/tools/repositories/_common.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

from fastmcp import Context


def _session(ctx: Context):
    """Return the shared HTTP session, or ``None`` when unavailable."""
    return ctx.lifespan_context.get("http_session")
