"""DAT-02: save_yaml must be atomic."""
import os

import pytest

from reqtool import fileio
from reqtool.fileio import load_yaml, save_yaml


def test_roundtrip(tmp_path):
    p = tmp_path / "a" / "R-1.yaml"
    save_yaml(p, {"id": "R-1", "title": "T"})
    assert load_yaml(p) == {"id": "R-1", "title": "T"}
    assert [f.name for f in p.parent.iterdir()] == ["R-1.yaml"]


def test_serialisation_error_keeps_original(tmp_path):
    p = tmp_path / "R-1.yaml"
    save_yaml(p, {"id": "R-1"})
    with pytest.raises(Exception):
        save_yaml(p, {"id": object()})
    assert load_yaml(p) == {"id": "R-1"}
    assert [f.name for f in tmp_path.iterdir()] == ["R-1.yaml"]


def test_crash_before_replace_keeps_original(tmp_path, monkeypatch):
    p = tmp_path / "R-1.yaml"
    save_yaml(p, {"id": "R-1"})

    def boom(*a, **k):
        raise OSError("disk gone")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        save_yaml(p, {"id": "R-2"})
    monkeypatch.undo()
    assert load_yaml(p) == {"id": "R-1"}
    assert [f.name for f in tmp_path.iterdir()] == ["R-1.yaml"]


def test_temp_file_is_not_a_yaml_glob_match(tmp_path, monkeypatch):
    seen = []
    real = os.replace

    def spy(src, dst):
        seen.append(os.path.basename(src))
        real(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    save_yaml(tmp_path / "R-1.yaml", {"id": "R-1"})
    assert seen and not seen[0].endswith(".yaml")
