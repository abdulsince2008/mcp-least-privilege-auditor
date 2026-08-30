"""MCP Least-Privilege Auditor.

A security tool that analyzes MCP (Model Context Protocol) servers
to find tools that are exposed but never used - excess attack surface.
"""

from mcp_auditor.auditor import AuditError, audit_from_config, audit_mcp_server
from mcp_auditor.manifest_parser import (
    ManifestParseError,
    discover_tools_from_server,
    discover_tools_from_server_sync,
    parse_manifest_file,
)
from mcp_auditor.models import (
    AuditResult,
    MCPTool,
    ToolCall,
    ToolSource,
    UsageLog,
)
from mcp_auditor.usage_parser import UsageLogParseError, merge_usage_logs, parse_usage_log

__version__ = "0.1.0"

__all__ = [
    "AuditError",
    "AuditResult",
    "MCPTool",
    "ManifestParseError",
    "ToolCall",
    "ToolSource",
    "UsageLog",
    "UsageLogParseError",
    "audit_from_config",
    "audit_mcp_server",
    "discover_tools_from_server",
    "discover_tools_from_server_sync",
    "merge_usage_logs",
    "parse_manifest_file",
    "parse_usage_log",
]