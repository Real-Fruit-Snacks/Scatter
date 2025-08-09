from pathlib import Path

import subprocess
import sys


def test_cli_command_file_precedence(tmp_path: Path) -> None:
    inv = tmp_path / "inventory.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: localhost
        """,
        encoding="utf-8",
    )

    cmdfile = tmp_path / "cmd.sh"
    cmdfile.write_text("echo from_file", encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "scatter",
        "run",
        "--dry-run",
        "--command-file",
        str(cmdfile),
        "--inventory",
        str(inv),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert proc.returncode == 0
    assert "from_file" in proc.stdout
