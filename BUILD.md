# Building Standalone Linux Executables

This document explains how to build standalone executables for Scatter that run on Linux Ubuntu systems without requiring Python to be installed.

## Overview

The standalone build process uses [PyInstaller](https://pyinstaller.org/) to bundle Python, all dependencies, and the Scatter application into a single executable file optimized for Linux Ubuntu systems.

## Build Process

### Prerequisites

- Linux development environment (or Ubuntu VM/container)
- Python 3.10+ installed
- Project dependencies installed (`pip install -e .`)

### Local Build

To build a standalone executable for Linux:

```bash
python build_standalone.py
```

This will:
1. Install PyInstaller and other build dependencies
2. Clean previous build artifacts  
3. Create a Linux-optimized standalone executable in `dist/`
4. Test the executable to ensure it works
5. Show the final executable size

### Build Output

The executable will be named: `scatter-X.X.X-linux-x86_64`

Where `X.X.X` is the version from `pyproject.toml`.

## Automated Builds

The GitHub Actions workflow `.github/workflows/standalone-release.yml` automatically builds Linux executables when a new tag is pushed:

```bash
git tag v1.0.0
git push origin v1.0.0
```

This creates a GitHub release with:
- Standalone Linux executable
- Wheel bundles for offline Python installation on Linux
- Installation instructions

## Distribution

Users can download the standalone executable from the GitHub Releases page and run it directly on Ubuntu/Linux systems:

```bash
# Download and run
chmod +x scatter-*-linux-x86_64
./scatter-*-linux-x86_64 --help

# Or install system-wide
sudo mv scatter-*-linux-x86_64 /usr/local/bin/scatter
scatter --help
```

## Technical Details

### PyInstaller Configuration

The build process uses these Linux-optimized PyInstaller options:
- `--onefile`: Create a single executable file
- `--console`: Console application (not GUI)
- `--optimize 2`: Python bytecode optimization
- `--strip`: Remove debug symbols for smaller size
- `--hidden-import uvloop`: Include uvloop for better asyncio performance
- Various `--hidden-import` directives for dependencies

### File Size

Typical executable size: ~15-20 MB for Linux

The executable includes:
- Python interpreter
- All Python dependencies (asyncssh, rich, typer, uvloop, etc.)
- Linux-specific libraries
- The Scatter application code

### Platform Support

- **Linux**: x86_64 (Ubuntu and compatible distributions)

## Troubleshooting

### Build Failures

If the build fails:

1. Check Python version: `python --version` (need 3.10+)
2. Install project: `pip install -e .`
3. Test imports: `python test_build.py`
4. Check PyInstaller: `pip install pyinstaller`

### Runtime Issues

If the executable doesn't work:

1. Test locally: `python -m scatter --help`
2. Check dependencies are bundled: Look at PyInstaller warnings
3. Try running with verbose output: `./scatter-* -vv --help`

### Size Optimization

To reduce executable size:
- The build excludes unused packages like `tkinter`, `numpy`, `matplotlib`
- Uses UPX compression if available
- Strips debug symbols on Unix platforms

## Development

To modify the build process:
- Edit `build_standalone.py` for build logic
- Edit `.github/workflows/standalone-release.yml` for CI/CD
- See PyInstaller documentation for advanced options
