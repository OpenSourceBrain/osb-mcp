#!/usr/bin/env python3
"""
OSB tools for the OSB MCP server

File: osb_mcp/tools/osb_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import asyncio
import logging
from typing import Any

import httpx
from cachetools import TTLCache
from fastmcp import Context
from fastmcp.tools import ToolResult
from klea_utils.mcp.registry import tool_meta
from klea_utils.mcp.schemas import ToolInfo
from klea_utils.mcp.tool_result import to_result
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

logger = logging.getLogger(__name__)

MAX_RESULTS = 20
SEARCH_TIMEOUT = httpx.Timeout(30)

# Cache for OSBv2 search results (2 hour TTL, max 100 entries)
OSBv2_SEARCH_CACHE: TTLCache[str, Any] = TTLCache(maxsize=100, ttl=7200)


@retry(
    wait=wait_random_exponential(multiplier=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
    reraise=True,
)
async def _search_osbv2_repos(session, url, query, content_types, user_id, max_num):
    """Search OSBv2 repositories with retry logic."""
    response = await session.get(
        url,
        params={
            "q": query,
            "types": content_types,
            "user_id": user_id,
            "page": 1,
            "per_page": max_num,
        },
        timeout=SEARCH_TIMEOUT,
        follow_redirects=True,
    )
    logger.debug(f"{response.request = }")
    response.raise_for_status()
    return response.json()


@tool_meta(
    ToolInfo(
        title="Find repositories on Open Source Brain",
        tags={"osb", "disabled", "repositories"},
        read_only=True,
        open_world=True,
    )
)
async def get_repositories_from_open_source_brain(
    ctx: Context,
    search_query: str,
    search_data: bool = True,
    search_models: bool = True,
    num: int = 5,
) -> ToolResult:
    """Search the Open Source Brain (v2) platform for model and data repositories.

    Use this tool to find neuroscience projects and repositories indexed from
    archival platforms (GitHub, DANDI Archive, FigShare), containing
    computational models (NeuroML, NEURON, NetPyNE, Brian, etc.) and
    experimental data (often NWB). Results include the URLs to the projects'
    file storage locations, which can be passed to other tools to download
    files.

    Use when:
    - Finding neuroscience models or data by topic.
    - Locating repository URLs to download files from.

    Do not use for:
    - Directly downloading files (use the download tools instead).

    Example: get_repositories_from_open_source_brain(search_query="cerebellum")

    Args:
        search_query: search term for querying Open Source Brain. Must be
            non-empty.
        search_data: true if data related repositories should be searched.
        search_models: true if modelling related repositories should be searched.
        num: number of search results to get (clamped to 1-20).

    Returns:
        Dictionary of repository information.
    """
    search_query = search_query.strip()
    if not search_query:
        return to_result({"Error": "search_query must be a non-empty string"})
    logger.debug(f"{search_query = }")

    num = max(1, min(num, MAX_RESULTS))

    session: httpx.AsyncClient = ctx.lifespan_context["http_session"]
    if session is None:
        return to_result({"Error": "OSB session not initialized"})

    # swagger-dev: https://workspaces.v2dev.opensourcebrain.org/api/ui/
    # swagger: https://workspaces.v2.opensourcebrain.org/api/ui/
    osb_repo_search_url = (
        "https://v2.opensourcebrain.org/proxy/workspaces/api/osbrepository"
    )

    # OSB Admin user id: we limit the search to repositories added by the Admin only
    user_id = "7aafb661-2f39-4683-8f35-528de0752dd7"
    query = f"name={search_query}+summary__like=%{search_query}%"

    if search_data and search_models:
        content_types = "experimental+modeling"
    elif search_data:
        content_types = "experimental"
    else:
        content_types = "modeling"

    repositories: dict[str, Any] = {}

    logger.debug(f"Searching OSBv2 repositories with query: {query}")

    cache_key = f"{search_query}+{content_types}"

    if search_query in OSBv2_SEARCH_CACHE:
        logger.debug(f"Cache hit for search: {cache_key}")
        res = OSBv2_SEARCH_CACHE[cache_key]
    else:
        try:
            res = await _search_osbv2_repos(
                session,
                osb_repo_search_url,
                query,
                content_types,
                user_id,
                max_num=num,
            )
            OSBv2_SEARCH_CACHE[cache_key] = res
        except (httpx.HTTPError, TimeoutError) as e:
            error_text = f"Error searching OSBv2: {e.__class__.__name__}: {e}"
            logger.error(error_text)
            return to_result({"Error": error_text})

    # Process up to num results
    logger.debug(f"{res =}")
    results = res["osbrepositories"]

    for i, m in enumerate(results[:num]):
        mcopy = m.copy()

        # remove user information
        del mcopy["user"]

        repositories[m.get("id", f"unknown_{i}")] = mcopy

    return to_result(repositories)
