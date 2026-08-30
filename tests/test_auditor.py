"""Tests for MCP Least-Privilege Auditor."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from mcp_auditor import audit_mcp_server, merge_usage_logs, parse_manifest_file, parse_usage_log
from mcp_auditor.manifest_parser import ManifestParseError
from mcp_auditor.models import MCPTool, ToolCall, ToolSource, UsageLog
from mcp_auditor.usage_parser import UsageLogParseError


class TestModels:
    """Test data models."""

    def test_mcp_tool_creation(self):
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            source=ToolSource.MANIFEST,
        )
        assert tool.name == "test_tool"
        assert tool.source == ToolSource.MANIFEST

    def test_mcp_tool_equality(self):
        tool1 = MCPTool(name="tool1", source=ToolSource.MANIFEST)
        tool2 = MCPTool(name="tool1", source=ToolSource.RUNTIME)
        tool3 = MCPTool(name="tool2", source=ToolSource.MANIFEST)

        assert tool1 == tool2  # Same name
        assert tool1 != tool3  # Different name
        assert hash(tool1) == hash(tool2)

    def test_usage_log_unique_tools(self):
        calls = [
            ToolCall(tool_name="tool1", timestamp="2025-01-01T00:00:00Z"),
            ToolCall(tool_name="tool2", timestamp="2025-01-01T00:00:00Z"),
            ToolCall(tool_name="tool1", timestamp="2025-01-01T00:00:00Z"),
        ]
        log = UsageLog(calls=calls)
        assert log.unique_tools_used() == {"tool1", "tool2"}
        assert log.call_count("tool1") == 2
        assert log.call_count("tool2") == 1
        assert log.call_count("tool3") == 0

    def test_audit_result_properties(self):
        from mcp_auditor.models import AuditResult

        tools = [
            MCPTool(name="used_tool", source=ToolSource.MANIFEST),
            MCPTool(name="unused_tool", source=ToolSource.MANIFEST),
        ]
        result = AuditResult(
            server_name="test-server",
            all_exposed_tools=tools,
            used_tools={"used_tool"},
            unused_tools=[tools[1]],  # Manually set for test
            total_calls=10,
            failed_calls=2,
        )
        assert result.unused_count == 1
        assert result.exposure_ratio == 0.5
        assert 0 <= result.risk_score <= 100


class TestManifestParser:
    """Test manifest parsing."""

    def test_parse_valid_manifest(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                {
                    "name": "test-server",
                    "version": "1.0.0",
                    "tools": [
                        {
                            "name": "tool1",
                            "description": "Tool 1",
                            "inputSchema": {"type": "object"},
                        }
                    ],
                },
                f,
            )
            path = f.name

        try:
            tools = parse_manifest_file(path)
            assert len(tools) == 1
            assert tools[0].name == "tool1"
            assert tools[0].source == ToolSource.MANIFEST
        finally:
            Path(path).unlink()

    def test_parse_manifest_array_format(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                [
                    {"name": "tool1", "inputSchema": {}},
                    {"name": "tool2", "inputSchema": {}},
                ],
                f,
            )
            path = f.name

        try:
            tools = parse_manifest_file(path)
            assert len(tools) == 2
        finally:
            Path(path).unlink()

    def test_parse_manifest_missing_file(self):
        with pytest.raises(ManifestParseError, match="No such file"):
            parse_manifest_file("nonexistent.json")

    def test_parse_manifest_invalid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json")
            path = f.name

        try:
            with pytest.raises(ManifestParseError, match="Invalid JSON"):
                parse_manifest_file(path)
        finally:
            Path(path).unlink()

    def test_parse_manifest_no_tools(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"name": "test", "version": "1.0.0", "tools": []}, f)
            path = f.name

        try:
            with pytest.raises(ManifestParseError, match="No tools found"):
                parse_manifest_file(path)
        finally:
            Path(path).unlink()

    def test_parse_client_config_error(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"mcpServers": {"server": {"command": "python"}}}, f)
            path = f.name

        try:
            with pytest.raises(ManifestParseError, match="client config"):
                parse_manifest_file(path)
        finally:
            Path(path).unlink()


class TestUsageParser:
    """Test usage log parsing."""

    def test_parse_jsonl(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"tool_name": "tool1", "timestamp": "2025-01-01T00:00:00Z"}\n')
            f.write('{"tool_name": "tool2", "timestamp": "2025-01-01T00:00:00Z"}\n')
            path = f.name

        try:
            log = parse_usage_log(path)
            assert len(log.calls) == 2
            assert log.calls[0].tool_name == "tool1"
            assert log.calls[1].tool_name == "tool2"
        finally:
            Path(path).unlink()

    def test_parse_json_array(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(
                [
                    {"tool_name": "tool1"},
                    {"tool_name": "tool2"},
                ],
                f,
            )
            path = f.name

        try:
            log = parse_usage_log(path)
            assert len(log.calls) == 2
        finally:
            Path(path).unlink()

    def test_parse_with_arguments(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write(
                '{"tool_name": "tool1", "arguments": {"key": "value"}, "success": true}\n'
            )
            path = f.name

        try:
            log = parse_usage_log(path)
            assert log.calls[0].arguments == {"key": "value"}
            assert log.calls[0].success is True
        finally:
            Path(path).unlink()

    def test_parse_missing_file(self):
        with pytest.raises(UsageLogParseError, match="not found"):
            parse_usage_log("nonexistent.jsonl")

    def test_merge_usage_logs(self):
        log1 = UsageLog(
            calls=[
                ToolCall(tool_name="tool1", timestamp="2025-01-01T00:00:00Z"),
                ToolCall(tool_name="tool2", timestamp="2025-01-01T01:00:00Z"),
            ]
        )
        log2 = UsageLog(
            calls=[
                ToolCall(tool_name="tool3", timestamp="2025-01-01T02:00:00Z"),
            ]
        )
        merged = merge_usage_logs([log1, log2])
        assert len(merged.calls) == 3
        assert merged.unique_tools_used() == {"tool1", "tool2", "tool3"}
        # Check sorted by timestamp
        assert merged.calls[0].tool_name == "tool1"
        assert merged.calls[2].tool_name == "tool3"


class TestAuditor:
    """Test full audit functionality."""

    def test_audit_manifest_and_usage(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as mf:
            json.dump(
                {
                    "name": "test-server",
                    "version": "1.0.0",
                    "tools": [
                        {"name": "tool1", "inputSchema": {}},
                        {"name": "tool2", "inputSchema": {}},
                        {"name": "tool3", "inputSchema": {}},
                    ],
                },
                mf,
            )
            manifest_path = mf.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as uf:
            uf.write('{"tool_name": "tool1", "timestamp": "2025-01-01T00:00:00Z"}\n')
            uf.write('{"tool_name": "tool2", "timestamp": "2025-01-01T00:00:00Z"}\n')
            usage_path = uf.name

        try:
            result = audit_mcp_server(
                manifest_path=manifest_path,
                usage_log_paths=[usage_path],
            )
            assert result.server_name == "test-server"
            assert result.server_version == "1.0.0"
            assert len(result.all_exposed_tools) == 3
            assert len(result.used_tools) == 2
            assert result.unused_count == 1
            assert "tool3" in [t.name for t in result.unused_tools]
            assert result.total_calls == 2
            assert result.risk_score >= 0
        finally:
            Path(manifest_path).unlink()
            Path(usage_path).unlink()

    def test_audit_missing_manifest(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as uf:
            uf.write('{"tool_name": "tool1"}\n')
            usage_path = uf.name

        try:
            with pytest.raises(Exception, match="Failed to parse manifest"):
                audit_mcp_server(
                    manifest_path="nonexistent.json",
                    usage_log_paths=[usage_path],
                )
        finally:
            Path(usage_path).unlink()

    def test_audit_missing_usage(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as mf:
            json.dump(
                {"name": "test", "tools": [{"name": "tool1", "inputSchema": {}}]},
                mf,
            )
            manifest_path = mf.name

        try:
            result = audit_mcp_server(manifest_path=manifest_path)
            assert result.total_calls == 0
            assert result.unused_count == 1
        finally:
            Path(manifest_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])