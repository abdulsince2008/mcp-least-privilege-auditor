"""MCP server manifest parsing."""

from __future__ import annotations

import asyncio
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import ListToolsResult

from mcp_auditor.models import MCPTool, ToolSource


class ManifestParseError(Exception):
    """Raised when manifest parsing fails."""


def parse_manifest_file(path: str | Path) -> list[MCPTool]:
    """
    Parse tools from an MCP manifest file (mcp.json, manifest.json, or .mcpb bundle).

    Args:
        path: Path to manifest file or directory containing manifest

    Returns:
        List of MCPTool objects

    Raises:
        ManifestParseError: If file cannot be parsed or no tools found
    """
    path = Path(path)

    # Handle directory - look for common manifest files
    if path.is_dir():
        for manifest_name in ["mcp.json", "manifest.json", "server.json", "mcp-manifest.json"]:
            manifest_path = path / manifest_name
            if manifest_path.exists():
                path = manifest_path
                break
        else:
            raise ManifestParseError(f"No manifest file found in directory: {path}")

    # Handle .mcpb bundles (zip files)
    if path.suffix == ".mcpb":
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile(path, "r") as zf:
                zf.extractall(tmpdir)
            return parse_manifest_file(Path(tmpdir))

    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ManifestParseError(f"Invalid JSON in manifest: {e}") from e
    except OSError as e:
        raise ManifestParseError(f"Cannot read manifest file: {e}") from e

    tools = []

    # MCPB manifest format
    if "tools" in data:
        for tool_data in data.get("tools", []):
            tools.append(_tool_from_manifest_dict(tool_data, ToolSource.MANIFEST))

    # FastMCP / mcp.json format
    elif "mcpServers" in data:
        # This is a client config, not a server manifest
        raise ManifestParseError(
            "File appears to be an MCP client config (mcpServers), not a server manifest. "
            "Point to the server's manifest.json or run against the server directly."
        )

    # Generic tool list
    elif isinstance(data, list):
        for tool_data in data:
            tools.append(_tool_from_manifest_dict(tool_data, ToolSource.MANIFEST))

    else:
        raise ManifestParseError(
            f"Unrecognized manifest format. Expected 'tools' array or list of tools. "
            f"Keys found: {list(data.keys())}"
        )

    if not tools:
        raise ManifestParseError("No tools found in manifest")

    return tools


def _tool_from_manifest_dict(data: dict[str, Any], source: ToolSource) -> MCPTool:
    """Create MCPTool from manifest dictionary."""
    return MCPTool(
        name=data.get("name", ""),
        description=data.get("description"),
        input_schema=data.get("inputSchema") or data.get("input_schema") or {},
        output_schema=data.get("outputSchema") or data.get("output_schema"),
        annotations=data.get("annotations"),
        source=source,
    )


async def discover_tools_from_server(
    command: list[str],
    env: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> list[MCPTool]:
    """
    Connect to an MCP server via stdio and discover tools at runtime.

    Args:
        command: Command to start the MCP server (e.g., ["python", "-m", "my_server"])
        env: Environment variables for the server process
        timeout: Connection timeout in seconds

    Returns:
        List of MCPTool objects discovered at runtime

    Raises:
        ManifestParseError: If connection fails or server doesn't respond
    """
    params = StdioServerParameters(command=command[0], args=command[1:], env=env or {})

    try:
        async with stdio_client(params) as (read, write), ClientSession(
            read, write
        ) as session:
            await asyncio.wait_for(session.initialize(), timeout=timeout)
            result: ListToolsResult = await asyncio.wait_for(
                session.list_tools(), timeout=timeout
            )

            tools = []
            for tool in result.tools:
                tools.append(
                    MCPTool(
                        name=tool.name,
                        description=tool.description,
                        input_schema=tool.input_schema,
                        output_schema=getattr(tool, "output_schema", None),
                        annotations=getattr(tool, "annotations", None),
                        source=ToolSource.RUNTIME,
                    )
                )
            return tools

    except asyncio.TimeoutError as e:
        raise ManifestParseError(f"Server connection timed out after {timeout}s") from e
    except Exception as e:
        raise ManifestParseError(f"Failed to connect to MCP server: {e}") from e


def discover_tools_from_server_sync(
    command: list[str],
    env: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> list[MCPTool]:
    """Synchronous wrapper for discover_tools_from_server."""
    return asyncio.run(discover_tools_from_server(command, env, timeout))


def get_server_info_from_manifest(path: str | Path) -> dict[str, Any]:
    """Extract server metadata from manifest file."""
    path = Path(path)

    if path.is_dir():
        for manifest_name in ["mcp.json", "manifest.json", "server.json", "mcp-manifest.json"]:
            manifest_path = path / manifest_name
            if manifest_path.exists():
                path = manifest_path
                break

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    return {
        "name": data.get("name") or data.get("server", {}).get("name") or "unknown",
        "version": data.get("version") or data.get("server", {}).get("version"),
        "description": data.get("description") or data.get("server", {}).get("description"),
    }