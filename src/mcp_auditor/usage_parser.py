"""Usage log parsing for MCP tool calls."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp_auditor.models import ToolCall, UsageLog


class UsageLogParseError(Exception):
    """Raised when usage log parsing fails."""



# Supported log formats
LOG_FORMAT_JSON = "json"
LOG_FORMAT_JSONL = "jsonl"
LOG_FORMAT_CLAUDE_DESKTOP = "claude_desktop"
LOG_FORMAT_CUSTOM = "custom"


def detect_log_format(path: Path) -> str:
    """Auto-detect log format from file extension and content."""
    suffix = path.suffix.lower()

    if suffix in {".jsonl", ".ndjson"}:
        return LOG_FORMAT_JSONL
    if suffix == ".json":
        return LOG_FORMAT_JSON
    if "claude" in path.name.lower() or "conversation" in path.name.lower():
        return LOG_FORMAT_CLAUDE_DESKTOP

    # Peek at first few lines
    try:
        with open(path) as f:
            first_line = f.readline().strip()
            if first_line.startswith("{") and first_line.endswith("}"):
                return LOG_FORMAT_JSONL
            if first_line.startswith("["):
                return LOG_FORMAT_JSON
    except OSError:
        pass

    return LOG_FORMAT_CUSTOM


def parse_usage_log(path: str | Path, format: str | None = None) -> UsageLog:
    """
    Parse usage log file into UsageLog object.

    Args:
        path: Path to usage log file
        format: Log format (auto-detected if None)

    Returns:
        UsageLog object with parsed tool calls

    Raises:
        UsageLogParseError: If file cannot be parsed
    """
    path = Path(path)

    if not path.exists():
        raise UsageLogParseError(f"Usage log file not found: {path}")

    fmt = format or detect_log_format(path)

    if fmt == LOG_FORMAT_JSONL:
        return _parse_jsonl(path)
    elif fmt == LOG_FORMAT_JSON:
        return _parse_json(path)
    elif fmt == LOG_FORMAT_CLAUDE_DESKTOP:
        return _parse_claude_desktop(path)
    else:
        return _parse_custom(path)


def _parse_jsonl(path: Path) -> UsageLog:
    """Parse JSONL format (one JSON object per line)."""
    calls = []
    with open(path) as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                call = _tool_call_from_dict(data)
                if call:
                    calls.append(call)
            except json.JSONDecodeError as e:
                raise UsageLogParseError(f"Invalid JSON on line {line_num}: {e}") from e

    return UsageLog(calls=calls, source=f"jsonl:{path.name}")


def _parse_json(path: Path) -> UsageLog:
    """Parse JSON array format."""
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise UsageLogParseError(f"Invalid JSON: {e}") from e

    if not isinstance(data, list):
        raise UsageLogParseError("JSON log must be an array of tool call objects")

    calls = []
    for item in data:
        call = _tool_call_from_dict(item)
        if call:
            calls.append(call)

    return UsageLog(calls=calls, source=f"json:{path.name}")


def _parse_claude_desktop(path: Path) -> UsageLog:
    """Parse Claude Desktop conversation export format."""
    try:
        with open(path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise UsageLogParseError(f"Invalid JSON in Claude export: {e}") from e

    calls = []

    # Handle different Claude export formats
    messages = data.get("messages", data.get("conversations", []))

    for msg in messages:
        # Look for tool_use blocks in assistant messages
        if msg.get("role") == "assistant":
            content = msg.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        call = ToolCall(
                            tool_name=block.get("name", ""),
                            timestamp=_parse_timestamp(msg.get("timestamp")),
                            arguments=block.get("input", {}),
                            success=True,  # Assume success unless we see error
                            session_id=msg.get("session_id"),
                        )
                        calls.append(call)
            elif isinstance(content, str):
                # Might have embedded tool calls in text
                calls.extend(_extract_tool_calls_from_text(content, msg.get("timestamp")))

    return UsageLog(calls=calls, source=f"claude_desktop:{path.name}")


def _parse_custom(path: Path) -> UsageLog:
    """Parse custom/unknown format with best-effort extraction."""
    calls = []

    try:
        with open(path) as f:
            content = f.read()
    except OSError as e:
        raise UsageLogParseError(f"Cannot read log file: {e}") from e

    # Try JSON first
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return _parse_json(path)
    except json.JSONDecodeError:
        pass

    # Try JSONL
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            call = _tool_call_from_dict(data)
            if call:
                calls.append(call)
        except json.JSONDecodeError:
            # Try regex extraction for common patterns
            calls.extend(_extract_tool_calls_from_text(line))

    if not calls:
        raise UsageLogParseError(
            f"Could not parse log format. Supported formats: JSON array, JSONL, "
            f"Claude Desktop export. File: {path}"
        )

    return UsageLog(calls=calls, source=f"custom:{path.name}")


def _tool_call_from_dict(data: dict[str, Any]) -> ToolCall | None:
    """Extract ToolCall from dictionary with flexible field mapping."""
    # Required field
    tool_name = data.get("tool_name") or data.get("tool") or data.get("name")
    if not tool_name:
        return None

    # Optional fields with fallbacks
    timestamp = _parse_timestamp(
        data.get("timestamp")
        or data.get("time")
        or data.get("ts")
        or data.get("@timestamp")
    )

    arguments = data.get("arguments") or data.get("args") or data.get("input") or {}
    if not isinstance(arguments, dict):
        arguments = {}

    success = data.get("success", data.get("ok", True))
    error = data.get("error") or data.get("err")
    duration_ms = data.get("duration_ms") or data.get("duration") or data.get("elapsed_ms")
    session_id = data.get("session_id") or data.get("session") or data.get("conversation_id")
    client_id = data.get("client_id") or data.get("client")

    return ToolCall(
        tool_name=tool_name,
        timestamp=timestamp,
        arguments=arguments,
        success=success,
        error=error,
        duration_ms=float(duration_ms) if duration_ms is not None else None,
        session_id=session_id,
        client_id=client_id,
    )


def _parse_timestamp(value: Any) -> datetime:
    """Parse timestamp from various formats."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        # Assume Unix timestamp (seconds or milliseconds)
        if value > 1e12:
            value = value / 1000
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        # Try common formats
        for fmt in [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                dt = datetime.strptime(value, fmt)  # noqa: DTZ007
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return datetime.now(timezone.utc)


def _extract_tool_calls_from_text(text: str, timestamp: Any = None) -> list[ToolCall]:
    """Extract tool calls from free text using regex patterns."""
    calls = []

    # Pattern: tool_name(args) or tool_name{args}
    patterns = [
        r'(\w+)\s*\(\s*(\{.*?\})\s*\)',  # tool_name({args})
        r'(\w+)\s*\{\s*(\{.*?\})\s*\}',  # tool_name{{args}}
        r'"tool":\s*"(\w+)"',  # "tool": "name"
        r'"name":\s*"(\w+)"',  # "name": "name"
    ]

    ts = _parse_timestamp(timestamp) if timestamp else datetime.now(timezone.utc)

    for pattern in patterns:
        for match in re.finditer(pattern, text, re.DOTALL):
            tool_name = match.group(1)
            args_str = match.group(2) if len(match.groups()) > 1 else "{}"
            try:
                arguments = json.loads(args_str)
            except json.JSONDecodeError:
                arguments = {}

            calls.append(ToolCall(tool_name=tool_name, timestamp=ts, arguments=arguments))

    return calls


def merge_usage_logs(logs: list[UsageLog]) -> UsageLog:
    """Merge multiple usage logs into one."""
    all_calls = []
    sources = []
    for log in logs:
        all_calls.extend(log.calls)
        sources.append(log.source)

    # Sort by timestamp
    all_calls.sort(key=lambda c: c.timestamp)

    return UsageLog(
        calls=all_calls,
        source="merged:" + ",".join(sources),
    )