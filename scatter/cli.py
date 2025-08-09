"""CLI entrypoints for Scatter.

This module exposes the `typer` application and the primary `run` command.

Key behaviors
- Command resolution order: per-host `command` > `--command-file` > positional CLI `command`.
- Auth precedence: per-host `username`/`port`/`identity`/`password` override CLI/global values.
- Host key checks: disabled by default to match project policy; see `ssh._connect`.
- Concurrency: a shared semaphore enforces the `--limit` of concurrent sessions.
- Output modes:
  - Default prints a results table (and per-host progress when enabled).
  - `--quiet` prints a single summary line.
  - `-v/-vv` increase verbosity; `-vv` also prints stdout/stderr blocks.
- Artifacts: `--save-dir` writes per-host output files; `--log-file` writes JSONL records per host.
"""

from __future__ import annotations

import asyncio
import sys
from enum import Enum
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.table import Table

from .config import Inventory, HostEntry, load_inventory
from .ssh import ExecOptions, execute_on_hosts

app = typer.Typer(add_completion=False, help="Concurrent SSH executor for 100+ hosts")
console = Console()


class KnownHostsPolicy(str, Enum):
    strict = "strict"
    off = "off"


@app.callback()
def _setup() -> None:
    """Set a sane asyncio event loop policy for the current platform.

    - On Windows, prefer ``WindowsSelectorEventLoopPolicy`` for wide compatibility.
    - On non-Windows, attempt to use ``uvloop`` if available (best-effort).
    """
    # Ensure a safe loop policy on Windows
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    else:
        # On Linux, prefer uvloop if available for better performance
        try:
            import uvloop  # type: ignore

            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        except Exception:
            pass


