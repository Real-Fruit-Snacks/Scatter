from pathlib import Path

import subprocess
import sys


def test_cli_dry_run(tmp_path: Path) -> None:
    # Create minimal inventory
    inv = tmp_path / "inventory.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          port: 22
          connect_timeout: 5
          known_hosts: off
          pty: false
        hosts:
          - host: 127.0.0.1
            command: echo hello
        """,
        encoding="utf-8",
    )

    # Run the CLI in dry-run mode
    cmd = [
        sys.executable,
        "-m",
        "scatter",
        "run",
        "--dry-run",
        "--inventory",
        str(inv),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert proc.returncode == 0
    assert "Planned SSH Execution" in proc.stdout
    assert "127.0.0.1" in proc.stdout
