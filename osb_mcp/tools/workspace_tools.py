#!/usr/bin/env python3
"""
Workspace tools for the OSB MCP server.

Tools to create workspaces and add resources to them on the Open Source
Brain (v2) platform, wrapping the Workspaces manager REST API.

File: osb_mcp/tools/workspace_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import asyncio
import json
import logging
import os
from typing import Annotated, Any

import httpx
from fastmcp import Context
from fastmcp.tools import ToolResult
from klea_utils.mcp.registry import tool_meta
from klea_utils.mcp.schemas import ToolInfo
from klea_utils.mcp.tool_result import to_result
from pydantic import Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from osb_mcp.auth import resolve_auth

logger = logging.getLogger(__name__)

#: Environment variable overriding the base URL of the OSB Workspaces
#: manager REST API.
OSB_WORKSPACES_API_URL_ENV = "OSB_WORKSPACES_API_URL"
#: Default base URL of the OSB Workspaces manager REST API.
OSB_WORKSPACES_API_URL_DEFAULT = "https://workspaces.v2.opensourcebrain.org/api"

#: Environment variable holding the bearer token used to authenticate
#: write requests to the Workspaces manager API.
OSB_API_TOKEN_ENV = "OSB_API_TOKEN"

REQUEST_TIMEOUT = httpx.Timeout(30)


def _api_base_url() -> str:
    """Return the base URL of the OSB Workspaces manager API."""
    return os.environ.get(
        OSB_WORKSPACES_API_URL_ENV, OSB_WORKSPACES_API_URL_DEFAULT
    ).rstrip("/")


def _http_error_detail(exc: Exception) -> str:
    """Return the HTTP status and response body for an HTTP status error.

    ``httpx.HTTPStatusError`` carries the failing response, whose body is
    otherwise discarded by ``raise_for_status``.  Other ``httpx.HTTPError``
    subclasses (for example ``ConnectError``) have no response, so an empty
    string is returned for them.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return f" (HTTP {exc.response.status_code}): {exc.response.text[:2000]}"
    return ""


