"""
reqtool.commands.migrate
========================
``req migrate``: bring an older repository up to the current layout.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Mapping, Optional

import click

from .common import cli, _repo_root


def migrate_tbds(root: Path) -> dict[str, int]:
    """Move ``tbds/*.yaml`` into ``decisions/``. Safe to run again: moved files are not touched twice."""
    src, dst = root / "tbds", root / "decisions"
    moved = skipped = 0
    if src.is_dir():
        dst.mkdir(parents=True, exist_ok=True)
        for path in sorted(src.glob("*.yaml")):
            target = dst / path.name
            if target.exists():
                if target.read_bytes() == path.read_bytes():
                    path.unlink()  # identical copy already migrated
                else:
                    skipped += 1  # differing file: leave both for a person to reconcile
                continue
            shutil.move(str(path), str(target))
            moved += 1
        try:
            src.rmdir()
        except OSError:
            pass  # not empty (skipped files, other content)
    return {"moved": moved, "skipped": skipped}


def migrate_settings(root: Path) -> list[str]:
    """Give an older repository its own workflow and writing-check files. Existing files are never changed."""
    from ..repo_init import write_hierarchy_file, write_lint_file
    written = []
    reqtool_dir = root / ".reqtool"
    if reqtool_dir.is_dir():
        if not (reqtool_dir / "hierarchy.yaml").exists():
            write_hierarchy_file(root)
            written.append(".reqtool/hierarchy.yaml")
        if not (reqtool_dir / "lint.yaml").exists():
            write_lint_file(root)
            written.append(".reqtool/lint.yaml")
    return written


def migrate_rules(root: Path) -> bool:
    """Add the parent/child rule set to a repository that has none, with every rule off so behaviour is unchanged."""
    from ..fileio import load_yaml, save_yaml
    from ..workflow_rules import default_rules
    path = root / ".reqtool" / "hierarchy.yaml"
    if not path.exists():
        return False
    data = load_yaml(path)
    if not isinstance(data, dict) or "rules" in data:
        return False
    data["rules"] = default_rules("off", "off")
    save_yaml(path, data)
    return True


def migrate_principles(root: Path) -> dict:
    """Give principles an area and category (from the default packs by id, else the old domain). Safe to run again."""
    from ..services.principles import PrincipleService
    from ..store import Store
    if not (root / ".reqtool" / "config.yaml").exists():
        return {"placed": 0, "unplaced": [], "wrote_vocabulary": False}
    store = Store(root)
    store.load()
    return PrincipleService(store).place_existing()


def _next_decision_number(decisions: Mapping[str, dict]) -> int:
    import re
    nums = [int(m.group(1)) for d in decisions.values() for m in [re.fullmatch(r"DEC-(\d+)", d.get("id", ""))] if m]
    return max(nums, default=0) + 1


def migrate_decisions(root: Path) -> dict:
    """Turn every TBD into a decision (#371). A TBD that was resolved into a decision is merged into it; the rest
    become pending (or accepted) decisions with a ``DEC-nnn`` id. The old id stays as an alias, so ``[TBD-002]``
    markers and links still resolve, and requirement links of type ``tbd`` become ``decision``. Safe to run again."""
    from ..artefacts import legacy_decision_status
    from ..store import Store
    result = {"converted": 0, "merged": 0, "links": 0}
    if not (root / ".reqtool").is_dir():
        return result
    store = Store(root)
    store.load()
    decisions = store.decision_map()
    redirect: dict[str, str] = {}
    number = _next_decision_number(decisions)
    for uid, d in sorted(decisions.items(), key=lambda kv: kv[1].get("id", "")):
        if d.get("type") != "tbd" or d.get("deleted"):
            continue
        old_id = d.get("id") or uid
        target_uid = str(d.get("resolution_ref") or "")
        target = decisions.get(target_uid)
        if d.get("status") == "resolved" and target and not target.get("deleted") and target.get("type") != "tbd":
            store.update_decision(target_uid, {
                "aliases": list(dict.fromkeys([*(target.get("aliases") or []), old_id, *(d.get("aliases") or [])])),
                "affected_requirements": sorted(set(target.get("affected_requirements") or [])
                                                | set(d.get("affected_requirements") or [])),
            }, summary=f"Merged {old_id} into this decision.")
            store.update_decision(uid, {"type": "decision", "status": "accepted"},
                                  summary=f"Merged into {target.get('id', target_uid)}.")
            store.delete_decision(uid)
            redirect[uid] = target_uid
            result["merged"] += 1
            continue
        status = legacy_decision_status(d.get("status"))
        store.update_decision(uid, {
            "type": "decision", "status": status, "id": f"DEC-{number:03d}",
            "in_progress": d.get("status") == "in_progress",
            "aliases": list(dict.fromkeys([*(d.get("aliases") or []), old_id])),
        }, summary=f"Converted from open question {old_id}.")
        number += 1
        result["converted"] += 1
    for uid, req in store.requirement_map().items():
        links = req.get("links") or []
        if not any(link.get("type") == "tbd" or link.get("ref") in redirect for link in links):
            continue
        new_links = []
        for link in links:
            link = dict(link)
            if link.get("type") == "tbd":
                link["type"] = "decision"
            link["ref"] = redirect.get(str(link.get("ref")), link.get("ref"))
            new_links.append(link)
        store.update_requirement(uid, {"links": new_links}, summary="Links to open questions now point at decisions.")
        result["links"] += 1
    return result


def _move(root: Path, src: Path, dest: Path, use_git: bool) -> None:
    """Move a file or folder, with ``git mv`` when it is tracked so ``git log --follow`` keeps its history."""
    from ..git_ops import run_git
    dest.parent.mkdir(parents=True, exist_ok=True)
    if use_git:
        rc, _, _ = run_git(["mv", "-k", str(src.relative_to(root)), str(dest.relative_to(root))], root)
        if rc == 0 and not src.exists():
            return
    shutil.move(str(src), str(dest))


def migrate_layout(root: Path) -> dict:
    """Move work items and issues from requirements/ to work/, and modules from modules/<id>/ to
    requirements/modules/<id>/ (#380). File contents are not changed. Safe to run again: anything already in
    place is left alone, and a module already present at the new place is reported, not overwritten."""
    from .. import layout
    from ..fileio import load_yaml
    from ..git_ops import is_git_repo
    from ..stores import hierarchy_store
    result: dict = {"work": 0, "modules": 0, "skipped_modules": []}
    if not (root / ".reqtool").is_dir():
        return result
    use_git = is_git_repo(root)
    hierarchy = hierarchy_store.load_hierarchy(root)
    for path in sorted((root / layout.REQUIREMENTS_DIR).glob("*.yaml")):
        try:
            data = load_yaml(path)
        except Exception:
            continue
        if isinstance(data, dict) and layout.family(data.get("req_type"), hierarchy) == "work":
            _move(root, path, root / layout.WORK_DIR / path.name, use_git)
            result["work"] += 1
    legacy = root / layout.LEGACY_MODULES_DIR
    if legacy.is_dir():
        for folder in sorted(p for p in legacy.iterdir() if p.is_dir()):
            dest = root / layout.MODULES_DIR / folder.name
            if dest.exists():
                result["skipped_modules"].append(folder.name)
                continue
            _move(root, folder, dest, use_git)
            result["modules"] += 1
        try:
            legacy.rmdir()
        except OSError:
            pass  # not empty (a module left in place)
    attrs = root / ".gitattributes"
    if attrs.exists():
        from ..merge import ATTRIBUTES
        lines = attrs.read_text(encoding="utf-8").splitlines()
        if "requirements/*.yaml merge=reqtool" in lines:
            missing = [a for a in ATTRIBUTES if a not in lines]
            if missing:
                attrs.write_text("\n".join(lines + missing) + "\n", encoding="utf-8")
    return result


@cli.command()
@click.option("--repo", default=None, help="Path to the requirements repository root.")
def migrate(repo: Optional[str]):
    """Migrate legacy layouts: TBDs move into decisions/ and become decisions, work items move to work/ and
    modules to requirements/modules/, the repository gets its own workflow and lint files, and principles get an
    area and category."""
    root = Path(repo).resolve() if repo else _repo_root()
    result = migrate_tbds(root)
    click.echo(f"TBDs moved to decisions/: {result['moved']}")
    if result["skipped"]:
        click.echo(f"{result['skipped']} file(s) differ from the copy in decisions/ and were left in tbds/ -- reconcile them by hand.")
    converted = migrate_decisions(root)
    click.echo(f"Open questions converted to decisions: {converted['converted']}, merged into the decision they "
               f"became: {converted['merged']}, requirements relinked: {converted['links']}")
    moved = migrate_layout(root)
    click.echo(f"Work items moved to work/: {moved['work']}, modules moved to requirements/modules/: {moved['modules']}")
    if moved["skipped_modules"]:
        click.echo("Already in requirements/modules/, left in modules/ to reconcile by hand: "
                   + ", ".join(moved["skipped_modules"]))
    for name in migrate_settings(root):
        click.echo(f"Wrote {name} (the repository now owns these settings).")
    if migrate_rules(root):
        click.echo("Added the parent and child rules to .reqtool/hierarchy.yaml (all off; turn them on in the workflow editor).")
    placed = migrate_principles(root)
    click.echo(f"Principles placed in an area and category: {placed['placed']}")
    if placed["wrote_vocabulary"]:
        click.echo("Wrote principle_areas to .reqtool/enums.yaml (the repository now owns its principle areas).")
    if placed["unplaced"]:
        click.echo("No area could be worked out for: " + ", ".join(sorted(placed["unplaced"])) + " -- set it in the editor.")
