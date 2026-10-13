#!/usr/bin/env python3
"""
Bibliographic tools for the OSB MCP server.

Read-only tools to resolve a DOI to its bibliographic record (title,
authors, year, journal, abstract) via the DOI resolution services in
klea_utils (Crossref, OpenAlex, Semantic Scholar).  The resolver caches
results to disk so repeated lookups never re-query the APIs.

File: osb_mcp/tools/biblio_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import asyncio
import logging
import os
from typing import Annotated

from fastmcp.tools import ToolResult
from klea_utils.biblio.doi import DoiResolver
from klea_utils.mcp.registry import tool_meta
from klea_utils.mcp.schemas import ToolInfo
from klea_utils.mcp.tool_result import to_result
from klea_utils.paths import get_cache_dir
from pydantic import Field

from osb_mcp.utils import OSB_MCP_DIRS

logger = logging.getLogger(__name__)

#: Environment variable for the polite-pool contact email sent to the
#: bibliographic APIs (raises their rate limits). Falls back to no mailto.
OSB_INGEST_MAILTO_ENV = "OSB_INGEST_MAILTO"

#: Shared resolver, created lazily on first use.
_resolver: DoiResolver | None = None


def _get_resolver() -> DoiResolver:
    """Return the shared DoiResolver, creating it on first use.

    The resolver is reused across calls so its on-disk cache
    (``doi-cache.json`` under the OSB MCP cache directory) persists between
    invocations.  The polite-pool mailto is read from ``OSB_INGEST_MAILTO``.
    """
    global _resolver
    if _resolver is None:
        _resolver = DoiResolver(
            cache_dir=str(get_cache_dir(OSB_MCP_DIRS)),
            mailto=os.environ.get(OSB_INGEST_MAILTO_ENV),
        )
    return _resolver


@tool_meta(
    ToolInfo(
        title="Resolve a DOI to its bibliographic record",
        tags={"osb", "biblio", "doi"},
        read_only=True,
        open_world=True,
    )
)
async def get_paper_by_doi(
    doi: Annotated[
        str,
        Field(
            description=(
                "A DOI, optionally wrapped in a https://doi.org/ URL or "
                "'doi:' prefix (it is normalised before resolution)."
            )
        ),
    ],
) -> ToolResult:
    """Resolve a DOI to its bibliographic record.

    Use this tool to fetch the metadata -- including the abstract -- for a
    published paper when its DOI is known.  Resolution is attempted via
    Crossref, OpenAlex and Semantic Scholar (round-robin, with fallback on
    rate limits), so a record is usually returned even if one service is
    down.  Results are cached to disk.

    Use when:
    - You have a paper's DOI (e.g. from repository metadata) and need its
      title, authors, year, journal or abstract.
    - You want to confirm a paper's details before citing it.

    Do not use for:
    - Looking up a paper by title (this tool only accepts a DOI).
    - Resolving non-DOI identifiers (arXiv, PubMed IDs are not supported).

    Example: get_paper_by_doi(doi="10.1162/neco.1997.9.8.1735")

    Args:
        doi: A DOI string (URL/prefix wrappers are normalised).

    Returns:
        Dictionary with title, authors, year, journal, abstract, doi, error.
        On failure ``error`` is set and the other fields are ``None``/empty.
    """
    record = await asyncio.to_thread(_get_resolver().resolve, doi)
    if record is None:
        return to_result(
            {
                "title": None,
                "authors": [],
                "year": None,
                "journal": None,
                "abstract": None,
                "doi": None,
                "error": f"Could not resolve DOI: {doi!r}",
            }
        )
    return to_result(
        {
            "title": record.title,
            "authors": record.authors,
            "year": record.year,
            "journal": record.journal,
            "abstract": record.abstract,
            "doi": record.doi,
            "error": "",
        }
    )
