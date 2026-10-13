#!/usr/bin/env python3
"""
GitHub tools for the OSB MCP server.

File: osb_mcp/tools/repositories/github.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import logging
from typing import Annotated

from fastmcp import Context
from fastmcp.tools import ToolResult
from klea_utils.mcp.registry import tool_meta
from klea_utils.mcp.schemas import ToolInfo
from klea_utils.mcp.tool_impls.repositories.github import (
    github_list_files,
    github_list_versions,
)
from klea_utils.mcp.tool_result import to_result
from pydantic import Field

from ._common import _session

logger = logging.getLogger(__name__)


@tool_meta(
    ToolInfo(
        title="List versions of a GitHub repository",
        tags={"osb", "github", "versions"},
        read_only=True,
        open_world=True,
    )
)
async def list_github_versions(
    ctx: Context,
    url: Annotated[str, Field(min_length=1)],
) -> ToolResult:
    """List the available versions (branches and tags) of a GitHub repository.

    Use this tool to discover which branches or tags a GitHub repository
    offers before listing its files.

    Use when:
    - Finding the branches and tags of a GitHub repository.

    Do not use for:
    - Listing files (use the list_github_files tool instead).

    Example: list_github_versions(url="https://github.com/NeuroML/neuroklea")

    Args:
        url: GitHub repository URL (https://github.com/<owner>/<repo>).

    Returns:
        Dictionary with source, url, versions, and an empty files list.
    """
    session = _session(ctx)
    if session is None:
        return to_result({"Error": "HTTP session not initialized"})
    result = await github_list_versions(session=session, url=url)
    return to_result(result)


@tool_meta(
    ToolInfo(
        title="List files of a GitHub repository",
        tags={"osb", "github", "files"},
        read_only=True,
        open_world=True,
    )
)
async def list_github_files(
    ctx: Context,
    url: Annotated[str, Field(min_length=1)],
    version: Annotated[
        str | None,
        Field(description="Branch or tag to list. Defaults to the default branch."),
    ] = None,
) -> ToolResult:
    """List the files of a GitHub repository at a given branch or tag.

    Use this tool to get the file list of a GitHub repository so files can
    be downloaded, e.g. before passing the result to the download_files tool.

    Use when:
    - Finding what files a GitHub repository contains at a branch or tag.

    Do not use for:
    - Downloading files (use the download_files tool instead).
    - Listing versions (use the list_github_versions tool instead).

    Example: list_github_files(url="https://github.com/NeuroML/neuroklea")

    Args:
        url: GitHub repository URL (https://github.com/<owner>/<repo>).
        version: Branch or tag to list. Defaults to the default branch.

    Returns:
        Dictionary with source, url, version, files (path, name,
        download_url, size), and error.
    """
    session = _session(ctx)
    if session is None:
        return to_result({"Error": "HTTP session not initialized"})
    result = await github_list_files(session=session, url=url, version=version)
    return to_result(result)
