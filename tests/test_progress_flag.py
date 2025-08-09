from pathlib import Path
import subprocess
import sys

def test_no_progress_dry_run(tmp_path: Path) -> None:
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

    proc = subprocess.run(
        [sys.executable, "-m", "scatter", "run", "--dry-run", "--no-progress", "--inventory", str(inv)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "Planned SSH Execution" in proc.stdout
