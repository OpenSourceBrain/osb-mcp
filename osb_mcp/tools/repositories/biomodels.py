#!/usr/bin/env python3
"""
BioModels tools for the OSB MCP server.

File: osb_mcp/tools/repositories/biomodels.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import logging
from typing import Annotated

from fastmcp import Context
from fastmcp.tools import ToolResult
from klea_utils.mcp.registry import tool_meta
from klea_utils.mcp.schemas import ToolInfo
from klea_utils.mcp.tool_impls.repositories.biomodels import (
    biomodels_list_files,
    biomodels_list_versions,
)
from klea_utils.mcp.tool_result import to_result
from pydantic import Field

from ._common import _session

logger = logging.getLogger(__name__)


@tool_meta(
    ToolInfo(
        title="List revisions of a BioModels model",
        tags={"osb", "biomodels", "versions"},
        read_only=True,
        open_world=True,
    )
)
async def list_biomodels_versions(
    ctx: Context,
    url: Annotated[str, Field(min_length=1)],
) -> ToolResult:
    """List the available revisions of a BioModels model.

    Use this tool to discover which revisions a BioModels model offers
    before listing its files.

    Use when:
    - Finding the revisions of a BioModels model.

    Do not use for:
    - Listing files (use the list_biomodels_files tool instead).

    Example: list_biomodels_versions(url="https://www.ebi.ac.uk/biomodels/BIOMD0000000001")

    Args:
        url: BioModels model URL (e.g.
            https://www.biomodels.org/MODEL0912160000).

    Returns:
        Dictionary with source, url, versions, and an empty files list.
    """
    session = _session(ctx)
    if session is None:
        return to_result({"Error": "HTTP session not initialized"})
    result = await biomodels_list_versions(session=session, url=url)
    return to_result(result)


@tool_meta(
    ToolInfo(
        title="List files of a BioModels model",
        tags={"osb", "biomodels", "files"},
        read_only=True,
        open_world=True,
    )
)
async def list_biomodels_files(
    ctx: Context,
    url: Annotated[str, Field(min_length=1)],
    version: Annotated[
        str | None,
        Field(description="Revision number to list. Defaults to the latest revision."),
    ] = None,
) -> ToolResult:
    """List the files of a BioModels model at a given revision.

    Use this tool to get the file list of a BioModels model so files can be
    downloaded, e.g. before passing the result to the download_files tool.

    Use when:
    - Finding what files a BioModels model contains.

    Do not use for:
    - Downloading files (use the download_files tool instead).
    - Listing revisions (use the list_biomodels_versions tool instead).

    Example: list_biomodels_files(url="https://www.ebi.ac.uk/biomodels/BIOMD0000000001")

    Args:
        url: BioModels model URL (e.g.
            https://www.biomodels.org/MODEL0912160000).
        version: Revision number (as a string) to list. Defaults to the
            latest revision.

    Returns:
        Dictionary with source, url, version, files (path, name,
        download_url, size), and error.
    """
    session = _session(ctx)
    if session is None:
        return to_result({"Error": "HTTP session not initialized"})
    result = await biomodels_list_files(session=session, url=url, version=version)
    return to_result(result)