@retry(
    wait=wait_random_exponential(multiplier=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
    reraise=True,
)
async def _post_json(session, url, payload, headers):
    """POST a JSON payload to the Workspaces manager API with retries."""
    response = await session.post(
        url,
        json=payload,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    logger.debug(f"{response.request = }")
    if response.is_error:
        logger.error(
            "HTTP %s from %s: %s",
            response.status_code,
            url,
            response.text[:2000],
        )
    response.raise_for_status()
    if response.content:
        try:
            return response.json()
        except json.JSONDecodeError:
            return {
                "status_code": response.status_code,
                "body": response.text[:2000],
            }
    return {"status_code": response.status_code}


@retry(
    wait=wait_random_exponential(multiplier=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
    reraise=True,
)
async def _get_json(session, url, params=None, headers=None):
    """GET a JSON resource from the Workspaces manager API with retries."""
    response = await session.get(
        url,
        params=params,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    logger.debug(f"{response.request = }")
    if response.is_error:
        logger.error(
            "HTTP %s from %s: %s",
            response.status_code,
            url,
            response.text[:2000],
        )
    response.raise_for_status()
    if response.content:
        try:
            return response.json()
        except json.JSONDecodeError:
            return {
                "status_code": response.status_code,
                "body": response.text[:2000],
            }
    return {"status_code": response.status_code}


@retry(
    wait=wait_random_exponential(multiplier=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((httpx.HTTPError, asyncio.TimeoutError)),
    reraise=True,
)
async def _delete_json(session, url, headers):
    """DELETE a resource from the Workspaces manager API with retries."""
    response = await session.delete(
        url,
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )
    logger.debug(f"{response.request = }")
    if response.is_error:
        logger.error(
            "HTTP %s from %s: %s",
            response.status_code,
            url,
            response.text[:2000],
        )
    response.raise_for_status()
    if response.content:
        try:
            return response.json()
        except json.JSONDecodeError:
            return {
                "status_code": response.status_code,
                "body": response.text[:2000],
            }
    return {"status_code": response.status_code}


@tool_meta(
    ToolInfo(
        title="Create a workspace on Open Source Brain",
        tags={"osb", "workspace"},
        read_only=False,
        open_world=True,
    )
)
async def create_workspace(
    ctx: Context,
    name: Annotated[str, Field(description="Name of the workspace to create.")],
    description: Annotated[
        str, Field(description="Description of the workspace to create.")
    ],
    publicable: Annotated[
        bool, Field(description="Whether the workspace is public.")
    ] = False,
    featured: Annotated[
        bool, Field(description="Whether the workspace is featured.")
    ] = False,
    license: Annotated[
        str | None, Field(description="License of the workspace.")
    ] = None,
    tags: Annotated[
        list[str] | None,
        Field(description="Tags to attach to the workspace."),
    ] = None,
) -> ToolResult:
    """Create a new workspace on the Open Source Brain (v2) platform.

    Use this tool to create a workspace on OSBv2, optionally marking it
    public or featured and attaching tags.  The workspace owner is set
    server-side to the authenticated user.

    Use when:
    - Creating a new workspace to hold models or data.
    - Setting up a workspace before adding resources to it.

    Do not use for:
    - Adding files to an existing workspace (use
      upload_files_to_workspace instead).
    - Listing or searching existing workspaces.

    Example: create_workspace(name="My workspace", description="A demo workspace")

    Args:
        name: Name of the workspace to create.
        description: Description of the workspace to create.
        publicable: Whether the workspace is public.
        featured: Whether the workspace is featured.
        license: License of the workspace.
        tags: Tags to attach to the workspace.

    Returns:
        Dictionary of the created workspace on success, or a dictionary
        with an ``Error`` key on failure.
    """
    name = name.strip()
    if not name:
        return to_result({"Error": "name must be a non-empty string"})

    session: httpx.AsyncClient = ctx.lifespan_context["http_session"]
    if session is None:
        return to_result({"Error": "OSB session not initialized"})

    headers, error = resolve_auth(ctx, required=True)
    if error is not None:
        return to_result(error)

    payload: dict[str, Any] = {
        "name": name,
        "description": description,
        "publicable": publicable,
        "featured": featured,
    }
    if license is not None:
        payload["license"] = license
    if tags:
        payload["tags"] = [{"tag": tag} for tag in tags]

    url = f"{_api_base_url()}/workspace"

    try:
        res = await _post_json(session, url, payload, headers)
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError) as e:
        error_text = (
            f"Error creating workspace: {e.__class__.__name__}: {e}"
            f"{_http_error_detail(e)}"
        )
        logger.error(error_text)
        return to_result({"Error": error_text})

    if not isinstance(res, dict):
        res = {"status": res}

    return to_result(res)


@tool_meta(
    ToolInfo(
        title="Upload files to a workspace on Open Source Brain",
        tags={"osb", "workspace"},
        read_only=False,
        open_world=True,
    )
)
async def upload_files_to_workspace(
    ctx: Context,
    workspace_id: Annotated[
        int, Field(description="ID of the workspace to add files to.")
    ],
    files: Annotated[
        list[dict[str, str]],
        Field(
            description=(
                "Files to add, each a mapping with a 'name' and a 'path' "
                "(the download URL of the file)."
            )
        ),
    ],
) -> ToolResult:
    """Add files to a workspace on the Open Source Brain (v2) platform.

    Use this tool to register files (referenced by their download URLs) as
    resources of an existing workspace.  The Workspaces manager API imports
    each resource origin into the workspace.

    Use when:
    - Adding model or data files to an existing workspace.
    - Populating a workspace from files hosted elsewhere.

    Do not use for:
    - Creating a workspace (use create_workspace instead).
    - Uploading raw file bytes; this API registers resources by URL.

    Example: upload_files_to_workspace(workspace_id=1, files=[{"name": "model.nml", "path": "https://example.org/model.nml"}])

    Args:
        workspace_id: ID of the workspace to add files to.
        files: Files to add, each a mapping with a 'name' and a 'path'
            (the download URL of the file).

    Returns:
        Dictionary with the API response on success, or a dictionary with
        an ``Error`` key on failure.
    """
    if not files:
        return to_result({"Error": "files must be a non-empty list"})

    session: httpx.AsyncClient = ctx.lifespan_context["http_session"]
    if session is None:
        return to_result({"Error": "OSB session not initialized"})

    headers, error = resolve_auth(ctx, required=True)
    if error is not None:
        return to_result(error)

    payload = {"resourceorigins": files}
    url = f"{_api_base_url()}/workspace/{workspace_id}/import"

    try:
        res = await _post_json(session, url, payload, headers)
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError) as e:
        error_text = (
            f"Error uploading files to workspace: {e.__class__.__name__}: {e}"
            f"{_http_error_detail(e)}"
        )
        logger.error(error_text)
        return to_result({"Error": error_text})

    if not isinstance(res, dict):
        res = {"status": res}

    return to_result(res)


@tool_meta(
    ToolInfo(
        title="List workspaces on Open Source Brain",
        tags={"osb", "workspace"},
        read_only=True,
        open_world=True,
    )
)
async def get_workspaces(
    ctx: Context,
    page: Annotated[
        int,
        Field(description="The page number for starting to collect the result set."),
    ] = 1,
    per_page: Annotated[int, Field(description="The number of items to return.")] = 20,
    q: Annotated[
        str | None,
        Field(
            description=(
                "The search string for filtering the workspaces, e.g. "
                "'name__like=Work%+id__=1+tags[tag]=Tag'."
            )
        ),
    ] = None,
    tags: Annotated[
        str | None,
        Field(
            description=(
                "The tags to filter with, concatenated with '+' (OR "
                "operator), e.g. 'tag1+tag2'."
            )
        ),
    ] = None,
) -> ToolResult:
    """List workspaces on the Open Source Brain (v2) platform.

    Use this tool to retrieve the workspaces available on OSBv2, optionally
    filtering them by a search string or tags and paging through the
    results.

    Use when:
    - Listing the workspaces available on OSBv2.
    - Finding the ID of a workspace before adding resources to it or
      deleting it.

    Do not use for:
    - Creating a workspace (use create_workspace instead).
    - Adding files to a workspace (use upload_files_to_workspace instead).

    Example: get_workspaces(q="name__like=Work%")

    Args:
        page: The page number for starting to collect the result set.
        per_page: The number of items to return.
        q: The search string for filtering the workspaces.
        tags: The tags to filter with, concatenated with '+' (OR operator).

    Returns:
        Dictionary of the matching workspaces and pagination on success, or
        a dictionary with an ``Error`` key on failure.
    """
    session: httpx.AsyncClient = ctx.lifespan_context["http_session"]
    if session is None:
        return to_result({"Error": "OSB session not initialized"})

    headers, _ = resolve_auth(ctx, required=False)

    params: dict[str, Any] = {"page": page, "per_page": per_page}
    if q is not None:
        params["q"] = q
    if tags is not None:
        params["tags"] = tags

    url = f"{_api_base_url()}/workspace"

    try:
        res = await _get_json(session, url, params, headers)
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError) as e:
        error_text = (
            f"Error getting workspaces: {e.__class__.__name__}: {e}"
            f"{_http_error_detail(e)}"
        )
        logger.error(error_text)
        return to_result({"Error": error_text})

    if not isinstance(res, dict):
        res = {"status": res}

    return to_result(res)


@tool_meta(
    ToolInfo(
        title="Get a workspace on Open Source Brain",
        tags={"osb", "workspace"},
        read_only=True,
        open_world=True,
    )
)
async def get_workspace(
    ctx: Context,
    workspace_id: Annotated[int, Field(description="ID of the workspace to retrieve.")],
) -> ToolResult:
    """Retrieve a workspace from the Open Source Brain (v2) platform.

    Use this tool to fetch a single workspace, including its resources, by
    its ID.

    Use when:
    - Retrieving the details of a workspace.
    - Listing the resources of a workspace before deleting one.

    Do not use for:
    - Listing all workspaces (use get_workspaces instead).
    - Creating a workspace (use create_workspace instead).

    Example: get_workspace(workspace_id=1)

    Args:
        workspace_id: ID of the workspace to retrieve.

    Returns:
        Dictionary of the workspace (including its ``resources``) on
        success, or a dictionary with an ``Error`` key on failure.
    """
    session: httpx.AsyncClient = ctx.lifespan_context["http_session"]
    if session is None:
        return to_result({"Error": "OSB session not initialized"})

    headers, _ = resolve_auth(ctx, required=False)

    url = f"{_api_base_url()}/workspace/{workspace_id}"

    try:
        res = await _get_json(session, url, headers=headers)
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError) as e:
        error_text = (
            f"Error getting workspace: {e.__class__.__name__}: {e}"
            f"{_http_error_detail(e)}"
        )
        logger.error(error_text)
        return to_result({"Error": error_text})

    if not isinstance(res, dict):
        res = {"status": res}

    return to_result(res)


@tool_meta(
    ToolInfo(
        title="Delete a workspace on Open Source Brain",
        tags={"osb", "workspace"},
        read_only=False,
        open_world=True,
    )
)
async def delete_workspace(
    ctx: Context,
    workspace_id: Annotated[int, Field(description="ID of the workspace to delete.")],
) -> ToolResult:
    """Delete a workspace on the Open Source Brain (v2) platform.

    Use this tool to permanently remove an existing workspace from OSBv2.

    Use when:
    - Deleting a workspace that is no longer needed.

    Do not use for:
    - Deleting a single resource of a workspace (use delete_resource
      instead).
    - Creating a workspace (use create_workspace instead).

    Example: delete_workspace(workspace_id=1)

    Args:
        workspace_id: ID of the workspace to delete.

    Returns:
        Dictionary with the API response on success, or a dictionary with
        an ``Error`` key on failure.
    """
    session: httpx.AsyncClient = ctx.lifespan_context["http_session"]
    if session is None:
        return to_result({"Error": "OSB session not initialized"})

    headers, error = resolve_auth(ctx, required=True)
    if error is not None:
        return to_result(error)

    url = f"{_api_base_url()}/workspace/{workspace_id}"

    try:
        res = await _delete_json(session, url, headers)
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError) as e:
        error_text = (
            f"Error deleting workspace: {e.__class__.__name__}: {e}"
            f"{_http_error_detail(e)}"
        )
        logger.error(error_text)
        return to_result({"Error": error_text})

    if not isinstance(res, dict):
        res = {"status": res}

    return to_result(res)


