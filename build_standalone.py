#!/usr/bin/env python3
"""
Build standalone distributions for Scatter.

This script creates:
1. Standalone executable using PyInstaller (binary)
2. Portable tarball with Python files and dependencies (source)

Usage:
    python build_standalone.py [--type=binary|tarball|both]
"""

import argparse
import platform
import shutil
import subprocess
import sys
import tarfile
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


def create_portable_tarball():
    """Create a portable tarball with Python files and dependencies."""
    version = get_version()
    platform_suffix = get_platform_suffix()
    tarball_name = f"scatter-{version}-{platform_suffix}-portable.tar.gz"
    
    print(f"Creating portable tarball: {tarball_name}")
    
    # Create temporary directory for the portable package
    temp_dir = Path("temp_portable")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()
    
    try:
        # Create the main package directory
        package_dir = temp_dir / f"scatter-{version}-portable"
        package_dir.mkdir()
        
        # Download dependencies to a local directory
        wheelhouse_dir = package_dir / "wheelhouse"
        wheelhouse_dir.mkdir()
        
        print("📦 Downloading dependencies...")
        subprocess.run([
            sys.executable, "-m", "pip", "download",
            "--dest", str(wheelhouse_dir),
            "."
        ], check=True, capture_output=True)
        
        # Copy source files
        print("📁 Copying source files...")
        
        # Copy the scatter package
        shutil.copytree("scatter", package_dir / "scatter")
        
        # Copy important files
        important_files = [
            "README.md",
            "inventory.example.yaml", 
            "pyproject.toml",
            "requirements.txt",
            "standalone_entry.py"
        ]
        
        for file in important_files:
            if Path(file).exists():
                shutil.copy2(file, package_dir / file)
        
        # Create a run script
        run_script = package_dir / "run_scatter.py"
        run_script.write_text('''#!/usr/bin/env python3
"""
Portable Scatter runner.
This script sets up the Python path and runs Scatter using local dependencies.
"""
import sys
import subprocess
from pathlib import Path

# Add wheelhouse to Python path for dependencies
script_dir = Path(__file__).parent
wheelhouse = script_dir / "wheelhouse"

# Install dependencies locally if not already installed
try:
    import scatter
except ImportError:
    print("Installing dependencies...")
    subprocess.run([
        sys.executable, "-m", "pip", "install", 
        "--user", "--no-index", "--find-links", str(wheelhouse),
        "scatter"
    ], check=True)

# Now run scatter
from scatter.cli import app
if __name__ == "__main__":
    app()
''')
        
        # Create a bash launcher script
        bash_script = package_dir / "scatter.sh"
        bash_script.write_text('''#!/bin/bash
# Portable Scatter launcher for Linux
cd "$(dirname "$0")"
python3 run_scatter.py "$@"
''')
        bash_script.chmod(0o755)
        
        # Create README for the portable package
        portable_readme = package_dir / "PORTABLE_README.md"
        portable_readme.write_text(f'''# Scatter {version} Portable Package

This is a portable version of Scatter that includes all dependencies.

## Requirements
- Python 3.10+ installed on the system
- Linux Ubuntu or compatible

## Usage

### Option 1: Direct Python execution
```bash
python3 run_scatter.py --help
python3 run_scatter.py run "hostname" --inventory inventory.example.yaml
```

### Option 2: Using the shell script
```bash
./scatter.sh --help  
./scatter.sh run "hostname" --inventory inventory.example.yaml
```

## What's Included
- `scatter/` - The Scatter Python package
- `wheelhouse/` - All dependencies as wheel files
- `run_scatter.py` - Python runner script
- `scatter.sh` - Bash launcher script
- `README.md` - Main documentation
- `inventory.example.yaml` - Example inventory file

## Installation (Optional)
If you want to install system-wide:
```bash
pip install --no-index --find-links wheelhouse scatter
```

Then you can use `scatter` command directly.
''')
        
        # Create the tarball
        dist_dir = Path("dist")
        dist_dir.mkdir(exist_ok=True)
        tarball_path = dist_dir / tarball_name
        
        print(f"📦 Creating tarball...")
        with tarfile.open(tarball_path, "w:gz") as tar:
            tar.add(package_dir, arcname=package_dir.name)
        
        # Cleanup temp directory
        shutil.rmtree(temp_dir)
        
        print(f"✅ Portable tarball created: {tarball_path}")
        
        # Show size
        size_mb = tarball_path.stat().st_size / (1024 * 1024)
        print(f"📊 Tarball size: {size_mb:.1f} MB")
        
        return str(tarball_path)
        
    except Exception as e:
        # Cleanup on error
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise e


