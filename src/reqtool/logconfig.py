"""
reqtool.logconfig
=================
Logging set-up for the entry points (the ``req`` CLI, ``req serve`` and the uvicorn app factory).

Library modules keep ``logging.getLogger(__name__)``; this configures the top-level ``reqtool``
logger once with ctxlogkit so every child logger inherits its handlers. Log lines go to stderr,
never stdout, so command output stays clean for pipes and scripts. ``LOG_LEVEL`` overrides the
level an entry point asks for.
"""

from __future__ import annotations

import logging
import os
import sys

from ctxlogkit import setup_logging


class _CurrentStderr:
    """A stream that writes to whatever ``sys.stderr`` is when a record is emitted.

    Click's test runner and the frozen executables swap ``sys.stderr`` after start-up; a handler bound
    to the original object would keep writing to a stale stream.
    """

    def write(self, text: str) -> int:
        return sys.stderr.write(text)

    def flush(self) -> None:
        sys.stderr.flush()

    def isatty(self) -> bool:
        isatty = getattr(sys.stderr, "isatty", None)
        return bool(isatty and isatty())


def configure_logging(level: str = "WARNING") -> logging.Logger:
    """Configure the ``reqtool`` logger; safe to call again (handlers are replaced, not added)."""
    return setup_logging(
        name="reqtool",
        level=os.environ.get("LOG_LEVEL") or level,
        console_stream=_CurrentStderr(),  # type: ignore[arg-type]
        use_emoji=False,  # Windows consoles and pipes without UTF-8 print them as escapes
    )
