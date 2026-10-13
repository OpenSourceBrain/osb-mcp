#!/usr/bin/env python3
"""
Download tool for the OSB MCP server.

Generic tool that downloads the file lists returned by the repository
source tools.

File: osb_mcp/tools/repositories/download.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import logging
from typing import Annotated, Any

from fastmcp import Context
from fastmcp.tools import ToolResult
from klea_utils.mcp.registry import tool_meta
from klea_utils.mcp.schemas import ToolInfo
from klea_utils.mcp.tool_impls.download_file import (
    download_files as download_files_impl,
)
from klea_utils.mcp.tool_result import to_result
from pydantic import Field

from ._common import _session

logger = logging.getLogger(__name__)


@tool_meta(
    ToolInfo(
        title="Download files",
        tags={"osb", "files", "download"},
        destructive=True,
        open_world=True,
    )
)
async def download_files(
    ctx: Context,
    files: Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "List of file entries with path and download_url, as "
                "returned by the repository list tools."
            )
        ),
    ],
    target_dir: Annotated[
        str,
        Field(
            description=(
                "Directory to download the files into. Files are written "
                "under this directory at their relative path."
            ),
            min_length=1,
        ),
    ],
    max_concurrency: Annotated[
        int,
        Field(description="Maximum number of simultaneous downloads", ge=1, le=10),
    ] = 3,
) -> ToolResult:
    """Download a list of files into a target directory.

    Use this tool to download files listed by the repository list tools
    (list_github_files, list_figshare_files, etc.).  Each file entry needs
    the path and download_url fields returned by those tools.  Individual
    failures are reported per file and do not abort the batch.

    Use when:
    - Downloading files listed by a repository list tool.

    Do not use for:
    - Listing files (use the repository list tools instead).

    Example: download_files(files=[{"path": "README.md", "download_url": "https://raw.githubusercontent.com/NeuroML/neuroklea/development/README.md"}], target_dir="downloads")

    Args:
        files: List of file entries with path and download_url, as returned
            by the repository list tools.
        target_dir: Directory to download the files into.
        max_concurrency: Maximum number of simultaneous downloads.

    Returns:
        Dictionary with results (one entry per file: path plus saved_to on
        success or error on failure) and error.
    """
    session = _session(ctx)
    if session is None:
        return to_result({"Error": "HTTP session not initialized"})
    result = await download_files_impl(
        session=session,
        files=files,
        target_dir=target_dir,
        max_concurrency=max_concurrency,
    )
    return to_result(result)
