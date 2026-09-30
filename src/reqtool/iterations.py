"""
reqtool.iterations
==================
Iteration, Sprint, Phase, and Milestone Management Engine.
Flexible methodology support: Scrum, Waterfall, Wagile (hybrid), and Kanban.
Stores iteration schedules and milestone readiness in .reqtool/iterations.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional
from reqtool.fileio import load_yaml, save_yaml
from reqtool.models import Iteration


class IterationStore:
    def __init__(self, root: Path):
        self.root = root
        self.iterations_file = root / ".reqtool" / "iterations.yaml"

    def load_iterations(self) -> list[dict[str, Any]]:
        if not self.iterations_file.exists():
            self._seed_default_iterations()
        data = load_yaml(self.iterations_file)
        if isinstance(data, list):
            return data
        return []

    def save_iterations(self, iterations: list[dict[str, Any]]) -> None:
        self.iterations_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(self.iterations_file, iterations)

    def _seed_default_iterations(self) -> None:
        defaults = [
            {
                "id": "sprint-01",
                "title": "Sprint 01 - Foundation & Core Architecture",
                "methodology": "scrum",
                "start_date": "2026-10-01",
                "end_date": "2026-10-14",
                "capacity_story_points": 40.0,
                "status": "active",
                "notes": "Scrum iteration focusing on core requirements & backend APIs",
            },
            {
                "id": "phase-gate-1",
                "title": "Phase Gate 1: System Requirements Review (SRR)",
                "methodology": "waterfall",
                "milestone_date": "2026-11-01",
                "status": "planned",
                "gate_review_passed": False,
                "notes": "Waterfall milestone gate requiring 100% approved baseline",
            },
            {
                "id": "wagile-sprint-02",
                "title": "Wagile Cycle 02 - Hybrid Sprint + CDR Gate",
                "methodology": "wagile",
                "start_date": "2026-11-15",
                "end_date": "2026-11-30",
                "milestone_date": "2026-11-30",
                "capacity_story_points": 50.0,
                "status": "planned",
                "notes": "Hybrid Wagile cycle combining sprint velocity with formal gate sign-off",
            },
        ]
        self.save_iterations(defaults)

    def get_iteration(self, iteration_id: str) -> Optional[dict[str, Any]]:
        for it in self.load_iterations():
            if it.get("id") == iteration_id:
                return it
        return None

    def upsert_iteration(self, iteration_data: dict[str, Any]) -> dict[str, Any]:
        it_id = iteration_data.get("id")
        if not it_id:
            raise ValueError("Iteration 'id' parameter required")
        iterations = self.load_iterations()
        idx = next((i for i, it in enumerate(iterations) if it.get("id") == it_id), None)
        if idx is not None:
            iterations[idx] = {**iterations[idx], **iteration_data}
        else:
            iterations.append(iteration_data)
        self.save_iterations(iterations)
        return iteration_data

    def delete_iteration(self, iteration_id: str) -> bool:
        iterations = self.load_iterations()
        filtered = [it for it in iterations if it.get("id") != iteration_id]
        if len(filtered) < len(iterations):
            self.save_iterations(filtered)
            return True
        return False
