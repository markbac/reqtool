"""
scripts/test_binary.py
=======================
Empirical runtime test script for compiled standalone executables.
Launches dist executables in background processes, verifies HTTP 200 responses on /health, /, and /api/auth/login.
"""

import sys
import time
import json
import urllib.error
import urllib.request
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()

def test_executable(exe_name: str, port: int):
    exe_path = ROOT / "dist" / (f"{exe_name}.exe" if sys.platform == "win32" else exe_name)
    if not exe_path.exists():
        print(f"Error: Executable not found at {exe_path}")
        sys.exit(1)

    print(f"\n--- Testing Executable: {exe_name} (port {port}) ---")
    cmd = [str(exe_path)]
    if exe_name == "reqtool":
        cmd.extend(["serve", "--port", str(port)])
    else:
        cmd.extend(["--port", str(port)])

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        time.sleep(3)

        if proc.poll() is not None:
            stdout, _ = proc.communicate()
            print(f"FAILED: Process exited prematurely with code {proc.returncode}")
            print("Output:\n" + stdout)
            sys.exit(1)

        # Test /health
        url_health = f"http://127.0.0.1:{port}/health"
        req = urllib.request.Request(url_health)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read().decode("utf-8")
            print(f"GET {url_health} -> {resp.status} OK")
            assert resp.status == 200
            assert "version" in data

        # Test root /
        url_root = f"http://127.0.0.1:{port}/"
        with urllib.request.urlopen(url_root, timeout=5) as resp:
            print(f"GET {url_root} -> {resp.status} OK")
            assert resp.status == 200

        # Test /auth/login is alive and no default account exists
        login_data = json.dumps({"username": "admin", "password": "admin123"}).encode("utf-8")
        login_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/auth/login",
            data=login_data,
            headers={"Content-Type": "application/json"}
        )
        try:
            urllib.request.urlopen(login_req, timeout=5)
            raise AssertionError("default admin credentials were accepted")
        except urllib.error.HTTPError as exc:
            print(f"POST /auth/login (default creds) -> {exc.code} (expected 401)")
            assert exc.code == 401

        print(f"SUCCESS: Executable {exe_name} is fully functional!")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

if __name__ == "__main__":
    test_executable("reqtool-web", 18881)
    test_executable("reqtool-app", 18882)
    test_executable("reqtool-server", 18883)
    test_executable("reqtool-client", 18884)
    test_executable("reqtool", 18885)
    print("\nALL STANDALONE EXECUTABLES EMPIRICALLY VERIFIED CLEAN!")
