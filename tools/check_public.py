"""Reject private runtime paths and credential files in the Git index.

This publication boundary check supplements a dedicated secret scanner; it does
not assert that arbitrary source text is free of credentials.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOTS = {"data", "master", "sessions", "saves", "campaigns", "logs", "qa", ".venv", "venv", "node_modules"}
PRIVATE_FILES = {"handoff.md", "rules.md", "docs/tavolo_locale.md"}
IGNORED_EXAMPLES = ("data/campaign.json", "master/MEMORIA.md", "saves/snapshot.json",
                    "sessions/sessione-001.md", "campaigns/private/source.pdf", ".env",
                    ".env.production", "handoff.md", "rules.md")


def check(root: Path) -> dict:
    result = subprocess.run(["git", "ls-files", "--stage", "-z"], cwd=root,
                            check=True, capture_output=True)
    findings = []
    entries = [item for item in result.stdout.decode("utf-8").split("\0") if item]
    for entry in entries:
        meta, path = entry.split("\t", 1)
        mode, _, stage = meta.split()
        parts = PurePosixPath(path)
        name = parts.name.lower()
        reason = None
        if parts.parts[0].lower() in PRIVATE_ROOTS or path.lower() in PRIVATE_FILES:
            reason = "private_runtime_path"
        elif name.startswith(".env") and name not in {".env.example", ".env.template"}:
            reason = "environment_credentials"
        elif name in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials.json", "service-account.json"} or parts.suffix.lower() in {".key", ".pem", ".p12", ".pfx", ".keystore"}:
            reason = "credential_file"
        elif parts.suffix.lower() == ".pdf":
            reason = "external_source_pdf"
        elif mode in {"120000", "160000"}:
            reason = "symlink_or_submodule_requires_review"
        elif stage != "0":
            reason = "unresolved_merge"
        if reason:
            findings.append({"path": path, "reason": reason})
    ignored = subprocess.run(["git", "check-ignore", "-z", "--no-index", "--stdin"], cwd=root,
                             input=("\0".join(IGNORED_EXAMPLES) + "\0").encode("utf-8"),
                             capture_output=True)
    if ignored.returncode not in (0, 1):
        raise RuntimeError("Could not verify runtime ignore rules")
    protected = set(ignored.stdout.decode("utf-8").split("\0"))
    findings.extend({"path": path, "reason": "runtime_ignore_rule_missing"}
                    for path in IGNORED_EXAMPLES if path not in protected)
    return {"ok": not findings, "indexed_files": len(entries), "findings": findings,
            "scope": "Git index paths and runtime ignore rules; run a secret scanner separately"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = check(args.root.resolve())
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError):
        print(json.dumps({"ok": False, "error": "Cannot inspect the Git index"}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
