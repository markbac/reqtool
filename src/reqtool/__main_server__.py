"""Entrypoint for reqtool-server standalone executable (auto-launches backend server listening on 0.0.0.0:8765)."""
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from reqtool.cli import cli


def main():
    if len(sys.argv) == 1 or (len(sys.argv) > 1 and sys.argv[1].startswith("-")):
        # A network-facing server always requires login (override with --auth local
        # only together with --host 127.0.0.1).
        if "--auth" not in sys.argv:
            sys.argv[1:1] = ["--auth", "required"]
        if "--host" not in sys.argv:
            sys.argv[1:1] = ["--host", "0.0.0.0"]
        sys.argv.insert(1, "serve")
    cli()


if __name__ == "__main__":
    main()
