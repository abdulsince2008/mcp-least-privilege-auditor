"""Core audit logic for MCP Least-Privilege Auditor."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_auditor.manifest_parser import (
    ManifestParseError,
    discover_tools_from_server_sync,
    get_server_info_from_manifest,
    parse_manifest_file,
)
from mcp_auditor.models import AuditResult, MCPTool, UsageLog
from mcp_auditor.usage_parser import UsageLogParseError, merge_usage_logs, parse_usage_log


class AuditError(Exception):
    """Raised when audit fails."""



def audit_mcp_server(
    manifest_path: str | Path | None = None,
    server_command: list[str] | None = None,
    usage_log_paths: list[Path] | None = None,
    server_env: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> AuditResult:
    """
    Perform least-privilege audit on an MCP server.

    Args:
        manifest_path: Path to server manifest file or directory
        server_command: Command to start server for runtime discovery (e.g., ["python", "-m", "server"])
        usage_log_paths: List of paths to usage log files
        server_env: Environment variables for server process
        timeout: Server connection timeout

    Returns:
        AuditResult with findings

    Raises:
        AuditError: If audit cannot be completed
    """
    # Discover tools from manifest and/or runtime
    manifest_tools: list[MCPTool] = []
    runtime_tools: list[MCPTool] = []
    server_info = {}

    if manifest_path:
        try:
            manifest_tools = parse_manifest_file(manifest_path)
            server_info = get_server_info_from_manifest(manifest_path)
        except ManifestParseError as e:
            raise AuditError(f"Failed to parse manifest: {e}") from e

    if server_command:
        try:
            runtime_tools = discover_tools_from_server_sync(
                server_command, server_env, timeout
            )
        except ManifestParseError as e:
            raise AuditError(f"Failed to discover runtime tools: {e}") from e

    # Combine tools (runtime takes precedence for duplicates)
    all_tools = _merge_tools(manifest_tools, runtime_tools)

    if not all_tools:
        raise AuditError("No tools discovered from manifest or runtime")

    # Parse usage logs
    usage_log = UsageLog(calls=[])
    if usage_log_paths:
        logs = []
        for log_path in usage_log_paths:
            try:
                log = parse_usage_log(log_path)
                logs.append(log)
            except UsageLogParseError as e:
                raise AuditError(f"Failed to parse usage log {log_path}: {e}") from e

        if logs:
            usage_log = merge_usage_logs(logs)

    # Perform audit
    used_tool_names = usage_log.unique_tools_used()

    # Tools exposed but never used
    unused_tools = [t for t in all_tools if t.name not in used_tool_names]

    # Tools used but not in manifest (runtime-only)
    missing_from_manifest = used_tool_names - {t.name for t in manifest_tools}

    # Calculate statistics
    total_calls = len(usage_log.calls)
    failed_calls = len(usage_log.failed_calls())

    return AuditResult(
        server_name=server_info.get("name", "unknown"),
        server_version=server_info.get("version"),
        manifest_path=str(manifest_path) if manifest_path else None,
        usage_log_path=str(usage_log_paths[0]) if usage_log_paths else None,
        all_exposed_tools=all_tools,
        used_tools=used_tool_names,
        unused_tools=unused_tools,
        missing_from_manifest=missing_from_manifest,
        total_calls=total_calls,
        unique_tools_called=len(used_tool_names),
        failed_calls=failed_calls,
    )


def _merge_tools(
    manifest_tools: list[MCPTool], runtime_tools: list[MCPTool]
) -> list[MCPTool]:
    """Merge tools from manifest and runtime, preferring runtime for duplicates."""
    tool_map: dict[str, MCPTool] = {}

    # Add manifest tools first
    for tool in manifest_tools:
        tool_map[tool.name] = tool

    # Override with runtime tools (more accurate)
    for tool in runtime_tools:
        tool_map[tool.name] = tool

    return list(tool_map.values())


def audit_from_config(config_path: str | Path) -> AuditResult:
    """
    Audit from a JSON config file.

    Config format:
    {
        "manifest_path": "./mcp.json",
        "server_command": ["python", "-m", "my_server"],
        "usage_logs": ["./logs/usage.jsonl"],
        "server_env": {"KEY": "value"},
        "timeout": 30
    }
    """
    config_path = Path(config_path)
    try:
        with open(config_path) as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise AuditError(f"Failed to read config: {e}") from e

    return audit_mcp_server(
        manifest_path=config.get("manifest_path"),
        server_command=config.get("server_command"),
        usage_log_paths=config.get("usage_logs"),
        server_env=config.get("server_env"),
        timeout=config.get("timeout", 30.0),
    )