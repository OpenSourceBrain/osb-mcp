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


def _auth_headers() -> dict[str, str]:
    """Return the Authorization header for the Workspaces manager API.

    The bearer token is read from the ``OSB_API_TOKEN`` environment
    variable.  When it is unset an empty mapping is returned and the
    request is sent unauthenticated (the API will reject it).
    """
    token = os.environ.get(OSB_API_TOKEN_ENV)
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


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
    response.raise_for_status()
    if response.content:
        return response.json()
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
        res = await _post_json(session, url, payload, _auth_headers())
    except (httpx.HTTPError, TimeoutError) as e:
        error_text = f"Error creating workspace: {e.__class__.__name__}: {e}"
        logger.error(error_text)
        return to_result({"Error": error_text})

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

    payload = {"resourceorigins": files}
    url = f"{_api_base_url()}/workspace/{workspace_id}/import"

    try:
        res = await _post_json(session, url, payload, _auth_headers())
    except (httpx.HTTPError, TimeoutError) as e:
        error_text = f"Error uploading files to workspace: {e.__class__.__name__}: {e}"
        logger.error(error_text)
        return to_result({"Error": error_text})

    return to_result(res)
