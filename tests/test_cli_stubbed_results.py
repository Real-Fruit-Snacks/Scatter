from pathlib import Path
from typing import List

import pytest
from typer.testing import CliRunner

from scatter.cli import app
from scatter.ssh import ExecResult


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def write_inventory(tmp_path: Path) -> Path:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
          pty: false
        hosts:
          - host: host1
            command: echo ok
          - host: host2
            command: echo ok2
        """,
        encoding="utf-8",
    )
    return inv


@pytest.mark.parametrize("use_save_dir", [False, True])
def test_summary_and_error_listing_with_stubbed_results(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, use_save_dir: bool) -> None:
    inv = write_inventory(tmp_path)

    async def fake_run_on_host(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        if host == "host1":
            return ExecResult(host=host, exit_status=0, stdout="hello\nworld\n", stderr="", ok=True, started_at=0.0, ended_at=0.1)
        else:
            return ExecResult(host=host, exit_status=None, stdout="", stderr="boom", ok=False, started_at=0.0, ended_at=0.2, error="Auth failed")

    monkeypatch.setattr("scatter.ssh.run_on_host", fake_run_on_host)

    args: List[str] = ["run", "--inventory", str(inv), "--no-progress"]
    if use_save_dir:
        args += ["--save-dir", str(tmp_path / "out")] 

    result = runner.invoke(app, args)

    # One host fails
    assert result.exit_code == 1
    stdout = result.stdout
    assert "Failed:" in stdout and "Succeeded:" in stdout
    assert "host1" in stdout and "host2" in stdout
    assert "FAIL" in stdout and "OK" in stdout
    assert "- host2: Auth failed" in stdout

    if use_save_dir:
        outdir = tmp_path / "out"
        assert (outdir / "host1.stdout.txt").read_text(encoding="utf-8").startswith("hello")
        assert (outdir / "host1.stderr.txt").read_text(encoding="utf-8") == ""
        assert (outdir / "host2.stdout.txt").read_text(encoding="utf-8") == ""
        # stderr file contains error stderr string
        assert (outdir / "host2.stderr.txt").read_text(encoding="utf-8").strip() == "boom"


def test_verbose_prints_blocks(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = write_inventory(tmp_path)

    async def fake_run_on_host(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        if host == "host1":
            return ExecResult(host=host, exit_status=0, stdout="line1\nline2\n", stderr="", ok=True, started_at=0.0, ended_at=0.1)
        else:
            return ExecResult(host=host, exit_status=1, stdout="", stderr="errline", ok=False, started_at=0.0, ended_at=0.2, error="SomeError")

    monkeypatch.setattr("scatter.ssh.run_on_host", fake_run_on_host)

    # -vv should enable block printing; also disable progress for stable output
    result = runner.invoke(app, ["run", "-vv", "--inventory", str(inv), "--no-progress"])

    assert result.exit_code == 1
    text = result.stdout
    assert "STDOUT - host1" in text
    assert "line1" in text
    assert "STDERR - host2" in text
    assert "errline" in text


def test_missing_command_errors(runner: CliRunner, tmp_path: Path) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: h1
        """,
        encoding="utf-8",
    )

    # No CLI command and no host command
    result = runner.invoke(app, ["run", "--inventory", str(inv), "--no-progress"])
    assert result.exit_code != 0
    # Typer writes parameter errors to stderr
    assert "No command provided" in (result.stderr or "") or "Error" in (result.stderr or "")
