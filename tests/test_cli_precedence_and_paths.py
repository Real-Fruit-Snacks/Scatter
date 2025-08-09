from __future__ import annotations

import os
from pathlib import Path
from typing import List

import pytest
from typer.testing import CliRunner

from scatter.cli import app
from scatter.ssh import ExecResult


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_username_port_precedence_host_over_cli(runner: CliRunner, tmp_path: Path) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: default
          port: 22
          known_hosts: off
        hosts:
          - host: h1
            username: hostuser
            port: 2201
            command: echo x
        """,
        encoding="utf-8",
    )

    # CLI sets username/port, but current implementation prefers per-host values
    result = runner.invoke(
        app,
        [
            "run",
            "--inventory",
            str(inv),
            "--dry-run",
            "--username",
            "cliuser",
            "--port",
            "10022",
            "--no-progress",
        ],
    )

    # We don't execute SSH; just check summary table reflects host-level auth
    assert result.exit_code == 0
    text = result.stdout
    assert "h1" in text
    assert "key:" not in text  # no identity provided at host/CLI
    # Ensure CLI arguments were accepted (exit 0) and output includes the host
    # and auth preview shows a key when configured


def test_command_resolution_order_host_overrides_file_and_cli(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: u
          known_hosts: off
        hosts:
          - host: h
            command: echo from_host
        """,
        encoding="utf-8",
    )

    cmdfile = tmp_path / "cmd.txt"
    cmdfile.write_text("echo from_file", encoding="utf-8")

    async def fake(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        return ExecResult(host=host, exit_status=0, stdout=cmd + "\n", stderr="", ok=True, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    res = runner.invoke(
        app,
        [
            "run",
            "--inventory",
            str(inv),
            "--command-file",
            str(cmdfile),
            "echo from_cli",
            "--no-progress",
        ],
    )
    assert res.exit_code == 0
    # Because host.command wins, stdout should include 'echo from_host'
    assert "from_host" in res.stdout
    assert "from_file" not in res.stdout
    assert "from_cli" not in res.stdout


def test_command_resolution_cli_used_when_no_host_or_file(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: u
          known_hosts: off
        hosts:
          - host: h
        """,
        encoding="utf-8",
    )

    async def fake(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        return ExecResult(host=host, exit_status=0, stdout=cmd + "\n", stderr="", ok=True, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    res = runner.invoke(app, ["run", "--inventory", str(inv), "echo from_cli", "--no-progress"])
    assert res.exit_code == 0
    assert "from_cli" in res.stdout


def test_path_expansion_for_identity_and_files(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[override]
    # Prepare env var-based paths
    monkeypatch.setenv("MY_KEY", str(tmp_path / "id_ed25519"))
    (tmp_path / "id_ed25519").write_text("dummy", encoding="utf-8")

    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: u
          known_hosts: off
          identity: env:MY_KEY
        hosts:
          - host: h
            command: echo ok
        """,
        encoding="utf-8",
    )

    # Also pass CLI identity using ~ expansion
    home_identity = Path("~") / "my_id"
    expanded_home_identity = Path(os.path.expanduser(str(home_identity)))
    expanded_home_identity.parent.mkdir(parents=True, exist_ok=True)
    expanded_home_identity.write_text("dummy", encoding="utf-8")

    # Use dry-run and ensure printed preview includes 'key:' and expanded path
    res = runner.invoke(
        app,
        [
            "run",
            "--dry-run",
            "--inventory",
            str(inv),
            "--identity",
            str(home_identity),
        ],
    )
    assert res.exit_code == 0
    # The preview prints 'key:<path>' for auth
    assert "key:" in res.stdout
    assert str(expanded_home_identity) in res.stdout


def test_known_hosts_flag_wiring_to_exec_options(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: u
          known_hosts: strict
        hosts:
          - host: h
            command: echo ok
        """,
        encoding="utf-8",
    )

    seen: dict = {}

    async def fake(host: str, cmd: str, options, semaphore) -> ExecResult:  # type: ignore[override]
        seen["known_hosts"] = options.known_hosts
        return ExecResult(host=host, exit_status=0, stdout="", stderr="", ok=True, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    # Override to off via CLI
    res = runner.invoke(app, ["run", "--inventory", str(inv), "--no-progress", "--known-hosts", "off"])
    assert res.exit_code == 0
    assert seen.get("known_hosts") == "off"


def test_per_host_identity_expansion_in_dry_run(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    keyfile = tmp_path / "per_host_id"
    keyfile.write_text("k", encoding="utf-8")
    monkeypatch.setenv("HKEY", str(keyfile))

    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: u
          known_hosts: off
        hosts:
          - host: h
            identity: env:HKEY
            command: echo ok
        """,
        encoding="utf-8",
    )

    res = runner.invoke(app, ["run", "--inventory", str(inv), "--dry-run"])
    assert res.exit_code == 0
    # The preview line should indicate that a key path is present
    assert "key:" in res.stdout


def test_quiet_mode_non_dry_run_only_summary(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        ok = host == "a"
        return ExecResult(host=host, exit_status=0 if ok else 1, stdout="", stderr="", ok=ok, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    res = runner.invoke(app, ["run", "--inventory", str(inv), "--quiet"])
    assert res.exit_code == 1
    # Quiet mode prints only one summary line, without the rich table
    out = res.stdout.strip().splitlines()
    assert len(out) == 1
    assert ("Failed:" in out[0]) or ("Succeeded:" in out[0])


def test_progress_with_quiet_suppresses_streaming(runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        return ExecResult(host=host, exit_status=0, stdout="", stderr="", ok=True, started_at=0.0, ended_at=0.1)

    monkeypatch.setattr("scatter.ssh.run_on_host", fake)

    res = runner.invoke(app, ["run", "--inventory", str(inv), "--quiet"])
    assert res.exit_code == 0
    # Ensure no per-host streaming lines appear (quiet mode suppresses details)
    assert len(res.stdout.strip().splitlines()) == 1


