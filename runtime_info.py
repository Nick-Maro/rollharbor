"""Identify the loaded server code without depending on mutable campaign data."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import os
import subprocess
import sys

RUNTIME_FILES = ("server.py", "engine.py", "character_builder.py", "runtime_info.py")


def runtime_fingerprint(root: str | Path) -> str:
    root = Path(root).resolve()
    # Isolated QA roots contain only web/data; their runtime is this checkout.
    code_root = root if (root / "server.py").is_file() else Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for relative in RUNTIME_FILES:
        path = code_root / relative
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes() if path.is_file() else b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Identifica il codice del server locale.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--launch-server", action="store_true", help="Avvia un processo locale senza ereditare i canali della chat.")
    parser.add_argument("--port", type=int, default=8765)
    arguments = parser.parse_args()
    if arguments.launch_server:
        root = arguments.root.resolve()
        if not 1 <= arguments.port <= 65535 or not (root / "server.py").is_file():
            parser.error("Porta o cartella del server non valida.")
        logs = root / "logs"
        logs.mkdir(exist_ok=True)
        output_path = logs / f"server-{arguments.port}.log"
        error_path = logs / f"server-{arguments.port}.error.log"
        # Closing every unrelated handle is essential when a launcher is invoked
        # through a captured chat/tool pipe. An inherited pipe can keep it waiting
        # after PowerShell has already exited.
        with output_path.open("ab") as output, error_path.open("ab") as errors:
            process = subprocess.Popen(
                [sys.executable, "-u", str(root / "server.py"), "--port", str(arguments.port)],
                cwd=root, stdin=subprocess.DEVNULL, stdout=output, stderr=errors,
                close_fds=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
            )
        print(json.dumps({"pid": process.pid, "output_log": str(output_path), "error_log": str(error_path)}))
    else:
        print(json.dumps({"fingerprint": runtime_fingerprint(arguments.root)}))
