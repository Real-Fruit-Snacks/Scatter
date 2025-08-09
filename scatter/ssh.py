"""Async SSH execution primitives.

This module provides primitives to connect to hosts and run commands concurrently.

Design notes
- Host key verification is intentionally disabled (``known_hosts=None``) to match
  the project policy of ``-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null``.
  The ``ExecOptions.known_hosts`` value is accepted for future flexibility but
  currently not enforced at the transport layer.
- Concurrency is limited via a shared ``asyncio.Semaphore`` passed into ``run_on_host``.
- Results include timing metadata and basic success/failure information.
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import asyncssh
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential


@dataclass
class ExecResult:
    """Result of executing a command on a host.

    Attributes
    - host: Target hostname or address
    - exit_status: Command exit status (``None`` on connection/setup failures)
    - stdout/stderr: Captured output streams (empty strings if none)
    - ok: Convenience flag indicating success (``exit_status == 0``)
    - started_at/ended_at: ``time.perf_counter()`` timestamps to compute duration
    - error: Optional structured error string on failures
    """
    host: str
    exit_status: Optional[int]
    stdout: str
    stderr: str
    ok: bool
    started_at: float
    ended_at: float
    error: Optional[str] = None

    @property
    def duration(self) -> float:
        return self.ended_at - self.started_at


@dataclass
class ExecOptions:
    """Execution options for SSH commands.

    Fields support typical SSH settings; ``identity`` and any path-like values
    are expected to be expanded by the caller. ``known_hosts`` is tracked for
    future use but currently host key checking is disabled in ``_connect``.
    """
    username: Optional[str]
    port: Optional[int]
    identity: Optional[Path]
    password: Optional[str]
    known_hosts: str  # "strict" | "off"
    connect_timeout: float
    pty: bool
    limit: int
    command_timeout: Optional[float] = None
    retry_attempts: int = 1


async def _connect(host: str, options: ExecOptions) -> asyncssh.SSHClientConnection:
    """Establish an SSH connection with liberal defaults.

    Notes
    - Agent forwarding is enabled.
    - Host key checking and known_hosts usage are disabled by passing ``None``.
    - ``client_keys`` and ``password`` are supplied when present in options.
    """
    connect_kwargs: Dict[str, Any] = dict(
        host=host,
        port=options.port or 22,
        username=options.username,
        connect_timeout=options.connect_timeout,
        agent_forwarding=True,
    )

    if options.identity:
        connect_kwargs["client_keys"] = [str(options.identity)]
    if options.password:
        connect_kwargs["password"] = options.password

    # Enforce no host key checking and no known_hosts file usage, equivalent to:
    #   -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
    connect_kwargs["known_hosts"] = None

    return await asyncssh.connect(**connect_kwargs)


async def _run_command(conn: asyncssh.SSHClientConnection, command: str, options: ExecOptions) -> asyncssh.SSHCompletedProcess:
    """Run a command on an established connection without raising on failure."""
    return await conn.run(command, check=False, timeout=options.command_timeout, term_type="xterm" if options.pty else None)


async def run_on_host(host: str, command: str, options: ExecOptions, semaphore: asyncio.Semaphore) -> ExecResult:
    """Run a command on a single host, respecting the shared concurrency limit.

    Retries connection errors up to ``options.retry_attempts`` using exponential
    backoff. Always returns an ``ExecResult`` capturing success or failure.
    """
    started = time.perf_counter()

    async with semaphore:
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max(1, options.retry_attempts)),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
                retry=retry_if_exception_type((asyncssh.Error, OSError)),
                reraise=True,
            ):
                with attempt:
                    conn = await _connect(host, options)
                    try:
                        completed = await _run_command(conn, command, options)
                        return ExecResult(
                            host=host,
                            exit_status=completed.exit_status,
                            stdout=completed.stdout or "",
                            stderr=completed.stderr or "",
                            ok=(completed.exit_status == 0),
                            started_at=started,
                            ended_at=time.perf_counter(),
                        )
                    finally:
                        try:
                            conn.close()
                            await conn.wait_closed()
                        except Exception:
                            pass
        except Exception as exc:  # noqa: BLE001
            return ExecResult(
                host=host,
                exit_status=None,
                stdout="",
                stderr="",
                ok=False,
                started_at=started,
                ended_at=time.perf_counter(),
                error=f"{type(exc).__name__}: {exc}",
            )


async def execute_on_hosts(hosts: Iterable[str], command: str, options: ExecOptions) -> List[ExecResult]:
    """Execute the same command across multiple hosts concurrently.

    The result list order matches the input ``hosts`` order even though
    execution completes out-of-order internally.
    """
    # Windows event loop policy safety for network-heavy asyncio apps
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

    semaphore = asyncio.Semaphore(options.limit)
    tasks = [asyncio.create_task(run_on_host(host, command, options, semaphore)) for host in hosts]
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return list(results)


