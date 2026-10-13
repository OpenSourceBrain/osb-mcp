"""Live integration tests for the workspace tools.

These tests exercise ``create_workspace`` and ``upload_files_to_workspace``
against a real, configured API instance.  They are *not* unit tests: they
require network access and a valid ``OSB_API_TOKEN``.

The whole module is skipped when ``OSB_API_TOKEN`` is unset, so it is safe to
collect in CI.  There is deliberately no ``live`` marker -- the skip condition
is the single gate.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import httpx
import pytest

from osb_mcp.tools.workspace_tools import create_workspace, upload_files_to_workspace

pytestmark = pytest.mark.skipif(
    not os.environ.get("OSB_API_TOKEN"),
    reason="OSB_API_TOKEN is not set; skipping live workspace tool tests",
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
