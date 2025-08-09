from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from scatter.ssh import ExecOptions, run_on_host, execute_on_hosts


class DummyConn:
    def __init__(self, to_return: Any) -> None:
        self._to_return = to_return
        self.closed = False

    async def run(self, command: str, check: bool, timeout: float | None, term_type: str | None):
        return self._to_return

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class Completed:
    def __init__(self, exit_status: int, stdout: str = "", stderr: str = "") -> None:
        self.exit_status = exit_status
        self.stdout = stdout
        self.stderr = stderr


def make_options(**overrides: Any) -> ExecOptions:
    base = dict(
        username="u",
        port=2222,
        identity=None,
        password=None,
        known_hosts="off",
        connect_timeout=5.0,
        pty=False,
        limit=5,
        command_timeout=None,
        retry_attempts=1,
    )
    base.update(overrides)
    return ExecOptions(**base)


def test_connect_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: Dict[str, Any] = {}

    async def fake_connect(**kwargs: Any):  # type: ignore[no-redef]
        captured.update(kwargs)
        return DummyConn(Completed(0))

    monkeypatch.setattr("asyncssh.connect", fake_connect)

    opts = make_options(username="alice", port=2200, password="pw", connect_timeout=3.0)

    async def go():
        sem = asyncio.Semaphore(1)
        res = await run_on_host("example", "true", opts, sem)
        return res

    res = asyncio.run(go())
    assert res.ok is True
    # Verify critical kwargs
    assert captured["host"] == "example"
    assert captured["port"] == 2200
    assert captured["username"] == "alice"
    assert captured["password"] == "pw"
    assert captured["connect_timeout"] == 3.0
    assert captured["agent_forwarding"] is True
    # Host key checks disabled per policy
    assert captured.get("known_hosts") is None


def test_client_keys_from_identity(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    captured: Dict[str, Any] = {}

    async def fake_connect(**kwargs: Any):  # type: ignore[no-redef]
        captured.update(kwargs)
        return DummyConn(Completed(0))

    monkeypatch.setattr("asyncssh.connect", fake_connect)

    key = tmp_path / "id_test"
    key.write_text("k", encoding="utf-8")
    opts = make_options(identity=key)

    async def go():
        sem = asyncio.Semaphore(1)
        res = await run_on_host("example", "true", opts, sem)
        return res

    res = asyncio.run(go())
    assert res.ok is True
    assert captured.get("client_keys") == [str(key)]


def test_pty_and_timeout_propagation(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    class SpyConn(DummyConn):
        async def run(self, command: str, check: bool, timeout: float | None, term_type: str | None):  # type: ignore[override]
            calls.append({"timeout": timeout, "term_type": term_type, "command": command})
            return Completed(0)

    async def fake_connect(**kwargs: Any):  # type: ignore[no-redef]
        return SpyConn(Completed(0, stdout="ok"))

    monkeypatch.setattr("asyncssh.connect", fake_connect)

    opts = make_options(pty=True, command_timeout=7.0)

    async def go():
        sem = asyncio.Semaphore(1)
        res = await run_on_host("h", "echo hi", opts, sem)
        return res

    res = asyncio.run(go())
    assert res.ok is True
    assert calls, "Expected SpyConn.run to be called"
    assert calls[0]["term_type"] == "xterm"
    assert calls[0]["timeout"] == 7.0


def test_retry_behavior_success_on_second_try(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    class FailingOnce(DummyConn):
        async def run(self, command: str, check: bool, timeout: float | None, term_type: str | None):  # type: ignore[override]
            return Completed(0)

    async def fake_connect(**kwargs: Any):  # type: ignore[no-redef]
        attempts["count"] += 1
        if attempts["count"] == 1:
            # Use OSError to avoid strict constructor signature differences
            raise OSError("transient")
        return FailingOnce(Completed(0))

    monkeypatch.setattr("asyncssh.connect", fake_connect)

    opts = make_options(retry_attempts=2)

    async def go():
        sem = asyncio.Semaphore(1)
        res = await run_on_host("h", "true", opts, sem)
        return res

    res = asyncio.run(go())
    assert res.ok is True
    assert attempts["count"] == 2


def test_retry_behavior_all_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    async def fake_connect(**kwargs: Any):  # type: ignore[no-redef]
        attempts["count"] += 1
        # Use OSError to avoid strict constructor signature differences
        raise OSError("boom")

    monkeypatch.setattr("asyncssh.connect", fake_connect)

    opts = make_options(retry_attempts=3)

    async def go():
        sem = asyncio.Semaphore(1)
        res = await run_on_host("h", "true", opts, sem)
        return res

    res = asyncio.run(go())
    assert res.ok is False
    assert res.exit_status is None
    assert "Error" in (res.error or "") or "boom" in (res.error or "")
    assert attempts["count"] == 3


def test_execute_on_hosts_preserves_input_order(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(host: str, command: str, options: ExecOptions, semaphore: asyncio.Semaphore):  # type: ignore[override]
        # Return in reverse order artificially by delaying certain hosts
        if host.endswith("3"):
            await asyncio.sleep(0.01)
        return type("R", (), {"host": host, "ok": True, "exit_status": 0, "stdout": "", "stderr": "", "started_at": 0.0, "ended_at": 0.0})()

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    opts = make_options()

    async def go():
        return await execute_on_hosts(["h1", "h2", "h3"], "echo", opts)

    results = asyncio.run(go())
    assert [r.host for r in results] == ["h1", "h2", "h3"]


def test_concurrency_limit_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    # Track concurrent calls inside command execution
    state = {"active": 0, "max_active": 0}

    async def fake_connect(**kwargs: Any):  # type: ignore[no-redef]
        return DummyConn(Completed(0))

    async def fake_run_command(conn, command: str, options: ExecOptions):  # type: ignore[no-redef]
        # Simulate work and track concurrency
        state["active"] += 1
        state["max_active"] = max(state["max_active"], state["active"])
        await asyncio.sleep(0.02)
        state["active"] -= 1
        return Completed(0)

    monkeypatch.setattr("scatter.ssh._connect", fake_connect)
    monkeypatch.setattr("scatter.ssh._run_command", fake_run_command)

    opts = make_options(limit=2)

    async def go():
        return await execute_on_hosts([f"h{i}" for i in range(6)], "echo", opts)

    results = asyncio.run(go())
    # Focus on concurrency behavior; results may vary across environments
    assert state["max_active"] <= 2


