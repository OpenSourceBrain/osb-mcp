#!/usr/bin/env python3
"""
Tests for the OSB sqlite tools.

File: mcp/tests/test_sqlite_tools.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import logging
import sqlite3

from osb_mcp.tools import sqlite_tools

logger = logging.getLogger(__name__)


def _make_db(tmp_path):
    """Create a small sqlite database and return its absolute path."""
    db = tmp_path / "data.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE repos (id INTEGER, name TEXT, uri TEXT)")
    conn.execute(
        "INSERT INTO repos VALUES (1, 'OSBv2', 'https://github.com/OpenSourceBrain/OSBv2')"
    )
    conn.execute(
        "INSERT INTO repos VALUES (2, 'Klea', 'https://github.com/NeuroML/neuroklea')"
    )
    conn.commit()
    conn.close()
    return db


def _point_env(tmp_path, monkeypatch):
    """Create a test DB and point OSB_DATA_DB_PATH at it."""
    db = _make_db(tmp_path)
    monkeypatch.setenv("OSB_DATA_DB_PATH", str(db))
    return db


async def test_sqlite_tools_register():
    from fastmcp import FastMCP
    from klea_utils.mcp.registry import register_tools

    mcp = FastMCP("test")
    register_tools(mcp, [sqlite_tools])
    tools = await mcp.list_tools()
    names = sorted(t.name for t in tools)
    assert names == ["list_osb_sqlite_schema", "query_osb_sqlite"]


async def test_query_tool_description_embeds_schema():
    from fastmcp import FastMCP
    from klea_utils.mcp.registry import register_tools

    mcp = FastMCP("test")
    register_tools(mcp, [sqlite_tools])
    tools = await mcp.list_tools()
    query = next(t for t in tools if t.name == "query_osb_sqlite")
    logger.debug(f"{query.description = }")
    assert "osb-data-repos.sqlite" in query.description
    assert "repositories(" in query.description
    assert "repo_tags(" in query.description


async def test_query_osb_sqlite_reads_rows(tmp_path, monkeypatch):
    _point_env(tmp_path, monkeypatch)
    result = await sqlite_tools.query_osb_sqlite(
        sql="SELECT name, uri FROM repos ORDER BY id"
    )
    logger.debug(f"{result = }")
    assert not result.is_error
    data = result.structured_content
    assert data["error"] == ""
    assert data["columns"] == ["name", "uri"]
    assert data["row_count"] == 2
    assert data["rows"] == [
        ["OSBv2", "https://github.com/OpenSourceBrain/OSBv2"],
        ["Klea", "https://github.com/NeuroML/neuroklea"],
    ]
    assert data["truncated"] is False


async def test_query_osb_sqlite_respects_limit(tmp_path, monkeypatch):
    _point_env(tmp_path, monkeypatch)
    result = await sqlite_tools.query_osb_sqlite(
        sql="SELECT name FROM repos",
        limit=1,
    )
    logger.debug(f"{result = }")
    assert not result.is_error
    data = result.structured_content
    assert data["error"] == ""
    assert data["row_count"] == 1
    assert data["truncated"] is True


async def test_list_osb_sqlite_schema_lists_tables(tmp_path, monkeypatch):
    _point_env(tmp_path, monkeypatch)
    result = await sqlite_tools.list_osb_sqlite_schema()
    logger.debug(f"{result = }")
    assert not result.is_error
    data = result.structured_content
    assert data["error"] == ""
    assert "repos" in data["tables"]
    columns = {c["name"] for c in data["tables"]["repos"]["columns"]}
    assert columns == {"id", "name", "uri"}


async def test_query_osb_sqlite_rejects_non_select(tmp_path, monkeypatch):
    _point_env(tmp_path, monkeypatch)
    result = await sqlite_tools.query_osb_sqlite(sql="DELETE FROM repos")
    logger.debug(f"{result = }")
    assert result.is_error
    data = result.structured_content
    assert data["rows"] == []
    assert "Only SELECT" in data["error"]


async def test_query_osb_sqlite_unknown_table_hint(tmp_path, monkeypatch):
    _point_env(tmp_path, monkeypatch)
    result = await sqlite_tools.query_osb_sqlite(sql="SELECT * FROM nope")
    logger.debug(f"{result = }")
    assert result.is_error
    data = result.structured_content
    assert data["rows"] == []
    assert "no such table" in data["error"]
    assert "repos" in data["error"]
