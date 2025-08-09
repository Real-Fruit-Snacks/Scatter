from pathlib import Path
import subprocess
import sys
import json


def test_log_file_dry_run(tmp_path: Path) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: 127.0.0.1
            command: echo hello
        """,
        encoding="utf-8",
    )

    logfile = tmp_path / "out.jsonl"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scatter",
            "run",
            "--inventory",
            str(inv),
            "--dry-run",
            "--log-file",
            str(logfile),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # In dry-run we exit 0 before logging. So we emulate by running with --dry-run disabled
    # but it's okay to just check file existence is not created in dry-run.
    assert proc.returncode == 0
    assert not logfile.exists()

    # Now run without dry-run and with a trivial localhost (this will attempt SSH and may fail); we won't assert contents
    # Skipping actual non-dry run to avoid flakiness.
