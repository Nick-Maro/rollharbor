"""Export an explicit public allowlist into a new directory, without Git history."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    "README.md", "README.it.md", "LICENSE", ".gitattributes", ".editorconfig",
    "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "server.py", "engine.py",
    "character_builder.py", "runtime_info.py", "AVVIA.cmd", "AVVIA.ps1",
    "ARRESTA.cmd", "ARRESTA.ps1",
)
PATTERNS = (
    "tools/*.py", "tools/*.ps1", "tools/PLAYBOOK.md", "tools/DUNGEON_MAPS.md",
    "web/*.html", "web/*.js", "web/*.css", "web/assets/sigil.svg", "web/assets/demo-coast.svg",
    "web/assets/immersion/extra/*.png", "web/assets/immersion/extra/*.webp",
    "web/assets/immersion/extra/README.md",
    "web/assets/maps/rocca-cisterne.svg", "web/assets/maps/rocca-cisterne.png",
    "web/assets/maps/rocca-cisterne.map.json", "web/assets/maps/rocca-cisterne-blue.svg",
    "web/assets/maps/rocca-cisterne-blue.png", "web/assets/maps/rocca-cisterne-blue.map.json",
    "examples/demo/*.json", "examples/demo/*.md", "tests/test_*.py",
    "tests/browser_public_smoke.py", "tests/launcher_smoke.py",
    "docs/GETTING_STARTED.md", "docs/DM_GUIDE.md", "docs/PUBLISHING.md",
    "docs/RELEASE_CHECKLIST.md", "docs/screenshots/*.png", ".github/**/*.yml",
    ".github/**/*.md", "publication/AGENTS.md", "publication/ATTRIBUZIONI.md",
    "publication/.gitignore", "publication/map-library.json", "publication/npc_profiles.py",
    "publication/PLAYBOOK.md",
)


def public_files(root: Path) -> dict[str, Path]:
    selected = {name: root / name for name in ROOT_FILES}
    for pattern in PATTERNS:
        for path in root.glob(pattern):
            if path.is_file():
                selected[path.relative_to(root).as_posix()] = path
    for name in ("AGENTS.md", "ATTRIBUZIONI.md", ".gitignore"):
        selected[name] = root / "publication" / name
    selected["tools/PLAYBOOK.md"] = root / "publication/PLAYBOOK.md"
    selected["tools/npc_profiles.py"] = root / "publication/npc_profiles.py"
    selected["web/assets/maps/library.json"] = root / "publication/map-library.json"
    for relative, source in selected.items():
        if not source.is_file():
            raise ValueError(f"Missing required public file: {relative}")
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError(f"Source escapes the project: {relative}")
    return selected


def export(root: Path, destination: Path) -> dict:
    root, destination = root.resolve(), destination.resolve()
    if destination == root or destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("Choose a new sibling directory, outside the source tree and its parents.")
    if destination.exists():
        raise ValueError("Destination already exists. Choose a new path; existing checkouts are never overwritten.")
    selected = public_files(root)
    # Do every preflight check before creating the destination.
    destination.mkdir(parents=True)
    manifest = {}
    for relative, source in sorted(selected.items()):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        manifest[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / "PUBLIC_EXPORT.json").write_text(
        json.dumps({"format": 1, "files": manifest}, indent=2) + "\n", encoding="utf-8")
    return {"destination": str(destination), "files": len(selected), "git_history_copied": False,
            "runtime_copied": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(export(args.root, args.destination), ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
