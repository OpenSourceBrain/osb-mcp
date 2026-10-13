#!/usr/bin/env python3
"""
MCP server for OSB tooling

File: osb_mcp/server/main.py

Copyright 2026 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>
"""

import asyncio
from textwrap import dedent

import typer

mcp_app = typer.Typer()


async def create_server(port: int = 8542):
    """main server creator"""
    # Lazy: fastmcp/fastmcp_docs/starlette/neuroml_mcp.tools all pull in
    # heavy deps (starlette, uvicorn, httpx, neuroml tool sandboxes, etc.)
    # Keep at function level so --help on the containing typer app stays fast.
    from fastmcp import FastMCP
    from fastmcp_docs import FastMCPDocs
    from klea_utils.mcp.registry import register_tools
    from starlette.requests import Request
    from starlette.responses import JSONResponse, PlainTextResponse

    from osb_mcp.tools import biblio_tools, osb_tools, sqlite_tools, workspace_tools
    from osb_mcp.tools.repositories import biomodels, dandi, download, figshare, github

    from .app_lifespan import app_lifespan

    usage = dedent(
        """
        OSB tools assistant server.

        """
    )
    mcp = FastMCP("OSB_MCP", instructions=usage, lifespan=app_lifespan)
    register_tools(
        mcp,
        [
            osb_tools,
            sqlite_tools,
            biblio_tools,
            github,
            figshare,
            dandi,
            biomodels,
            download,
            workspace_tools,
        ],
    )

    @mcp.custom_route("/health", methods=["GET"])
    async def health_check(request: Request) -> PlainTextResponse:
        return PlainTextResponse("OK")

    @mcp.custom_route("/list", methods=["GET"])
    async def tool_list(request: Request) -> JSONResponse:
        all_tools = await mcp.list_tools()
        tools_info = [
            {
                "name": str(tool.name),
                "title": tool.title,
                "description": tool.description,
            }
            for tool in all_tools
        ]
        resp = {"registered_tools": tools_info}
        return JSONResponse(resp)

    docs = FastMCPDocs(mcp, title="OSB MCP")
    await docs.setup()

    return mcp


@mcp_app.command()
def mcp_cli(
    port: int = 8542,
    transport: str = "streamable-http",
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
):
    """main runner method"""
    # Configure process-wide logging for this server.  Lazy: keeps the
    # fastmcp/starlette import chain out of --help.
    from klea_utils.plogging import resolve_log_level, setup_root_logger
    from platformdirs import PlatformDirs

    setup_root_logger(
        "osb-mcp",
        stderr_level=resolve_log_level(debug),
        log_dir=PlatformDirs("osb_mcp").user_data_dir,
    )
    mcp = asyncio.run(create_server(port))
    mcp.run(transport=transport, port=8542)


if __name__ == "__main__":
    mcp_app()
