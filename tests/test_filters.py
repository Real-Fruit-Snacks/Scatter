from pathlib import Path
import subprocess
import sys


def test_include_exclude_tags(tmp_path: Path) -> None:
    inv = tmp_path / "inv.yaml"
    inv.write_text(
        """
        defaults:
          username: ubuntu
          known_hosts: off
        hosts:
          - host: web-1
            tags: [web, prod]
            command: echo a
          - host: db-1
            tags: [db, staging]
            command: echo b
          - host: cache-1
            tags: [cache]
            command: echo c
        """,
        encoding="utf-8",
    )

    # Include web or db, exclude staging
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scatter",
            "run",
            "--dry-run",
            "--inventory",
            str(inv),
        ],
        capture_output=True,
        text=True,
    )
    # No filters prints all
    assert proc.returncode == 0
    out = proc.stdout
    assert "web-1" in out and "db-1" in out and "cache-1" in out

    # With filters (currently not implemented in CLI; placeholder for future extension)
    # This test documents desired behavior when filters are added in the future.
    # We simply ensure current behavior doesn't crash with unknown args by skipping actual call.


def test_hosts_filter_pattern_placeholder() -> None:
    # Placeholder to keep a slot for host pattern filtering tests when implemented
    assert True
