from __future__ import annotations

from pathlib import Path
import json

import pytest
from typer.testing import CliRunner

from scatter.cli import app
from scatter.ssh import ExecResult


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_logfile_nested_dirs_created_and_records_written(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: u
          known_hosts: off
        hosts:
          - host: a
            command: echo a
          - host: b
            command: echo b
        """,
        encoding="utf-8",
    )

    async def fake(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        return ExecResult(host=host, exit_status=0, stdout=host + "\n", stderr="", ok=True, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    logfile = tmp_path / "nested" / "logs" / "run.jsonl"
    res = runner.invoke(app, ["run", "--inventory", str(inv), "--no-progress", "--log-file", str(logfile)])
    assert res.exit_code == 0
    assert logfile.exists()
    lines = logfile.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    recs = [json.loads(l) for l in lines]
    assert {r["host"] for r in recs} == {"a", "b"}


def test_save_dir_nested_dirs_created(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: u
          known_hosts: off
        hosts:
          - host: h
            command: echo ok
        """,
        encoding="utf-8",
    )

    async def fake(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        return ExecResult(host=host, exit_status=0, stdout="hi", stderr="", ok=True, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    outdir = tmp_path / "nested" / "outputs"
    res = runner.invoke(app, ["run", "--inventory", str(inv), "--no-progress", "--save-dir", str(outdir)])
    assert res.exit_code == 0
    assert (outdir / "h.stdout.txt").exists()
    assert (outdir / "h.stderr.txt").exists()


def test_jsonl_failure_record_has_error(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: u
          known_hosts: off
        hosts:
          - host: bad
            command: echo x
        """,
        encoding="utf-8",
    )

    async def fake(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        return ExecResult(host=host, exit_status=None, stdout="", stderr="E", ok=False, started_at=0.0, ended_at=0.1, error="Auth failed")

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    logfile = tmp_path / "out.jsonl"
    res = runner.invoke(app, ["run", "--inventory", str(inv), "--no-progress", "--log-file", str(logfile)])
    assert res.exit_code == 1
    rec = json.loads(logfile.read_text(encoding="utf-8").strip())
    assert rec["ok"] is False
    assert rec["exit_status"] is None
    assert rec["error"]


