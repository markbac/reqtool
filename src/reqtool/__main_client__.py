"""Entrypoint for reqtool-client standalone executable (auto-launches desktop client application interface)."""
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
        sys.argv.insert(1, "--app")
        sys.argv.insert(1, "serve")
    cli()


if __name__ == "__main__":
    main()
