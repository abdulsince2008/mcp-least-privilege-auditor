"""CLI for MCP Least-Privilege Auditor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.table import Table

from mcp_auditor.auditor import AuditError, audit_from_config, audit_mcp_server
from mcp_auditor.models import AuditResult

app = typer.Typer(
    name="mcp-auditor",
    help="MCP Least-Privilege Auditor - Find exposed but unused tools in MCP servers",
    add_completion=False,
)
console = Console()


@app.command()
def audit(
    manifest: Annotated[
        Path | None,
        typer.Option(
            "--manifest", "-m", help="Path to MCP server manifest file or directory"
        ),
    ] = None,
    server_command: Annotated[
        list[str] | None,
        typer.Option(
            "--server", "-s", help="Command to start MCP server for runtime discovery"
        ),
    ] = None,
    usage_logs: Annotated[
        list[Path] | None,
        typer.Option(
            "--usage", "-u", help="Path(s) to usage log file(s) (JSON, JSONL, Claude export)"
        ),
    ] = None,
    config: Annotated[
        Path | None,
        typer.Option("--config", "-c", help="Path to JSON config file"),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output file for results (JSON)"),
    ] = None,
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: table, json, summary"),
    ] = "table",
    timeout: Annotated[
        float,
        typer.Option("--timeout", "-t", help="Server connection timeout (seconds)"),
    ] = 30.0,
    env: Annotated[
        list[str] | None,
        typer.Option("--env", "-e", help="Environment variables (KEY=VALUE)"),
    ] = None,
) -> None:
    """
    Audit an MCP server for least-privilege violations.

    Provide either --manifest, --server, or --config.
    """
    # Parse env vars
    server_env = {}
    if env:
        for e in env:
            if "=" in e:
                k, v = e.split("=", 1)
                server_env[k] = v

    # Load from config if provided
    if config:
        if manifest or server_command or usage_logs:
            console.print(
                "[yellow]Warning: --config provided, ignoring other options[/yellow]"
            )
        try:
            result = audit_from_config(config)
        except AuditError as e:
            console.print(f"[red]Audit failed: {e}[/red]")
            raise typer.Exit(1)
    else:
        if not manifest and not server_command:
            console.print("[red]Error: Must provide --manifest, --server, or --config[/red]")
            raise typer.Exit(1)

        try:
            result = audit_mcp_server(
                manifest_path=manifest,
                server_command=server_command,
                usage_log_paths=usage_logs,
                server_env=server_env or None,
                timeout=timeout,
            )
        except AuditError as e:
            console.print(f"[red]Audit failed: {e}[/red]")
            raise typer.Exit(1)

    # Output results
    if output:
        _write_output(result, output, format)
        console.print(f"[green]Results written to {output}[/green]")
    else:
        _print_output(result, format)


@app.command()
def sample(
    output_dir: Annotated[
        Path,
        typer.Argument(help="Directory to write sample files"),
    ] = Path("./sample_data"),
) -> None:
    """Generate sample manifest and usage log files for testing."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Sample manifest
    manifest = {
        "name": "example-mcp-server",
        "version": "1.0.0",
        "description": "Example MCP server with various tools",
        "tools": [
            {
                "name": "read_file",
                "description": "Read a file from the filesystem",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"}
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write a file to the filesystem",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to write"},
                        "content": {"type": "string", "description": "Content to write"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "list_directory",
                "description": "List contents of a directory",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path"}
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "execute_command",
                "description": "Execute a shell command (DANGEROUS - rarely used)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to execute"}
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "query_database",
                "description": "Query a SQL database",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "SQL query"},
                        "params": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "send_email",
                "description": "Send an email (legacy, deprecated)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        ],
    }

    # Sample usage log (JSONL) - only uses read_file, list_directory, query_database
    usage_log = [
        {
            "tool_name": "read_file",
            "timestamp": "2025-01-15T10:30:00Z",
            "arguments": {"path": "/home/user/config.json"},
            "success": True,
            "duration_ms": 45.2,
            "session_id": "sess_001",
        },
        {
            "tool_name": "list_directory",
            "timestamp": "2025-01-15T10:31:00Z",
            "arguments": {"path": "/home/user/projects"},
            "success": True,
            "duration_ms": 12.1,
            "session_id": "sess_001",
        },
        {
            "tool_name": "read_file",
            "timestamp": "2025-01-15T10:32:00Z",
            "arguments": {"path": "/home/user/projects/README.md"},
            "success": True,
            "duration_ms": 38.7,
            "session_id": "sess_001",
        },
        {
            "tool_name": "query_database",
            "timestamp": "2025-01-15T10:35:00Z",
            "arguments": {"query": "SELECT * FROM users WHERE active = 1", "params": []},
            "success": True,
            "duration_ms": 156.3,
            "session_id": "sess_002",
        },
        {
            "tool_name": "read_file",
            "timestamp": "2025-01-15T10:40:00Z",
            "arguments": {"path": "/etc/hosts"},
            "success": False,
            "error": "Permission denied",
            "duration_ms": 5.1,
            "session_id": "sess_002",
        },
        {
            "tool_name": "list_directory",
            "timestamp": "2025-01-15T10:41:00Z",
            "arguments": {"path": "/home/user"},
            "success": True,
            "duration_ms": 8.9,
            "session_id": "sess_003",
        },
    ]

    manifest_path = output_dir / "manifest.json"
    usage_path = output_dir / "usage.jsonl"

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    with open(usage_path, "w") as f:
        f.writelines(json.dumps(entry) + "\n" for entry in usage_log)

    console.print(f"[green]Sample files created in {output_dir}/[/green]")
    console.print(f"  - {manifest_path}")
    console.print(f"  - {usage_path}")
    console.print("\nRun audit with:")
    console.print(f"  mcp-auditor audit -m {manifest_path} -u {usage_path}")


