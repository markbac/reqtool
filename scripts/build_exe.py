"""
scripts/build_exe.py
====================
Standalone executable build helper script for reqtool.
Builds frontend UI assets, packages documentation bundle, and compiles single-file executable using PyInstaller.
"""

import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

def build_ui():
    print("=== Building UI static assets ===")
    ui_dir = ROOT / "src" / "reqtool" / "ui"
    subprocess.run(["npm", "install"], cwd=ui_dir, check=True, shell=True)
    subprocess.run(["npm", "run", "build"], cwd=ui_dir, check=True, shell=True)
    print("UI build complete: src/reqtool/ui/dist\n")

def build_docs_bundle():
    print("=== Packaging Documentation & User Guide Bundle ===")
    dist_dir = ROOT / "dist"
    dist_dir.mkdir(exist_ok=True)
    zip_path = dist_dir / "reqtool-documentation-and-user-guide.zip"
    
    docs_dir = ROOT / "docs"
    files_to_pack = [
        ROOT / "README.md",
        ROOT / "ARCHITECTURE.md",
        ROOT / "LICENSE",
    ]
    if docs_dir.exists():
        files_to_pack.extend(list(docs_dir.glob("*.md")))

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files_to_pack:
            if f.exists():
                arcname = f.name if f.parent == ROOT else f"docs/{f.name}"
                zf.write(f, arcname)
    print(f"Documentation bundle created: {zip_path}\n")

def build_exe():
    print("=== Compiling PyInstaller standalone executable ===")
    subprocess.run([sys.executable, "-m", "PyInstaller", "reqtool.spec", "--clean"], cwd=ROOT, check=True)
    exe_path = ROOT / "dist" / ("reqtool.exe" if sys.platform == "win32" else "reqtool")
    print(f"\nSuccess! Standalone executable created at: {exe_path}")

if __name__ == "__main__":
    build_ui()
    build_docs_bundle()
    build_exe()
