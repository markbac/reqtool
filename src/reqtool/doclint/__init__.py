"""Writing checks for requirement text: glossary, wordy phrases, undefined acronyms, vague terms and Vale.

The design follows py-doc's ``lint`` package (rules DOC001 to DOC003), with a settings file kept in the
repository (``.reqtool/lint.yaml``) so an administrator can change every setting.
"""

from .config import LintConfig, ValeSettings, default_settings, parse_settings, settings_problems
from .linter import DocLinter, LintIssue, LintReport

__all__ = ["DocLinter", "LintConfig", "LintIssue", "LintReport", "ValeSettings",
           "default_settings", "parse_settings", "settings_problems"]
