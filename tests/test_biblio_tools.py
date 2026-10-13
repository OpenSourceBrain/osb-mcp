#!/usr/bin/env python3
"""
Tests for the OSB bibliographic tools.

File: mcp/tests/test_biblio_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import logging

import httpx
from klea_utils.biblio.doi import DoiResolver

from osb_mcp.tools import biblio_tools

logger = logging.getLogger(__name__)

CROSSREF_JSON = {
    "message": {
        "DOI": "10.1234/abc.5678",
        "title": ["A Crossref Sample Paper"],
        "author": [{"given": "Jane", "family": "Doe"}],
        "issued": {"date-parts": [[2024, 5, 1]]},
        "container-title": ["Journal of Samples"],
        "abstract": "<jats:p>This is the <jats:italic>abstract</jats:italic> text.</jats:p>",
    }
}

OPENALEX_JSON = {
    "title": "An OpenAlex Sample Paper",
    "authorships": [{"author": {"display_name": "Jane Doe"}}],
    "publication_year": 2023,
    "primary_location": {"source": {"display_name": "Journal of Open Samples"}},
    "abstract_inverted_index": {"This": [0], "is": [1], "an": [2], "abstract": [3]},
    "doi": "https://doi.org/10.2345/def.6789",
}

S2_JSON = {
    "title": "A Semantic Scholar Sample Paper",
    "authors": [{"name": "Jane Doe"}],
    "year": 2022,
    "venue": "Journal of Semantic Samples",
    "abstract": "Plain abstract text.",
    "externalIds": {"DOI": "10.3456/ghi.7890"},
}


def _handler_for(route):
    """Build a MockTransport handler that routes by service URL.

    The *route* callback returns the JSON payload (or ``None``); this wraps
    it into a 200/404 ``httpx.Response`` as required by ``MockTransport``.
    """

    def handler(request):
        url = str(request.url)
        if "api.crossref.org" in url:
            payload = route("crossref", request)
        elif "api.openalex.org" in url:
            payload = route("openalex", request)
        elif "api.semanticscholar.org" in url:
            payload = route("semantic_scholar", request)
        else:
            payload = None
        if payload is None:
            return httpx.Response(404)
        return httpx.Response(200, json=payload)

    return handler


def _make_resolver(tmp_path, handler):
    """Return a DoiResolver backed by a mock transport (no real network)."""
    return DoiResolver(cache_dir=str(tmp_path), transport=httpx.MockTransport(handler))


async def test_biblio_tools_register():
    from fastmcp import FastMCP
    from klea_utils.mcp.registry import register_tools

    mcp = FastMCP("test")
    register_tools(mcp, [biblio_tools])
    tools = await mcp.list_tools()
    assert [t.name for t in tools] == ["get_paper_by_doi"]


async def test_get_paper_by_doi_resolves(tmp_path, monkeypatch):
    def route(service, request):
        return {
            "crossref": CROSSREF_JSON,
            "openalex": OPENALEX_JSON,
            "semantic_scholar": S2_JSON,
        }[service]

    resolver = _make_resolver(tmp_path, _handler_for(route))
    monkeypatch.setattr(biblio_tools, "_resolver", resolver)

    result = await biblio_tools.get_paper_by_doi(doi="10.1234/abc.5678")
    logger.debug(f"{result = }")
    assert not result.is_error
    data = result.structured_content
    assert data["error"] == ""
    assert data["title"] == "A Crossref Sample Paper"
    assert data["authors"] == ["Jane Doe"]
    assert data["year"] == 2024
    assert data["journal"] == "Journal of Samples"
    assert data["abstract"] == "This is the abstract text."
    assert data["doi"] == "10.1234/abc.5678"


async def test_get_paper_by_doi_unresolvable(tmp_path, monkeypatch):
    def route(service, request):
        return None

    resolver = _make_resolver(tmp_path, _handler_for(route))
    monkeypatch.setattr(biblio_tools, "_resolver", resolver)

    result = await biblio_tools.get_paper_by_doi(doi="10.9999/nope.0000")
    logger.debug(f"{result = }")
    assert result.is_error
    data = result.structured_content
    assert data["error"]
    assert "Could not resolve DOI" in data["error"]
    assert data["title"] is None
    assert data["authors"] == []
    assert data["abstract"] is None
    assert data["doi"] is None
