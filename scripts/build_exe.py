"""
scripts/build_exe.py
====================
Standalone executable build helper script for reqtool.
Builds frontend UI assets and compiles single-file executable using PyInstaller.
"""

import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

def build_ui():
    print("=== Building UI static assets ===")
    ui_dir = ROOT / "src" / "reqtool" / "ui"
    subprocess.run(["npm", "install"], cwd=ui_dir, check=True, shell=True)
    subprocess.run(["npm", "run", "build"], cwd=ui_dir, check=True, shell=True)
    print("UI build complete: src/reqtool/ui/dist\n")

def build_exe():
    print("=== Compiling PyInstaller standalone executable ===")
    subprocess.run([sys.executable, "-m", "PyInstaller", "reqtool.spec", "--clean"], cwd=ROOT, check=True)
    exe_path = ROOT / "dist" / ("reqtool.exe" if sys.platform == "win32" else "reqtool")
    print(f"\nSuccess! Standalone executable created at: {exe_path}")

if __name__ == "__main__":
    build_ui()
    build_exe()
