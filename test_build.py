#!/usr/bin/env python3
"""
Test build script functionality without actually building.
This verifies the build script dependencies and setup.
"""

import sys
import subprocess
from pathlib import Path


def test_dependencies():
    """Test that all required dependencies can be installed."""
    print("Testing build dependencies...")

    # Test tomllib/tomli
    try:
        import tomllib
        print("✅ Using built-in tomllib")
    except ImportError:
        try:
            import tomli
            print("✅ Using tomli package")
        except ImportError:
            print("⚠️  Will need to install tomli")

    # Test PyInstaller
    try:
        import PyInstaller
        print(f"✅ PyInstaller {PyInstaller.__version__} available")
    except ImportError:
        print("⚠️  Will need to install PyInstaller")

    # Test that we can read version
    try:
        if sys.version_info >= (3, 11):
            import tomllib
            with open("pyproject.toml", "rb") as f:
                data = tomllib.load(f)
        else:
            import tomli
            with open("pyproject.toml", "rb") as f:
                data = tomli.load(f)

        version = data["project"]["version"]
        print(f"✅ Project version: {version}")
    except Exception as e:
        print(f"❌ Could not read version: {e}")
        return False

    return True


def test_scatter_import():
    """Test that scatter can be imported."""
    try:
        import scatter
        print("✅ Scatter module can be imported")

        # Test CLI import
        from scatter.cli import app
        print("✅ Scatter CLI can be imported")

        return True
    except Exception as e:
        print(f"❌ Could not import scatter: {e}")
        return False


def main():
    """Run tests."""
    if not Path("pyproject.toml").exists():
        print("❌ Not in project root (no pyproject.toml)")
        sys.exit(1)

    print("🧪 Testing build script prerequisites...")
    print(f"Python {sys.version}")
    print()

    success = True

    if not test_dependencies():
        success = False

    print()
    if not test_scatter_import():
        success = False

    print()
    if success:
        print("🎉 All tests passed! Build script should work.")
        print("Run: python build_standalone.py")
    else:
        print("❌ Some tests failed. Install missing dependencies first:")
        print("pip install -e .")
        print("pip install pyinstaller")
        if sys.version_info < (3, 11):
            print("pip install tomli")
        sys.exit(1)


if __name__ == "__main__":
    main()
