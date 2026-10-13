#!/usr/bin/env python3
"""
Tests for the OSB workspace tools.

File: tests/test_workspace_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import json
import logging

import httpx

from osb_mcp import auth
from osb_mcp.tools import workspace_tools

logger = logging.getLogger(__name__)


class _FakeContext:
    """Minimal stand-in for a fastmcp ``Context``.

    The workspace tools only read ``ctx.lifespan_context["http_session"]``,
    so a tiny object exposing that mapping is enough to exercise them
    without a running server.
    """

    def __init__(self, session):
        self.lifespan_context = {"http_session": session}


def _make_session(handler):
    """Return an ``httpx.AsyncClient`` backed by a mock transport.

    No real network access is performed: ``httpx.MockTransport`` routes
    every request through *handler*.
    """
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_workspace_tools_register():
    from fastmcp import FastMCP
    from klea_utils.mcp.registry import register_tools

    mcp = FastMCP("test")
    register_tools(mcp, [workspace_tools])
    tools = await mcp.list_tools()
    assert [t.name for t in tools] == [
        "create_workspace",
        "delete_resource",
        "delete_workspace",
        "get_workspace",
        "get_workspaces",
        "upload_files_to_workspace",
    ]


async def test_create_workspace(monkeypatch):
    monkeypatch.setenv(
        workspace_tools.OSB_WORKSPACES_API_URL_ENV, "https://example.test/api"
    )
    monkeypatch.setenv("OSB_API_TOKEN", "test-token")
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"id": 1, "name": "My workspace"})

    session = _make_session(handler)
    ctx = _FakeContext(session)

    result = await workspace_tools.create_workspace(
        ctx, name="My workspace", description="A demo workspace"
    )
    logger.debug(f"{result = }")
    assert not result.is_error
    data = result.structured_content
    assert data["id"] == 1
    assert data["name"] == "My workspace"
    assert captured["url"] == "https://example.test/api/workspace"
    assert captured["payload"] == {
        "name": "My workspace",
        "description": "A demo workspace",
        "publicable": False,
        "featured": False,
    }
    await session.aclose()


async def test_create_workspace_empty_name():
    ctx = _FakeContext(None)

    result = await workspace_tools.create_workspace(
        ctx, name="   ", description="A demo workspace"
    )
    logger.debug(f"{result = }")
    assert "Error" in result.structured_content
    assert "name must be a non-empty string" in result.structured_content["Error"]


async def test_create_workspace_no_session():
    ctx = _FakeContext(None)

    result = await workspace_tools.create_workspace(
        ctx, name="My workspace", description="A demo workspace"
    )
    logger.debug(f"{result = }")
    assert "Error" in result.structured_content
    assert "OSB session not initialized" in result.structured_content["Error"]


async def test_upload_files_to_workspace(monkeypatch):
    monkeypatch.setenv(
        workspace_tools.OSB_WORKSPACES_API_URL_ENV, "https://example.test/api"
    )
    monkeypatch.setenv("OSB_API_TOKEN", "test-token")
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    session = _make_session(handler)
    ctx = _FakeContext(session)

    files = [{"name": "model.nml", "path": "https://example.org/model.nml"}]
    result = await workspace_tools.upload_files_to_workspace(
        ctx, workspace_id=1, files=files
    )
    logger.debug(f"{result = }")
    assert not result.is_error
    assert result.structured_content == {"status": "ok"}
    assert captured["url"] == "https://example.test/api/workspace/1/import"
    assert captured["payload"] == {"resourceorigins": files}
    await session.aclose()


async def test_upload_files_to_workspace_empty_files():
    ctx = _FakeContext(None)

    result = await workspace_tools.upload_files_to_workspace(
        ctx, workspace_id=1, files=[]
    )
    logger.debug(f"{result = }")
    assert "Error" in result.structured_content
    assert "files must be a non-empty list" in result.structured_content["Error"]


async def test_get_workspaces(monkeypatch):
    monkeypatch.setenv(
        workspace_tools.OSB_WORKSPACES_API_URL_ENV, "https://example.test/api"
    )
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200, json={"results": [{"id": 1, "name": "My workspace"}]}
        )

    session = _make_session(handler)
    ctx = _FakeContext(session)

    result = await workspace_tools.get_workspaces(ctx, page=1, per_page=20)
    logger.debug(f"{result = }")
    assert not result.is_error
    assert result.structured_content == {"results": [{"id": 1, "name": "My workspace"}]}
    assert captured["method"] == "GET"
    assert captured["url"].split("?")[0] == "https://example.test/api/workspace"
    assert captured["params"] == {"page": "1", "per_page": "20"}
    await session.aclose()


async def test_get_workspaces_no_session():
    ctx = _FakeContext(None)

    result = await workspace_tools.get_workspaces(ctx)
    logger.debug(f"{result = }")
    assert "Error" in result.structured_content
    assert "OSB session not initialized" in result.structured_content["Error"]


async def test_delete_workspace(monkeypatch):
    monkeypatch.setenv(
        workspace_tools.OSB_WORKSPACES_API_URL_ENV, "https://example.test/api"
    )
    monkeypatch.setenv("OSB_API_TOKEN", "test-token")
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["method"] = request.method
        return httpx.Response(200, json={"status": "ok"})

    session = _make_session(handler)
    ctx = _FakeContext(session)

    result = await workspace_tools.delete_workspace(ctx, workspace_id=1)
    logger.debug(f"{result = }")
    assert not result.is_error
    assert result.structured_content == {"status": "ok"}
    assert captured["method"] == "DELETE"
    assert captured["url"] == "https://example.test/api/workspace/1"
    await session.aclose()


async def test_delete_workspace_no_session():
    ctx = _FakeContext(None)

    result = await workspace_tools.delete_workspace(ctx, workspace_id=1)
    logger.debug(f"{result = }")
    assert "Error" in result.structured_content
    assert "OSB session not initialized" in result.structured_content["Error"]


async def test_delete_resource(monkeypatch):
    monkeypatch.setenv(
        workspace_tools.OSB_WORKSPACES_API_URL_ENV, "https://example.test/api"
    )
    monkeypatch.setenv("OSB_API_TOKEN", "test-token")
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["method"] = request.method
        return httpx.Response(200, json={"status": "ok"})

    session = _make_session(handler)
    ctx = _FakeContext(session)

    result = await workspace_tools.delete_resource(ctx, resource_id=1)
    logger.debug(f"{result = }")
    assert not result.is_error
    assert result.structured_content == {"status": "ok"}
    assert captured["method"] == "DELETE"
    assert captured["url"] == "https://example.test/api/workspaceresource/1"
    await session.aclose()


async def test_delete_resource_no_session():
    ctx = _FakeContext(None)

    result = await workspace_tools.delete_resource(ctx, resource_id=1)
    logger.debug(f"{result = }")
    assert "Error" in result.structured_content
    assert "OSB session not initialized" in result.structured_content["Error"]


async def test_create_workspace_missing_credential(monkeypatch):
    monkeypatch.setenv(
        workspace_tools.OSB_WORKSPACES_API_URL_ENV, "https://example.test/api"
    )
    monkeypatch.delenv("OSB_API_TOKEN", raising=False)
    monkeypatch.delenv("OSB_USERNAME", raising=False)
    monkeypatch.delenv("OSB_PASSWORD", raising=False)
    monkeypatch.setattr(auth, "_cached_token", None)

    session = _make_session(lambda request: httpx.Response(200, json={}))
    ctx = _FakeContext(session)

    result = await workspace_tools.create_workspace(
        ctx, name="My workspace", description="A demo workspace"
    )
    logger.debug(f"{result = }")
    assert "Error" in result.structured_content
    assert "Authentication required" in result.structured_content["Error"]
    await session.aclose()


async def test_create_workspace_uses_authorization_header(monkeypatch):
    monkeypatch.setenv(
        workspace_tools.OSB_WORKSPACES_API_URL_ENV, "https://example.test/api"
    )
    monkeypatch.setenv("OSB_API_TOKEN", "env-token")
    monkeypatch.setattr(
        "fastmcp.server.dependencies.get_http_headers",
        lambda include=None: {"authorization": "Bearer header-token"},
    )
    captured = {}

    def handler(request):
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"id": 1, "name": "My workspace"})

    session = _make_session(handler)
    ctx = _FakeContext(session)

    result = await workspace_tools.create_workspace(
        ctx, name="My workspace", description="A demo workspace"
    )
    logger.debug(f"{result = }")
    assert not result.is_error
    assert captured["auth"] == "Bearer header-token"
    await session.aclose()
