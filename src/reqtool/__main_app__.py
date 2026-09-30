"""Entrypoint for reqtool-app standalone executable (auto-launches desktop app interface)."""
import sys
from reqtool.cli import cli


def main():
    if len(sys.argv) == 1:
        sys.argv.extend(["serve", "--app"])
    cli()


if __name__ == "__main__":
    main()
