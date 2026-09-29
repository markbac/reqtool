"""reqtool main entrypoint for python -m reqtool or PyInstaller standalone executable builds."""
from reqtool.cli import cli

if __name__ == "__main__":
    cli()
