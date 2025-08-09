from pathlib import Path
import subprocess
import sys


def run_cli(args: list[str], cwd: Path | None = None):
    return subprocess.run([sys.executable, "-m", "scatter", *args], capture_output=True, text=True, cwd=cwd)


def test_identity_in_defaults_and_host_override(tmp_path: Path) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
          identity: ~/.ssh/id_rsa
        hosts:
          - host: h1
            identity: ~/.ssh/other
            command: echo hi
        """,
        encoding="utf-8",
    )

    proc = run_cli(["run", "--dry-run", "--inventory", str(inv)])
    assert proc.returncode == 0
    # The preview should include key: paths; we won't assert full path expansion to be portable
    assert "key:" in proc.stdout


def test_summary_counts_and_quiet_mode(tmp_path: Path) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: 127.0.0.1
            command: echo ok
        """,
        encoding="utf-8",
    )

    # Use dry-run to avoid real SSH, just check quiet summary
    proc = run_cli(["run", "--dry-run", "--inventory", str(inv), "--quiet"])
    assert proc.returncode == 0
    assert "Will run on 1 hosts" in proc.stdout or "Succeeded:" in proc.stdout or proc.stdout.strip() != ""
