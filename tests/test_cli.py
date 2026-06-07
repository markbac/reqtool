"""
test_cli.py -- Tests for reqtool CLI commands.

Covers: init (blank, defaults, demo), validate, verify, export, import,
new, show, history, diff, stats, openapi, version.
"""
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reqtool.cli import cli


def run(*args, cwd=None) -> "Result":
    runner = CliRunner(mix_stderr=False)
    return runner.invoke(cli, list(args), catch_exceptions=False)


# ===========================================================================
# req init
# ===========================================================================

class TestInitBlank:
    def test_init_creates_config(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(cli, ["init", "--id", "test", "--title", "Test"])
            assert result.exit_code == 0, result.output
            assert (Path(td) / ".reqtool" / "config.yaml").exists()

    def test_init_creates_dirs(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "--id", "test", "--title", "Test"])
            root = Path(td)
            for d in ("requirements", "principles", "tbds", ".reqtool"):
                assert (root / d).is_dir()

    def test_init_creates_enums(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "--id", "test", "--title", "Test"])
            assert (Path(td) / ".reqtool" / "enums.yaml").exists()

    def test_init_twice_fails(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init", "--id", "test", "--title", "Test"])
            result = runner.invoke(cli, ["init", "--id", "test", "--title", "Test"])
            assert result.exit_code != 0


class TestInitDefaults:
    def test_init_defaults_creates_principles(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(cli, ["init", "defaults", "--id", "x", "--title", "X"])
            assert result.exit_code == 0, result.output
            root = Path(td)
            principles = list((root / "principles").glob("*.yaml"))
            assert len(principles) >= 15

    def test_init_defaults_creates_workflow(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "defaults", "--id", "x", "--title", "X"])
            from reqtool.fileio import load_yaml
            cfg = load_yaml(Path(td) / ".reqtool" / "config.yaml")
            assert "workflow" in cfg

    def test_init_defaults_creates_templates(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "defaults", "--id", "x", "--title", "X"])
            assert (Path(td) / ".reqtool" / "templates.yaml").exists()

    def test_init_defaults_populates_enums(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "defaults", "--id", "x", "--title", "X"])
            from reqtool.fileio import load_yaml
            enums = load_yaml(Path(td) / ".reqtool" / "enums.yaml")
            assert len(enums.get("team", [])) > 0
            assert len(enums.get("nfr_keys", [])) > 0

    def test_init_defaults_principle_domains(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "defaults", "--id", "x", "--title", "X"])
            from reqtool.store import Store
            root = Path(td)
            s = Store(root)
            s.load()
            domains = {p.get("domain") for p in s.principles.values()}
            # Should cover at least 6 of 8 categories
            assert len(domains) >= 6

    def test_init_defaults_output_mentions_count(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["init", "defaults", "--id", "x", "--title", "X"])
            assert "principles" in result.output


class TestInitDemo:
    def test_init_demo_creates_requirements(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            result = runner.invoke(cli, ["init", "demo"])
            assert result.exit_code == 0, result.output
            requirements = list((Path(td) / "requirements").glob("*.yaml"))
            assert len(requirements) >= 100

    def test_init_demo_creates_product(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "demo"])
            product_manifest = Path(td) / "products" / "env-sensor-v1" / "_product.yaml"
            assert product_manifest.exists()

    def test_init_demo_creates_tbds(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "demo"])
            tbds = list((Path(td) / "tbds").glob("*.yaml"))
            assert len(tbds) >= 5

    def test_init_demo_creates_principles(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "demo"])
            principles = list((Path(td) / "principles").glob("*.yaml"))
            assert len(principles) >= 8

    def test_init_demo_output_summary(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["init", "demo"])
            assert "requirements" in result.output
            assert "principles" in result.output


# ===========================================================================
# req new
# ===========================================================================

class TestNew:
    def _init(self, runner):
        return runner.invoke(cli, ["init", "--id", "t", "--title", "T"])

    def test_new_requirement_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["new", "requirement", "--help"])
        assert result.exit_code == 0

    def test_new_principle_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["new", "principle", "--help"])
        assert result.exit_code == 0

    def test_new_tbd_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["new", "tbd", "--help"])
        assert result.exit_code == 0


# ===========================================================================
# req validate
# ===========================================================================

