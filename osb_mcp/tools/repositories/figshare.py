#!/usr/bin/env python3
"""
FigShare tools for the OSB MCP server.

File: osb_mcp/tools/repositories/figshare.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import logging
from typing import Annotated

from fastmcp import Context
from fastmcp.tools import ToolResult
from klea_utils.mcp.registry import tool_meta
from klea_utils.mcp.schemas import ToolInfo
from klea_utils.mcp.tool_impls.repositories.figshare import (
    figshare_list_files,
    figshare_list_versions,
)
from klea_utils.mcp.tool_result import to_result
from pydantic import Field

from ._common import _session

logger = logging.getLogger(__name__)


@tool_meta(
    ToolInfo(
        title="List versions of a FigShare article",
        tags={"osb", "figshare", "versions"},
        read_only=True,
        open_world=True,
    )
)
async def list_figshare_versions(
    ctx: Context,
    url: Annotated[str, Field(min_length=1)],
) -> ToolResult:
    """List the available versions of a FigShare article.

    Use this tool to discover which versions a FigShare article offers
    before listing its files.

    Use when:
    - Finding the versions of a FigShare article.

    Do not use for:
    - Listing files (use the list_figshare_files tool instead).

    Example: list_figshare_versions(url="https://figshare.com/articles/dataset/Title/14976822")

    Args:
        url: FigShare article URL (e.g.
            https://figshare.com/articles/dataset/<title>/<article_id>).

    Returns:
        Dictionary with source, url, versions, and an empty files list.
    """
    session = _session(ctx)
    if session is None:
        return to_result({"Error": "HTTP session not initialized"})
    result = await figshare_list_versions(session=session, url=url)
    return to_result(result)


@tool_meta(
    ToolInfo(
        title="List files of a FigShare article",
        tags={"osb", "figshare", "files"},
        read_only=True,
        open_world=True,
    )
)
async def list_figshare_files(
    ctx: Context,
    url: Annotated[str, Field(min_length=1)],
    version: Annotated[
        str | None,
        Field(
            description="Version label for the result. Defaults to the article's current version."
        ),
    ] = None,
) -> ToolResult:
    """List the files of a FigShare article.

    Use this tool to get the file list of a FigShare article so files can
    be downloaded, e.g. before passing the result to the download_files tool.

    Use when:
    - Finding what files a FigShare article contains.

    Do not use for:
    - Downloading files (use the download_files tool instead).
    - Listing versions (use the list_figshare_versions tool instead).

    Example: list_figshare_files(url="https://figshare.com/articles/dataset/Title/14976822")

    Args:
        url: FigShare article URL (e.g.
            https://figshare.com/articles/dataset/<title>/<article_id>).
        version: Version label for the result. Defaults to the article's
            current version.

    Returns:
        Dictionary with source, url, version, files (path, name,
        download_url, size), and error.
    """
    session = _session(ctx)
    if session is None:
        return to_result({"Error": "HTTP session not initialized"})
    result = await figshare_list_files(session=session, url=url, version=version)
    return to_result(result)
