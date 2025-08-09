import subprocess
import sys


def test_cli_help() -> None:
    proc = subprocess.run([sys.executable, "-m", "scatter", "--help"], capture_output=True, text=True)
    assert proc.returncode == 0
    assert "Concurrent SSH executor" in proc.stdout

    proc2 = subprocess.run([sys.executable, "-m", "scatter", "run", "--help"], capture_output=True, text=True)
    assert proc2.returncode == 0
    assert "Run COMMAND across all hosts" in proc2.stdout
