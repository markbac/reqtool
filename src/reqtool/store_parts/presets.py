"""Saved filter presets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from reqtool.store_parts._host import StoreHost

from reqtool.fileio import load_yaml, save_yaml


class PresetsMixin(StoreHost):
    def _presets_path(self) -> Path:
        return self.root / ".reqtool" / "filter_presets.yaml"

    def list_filter_presets(self) -> list[dict[str, Any]]:
        path = self._presets_path()
        if not path.exists():
            return []
        data = load_yaml(path)
        return data if isinstance(data, list) else []

    def save_filter_preset(self, preset: dict[str, Any]) -> dict[str, Any]:
        path = self._presets_path()
        presets = self.list_filter_presets()
        presets = [p for p in presets if p.get("id") != preset.get("id")]
        presets.append(preset)
        save_yaml(path, presets)
        return preset

    def delete_filter_preset(self, preset_id: str) -> bool:
        path = self._presets_path()
        presets = self.list_filter_presets()
        new = [p for p in presets if p.get("id") != preset_id]
        if len(new) == len(presets):
            return False
        save_yaml(path, new)
        return True
