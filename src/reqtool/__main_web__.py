"""Entrypoint for reqtool-web standalone executable (auto-launches web browser interface)."""
import sys
from reqtool.cli import cli


def main():
    if len(sys.argv) == 1:
        sys.argv.extend(["serve", "--browser"])
    cli()


if __name__ == "__main__":
    main()
