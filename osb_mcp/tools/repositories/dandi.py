#!/usr/bin/env python3
"""
DANDI Archive tools for the OSB MCP server.

File: osb_mcp/tools/repositories/dandi.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import logging
from typing import Annotated

from fastmcp import Context
from fastmcp.tools import ToolResult
from klea_utils.mcp.registry import tool_meta
from klea_utils.mcp.schemas import ToolInfo
from klea_utils.mcp.tool_impls.repositories.dandi import (
    dandi_list_files,
    dandi_list_versions,
)
from klea_utils.mcp.tool_result import to_result
from pydantic import Field

from ._common import _session

logger = logging.getLogger(__name__)


@tool_meta(
    ToolInfo(
        title="List versions of a DANDI dandiset",
        tags={"osb", "dandi", "versions"},
        read_only=True,
        open_world=True,
    )
)
async def list_dandi_versions(
    ctx: Context,
    url: Annotated[str, Field(min_length=1)],
) -> ToolResult:
    """List the available versions of a DANDI dandiset.

    Use this tool to discover which versions (including the working draft)
    a DANDI dandiset offers before listing its files.

    Use when:
    - Finding the versions of a DANDI dandiset.

    Do not use for:
    - Listing files (use the list_dandi_files tool instead).

    Example: list_dandi_versions(url="https://dandiarchive.org/dandiset/000025")

    Args:
        url: DANDI dandiset URL (https://dandiarchive.org/dandiset/<id>).

    Returns:
        Dictionary with source, url, versions, and an empty files list.
    """
    session = _session(ctx)
    if session is None:
        return to_result({"Error": "HTTP session not initialized"})
    result = await dandi_list_versions(session=session, url=url)
    return to_result(result)


@tool_meta(
    ToolInfo(
        title="List files of a DANDI dandiset",
        tags={"osb", "dandi", "files"},
        read_only=True,
        open_world=True,
    )
)
async def list_dandi_files(
    ctx: Context,
    url: Annotated[str, Field(min_length=1)],
    version: Annotated[
        str | None,
        Field(
            description="Version to list (e.g. draft or a published version). Defaults to draft."
        ),
    ] = None,
) -> ToolResult:
    """List the files of a DANDI dandiset at a given version.

    Use this tool to get the file list of a DANDI dandiset so files can be
    downloaded, e.g. before passing the result to the download_files tool.

    Use when:
    - Finding what files a DANDI dandiset contains.

    Do not use for:
    - Downloading files (use the download_files tool instead).
    - Listing versions (use the list_dandi_versions tool instead).

    Example: list_dandi_files(url="https://dandiarchive.org/dandiset/000025")

    Args:
        url: DANDI dandiset URL (https://dandiarchive.org/dandiset/<id>).
        version: Version to list (e.g. draft or a published version).
            Defaults to draft.

    Returns:
        Dictionary with source, url, version, files (path, name,
        download_url, size), and error.
    """
    session = _session(ctx)
    if session is None:
        return to_result({"Error": "HTTP session not initialized"})
    result = await dandi_list_files(session=session, url=url, version=version)
    return to_result(result)