def test_tarball(tarball_path):
    """Test the portable tarball."""
    print(f"Testing tarball: {tarball_path}")
    
    # Extract to temp directory and test
    test_dir = Path("temp_test_tarball")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    
    try:
        # Extract tarball
        with tarfile.open(tarball_path, "r:gz") as tar:
            tar.extractall(test_dir, filter='data')
        
        # Find the extracted directory
        extracted_dirs = list(test_dir.glob("scatter-*-portable"))
        if not extracted_dirs:
            print("❌ Could not find extracted package directory")
            print("Available directories:", list(test_dir.iterdir()))
            return False
        
        package_dir = extracted_dirs[0]
        print(f"Found package directory: {package_dir}")
        run_script = package_dir / "run_scatter.py"
        
        if not run_script.exists():
            print("❌ run_scatter.py not found in package")
            print("Available files:", list(package_dir.iterdir()) if package_dir.exists() else "Package dir doesn't exist")
            return False
        
        # Test the help command
        result = subprocess.run([
            sys.executable, "run_scatter.py", "--help"
        ], capture_output=True, text=True, timeout=30, cwd=str(package_dir))
        
        if result.returncode == 0 and "Concurrent SSH executor" in result.stdout:
            print("✅ Portable package test passed")
            return True
        else:
            print(f"❌ Portable package test failed (code {result.returncode})")
            if result.stderr:
                print("STDERR:", result.stderr[:500])
            return False
            
    except Exception as e:
        print(f"❌ Error testing tarball: {e}")
        return False
    finally:
        # Cleanup
        if test_dir.exists():
            shutil.rmtree(test_dir)


def main():
    """Main build process."""
    parser = argparse.ArgumentParser(description="Build Scatter distributions")
    parser.add_argument("--type", choices=["binary", "tarball", "both"], 
                       default="both", help="Type of distribution to build")
    args = parser.parse_args()

    if not Path("pyproject.toml").exists():
        print("❌ pyproject.toml not found. Run this script from the project root.")
        sys.exit(1)

    print(f"🚀 Building Scatter distributions (type: {args.type})...")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Python: {sys.version}")
    print()

    try:
        # Always install dependencies and clean
        install_build_deps()
        clean_build()
        
        results = []
        
        # Build binary executable
        if args.type in ["binary", "both"]:
            print("🔨 Building standalone binary executable...")
            exe_path = build_executable()
            
            if test_executable(exe_path):
                size_mb = Path(exe_path).stat().st_size / (1024 * 1024)
                print(f"✅ Binary executable: {exe_path} ({size_mb:.1f} MB)")
                results.append(f"Binary: {exe_path}")
            else:
                print("❌ Binary executable test failed")
                sys.exit(1)
        
        # Build portable tarball  
        if args.type in ["tarball", "both"]:
            print("� Building portable tarball...")
            tarball_path = create_portable_tarball()
            
            if test_tarball(tarball_path):
                size_mb = Path(tarball_path).stat().st_size / (1024 * 1024) 
                print(f"✅ Portable tarball: {tarball_path} ({size_mb:.1f} MB)")
                results.append(f"Tarball: {tarball_path}")
            else:
                print("❌ Portable tarball test failed")
                sys.exit(1)
        
        # Summary
        print()
        print("🎉 Build completed successfully!")
        for result in results:
            print(f"  📁 {result}")
        print()
        
        if args.type in ["binary", "both"]:
            print("📋 Binary Usage:")
            print("  - Users don't need Python installed")
            print("  - Single file download and run")
        
        if args.type in ["tarball", "both"]:
            print("📋 Tarball Usage:")
            print("  - Users need Python 3.10+ installed")  
            print("  - Extract and run: tar -xzf *.tar.gz && cd */ && ./scatter.sh --help")
            print("  - Includes source code and dependencies")

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
