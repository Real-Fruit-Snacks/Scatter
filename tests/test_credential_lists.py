from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

import pytest

from scatter.ssh import ExecOptions, run_on_host


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


def test_password_list_attempts_order(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: List[Tuple[Optional[str], Optional[str]]] = []

    async def fake_connect(**kwargs: Any):  # type: ignore[no-redef]
        attempts.append((kwargs.get("username"), kwargs.get("password")))
        # Fail first attempt, succeed on the second
        if len(attempts) == 1:
            raise OSError("first failed")
        return DummyConn(Completed(0))

    monkeypatch.setattr("asyncssh.connect", fake_connect)

    opts = make_options(username="admin", password_candidates=["p1", "p2"])  # type: ignore[arg-type]

    async def go():
        sem = asyncio.Semaphore(1)
        return await run_on_host("h", "true", opts, sem)

    res = asyncio.run(go())
    assert res.ok is True
    assert attempts == [("admin", "p1"), ("admin", "p2")]


def test_username_list_key_then_password(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    attempts: List[Tuple[Optional[str], Optional[str]]] = []

    key = tmp_path / "id_ed25519"
    key.write_text("k", encoding="utf-8")

    async def fake_connect(**kwargs: Any):  # type: ignore[no-redef]
        attempts.append((kwargs.get("username"), kwargs.get("password")))
        # Fail all key-only attempts, succeed on first password attempt
        if kwargs.get("password") is None:
            raise OSError("key only fails for test")
        return DummyConn(Completed(0))

    monkeypatch.setattr("asyncssh.connect", fake_connect)

    opts = make_options(identity=key, username_candidates=["u1", "u2"], password_candidates=["pw"])  # type: ignore[arg-type]

    async def go():
        sem = asyncio.Semaphore(1)
        return await run_on_host("h", "true", opts, sem)

    res = asyncio.run(go())
    assert res.ok is True
    # Expect key-only for each username first, then first password attempt
    assert attempts == [("u1", None), ("u2", None), ("u1", "pw")]


