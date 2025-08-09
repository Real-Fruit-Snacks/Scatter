from pathlib import Path
import pytest
from typer.testing import CliRunner

from scatter.cli import app
from scatter.ssh import ExecResult


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_progress_streaming_stubbed(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: s1
            command: echo a
          - host: s2
            command: echo b
        """,
        encoding="utf-8",
    )

    async def fake(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        if host == "s1":
            return ExecResult(host=host, exit_status=0, stdout="A\n", stderr="", ok=True, started_at=0.0, ended_at=0.1)
        return ExecResult(host=host, exit_status=1, stdout="", stderr="E", ok=False, started_at=0.0, ended_at=0.2, error=None)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    # progress enabled by default
    res = runner.invoke(app, ["run", "--inventory", str(inv)])
    # Exit 1 due to one failure
    assert res.exit_code == 1
    out = res.stdout
    # Should contain per-host lines printed as they complete
    assert "s1:" in out and "OK" in out
    assert "s2:" in out and "FAIL" in out
