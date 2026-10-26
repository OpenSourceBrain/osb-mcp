#!/usr/bin/env python3
"""
Tests for the workspace tools.

File: tests/test_workspace_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from klea_utils.mcp.schemas import ToolInfo

from osb_mcp.auth import KeycloakAuthError
from osb_mcp.tools import workspace_tools
from osb_mcp.tools.workspace_tools import (
    create_workspace,
    delete_resource,
    delete_workspace,
    get_workspace,
    get_workspaces,
    upload_files_to_workspace,
)

_CTX = object()


class _ModelStub:
    """Minimal stand-in for a generated-client model."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def __repr__(self) -> str:
        return f"_ModelStub({self.kwargs!r})"


class _ApiError(Exception):
    """Generated-client style error with status and reason attributes."""

    def __init__(
        self, message: str, *, status: int | None = None, reason: str = ""
    ) -> None:
        super().__init__(message)
        self.status = status
        self.reason = reason


class _StubRestApi:
    """Record awaited generated-client endpoint calls and return canned data."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self.result = {} if result is None else result
        self.calls: list[dict[str, Any]] = []

    async def _respond(self, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"endpoint": endpoint, **kwargs})
        return self.result

    async def workspace_post(self, *, workspace: Any) -> dict[str, Any]:
        return await self._respond("workspace_post", workspace=workspace)

    async def workspace_get(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        q: str | None = None,
        tags: str | None = None,
    ) -> dict[str, Any]:
        return await self._respond(
            "workspace_get", page=page, per_page=per_page, q=q, tags=tags
        )

    async def workspace_id_get(self, *, id: int) -> dict[str, Any]:
        return await self._respond("workspace_id_get", id=id)

    async def workspace_id_delete(self, *, id: int) -> dict[str, Any]:
        return await self._respond("workspace_id_delete", id=id)

    async def workspaces_controllers_workspace_controller_import_resources(
        self,
        *,
        id: int,
        workspaces_controllers_workspace_controller_import_resources_request: Any,
    ) -> dict[str, Any]:
        return await self._respond(
            "workspaces_controllers_workspace_controller_import_resources",
            id=id,
            workspaces_controllers_workspace_controller_import_resources_request=(
                workspaces_controllers_workspace_controller_import_resources_request
            ),
        )

    async def workspaceresource_id_delete(self, *, id: int) -> dict[str, Any]:
        return await self._respond("workspaceresource_id_delete", id=id)


def _patch_client(monkeypatch: Any, rest_api: Any) -> None:
    """Patch the generated-client factory used by the workspace tools."""
    monkeypatch.setattr(
        workspace_tools,
        "make_generated_client",
        lambda ctx: (None, rest_api),
    )


def _patch_models(monkeypatch: Any) -> None:
    """Patch the generated-client models used by the workspace tools."""
    monkeypatch.setattr(workspace_tools, "Workspace", _ModelStub)
    monkeypatch.setattr(workspace_tools, "Tag", _ModelStub)
    monkeypatch.setattr(workspace_tools, "ImportResourcesRequest", _ModelStub)


def _payload(result: Any) -> dict[str, Any]:
    """Extract the structured payload from a FastMCP ``ToolResult``."""
    for attr in ("structured_content", "structuredContent", "data", "result"):
        value = getattr(result, attr, None)
        if isinstance(value, dict):
            return value
    if isinstance(result, dict):
        return result

    content = getattr(result, "content", None)
    if content is None and isinstance(result, (list, tuple)):
        content = result
    for item in content or []:
        text = item if isinstance(item, str) else getattr(item, "text", None)
        if text:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
    raise AssertionError(f"unexpected ToolResult: {result!r}")


def _tool_info(tool: Any) -> Any:
    """Return the ``ToolInfo`` attached by the ``tool_meta`` decorator."""
    candidates = [tool]
    for attr in ("fn", "func", "__wrapped__"):
        inner = getattr(tool, attr, None)
        if inner is not None:
            candidates.append(inner)

    for candidate in candidates:
        for attr in (
            "__mcp_tool_info__",
            "__tool_info__",
            "__tool_meta__",
            "tool_info",
            "_tool_info",
            "mcp_tool_info",
        ):
            info = getattr(candidate, attr, None)
            if info is not None:
                return info
    return None


def test_workspace_tools_register() -> None:
    """Every workspace tool is registered with the FastMCP registry."""
    from fastmcp import FastMCP
    from klea_utils.mcp.registry import register_tools

    import osb_mcp.tools.workspace_tools as workspace_tools_module

    mcp = FastMCP("test")
    register_tools(mcp, [workspace_tools_module])

    async def _tool_names() -> set[str]:
        tools = await mcp.list_tools()
        return {tool.name for tool in tools}

    registered = asyncio.run(_tool_names())
    expected = {
        "create_workspace",
        "upload_files_to_workspace",
        "get_workspaces",
        "get_workspace",
        "delete_workspace",
        "delete_resource",
    }
    assert expected <= registered


def test_create_workspace(monkeypatch: Any) -> None:
    rest_api = _StubRestApi(result={"id": 7, "name": "demo"})
    _patch_client(monkeypatch, rest_api)
    _patch_models(monkeypatch)

    result = asyncio.run(
        create_workspace(
            _CTX,
            name="  demo  ",
            description="A demo workspace",
            publicable=True,
            featured=True,
            license="MIT",
            tags=["alpha", "beta"],
        )
    )

    assert _payload(result) == {"id": 7, "name": "demo"}
    assert len(rest_api.calls) == 1
    call = rest_api.calls[0]
    assert call["endpoint"] == "workspace_post"

    workspace = call["workspace"]
    assert isinstance(workspace, _ModelStub)
    data = dict(workspace.kwargs)
    tags = data.pop("tags")
    assert data == {
        "name": "demo",
        "description": "A demo workspace",
        "publicable": True,
        "featured": True,
        "license": "MIT",
    }
    assert [tag.kwargs for tag in tags] == [{"tag": "alpha"}, {"tag": "beta"}]


def test_create_workspace_rejects_empty_name(monkeypatch: Any) -> None:
    def _unexpected(ctx: Any) -> Any:
        raise AssertionError("the generated client must not be built")

    monkeypatch.setattr(workspace_tools, "make_generated_client", _unexpected)

    result = asyncio.run(create_workspace(_CTX, name="   ", description="desc"))

    assert _payload(result) == {"Error": "name must be a non-empty string"}


def test_create_workspace_reports_missing_credentials(monkeypatch: Any) -> None:
    def _missing(ctx: Any) -> Any:
        raise KeycloakAuthError("no bearer token")

    monkeypatch.setattr(workspace_tools, "make_generated_client", _missing)

    result = asyncio.run(create_workspace(_CTX, name="demo", description="desc"))

    assert _payload(result) == {
        "Error": "Error authenticating with OSBv2: no bearer token"
    }


def test_get_workspaces(monkeypatch: Any) -> None:
    expected = {"items": [{"id": 1}], "pagination": {"page": 2, "per_page": 5}}
    rest_api = _StubRestApi(result=expected)
    _patch_client(monkeypatch, rest_api)

    result = asyncio.run(
        get_workspaces(
            _CTX,
            page=2,
            per_page=5,
            q="name__like=Work%",
            tags="alpha+beta",
        )
    )

    assert _payload(result) == expected
    assert rest_api.calls == [
        {
            "endpoint": "workspace_get",
            "page": 2,
            "per_page": 5,
            "q": "name__like=Work%",
            "tags": "alpha+beta",
        }
    ]


def test_get_workspace(monkeypatch: Any) -> None:
    expected = {"id": 3, "name": "demo", "resources": []}
    rest_api = _StubRestApi(result=expected)
    _patch_client(monkeypatch, rest_api)

    result = asyncio.run(get_workspace(_CTX, workspace_id=3))

    assert _payload(result) == expected
    assert rest_api.calls == [{"endpoint": "workspace_id_get", "id": 3}]


def test_get_workspace_reports_api_error(monkeypatch: Any) -> None:
    class _FailingRestApi(_StubRestApi):
        async def workspace_id_get(self, *, id: int) -> dict[str, Any]:
            raise _ApiError("boom", status=500, reason="server error")

    _patch_client(monkeypatch, _FailingRestApi())
    monkeypatch.setattr(workspace_tools, "ApiException", _ApiError)

    result = asyncio.run(get_workspace(_CTX, workspace_id=3))

    assert _payload(result) == {
        "Error": "Error getting workspace: _ApiError: boom (HTTP 500): server error"
    }


def test_delete_workspace(monkeypatch: Any) -> None:
    rest_api = _StubRestApi()
    _patch_client(monkeypatch, rest_api)

    result = asyncio.run(delete_workspace(_CTX, workspace_id=3))

    assert _payload(result) == {"workspace_id": 3, "status": "deleted"}
    assert rest_api.calls == [{"endpoint": "workspace_id_delete", "id": 3}]


def test_upload_files_to_workspace(monkeypatch: Any) -> None:
    files = [
        {"name": "model.nml", "path": "https://example.org/model.nml"},
        {"name": "data.dat", "path": "https://example.org/data.dat"},
    ]
    rest_api = _StubRestApi(result={"imported": 2})
    _patch_client(monkeypatch, rest_api)
    _patch_models(monkeypatch)

    result = asyncio.run(
        upload_files_to_workspace(_CTX, workspace_id=4, files=files)
    )

    assert _payload(result) == {"imported": 2}
    assert len(rest_api.calls) == 1
    call = rest_api.calls[0]
    assert call["endpoint"] == (
        "workspaces_controllers_workspace_controller_import_resources"
    )
    assert call["id"] == 4
    request = call[
        "workspaces_controllers_workspace_controller_import_resources_request"
    ]
    assert isinstance(request, _ModelStub)
    assert request.kwargs == {"resourceorigins": files}


def test_upload_files_to_workspace_rejects_empty_files(monkeypatch: Any) -> None:
    def _unexpected(ctx: Any) -> Any:
        raise AssertionError("the generated client must not be built")

    monkeypatch.setattr(workspace_tools, "make_generated_client", _unexpected)

    result = asyncio.run(upload_files_to_workspace(_CTX, workspace_id=4, files=[]))

    assert _payload(result) == {"Error": "files must be a non-empty list"}


def test_delete_resource(monkeypatch: Any) -> None:
    rest_api = _StubRestApi()
    _patch_client(monkeypatch, rest_api)

    result = asyncio.run(delete_resource(_CTX, resource_id=5))

    assert _payload(result) == {"resource_id": 5, "status": "deleted"}
    assert rest_api.calls == [{"endpoint": "workspaceresource_id_delete", "id": 5}]