def _print_output(result: AuditResult, format: str) -> None:
    """Print audit results to console."""
    if format == "json":
        console.print(JSON.from_data(result.to_summary()))
        return

    if format == "summary":
        _print_summary(result)
        return

    # Default: table format
    _print_table(result)


def _print_summary(result: AuditResult) -> None:
    """Print concise summary."""
    summary = result.to_summary()

    # Risk level
    risk = summary["risk_score"]
    if risk >= 70:
        risk_style = "red"
        risk_label = "HIGH"
    elif risk >= 40:
        risk_style = "yellow"
        risk_label = "MEDIUM"
    else:
        risk_style = "green"
        risk_label = "LOW"

    panel = Panel(
        f"""
[bold]Server:[/bold] {summary['server_name']} ({summary['server_version'] or 'unknown'})
[bold]Risk Score:[/bold] [{risk_style}]{risk}/100 ({risk_label})[/{risk_style}]
[bold]Exposed Tools:[/bold] {summary['total_exposed_tools']}
[bold]Tools Used:[/bold] {summary['tools_used']}
[bold]Tools Unused:[/bold] {summary['tools_unused']}
[bold]Exposure Ratio:[/bold] {summary['exposure_ratio']:.0%}
[bold]Total Calls:[/bold] {summary['total_calls']}
[bold]Failed Calls:[/bold] {summary['failed_calls']}
""",
        title="MCP Least-Privilege Audit Summary",
        border_style=risk_style,
    )
    console.print(panel)

    if summary["unused_tool_names"]:
        console.print("\n[bold red]Unused Tools (Excess Attack Surface):[/bold red]")
        for name in summary["unused_tool_names"]:
            console.print(f"  • {name}")

    if summary["missing_from_manifest"]:
        console.print("\n[bold yellow]Tools Used But Not In Manifest:[/bold yellow]")
        for name in summary["missing_from_manifest"]:
            console.print(f"  • {name}")


def _print_table(result: AuditResult) -> None:
    """Print detailed table output."""
    _print_summary(result)

    # Exposed tools table
    table = Table(title="All Exposed Tools")
    table.add_column("Tool Name", style="cyan")
    table.add_column("Description", style="dim")
    table.add_column("Source", style="magenta")
    table.add_column("Used", style="green")
    table.add_column("Call Count", justify="right")

    for tool in result.all_exposed_tools:
        used = tool.name in result.used_tools
        call_count = result.used_tools and sum(
            1 for c in result.used_tools if c == tool.name
        ) or 0
        table.add_row(
            tool.name,
            tool.description or "—",
            tool.source.value,
            "✓" if used else "✗",
            str(call_count) if used else "0",
        )

    console.print(table)

    # Usage stats
    if result.total_calls > 0:
        usage_table = Table(title="Usage Statistics")
        usage_table.add_column("Metric", style="cyan")
        usage_table.add_column("Value", justify="right")

        usage_table.add_row("Total Tool Calls", str(result.total_calls))
        usage_table.add_row("Unique Tools Called", str(result.unique_tools_called))
        usage_table.add_row("Failed Calls", str(result.failed_calls))
        usage_table.add_row(
            "Failure Rate",
            f"{result.failed_calls / result.total_calls:.1%}",
        )
        usage_table.add_row("Risk Score", f"{result.risk_score}/100")

        console.print(usage_table)


def _write_output(result: AuditResult, output: Path, format: str) -> None:
    """Write results to file."""
    if format == "json":
        data = result.to_summary()
        # Add full tool details
        data["tools"] = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "output_schema": t.output_schema,
                "source": t.source.value,
                "used": t.name in result.used_tools,
            }
            for t in result.all_exposed_tools
        ]
    else:
        data = result.to_summary()

    with open(output, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    app()