#!/usr/bin/env python3
"""
OSB tools for the OSB MCP server

File: osb_mcp/tools/osb_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import asyncio
import inspect
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

from osb_mcp.auth import KeycloakAuthError, make_generated_client

try:  # pragma: no cover - depends on the generated client at runtime
    from workspaces.exceptions import ApiException
except ImportError:  # pragma: no cover
    ApiException = Exception  # type: ignore[assignment, misc]

logger = logging.getLogger(__name__)

MAX_RESULTS = 20

# Cache for OSBv2 search results (2 hour TTL, max 100 entries)
OSBv2_SEARCH_CACHE: TTLCache[str, Any] = TTLCache(maxsize=100, ttl=7200)


def _accepted_kwargs(func, params: dict[str, Any]) -> dict[str, Any]:
    """Return only the ``params`` that ``func`` accepts.

    The generated client's method signature differs between API revisions,
    so parameters the endpoint does not declare are dropped instead of
    raising ``TypeError``.
    """
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return dict(params)

    parameters = signature.parameters.values()
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters):
        return dict(params)

    names = set(signature.parameters)
    return {key: value for key, value in params.items() if key in names}


def _to_mapping(value: Any) -> dict[str, Any]:
    """Return a plain mapping for a generated-client response value."""
    if isinstance(value, dict):
        return value
    for attr in ("to_dict", "model_dump", "dict"):
        method = getattr(value, attr, None)
        if callable(method):
            try:
                mapped = method()
            except TypeError:  # pragma: no cover - unexpected signature
                continue
            if isinstance(mapped, dict):
                return mapped
    return value  # type: ignore[return-value]


@retry(
    wait=wait_random_exponential(multiplier=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
    reraise=True,
)
async def _search_osbv2_repos(ctx, query, content_types, user_id, max_num):
    """Search OSBv2 repositories through the generated API client.

    Builds the generated ``Configuration``/``ApiClient``/``RestApi`` objects
    via :func:`osb_mcp.auth.make_generated_client` and awaits the generated
    endpoint directly.
    """
    _, rest_api = make_generated_client(ctx)

    params = {
        "q": query,
        "types": content_types,
        "user_id": user_id,
        "page": 1,
        "per_page": max_num,
    }
    response = await rest_api.osbrepository_get(
        **_accepted_kwargs(rest_api.osbrepository_get, params)
    )
    return _to_mapping(response)


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

    # swagger-dev: https://workspaces.v2dev.opensourcebrain.org/api/ui/
    # swagger: https://workspaces.v2.opensourcebrain.org/api/ui/

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
                ctx,
                query,
                content_types,
                user_id,
                max_num=num,
            )
            OSBv2_SEARCH_CACHE[cache_key] = res
        except KeycloakAuthError as e:
            error_text = f"Error authenticating with OSBv2: {e}"
            logger.error(error_text)
            return to_result({"Error": error_text})
        except (httpx.HTTPError, TimeoutError, ApiException) as e:
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
