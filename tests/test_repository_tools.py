#!/usr/bin/env python3
"""
Tests for the repository source tools.

File: mcp/tests/test_repository_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import json
import logging

import httpx
import klea_utils.api.utils as api_utils
import pytest
from klea_utils.mcp.tool_impls import download_file as download_file_module
from klea_utils.mcp.tool_impls.repositories import sources as repo_sources

from osb_mcp.tools.repositories import biomodels, dandi, download, figshare, github

logger = logging.getLogger(__name__)

EXPECTED_TOOL_NAMES = [
    "download_files",
    "list_biomodels_files",
    "list_biomodels_versions",
    "list_dandi_files",
    "list_dandi_versions",
    "list_figshare_files",
    "list_figshare_versions",
    "list_github_files",
    "list_github_versions",
]


class _FakeResponse:
    """Minimal httpx-like response carrying JSON or raw bytes."""

    def __init__(self, payload, status: int = 200, headers: dict | None = None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://example.com")
            response = httpx.Response(self.status_code, request=request, content=b"{}")
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=request, response=response
            )

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def content(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")

    def json(self):
        return self._payload


class _FakeSession:
    """Serves canned responses per URL and records the calls made."""

    def __init__(
        self, routes: dict | None = None, response: _FakeResponse | None = None
    ):
        self._routes = routes or {}
        self._response = response
        self.calls: list[tuple[str, dict]] = []

    async def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self._response is not None:
            return self._response
        route = self._routes.get(url)
        if route is None:
            raise AssertionError(f"no route registered for {url}")
        if isinstance(route, Exception):
            raise route
        return route

    def stream(self, method, url, **kwargs):
        raise AssertionError("stream is not exercised in repository tool tests")


class _FakeCtx:
    """Minimal FastMCP Context stand-in."""

    def __init__(self):
        self.lifespan_context = {}


@pytest.fixture
def patch_session(monkeypatch):
    """Install a stub HTTP client in every repository tool module.

    The tool modules bind ``_session`` at import time, so the patch has to be
    applied to each module's own attribute rather than to the shared helper.
    """

    def _install(session):
        for module in (github, dandi, download):
            monkeypatch.setattr(module, "_session", lambda *args, **kwargs: session)
        return session

    return _install


@pytest.fixture(autouse=True)
def _fast_waits(monkeypatch):
    # Neutralise the exponential backoff so retry tests do not sleep.
    monkeypatch.setattr(api_utils, "wait_random_exponential", lambda **kw: 0.0)


@pytest.fixture(autouse=True)
def _hermetic_ssrf(monkeypatch):
    # Mock tests must not perform real DNS resolution for the SSRF guards.
    monkeypatch.setattr(repo_sources, "check_ssrf", lambda url: None)

    async def _noop_check_ssrf_async(url, timeout=None):
        return None

    monkeypatch.setattr(
        download_file_module, "check_ssrf_async", _noop_check_ssrf_async
    )


async def test_repository_tools_register():
    from fastmcp import FastMCP
    from klea_utils.mcp.registry import register_tools

    mcp = FastMCP("test")
    register_tools(mcp, [github, figshare, dandi, biomodels, download])
    tools = await mcp.list_tools()
    names = sorted(t.name for t in tools)
    assert names == sorted(EXPECTED_TOOL_NAMES)


GITHUB_API = "https://api.github.com/repos/NeuroML/neuroklea"


def _github_routes():
    return {
        f"{GITHUB_API}/git/trees/development": _FakeResponse(
            {
                "tree": [
                    {
                        "path": "README.md",
                        "mode": "100644",
                        "type": "blob",
                        "size": 12,
                        "sha": "e1",
                    },
                    {
                        "path": "src",
                        "mode": "040000",
                        "type": "tree",
                        "sha": "e2",
                    },
                ]
            }
        ),
    }


async def test_list_github_files_passthrough(patch_session):
    session = _FakeSession(routes=_github_routes())
    patch_session(session)
    result = await github.list_github_files(
        _FakeCtx(),
        url="https://github.com/NeuroML/neuroklea",
        version="development",
    )
    logger.debug(f"{result = }")
    assert not result.is_error
    data = result.structured_content
    assert data["error"] == ""
    assert data["version"] == "development"
    assert [f["path"] for f in data["files"]] == ["README.md"]
    # The session from the lifespan context reached the implementation.
    assert any("git/trees/development" in url for url, _ in session.calls)


async def test_list_github_versions_passthrough(patch_session):
    routes = {
        f"{GITHUB_API}/branches": _FakeResponse([{"name": "development"}]),
        f"{GITHUB_API}/tags": _FakeResponse([{"name": "v1.0"}]),
    }
    session = _FakeSession(routes=routes)
    patch_session(session)
    result = await github.list_github_versions(
        _FakeCtx(), url="https://github.com/NeuroML/neuroklea"
    )
    logger.debug(f"{result = }")
    assert not result.is_error
    data = result.structured_content
    assert data["error"] == ""
    assert data["versions"] == ["development", "v1.0"]


async def test_download_files_tool_writes(tmp_path, patch_session):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"file body")

    patch_session(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    files = [
        {"path": "a.txt", "download_url": "https://example.com/a.txt"},
        {"path": "sub/b.txt", "download_url": "https://example.com/b.txt"},
    ]
    result = await download.download_files(
        _FakeCtx(),
        files=files,
        target_dir=str(tmp_path),
        max_concurrency=2,
    )
    logger.debug(f"{result = }")
    assert not result.is_error
    data = result.structured_content
    assert data["error"] == ""
    by_path = {r["path"]: r for r in data["results"]}
    assert "saved_to" in by_path["a.txt"]
    assert "saved_to" in by_path["sub/b.txt"]
    assert (tmp_path / "a.txt").read_text() == "file body"
    assert (tmp_path / "sub" / "b.txt").read_text() == "file body"


async def test_list_dandi_files_passthrough(patch_session):
    DANDI_API = "https://api.dandiarchive.org/api"
    paths_url = f"{DANDI_API}/dandisets/000025/versions/draft/assets/paths/"
    routes = {
        paths_url: _FakeResponse(
            {
                "count": 1,
                "next": None,
                "previous": None,
                "results": [
                    {
                        "path": "001_140709EXP_A1.nwb",
                        "asset": {"asset_id": "abc-123"},
                        "aggregate_size": 12345,
                    }
                ],
            }
        ),
    }
    session = _FakeSession(routes=routes)
    patch_session(session)
    result = await dandi.list_dandi_files(
        _FakeCtx(), url="https://dandiarchive.org/dandiset/000025"
    )
    logger.debug(f"{result = }")
    assert not result.is_error
    data = result.structured_content
    assert data["error"] == ""
    assert data["version"] == "draft"
    assert [f["path"] for f in data["files"]] == ["001_140709EXP_A1.nwb"]
    assert data["files"][0]["download_url"].endswith("/assets/abc-123/download/")
