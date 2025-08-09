from pathlib import Path
import json
import pytest
from typer.testing import CliRunner

from scatter.cli import app
from scatter.ssh import ExecResult


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_jsonl_log_contents_with_stubbed_results(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: a
            command: echo a
          - host: b
            command: echo b
        """,
        encoding="utf-8",
    )

    async def fake_run_on_host(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        return ExecResult(host=host, exit_status=0, stdout=f"{host}\n", stderr="", ok=True, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake_run_on_host)

    logfile = tmp_path / "out.jsonl"
    result = runner.invoke(app, ["run", "--inventory", str(inv), "--no-progress", "--log-file", str(logfile)])

    assert result.exit_code == 0
    content = logfile.read_text(encoding="utf-8").strip().splitlines()
    assert len(content) == 2
    records = [json.loads(line) for line in content]
    hosts = {r["host"] for r in records}
    assert hosts == {"a", "b"}
    for rec in records:
        assert rec["ok"] is True
        assert rec["exit_status"] == 0
        assert rec["command"] in ("echo a", "echo b")
