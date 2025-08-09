from pathlib import Path
import subprocess
import sys


def test_pty_flag_in_dry_run(tmp_path: Path) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
          pty: true
        hosts:
          - host: h1
            command: echo ok
        """,
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, "-m", "scatter", "run", "--dry-run", "--inventory", str(inv)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    out = proc.stdout
    assert "Planned SSH Execution" in out
    assert "h1" in out
    assert "Will run on 1 hosts" in out
