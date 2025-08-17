#!/usr/bin/env python3
"""
Entry point for PyInstaller standalone executable.
This avoids relative import issues by importing the full module path.
"""

if __name__ == "__main__":
    from scatter.cli import app
    app()
