"""Live integration tests for the workspace tools.

These tests exercise ``create_workspace`` and ``upload_files_to_workspace``
against a real, configured API instance.  They are *not* unit tests: they
require network access and a valid ``OSB_API_TOKEN``.

The whole module is skipped unless the live tests are explicitly enabled, so
it is safe to collect in CI.  There is deliberately no ``live`` marker -- the
skip condition is the single gate.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime

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

def _live_tests_enabled() -> bool:
    """Return True only when live workspace tests are explicitly enabled.

    The tests hit a real OSBv2 deployment, so they are opt-in: set
    ``OSB_LIVE_TESTS=1`` together with a usable credential (``OSB_API_TOKEN``
    or ``OSB_USERNAME``/``OSB_PASSWORD``).
    """

    if os.environ.get("OSB_LIVE_TESTS", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }:
        return False
    return bool(os.environ.get("OSB_API_TOKEN")) or bool(
        os.environ.get("OSB_USERNAME") and os.environ.get("OSB_PASSWORD")
    )


pytestmark = pytest.mark.skipif(
    not _live_tests_enabled(),
    reason=(
        "Live workspace tool tests are opt-in: set OSB_LIVE_TESTS=1 with "
        "OSB_API_TOKEN or OSB_USERNAME/OSB_PASSWORD to run them"
    ),
)


class _FakeContext:
    """Minimal stand-in for the MCP request context.

    The refactored workspace tools no longer read a shared HTTP session from
    the lifespan context: they build their own client internally, so the stub
    only needs to expose the (empty) lifespan context shape.
    """

    def __init__(self) -> None:
        self.lifespan_context = {}


@pytest.fixture
def ctx():
    """Provide the context object the refactored workspace tools expect.

    No ``MockTransport`` is used: the tools talk to the API configured via
    ``OSB_WORKSPACES_API_URL`` and read their credentials from the
    environment.
    """

    return _FakeContext()


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