@tool_meta(
    ToolInfo(
        title="Delete a resource from a workspace on Open Source Brain",
        tags={"osb", "workspace"},
        read_only=False,
        open_world=True,
    )
)
async def delete_resource(
    ctx: Context,
    resource_id: Annotated[
        int, Field(description="ID of the workspace resource to delete.")
    ],
) -> ToolResult:
    """Delete a resource from a workspace on the Open Source Brain (v2) platform.

    Use this tool to permanently remove a single resource (file) from a
    workspace on OSBv2.

    Use when:
    - Deleting a resource that is no longer needed from a workspace.

    Do not use for:
    - Deleting an entire workspace (use delete_workspace instead).
    - Adding files to a workspace (use upload_files_to_workspace instead).

    Example: delete_resource(resource_id=1)

    Args:
        resource_id: ID of the workspace resource to delete.

    Returns:
        Dictionary with the API response on success, or a dictionary with
        an ``Error`` key on failure.
    """
    session: httpx.AsyncClient = ctx.lifespan_context["http_session"]
    if session is None:
        return to_result({"Error": "OSB session not initialized"})

    headers, error = resolve_auth(ctx, required=True)
    if error is not None:
        return to_result(error)

    url = f"{_api_base_url()}/workspaceresource/{resource_id}"

    try:
        res = await _delete_json(session, url, headers)
    except (httpx.HTTPError, httpx.InvalidURL, TimeoutError, ValueError) as e:
        error_text = (
            f"Error deleting resource: {e.__class__.__name__}: {e}"
            f"{_http_error_detail(e)}"
        )
        logger.error(error_text)
        return to_result({"Error": error_text})

    if not isinstance(res, dict):
        res = {"status": res}

    return to_result(res)
