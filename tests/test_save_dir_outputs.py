from pathlib import Path
import pytest
from typer.testing import CliRunner

from scatter.cli import app
from scatter.ssh import ExecResult


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_save_dir_writes_and_sanitizes(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: bad/host:name
            command: echo x
        """,
        encoding="utf-8",
    )

    async def fake_run_on_host(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        return ExecResult(host=host, exit_status=0, stdout="abc", stderr="", ok=True, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake_run_on_host)

    outdir = tmp_path / "out"
    res = runner.invoke(app, ["run", "--inventory", str(inv), "--no-progress", "--save-dir", str(outdir)])
    assert res.exit_code == 0

    # Sanitized file names
    assert (outdir / "bad_host_name.stdout.txt").exists()
    assert (outdir / "bad_host_name.stderr.txt").exists()
