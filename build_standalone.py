#!/usr/bin/env python3
"""
Build standalone executables for Scatter using PyInstaller.

This script creates self-contained executables that include Python and all dependencies,
so users can download and run without needing Python installed.

Usage:
    python build_standalone.py
"""

import platform
import shutil
import subprocess
import sys
from pathlib import Path


def get_platform_suffix():
    """Get platform-specific suffix for the executable name."""
    # Only targeting Linux Ubuntu systems
    import platform
    machine = platform.machine().lower()
    return f"linux-{machine}"


def get_version():
    """Get version from pyproject.toml."""
    try:
        import tomllib  # Python 3.11+
        with open("pyproject.toml", "rb") as f:
            pyproject = tomllib.load(f)
        return pyproject["project"]["version"]
    except ImportError:
        try:
            import tomli
            with open("pyproject.toml", "rb") as f:
                pyproject = tomli.load(f)
            return pyproject["project"]["version"]
        except ImportError:
            # Last resort: try to parse manually
            with open("pyproject.toml", "r") as f:
                for line in f:
                    if line.startswith('version = "'):
                        return line.split('"')[1]
            return "dev"


def install_build_deps():
    """Install build dependencies."""
    deps = ["pyinstaller>=6.0.0"]

    # Add tomli for Python < 3.11
    if sys.version_info < (3, 11):
        deps.append("tomli>=2.0.0")

    print("Installing build dependencies...")
    for dep in deps:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", dep],
                           check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to install {dep}: {e}")
            sys.exit(1)

    print("✅ Build dependencies installed")


def clean_build():
    """Clean previous build artifacts."""
    paths_to_clean = ["build", "dist", "scatter.spec", "__pycache__"]

    for path_str in paths_to_clean:
        path = Path(path_str)
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    print("✅ Cleaned previous build artifacts")


def create_version_info(version):
    """Linux doesn't need Windows version info - this is a no-op."""
    print("✅ Skipping Windows version info (Linux build)")
def build_executable():
    """Build standalone executable using PyInstaller."""
    version = get_version()
    platform_suffix = get_platform_suffix()
    exe_name = f"scatter-{version}-{platform_suffix}"

    print(f"Building {exe_name}...")

    # No Windows-specific setup needed for Linux builds
    create_version_info(version)

    # Linux-optimized PyInstaller options
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", exe_name,
        "--console",
        "--clean",
        # Entry point - use standalone entry to avoid relative import issues
        "standalone_entry.py",
        # Include important files
        "--add-data", "README.md:.",
        "--add-data", "inventory.example.yaml:.",
        # Linux optimizations
        "--optimize", "2",
        "--strip",  # Strip debug symbols
    ]

    # Hide imports for Linux deployment
    hidden_imports = [
        "scatter.cli",
        "scatter.config",
        "scatter.ssh",
        "asyncssh",
        "rich",
        "typer",
        "tenacity",
        "uvloop",  # Always include uvloop for Linux
    ]

    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])

    # Exclude unused packages to reduce size
    excludes = ["tkinter", "matplotlib",
                "numpy", "pandas", "jupyter", "IPython"]
    for exc in excludes:
        cmd.extend(["--exclude-module", exc])

    print(f"Running PyInstaller: {' '.join(cmd[:8])}...")
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True)
        print("✅ PyInstaller completed successfully")
        if result.stdout:
            # Show last 500 chars
            print("PyInstaller output:", result.stdout[-500:])
    except subprocess.CalledProcessError as e:
        print(f"❌ PyInstaller failed: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout[-1000:])
        if e.stderr:
            print("STDERR:", e.stderr[-1000:])
        sys.exit(1)

    exe_path = Path("dist") / exe_name
    if not exe_path.exists():
        print(f"❌ Expected executable not found: {exe_path}")
        print("Files in dist/:", list(Path("dist").glob("*"))
              if Path("dist").exists() else "dist/ doesn't exist")
        sys.exit(1)

    return str(exe_path)


def test_executable(exe_path):
    """Test the built executable."""
    print(f"Testing executable: {exe_path}")

    try:
        # Test help command
        result = subprocess.run([exe_path, "--help"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and "Concurrent SSH executor" in result.stdout:
            print("✅ Basic functionality test passed")
            return True
        else:
            print(f"❌ Help test failed (code {result.returncode})")
            if result.stderr:
                print("STDERR:", result.stderr[:500])
            return False
    except subprocess.TimeoutExpired:
        print("❌ Executable test timed out")
        return False
    except Exception as e:
        print(f"❌ Error testing executable: {e}")
        return False


def main():
    """Main build process."""
    if not Path("pyproject.toml").exists():
        print("❌ pyproject.toml not found. Run this script from the project root.")
        sys.exit(1)

    print("🚀 Building Scatter standalone executable...")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {sys.version}")

    try:
        # Install dependencies and clean
        install_build_deps()
        clean_build()

        # Build executable
        exe_path = build_executable()

        # Test executable
        if test_executable(exe_path):
            size_mb = Path(exe_path).stat().st_size / (1024 * 1024)
            print(f"🎉 Successfully built: {exe_path}")
            print(f"📊 Size: {size_mb:.1f} MB")
            print()
            print(
                "You can now distribute this single file to users who don't have Python installed!")
        else:
            print("❌ Executable test failed")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n⏹️  Build interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Build failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
