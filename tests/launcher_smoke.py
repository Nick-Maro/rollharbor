"""Optional Windows launcher QA, using an isolated copy with spaces in its path."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def run():
    if os.name != "nt":
        print(json.dumps({"skipped": "Windows launcher check"}))
        return
    qa_root = (ROOT / "QA").resolve()
    qa_root.mkdir(exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix=".launcher check ", dir=qa_root)
    isolated = Path(temporary.name).resolve()
    assert isolated.is_relative_to(qa_root) and isolated.name.startswith(".launcher check ")
    saved_before = (ROOT / "data" / "campaign.json").read_bytes()
    for relative in ("server.py", "engine.py", "character_builder.py", "runtime_info.py", "AVVIA.ps1", "ARRESTA.ps1", "tools/windows-runtime.ps1", "tools/setup_demo.py"):
        destination = isolated / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
    # A clean checkout must work through the launcher too. Never use the real
    # party as QA data: the server initializes this isolated original demo.
    shutil.copytree(ROOT / "examples/demo", isolated / "examples/demo")
    shutil.copytree(ROOT / "web", isolated / "web")

    def command(script, *arguments):
        result = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(isolated / script), "-Json", *arguments],
                                cwd=isolated, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=35)
        try:
            payload = json.loads(result.stdout.strip())
        except ValueError:
            raise AssertionError(f"Launcher output invalid: {result.stdout} {result.stderr}") from None
        assert result.returncode == 0 and payload["ok"], payload
        return payload

    try:
        first = command("AVVIA.ps1", "-NoBrowser")
        assert not first["reused"] and not first["restarted"]
        with urlopen(first["url"] + "api/health", timeout=3) as response:
            health = json.load(response)
        assert Path(health["workspace"]).resolve() == isolated
        assert health["pid"] == first["pid"]
        with ThreadPoolExecutor(max_workers=2) as executor:
            simultaneous = list(executor.map(lambda _: command("AVVIA.ps1", "-NoBrowser"), range(2)))
        assert all(result["reused"] and result["pid"] == first["pid"] for result in simultaneous)
        # Change only the isolated backend: the launcher must replace stale code.
        with (isolated / "engine.py").open("a", encoding="utf-8") as output:
            output.write("\n# Launcher QA: changed isolated backend.\n")
        refreshed = command("AVVIA.ps1", "-NoBrowser")
        assert refreshed["restarted"] and refreshed["pid"] != first["pid"]
        assert refreshed["revision"] == first["revision"]
        forced = command("AVVIA.ps1", "-NoBrowser", "-Restart")
        assert forced["restarted"] and forced["pid"] != refreshed["pid"]
        stopped = command("ARRESTA.ps1")
        assert stopped["stopped_ports"] == [forced["port"]]
        assert command("ARRESTA.ps1")["stopped_ports"] == []
        assert (ROOT / "data" / "campaign.json").read_bytes() == saved_before
        print(json.dumps({"ok": True, "paths_with_spaces": True, "concurrent_reuse": True,
                          "stale_code_restart": True, "forced_restart": True,
                          "stop_idempotent": True, "real_save_unchanged": True}))
    finally:
        try:
            command("ARRESTA.ps1")
        finally:
            # Cleanup may recurse only inside this explicitly created QA directory.
            assert isolated.is_relative_to(qa_root) and isolated.name.startswith(".launcher check ")
            temporary.cleanup()


if __name__ == "__main__":
    run()
