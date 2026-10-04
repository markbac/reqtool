"""
scripts/build_exe.py
====================
Standalone executable build helper script for reqtool.
Builds frontend UI assets, packages documentation bundle, and compiles standalone executables using PyInstaller.
Creates:
  - dist/reqtool-web.exe     (Auto-launches browser web interface)
  - dist/reqtool-app.exe     (Auto-launches desktop app interface)
  - dist/reqtool-server.exe  (Auto-launches multi-user backend server on 0.0.0.0:8765)
  - dist/reqtool-client.exe  (Auto-launches desktop client interface)
  - dist/reqtool.exe         (CLI entrypoint)
  - dist/reqtool-documentation-and-user-guide.zip
"""

import sys
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

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files_to_pack:
            if f.exists():
                arcname = f.name if f.parent == ROOT else f"docs/{f.name}"
                zf.write(f, arcname)
    print(f"Documentation bundle created: {zip_path}\n")


def build_exe():
    print("=== Compiling PyInstaller standalone executables ===")
    subprocess.run([sys.executable, "-m", "PyInstaller", "reqtool.spec", "--clean"], cwd=ROOT, check=True)
    ext = ".exe" if sys.platform == "win32" else ""
    web_exe = ROOT / "dist" / f"reqtool-web{ext}"
    app_exe = ROOT / "dist" / f"reqtool-app{ext}"
    server_exe = ROOT / "dist" / f"reqtool-server{ext}"
    client_exe = ROOT / "dist" / f"reqtool-client{ext}"
    cli_exe = ROOT / "dist" / f"reqtool{ext}"

    print(f"\nSuccess! Standalone executables created:")
    print(f"  - Web Interface:        {web_exe}")
    print(f"  - Desktop App:          {app_exe}")
    print(f"  - Multi-User Server:    {server_exe}")
    print(f"  - Remote Client App:    {client_exe}")
    print(f"  - CLI Tool:             {cli_exe}")


if __name__ == "__main__":
    build_ui()
    build_docs_bundle()
    build_exe()
