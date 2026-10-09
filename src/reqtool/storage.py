"""Where artefacts are read from and written to (ARC-04).

The store holds the rules (identifiers, versions, hierarchy, workflow). It reaches the file system only through a
``Storage``: ``FileStorage`` for a real repository, ``MemoryStorage`` so the same rules can be tested with no
files at all.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Protocol

from .fileio import load_yaml, save_yaml


class Storage(Protocol):
    def exists(self, path: Path) -> bool: ...
    def read(self, path: Path) -> Any: ...
    def write(self, path: Path, data: Any) -> None: ...
    def read_bytes(self, path: Path) -> bytes: ...
    def list_yaml(self, directory: Path) -> list[Path]: ...
    def list_dirs(self, directory: Path) -> list[Path]: ...


class FileStorage:
    """The repository on disk: one YAML file per artefact, written atomically by ``save_yaml``."""

    def exists(self, path: Path) -> bool:
        return path.exists()

    def read(self, path: Path) -> Any:
        return load_yaml(path)

    def write(self, path: Path, data: Any) -> None:
        save_yaml(path, data)

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def list_yaml(self, directory: Path) -> list[Path]:
        """The ``*.yaml`` files directly in ``directory``, sorted (none when it does not exist)."""
        return sorted(directory.glob("*.yaml")) if directory.is_dir() else []

    def list_dirs(self, directory: Path) -> list[Path]:
        return sorted(p for p in directory.iterdir() if p.is_dir()) if directory.is_dir() else []


class MemoryStorage:
    """A repository held in a dict, for tests: ``{path: data}``. Directories exist because files are under them."""

    def __init__(self, files: dict[Path, Any] | None = None) -> None:
        self.files: dict[Path, Any] = {Path(p): copy.deepcopy(d) for p, d in (files or {}).items()}

    def _under(self, directory: Path) -> bool:
        return any(directory in p.parents for p in self.files)

    def exists(self, path: Path) -> bool:
        return path in self.files or self._under(path)

    def read(self, path: Path) -> Any:
        if path not in self.files:
            raise FileNotFoundError(path)
        return copy.deepcopy(self.files[path])

    def write(self, path: Path, data: Any) -> None:
        self.files[path] = copy.deepcopy(data)

    def read_bytes(self, path: Path) -> bytes:
        return json.dumps(self.read(path), sort_keys=True, default=str).encode("utf-8")

    def list_yaml(self, directory: Path) -> list[Path]:
        return sorted(p for p in self.files if p.parent == directory and p.suffix == ".yaml")

    def list_dirs(self, directory: Path) -> list[Path]:
        children = {next(a for a in (p, *p.parents) if a.parent == directory)
                    for p in self.files if directory in p.parents}
        return sorted(c for c in children if c not in self.files)
