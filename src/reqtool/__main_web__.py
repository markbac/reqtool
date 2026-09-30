"""Entrypoint for reqtool-web standalone executable (auto-launches web browser interface)."""
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from reqtool.cli import cli


def main():
    if len(sys.argv) == 1:
        sys.argv.extend(["serve", "--browser"])
    cli()


if __name__ == "__main__":
    main()
