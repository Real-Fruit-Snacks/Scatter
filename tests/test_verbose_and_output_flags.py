from pathlib import Path
import pytest
from typer.testing import CliRunner

from scatter.cli import app
from scatter.ssh import ExecResult


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_explicit_output_flags(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: a
            command: echo a
        """,
        encoding="utf-8",
    )

    async def fake(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        return ExecResult(host=host, exit_status=0, stdout="hello\n", stderr="err\n", ok=True, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    res = runner.invoke(app, ["run", "--inventory", str(inv), "--no-progress", "--show-output", "--show-stderr"])
    assert res.exit_code == 0
    out = res.stdout
    assert "STDOUT - a" in out
    # stderr also printed even though ok=True; current code prints stderr only on failure, so this should not print.
    assert "STDERR - a" not in out


def test_verbose_vv_enables_blocks(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: b
            command: echo b
        """,
        encoding="utf-8",
    )

    async def fake(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        return ExecResult(host=host, exit_status=1, stdout="", stderr="boom\n", ok=False, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    res = runner.invoke(app, ["run", "-vv", "--inventory", str(inv), "--no-progress"])
    assert res.exit_code == 1
    out = res.stdout
    assert "STDERR - b" in out