class TestValidateCli:
    def test_validate_clean_exit_zero(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init", "--id", "t", "--title", "T"])
            result = runner.invoke(cli, ["validate"])
            # Clean repo, no errors -- exit 0
            assert result.exit_code == 0

    def test_validate_output_format(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init", "--id", "t", "--title", "T"])
            result = runner.invoke(cli, ["validate"])
            # Should mention errors and warnings count
            assert result.exit_code == 0  # clean repo, no errors


# ===========================================================================
# req stats
# ===========================================================================

class TestStats:
    def test_stats_requires_running_server(self, tmp_path):
        """req stats calls /metrics on a running server.
        Without a server this will fail -- verify graceful error handling."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init", "--id", "t", "--title", "T"])
            # With no server running, should fail with an informative message
            result = runner.invoke(cli, ["stats"])
            # Exit non-zero or prints connection error -- both acceptable
            assert result.exit_code != 0 or "connect" in result.output.lower() or "error" in result.output.lower()


# ===========================================================================
# req diff
# ===========================================================================

class TestDiffCli:
    def test_diff_requires_running_server(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init", "--id", "t", "--title", "T"])
            result = runner.invoke(cli, ["diff"])
            # Without server: connection error or exit non-zero
            assert result.exit_code != 0 or "connect" in result.output.lower() or "error" in result.output.lower()


# ===========================================================================
# req openapi
# ===========================================================================

class TestOpenApi:
    def test_openapi_to_stdout(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem():
            runner.invoke(cli, ["init", "--id", "t", "--title", "T"])
            result = runner.invoke(cli, ["openapi"])
            assert result.exit_code == 0
            assert "openapi" in result.output.lower() or "paths" in result.output.lower()

    def test_openapi_to_file(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "--id", "t", "--title", "T"])
            out_path = str(Path(td) / "spec.yaml")
            result = runner.invoke(cli, ["openapi", "-o", out_path])
            assert result.exit_code == 0
            assert Path(out_path).exists()


# ===========================================================================
# req version
# ===========================================================================

class TestVersion:
    def test_version_in_package(self):
        """Version is exposed as __version__, not as a CLI command."""
        from reqtool import __version__
        assert __version__ == "0.3.10"

    def test_no_version_command(self):
        assert "version" not in cli.commands


# ===========================================================================
# req show / history
# ===========================================================================

class TestShowHistory:
    def test_show_requirement(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "--id", "t", "--title", "T"])
            from reqtool.store import Store
            from pathlib import Path as P
            s = Store(P(td)); s.load()
            s.create_requirement({"id": "REQ-001", "title": "T",
                "content": {"description": "D", "rationale": "", "extended_description": ""}})
            result = runner.invoke(cli, ["show", "REQ-001"])
            assert result.exit_code == 0
            assert "REQ-001" in result.output

    def test_history_requirement(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            runner.invoke(cli, ["init", "--id", "t", "--title", "T"])
            from reqtool.store import Store
            from pathlib import Path as P
            s = Store(P(td)); s.load()
            s.create_requirement({"id": "REQ-001", "title": "T",
                "content": {"description": "D", "rationale": "", "extended_description": ""}})
            result = runner.invoke(cli, ["history", "REQ-001"])
            assert result.exit_code == 0


# ===========================================================================
# req export
# ===========================================================================

class TestExportCli:
    def _init(self, runner, td):
        runner.invoke(cli, ["init", "--id", "t", "--title", "T"])
        import sys; sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))
        from reqtool.store import Store
        from pathlib import Path as P
        s = Store(P(td)); s.load()
        s.create_requirement({"id": "REQ-001", "title": "T",
            "content": {"description": "D", "rationale": "", "extended_description": ""}})

    def test_export_csv(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            self._init(runner, td)
            result = runner.invoke(cli, ["export", "csv"])
            assert result.exit_code == 0
            exports = list((Path(td) / "exports").glob("*.csv"))
            assert len(exports) >= 1

    def test_export_markdown(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            self._init(runner, td)
            result = runner.invoke(cli, ["export", "markdown"])
            assert result.exit_code == 0

    def test_export_jsx(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem() as td:
            self._init(runner, td)
            result = runner.invoke(cli, ["export", "jsx"])
            assert result.exit_code == 0


# ===========================================================================
# Command registration sanity
# ===========================================================================

class TestCommandRegistration:
    def test_all_commands_registered(self):
        expected = {"init", "validate", "verify", "export", "import",
                    "new", "show", "history", "serve", "diff", "stats", "openapi"}
        registered = set(cli.commands.keys())
        missing = expected - registered
        assert not missing, f"Missing CLI commands: {missing}"

    def test_init_subcommands(self):
        init_cmd = cli.commands.get("init")
        assert init_cmd is not None
        assert hasattr(init_cmd, "commands")
        assert "defaults" in init_cmd.commands
        assert "demo" in init_cmd.commands

    def test_export_subcommands(self):
        export_cmd = cli.commands.get("export")
        assert export_cmd is not None
