"""Initialize the distributable demo without ever resetting an existing table."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError, StateStore, normalize_state, read_json, validate_state


def initialize(root: Path) -> dict:
    root = Path(root).resolve()
    store = StateStore(root)
    template = root / "examples" / "demo"
    with store.locked():
        present = [store.world_path.exists(), store.state_path.exists()]
        if all(present):
            state = store._read()
            return {"initialized": False, "preserved": True, "revision": state["revision"]}
        if any(present):
            raise CampaignError("Inizializzazione incompleta: conserva i file esistenti e recupera il file mancante da un backup. Nessun dato sovrascritto.")
        world = read_json(template / "world.json")
        state = normalize_state(read_json(template / "campaign.json"))
        validate_state(state, world)
        generated = {
            "master/CURRENT.md": (template / "CURRENT.md").read_text(encoding="utf-8"),
            "master/MEMORIA.md": "# Memoria privata\n\nNessuna azione narrativa risolta. Leggere sempre il salvataggio e il diario incrementale.\n",
            "handoff.md": (template / "handoff.md").read_text(encoding="utf-8"),
            "rules.md": (template / "rules.md").read_text(encoding="utf-8").replace("../../docs/DM_GUIDE.md", "docs/DM_GUIDE.md"),
            "campaigns/demo/prepared/encounters.json": (template / "encounters.json").read_text(encoding="utf-8"),
        }
        # Read and validate every template before creating the first save. A
        # missing template must not leave an apparently initialized broken table.
        json.loads(generated["campaigns/demo/prepared/encounters.json"])
        # The engine lock serializes first launches; exclusive creation also
        # protects against unrelated writers. Partial disk failures are reported.
        for path, value in ((store.world_path, world), (store.state_path, state)):
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
                stream.write("\n")
        for relative, content in generated.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                with path.open("x", encoding="utf-8", newline="\n") as stream:
                    stream.write(content)
            except FileExistsError:
                pass  # A user's notes always take precedence over demo notes.
    return {"initialized": True, "preserved": False, "revision": 0, "campaign_id": "demo"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(initialize(args.root), ensure_ascii=False))
        return 0
    except (CampaignError, OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
