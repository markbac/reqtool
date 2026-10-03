"""Post-build smoke test for a wheel install or a standalone binary.

Usage: python scripts/smoke_release.py <command> [args...]
  e.g. python scripts/smoke_release.py reqtool
       python scripts/smoke_release.py dist/reqtool

Creates a throw-away repository, starts the server, then checks /health, the UI entry page, a
requirement round trip, the PDF export and the ReqIF export. Exits non-zero on the first failure.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def call(url: str, data: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, method="POST" if data is not None else "GET",
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.status, resp.read()


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("ok   " if ok else "FAIL ") + name + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        raise SystemExit(1)


def main(cmd: list[str]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run([*cmd, "init", "defaults", "--repo", str(repo), "--id", "smoke", "--title", "Smoke Test"],
                       check=True, capture_output=True, timeout=120)
        port = free_port()
        server = subprocess.Popen([*cmd, "serve", "--repo", str(repo), "--port", str(port)],
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(60):
                try:
                    if call(f"{base}/health")[0] == 200:
                        break
                except OSError:
                    time.sleep(1)
            else:
                check("server starts", False, "no /health answer after 60 s")
            check("server starts", True)

            status, body = call(f"{base}/")
            check("UI is served", status == 200 and b"<html" in body.lower(), f"status {status}")

            status, body = call(f"{base}/requirements", {"title": "Smoke requirement"})
            check("create requirement", status in (200, 201), f"status {status}")

            status, body = call(f"{base}/export/pdf")
            check("PDF export", status == 200 and body.startswith(b"%PDF"), f"status {status}, {body[:40]!r}")

            status, body = call(f"{base}/export/reqif")
            check("ReqIF export", status == 200 and b"REQ-IF" in body, f"status {status}")
        finally:
            server.terminate()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.kill()
    print("smoke test passed")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