@app.command()
def run(
    command: Optional[str] = typer.Argument(None, help="Shell command to run on all hosts (overridden by per-host 'command' in inventory)"),
    inventory: Path = typer.Option(Path("inventory.yaml"), exists=False, dir_okay=False, help="Path to inventory YAML"),
    limit: int = typer.Option(50, min=1, help="Max concurrent SSH sessions"),
    identity: Optional[Path] = typer.Option(None, help="Path to private key file to use"),
    username: Optional[str] = typer.Option(None, help="Override SSH username for all hosts"),
    port: Optional[int] = typer.Option(None, help="Override SSH port for all hosts"),
    known_hosts: KnownHostsPolicy = typer.Option(
        KnownHostsPolicy.off,
        help="Host key verification policy (off: disables StrictHostKeyChecking and UserKnownHostsFile)",
    ),
    connect_timeout: float = typer.Option(10.0, min=1.0, help="SSH connect timeout (seconds)"),
    pty: bool = typer.Option(False, help="Request a PTY (xterm) for the command"),
    command_timeout: Optional[float] = typer.Option(None, help="Command timeout (seconds)"),
    retry_attempts: int = typer.Option(1, min=1, max=5, help="Connection retry attempts per host"),
    show_output: bool = typer.Option(False, help="Print full stdout per host after summary table"),
    show_stderr: bool = typer.Option(False, help="Also print stderr blocks for failed hosts"),
    save_dir: Optional[Path] = typer.Option(None, help="Directory to save per-host stdout/stderr files"),
    progress: bool = typer.Option(True, "--progress/--no-progress", help="Show progress bar and stream per-host results"),
    dry_run: bool = typer.Option(False, help="Preview target hosts, auth, and commands without executing"),
    command_file: Optional[Path] = typer.Option(None, help="Read command text from a file (used if host has no 'command')"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="Increase verbosity (repeat for more detail)"),
    quiet: bool = typer.Option(False, help="Minimal output: only summary and exit code"),
    log_file: Optional[Path] = typer.Option(None, help="Write JSON lines log with per-host results"),
) -> None:
    """Run COMMAND across all hosts in the inventory.

    Details
    - Command selection precedence: per-host ``command`` in the inventory takes precedence,
      then ``--command-file`` (first line shown in previews), then the positional CLI ``command``.
    - Authentication precedence: values defined on a host override CLI/global defaults. Paths
      provided via CLI or inventory support ``~`` and environment variable expansion.
    - Progress and verbosity: progress is enabled by default; ``--no-progress`` disables it.
      ``-vv`` implies ``--show-output`` and ``--show-stderr``. ``--quiet`` reduces output to a
      single summary line.
    - Outputs: when ``--save-dir`` is provided, per-host ``.stdout.txt`` and ``.stderr.txt`` files
      are written (with sanitized hostnames). When ``--log-file`` is provided, a JSON Lines file is
      written with one record per host including result metadata and the effective command.
    """

    inv: Inventory = load_inventory(inventory)

    # Effective known-hosts: CLI overrides inventory defaults
    effective_known_hosts = (known_hosts.value if known_hosts else inv.defaults.known_hosts).lower()

    # Expand user/vars for CLI-supplied paths
    expanded_identity = Path(os.path.expandvars(os.path.expanduser(str(identity)))) if identity else None
    inv_default_identity = (
        Path(os.path.expandvars(os.path.expanduser(str(inv.defaults.identity))))
        if getattr(inv.defaults, "identity", None)
        else None
    )
    base_identity = expanded_identity or inv_default_identity
    file_command: Optional[str] = None
    if command_file is not None:
        file_command = Path(os.path.expandvars(os.path.expanduser(str(command_file)))).read_text(encoding="utf-8")

    options = ExecOptions(
        username=username or inv.defaults.username,
        port=port or inv.defaults.port,
        identity=base_identity,
        password=None,
        known_hosts=effective_known_hosts,
        connect_timeout=connect_timeout or inv.defaults.connect_timeout,
        pty=pty if pty is not None else inv.defaults.pty,
        limit=limit,
        command_timeout=command_timeout,
        retry_attempts=retry_attempts,
    )

    # Build per-host command and auth. Precedence: host.command > --command-file > CLI command
    host_specs: List[tuple[str, str, ExecOptions]] = []
    for h in inv.hosts:
        host_command = h.command or file_command or command
        if not host_command:
            raise typer.BadParameter(f"No command provided for host {h.host}. Provide CLI 'command' or 'command' in inventory.")

        # Expand any per-host identity path and fall back to CLI/global
        per_host_identity = (
            Path(os.path.expandvars(os.path.expanduser(h.identity))) if h.identity else options.identity
        )

        per_host_options = ExecOptions(
            username=h.username or options.username,
            port=h.port or options.port,
            identity=per_host_identity,
            password=h.password if h.password else inv.defaults.password if inv.defaults.password else options.password,
            known_hosts=options.known_hosts,
            connect_timeout=options.connect_timeout,
            pty=options.pty,
            limit=options.limit,
            command_timeout=options.command_timeout,
            retry_attempts=options.retry_attempts,
        )
        host_specs.append((h.host, host_command, per_host_options))

    # Dry run: show plan and exit
    if dry_run:
        if not quiet:
            plan = Table(title="Planned SSH Execution", show_lines=False)
            plan.add_column("Host", style="bold")
            plan.add_column("User")
            plan.add_column("Port")
            plan.add_column("Auth")
            plan.add_column("PTY")
            plan.add_column("Command (preview)")

            for host, cmd, opts in host_specs:
                auth_parts = []
                if opts.identity:
                    auth_parts.append(f"key:{opts.identity}")
                if opts.password:
                    auth_parts.append("password:***")
                auth = ", ".join(auth_parts) if auth_parts else "agent/none"
                preview = (cmd.strip().splitlines() or [""])[0][:120]
                plan.add_row(host, str(opts.username or ""), str(opts.port or 22), auth, "yes" if opts.pty else "no", preview)

            console.print(plan)
            console.print(f"Will run on {len(host_specs)} hosts with concurrency={limit}")
        else:
            # Quiet mode still prints a one-line summary for visibility
            console.print(f"Will run on {len(host_specs)} hosts with concurrency={limit}")
        raise typer.Exit(code=0)

    # Verbosity influences defaults
    if verbose >= 2:
        show_output = True
        show_stderr = True

    if not quiet and not progress:
        console.print(f"Running on {len(host_specs)} hosts with concurrency={limit}...")

    # Execute per-host, but reuse the same concurrency limit by running a wrapper.
    async def _run_all():
        semaphore = asyncio.Semaphore(limit)
        tasks = [asyncio.create_task(_run_one(h, cmd, opts, semaphore)) for h, cmd, opts in host_specs]
        if progress and not quiet:
            from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

            results_local: List = []
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn(" {task.completed}/{task.total}"),
                TimeElapsedColumn(),
                console=console,
                transient=True,
            ) as prog:
                task_id = prog.add_task("Running", total=len(tasks))
                for coro in asyncio.as_completed(tasks):
                    res = await coro
                    results_local.append(res)
                    prog.advance(task_id)
                    status = "[green]OK[/green]" if res.ok else "[red]FAIL[/red]"
                    exit_text = "" if res.exit_status is None else str(res.exit_status)
                    first_line = (res.stdout.strip().splitlines() or [""])[0]
                    if res.ok:
                        prog.console.print(f"{res.host}: {status} exit={exit_text} dur={res.duration:.2f}s - {first_line[:120]}")
                    else:
                        reason = res.error or (res.stderr.strip().splitlines() or [""])[0]
                        prog.console.print(f"{res.host}: {status} {reason}")
            return results_local
        else:
            return await asyncio.gather(*tasks)

    async def _run_one(host: str, host_command: str, host_options: ExecOptions, semaphore: asyncio.Semaphore):
        from .ssh import run_on_host  # reuse implementation
        return await run_on_host(host, host_command, host_options, semaphore)

    results = asyncio.run(_run_all())

    ok_count = sum(1 for r in results if r.ok)
    failed_count = len(results) - ok_count
    exit_code = 0 if failed_count == 0 else 1

    if not quiet:
        table = Table(title="SSH Results", show_lines=False)
        table.add_column("Host", style="bold")
        table.add_column("Status")
        table.add_column("Exit")
        table.add_column("Duration (s)")
        table.add_column("Stdout (first line)")
        table.add_column("Error")

        for r in results:
            status = "OK" if r.ok else "FAIL"
            exit_text = "" if r.exit_status is None else str(r.exit_status)
            first_line = (r.stdout.strip().splitlines() or [""])[0]
            error_text = ""
            if not r.ok:
                # Prefer structured error, fallback to first stderr line
                error_text = (r.error or (r.stderr.strip().splitlines() or [""])[0])[:200]
            table.add_row(r.host, status, exit_text, f"{r.duration:.2f}", first_line[:200], error_text)

        console.print(table)

    if not quiet:
        if failed_count:
            console.print(f"[red]Failed: {failed_count}[/red], Succeeded: {ok_count}")
            # Print concise list of failures with reasons
            for r in results:
                if not r.ok:
                    reason = r.error or (r.stderr.strip().splitlines() or [""])[0]
                    console.print(f"[red]- {r.host}[/red]: {reason}")
        else:
            console.print(f"[green]Succeeded: {ok_count}[/green]")
    else:
        # Quiet mode prints only a single summary line
        if failed_count:
            console.print(f"Failed: {failed_count}, Succeeded: {ok_count}")
        else:
            console.print(f"Succeeded: {ok_count}")

    # Optionally print full outputs
    if (show_output or show_stderr) and not quiet:
        for r in results:
            if show_output and r.stdout:
                console.rule(f"[bold]STDOUT[/bold] - {r.host}")
                console.print(r.stdout)
            if show_stderr and (not r.ok) and r.stderr:
                console.rule(f"[bold red]STDERR[/bold red] - {r.host}")
                console.print(r.stderr)

    # Optionally save outputs to files
    if save_dir is not None:
        save_dir = Path(os.path.expandvars(os.path.expanduser(str(save_dir))))
        save_dir.mkdir(parents=True, exist_ok=True)

        def _sanitize(name: str) -> str:
            return "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name)

        for r in results:
            base = _sanitize(r.host)
            (save_dir / f"{base}.stdout.txt").write_text(r.stdout or "", encoding="utf-8")
            (save_dir / f"{base}.stderr.txt").write_text(r.stderr or "", encoding="utf-8")

    # Optional JSONL log file
    if log_file is not None:
        log_file = Path(os.path.expandvars(os.path.expanduser(str(log_file))))
        log_file.parent.mkdir(parents=True, exist_ok=True)
        host_to_command = {h: cmd for h, cmd, _ in host_specs}
        with log_file.open("w", encoding="utf-8") as f:
            for r in results:
                record = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "host": r.host,
                    "ok": r.ok,
                    "exit_status": r.exit_status,
                    "duration_sec": r.duration,
                    "error": r.error,
                    "stdout": r.stdout,
                    "stderr": r.stderr,
                    "command": host_to_command.get(r.host),
                }
                f.write(json.dumps(record) + "\n")

    raise typer.Exit(code=exit_code)


