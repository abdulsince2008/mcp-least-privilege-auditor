"""Data models for MCP Least-Privilege Auditor."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolSource(str, Enum):
    """Source of tool discovery."""

    MANIFEST = "manifest"
    RUNTIME = "runtime"


class MCPTool(BaseModel):
    """Represents an MCP tool exposed by a server."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None
    source: ToolSource = ToolSource.MANIFEST

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MCPTool):
            return NotImplemented
        return self.name == other.name


class ToolCall(BaseModel):
    """Represents a single tool call from usage logs."""

    tool_name: str
    timestamp: datetime
    arguments: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None
    duration_ms: float | None = None
    session_id: str | None = None
    client_id: str | None = None


class UsageLog(BaseModel):
    """Collection of tool calls from usage logs."""

    calls: list[ToolCall] = Field(default_factory=list)
    source: str = "unknown"
    parsed_at: datetime = Field(default_factory=datetime.now)

    def unique_tools_used(self) -> set[str]:
        """Return set of unique tool names that were called."""
        return {call.tool_name for call in self.calls}

    def call_count(self, tool_name: str) -> int:
        """Return number of times a specific tool was called."""
        return sum(1 for call in self.calls if call.tool_name == tool_name)

    def failed_calls(self) -> list[ToolCall]:
        """Return only failed tool calls."""
        return [call for call in self.calls if not call.success]


class AuditResult(BaseModel):
    """Result of the least-privilege audit."""

    server_name: str
    server_version: str | None = None
    manifest_path: str | None = None
    usage_log_path: str | None = None
    audited_at: datetime = Field(default_factory=datetime.now)

    all_exposed_tools: list[MCPTool] = Field(default_factory=list)
    used_tools: set[str] = Field(default_factory=set)
    unused_tools: list[MCPTool] = Field(default_factory=list)
    missing_from_manifest: set[str] = Field(default_factory=set)

    total_calls: int = 0
    unique_tools_called: int = 0
    failed_calls: int = 0

    @property
    def exposure_ratio(self) -> float:
        """Ratio of used tools to total exposed tools."""
        if not self.all_exposed_tools:
            return 0.0
        return len(self.used_tools) / len(self.all_exposed_tools)

    @property
    def unused_count(self) -> int:
        """Number of tools exposed but never used."""
        return len(self.unused_tools)

    @property
    def risk_score(self) -> int:
        """
        Risk score from 0-100 based on:
        - Number of unused tools (weight: 50)
        - Exposure ratio (weight: 30)
        - Failed call rate (weight: 20)
        """
        unused_penalty = min(self.unused_count * 5, 50)
        exposure_penalty = int((1 - self.exposure_ratio) * 30)
        failed_rate = self.failed_calls / self.total_calls if self.total_calls > 0 else 0
        failed_penalty = int(failed_rate * 20)
        return min(unused_penalty + exposure_penalty + failed_penalty, 100)

    def to_summary(self) -> dict[str, Any]:
        """Return a summary dictionary for reporting."""
        return {
            "server_name": self.server_name,
            "server_version": self.server_version,
            "total_exposed_tools": len(self.all_exposed_tools),
            "tools_used": len(self.used_tools),
            "tools_unused": self.unused_count,
            "exposure_ratio": round(self.exposure_ratio, 2),
            "risk_score": self.risk_score,
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "unused_tool_names": [t.name for t in self.unused_tools],
            "missing_from_manifest": list(self.missing_from_manifest),
        }