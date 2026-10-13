"""Live integration tests for the workspace tools.

These tests exercise ``create_workspace`` and ``upload_files_to_workspace``
against a real, configured API instance.  They are *not* unit tests: they
require network access and a valid ``OSB_API_TOKEN``.

The whole module is skipped when ``OSB_API_TOKEN`` is unset, so it is safe to
collect in CI.  There is deliberately no ``live`` marker -- the skip condition
is the single gate.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from osb_mcp.tools.workspace_tools import (
    create_workspace,
    delete_resource,
    delete_workspace,
    get_workspace,
    get_workspaces,
    upload_files_to_workspace,
)

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.skipif(
    not os.environ.get("OSB_API_TOKEN")
    and not (os.environ.get("OSB_USERNAME") and os.environ.get("OSB_PASSWORD")),
    reason=(
        "Neither OSB_API_TOKEN nor OSB_USERNAME/OSB_PASSWORD are set; "
        "skipping live workspace tool tests"
    ),
)


class _FakeContext:
    """Minimal stand-in for the MCP request context.

    The workspace tools read the shared HTTP session from
    ``ctx.lifespan_context["http_session"]``.  This object exposes exactly that
    shape so the tools can be driven directly from a test.
    """

    def __init__(self, http_session: httpx.AsyncClient) -> None:
        self.lifespan_context = {"http_session": http_session}


@pytest.fixture
async def ctx():
    """Provide a real ``httpx.AsyncClient`` wrapped in a context object.

    No ``MockTransport`` is used: the client talks to the API configured via
    ``OSB_WORKSPACES_API_URL`` (the tools read the base URL themselves).
    """

    async with httpx.AsyncClient(timeout=30.0) as client:
        yield _FakeContext(client)


def _unique_name(prefix: str = "live-test") -> str:
    """Return a collision-resistant workspace name."""

    stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{stamp}-{uuid.uuid4().hex[:8]}"


async def test_create_workspace(ctx):
    """Happy path: create a workspace with a unique name."""

    name = _unique_name()
    result = await create_workspace(ctx, name=name, description="A live test workspace")

    assert not result.is_error
    workspace = result.structured_content
    assert workspace.get("id")
    assert workspace.get("name") == name


async def test_upload_files_to_workspace(ctx):
    """Happy path: create a workspace, then upload a file into it."""

    name = _unique_name("live-upload")
    create_result = await create_workspace(
        ctx, name=name, description="A live upload test workspace"
    )
    assert not create_result.is_error
    workspace = create_result.structured_content
    workspace_id = workspace["id"]

    files = [
        {
            "name": "hello.txt",
            "path": "https://example.org/hello.txt",
        }
    ]

    result = await upload_files_to_workspace(
        ctx, workspace_id=workspace_id, files=files
    )

    assert not result.is_error


async def _wait_for_resource(ctx, workspace_id: int, timeout: float = 120.0):
    """Poll ``get_workspace`` until the workspace has a real resource.

    ``POST /workspace/{id}/import`` is asynchronous: it returns immediately
    and the resource only appears once the import has run.  Until then the
    workspace may report no resources at all, or a placeholder resource
    whose ``id`` is ``-1``.  Poll until a resource with a real id is
    present, or fail the test if none shows up in time.
    """

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        result = await get_workspace(ctx, workspace_id=workspace_id)
        assert not result.is_error
        resources = result.structured_content.get("resources") or []
        real_resources = [
            resource for resource in resources if resource.get("id") not in (None, -1)
        ]
        if real_resources:
            return real_resources
        await asyncio.sleep(2.0)
    pytest.fail("resource did not appear in the workspace before the timeout")


async def test_workspace_lifecycle(ctx):
    """Full lifecycle: list, create, add a resource, list, delete, delete."""

    # 1. List the existing workspaces.
    list_result = await get_workspaces(ctx)
    assert not list_result.is_error
    assert "workspaces" in list_result.structured_content

    # 2. Create a new workspace.
    name = _unique_name("live-lifecycle")
    create_result = await create_workspace(
        ctx, name=name, description="A live lifecycle test workspace"
    )
    assert not create_result.is_error
    workspace = create_result.structured_content
    workspace_id = workspace["id"]
    assert workspace.get("name") == name

    try:
        # 3. Create a resource in the workspace.
        files = [
            {
                "name": "Ih.channel.nml",
                "path": (
                    "https://raw.githubusercontent.com/OpenSourceBrain/"
                    "BlueBrainProjectShowcase/refs/heads/master/NMC/"
                    "NeuroML2/Ih.channel.nml"
                ),
            }
        ]
        upload_result = await upload_files_to_workspace(
            ctx, workspace_id=workspace_id, files=files
        )
        assert not upload_result.is_error

        # 4. List the workspace's resources (the import is asynchronous).
        resources = await _wait_for_resource(ctx, workspace_id)
        resource_id = resources[0]["id"]

        # 5. Delete the resource.
        delete_resource_result = await delete_resource(ctx, resource_id=resource_id)
        assert not delete_resource_result.is_error
    finally:
        # 6. Delete the workspace, even if the body failed.  Do not assert
        # here: a failed delete must not mask the original failure.
        delete_workspace_result = await delete_workspace(ctx, workspace_id=workspace_id)
        if delete_workspace_result.is_error:
            logger.warning(
                "Failed to delete workspace %s during cleanup: %s",
                workspace_id,
                delete_workspace_result.structured_content,
            )
