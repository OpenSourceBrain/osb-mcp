#!/usr/bin/env python3
"""
OSB SQLite tools for the OSB MCP server.

Read-only tools to inspect and query the OSB data repository index
(``osb-data-repos.sqlite``), wrapping the framework-agnostic implementations
in ``klea_utils``.  The database path is read from the ``OSB_DATA_DB_PATH``
environment variable (default ``osb-data-repos.sqlite``).

File: osb_mcp/tools/sqlite_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Annotated

from fastmcp.tools import ToolResult
from klea_utils.mcp.registry import tool_meta
from klea_utils.mcp.schemas import ToolInfo
from klea_utils.mcp.tool_impls.sqlite_query import (
    sqlite_query as sqlite_query_impl,
)
from klea_utils.mcp.tool_impls.sqlite_query import (
    sqlite_schema as sqlite_schema_impl,
)
from klea_utils.mcp.tool_result import to_result
from pydantic import Field

logger = logging.getLogger(__name__)

#: Environment variable holding the path to the OSB data database.
OSB_DATA_DB_PATH_ENV = "OSB_DATA_DB_PATH"
#: Default OSB data database path (relative to the working directory).
OSB_DATA_DB_PATH_DEFAULT = "osb-data-repos.sqlite"


def _osb_db_path() -> Path:
    """Return the resolved path to the OSB data database.

    The path is read from the ``OSB_DATA_DB_PATH`` environment variable and
    resolved against the working directory; the default is
    ``osb-data-repos.sqlite``.
    """
    return Path(
        os.environ.get(OSB_DATA_DB_PATH_ENV, OSB_DATA_DB_PATH_DEFAULT)
    ).resolve()


@tool_meta(
    ToolInfo(
        title="Query the OSB repository database",
        tags={"osb", "sqlite", "database"},
        read_only=True,
        open_world=False,
    )
)
async def query_osb_sqlite(
    sql: Annotated[
        str,
        Field(
            description="A single SELECT statement (a trailing semicolon is allowed)."
        ),
    ],
    limit: Annotated[
        int,
        Field(
            description="Maximum number of rows to return (clamped to 200).",
            ge=1,
            le=200,
        ),
    ] = 50,
) -> ToolResult:
    """Run a read-only SELECT query against the OSB repository database.

    Use this tool to answer questions from the OSB repository index
    (osb-data-repos.sqlite): the repositories indexed from archival platforms
    (GitHub, FigShare, DANDI, BioModels) and their tags.  The database is
    opened read-only, so nothing can be modified.

    Schema of osb-data-repos.sqlite:
    - repositories(id, name, uri, summary, default_context, content_types,
      repository_type, timestamp_created, timestamp_updated)
    - tags(id, tag)
    - repo_tags(repo_id, tag_id)

    Use when:
    - Answering a question from the OSB repository data (repositories, tags,
      content types).
    - Counting or filtering repositories by platform, content type, or tag.

    Do not use for:
    - Free-text search over document collections (use a retrieval store
      instead).
    - Writing or modifying data; this tool is read-only by construction.

    Example: query_osb_sqlite(sql="SELECT name, uri FROM repositories WHERE repository_type = 'github' LIMIT 5")

    Args:
        sql: A single SELECT statement (a trailing semicolon is allowed).
        limit: Maximum number of rows to return (clamped to 200).

    Returns:
        Dictionary with db_path, columns, rows, row_count, truncated, error.
    """
    db_path = _osb_db_path()
    result = await asyncio.to_thread(
        sqlite_query_impl,
        db_path=str(db_path),
        sql=sql,
        limit=limit,
        project_root=str(db_path.parent),
    )
    return to_result(result)


@tool_meta(
    ToolInfo(
        title="Inspect the OSB repository database schema",
        tags={"osb", "sqlite", "database"},
        read_only=True,
        open_world=False,
    )
)
async def list_osb_sqlite_schema() -> ToolResult:
    """List the tables and columns of the OSB repository database.

    Use this tool to confirm the schema of the OSB repository index
    (osb-data-repos.sqlite) before writing a query, e.g. to check the exact
    column names.

    Use when:
    - You need to confirm the tables or columns of the OSB database.

    Do not use for:
    - Querying data (use the query_osb_sqlite tool instead).

    Example: list_osb_sqlite_schema()

    Returns:
        Dictionary with db_path, tables, error.  ``tables`` maps each
        table/view name to its columns with declared types.
    """
    db_path = _osb_db_path()
    result = await asyncio.to_thread(
        sqlite_schema_impl,
        db_path=str(db_path),
        project_root=str(db_path.parent),
    )
    return to_result(result)
