"""Private, durable continuity for quick turns; never loaded by the web server.

The public campaign remains authoritative. Record the private event only after a
successful public commit, using its returned revision. Repeating an event ID is
safe: an identical payload is a no-op and a different payload is rejected.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from engine import CampaignError, ID_RE, StateStore, now, read_json, require, text_field  # noqa: E402


def _payload(value: dict, *, checkpoint: bool = False) -> tuple[dict, str]:
    require(isinstance(value, dict), "L'evento deve essere un oggetto JSON.")
    allowed = {"id", "revision", "summary", "references"} if checkpoint else {
        "id", "revision", "public", "dm", "pending", "roll_ids", "references", "details",
        "session", "clock", "actor", "intent", "outcome", "resources", "information", "question",
    }
    require(not set(value) - allowed, "Campi del diario non riconosciuti.")
    require(isinstance(value.get("id"), str) and bool(ID_RE.fullmatch(value["id"])),
            "id: usa 1–80 lettere, numeri, trattini o underscore.")
    require(type(value.get("revision")) is int and value["revision"] >= 0,
            "revision: serve la revisione reale del salvataggio.")
    for field in ("public", "dm", "summary", "actor", "intent", "outcome", "question"):
        if field in value:
            text_field(value[field], field, 20000, empty=True)
    for field in ("pending", "roll_ids", "references", "resources", "information"):
        if field in value:
            require(isinstance(value[field], list), f"{field}: serve una lista.")
    for field in ("details", "clock"):
        if field in value:
            require(isinstance(value[field], dict), f"{field}: serve un oggetto JSON.")
    if "session" in value:
        require(type(value["session"]) is int and value["session"] >= 1, "session non valida.")
    try:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
    except (ValueError, TypeError, UnicodeError) as exc:
        raise CampaignError("Evento non serializzabile come JSON finito.") from exc
    require(len(encoded) <= 131072, "Evento troppo grande (massimo 128 KiB).")
    return copy.deepcopy(value), hashlib.sha256(encoded).hexdigest()


class TurnLog:
    def __init__(self, root: str | Path):
        self.store = StateStore(root)
        self.path = self.store.root / "master" / "turn-log.json"

    def _load_locked(self, state: dict) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "campaign_id": state["campaign_id"],
                    "events": [], "checkpoints": []}
        # Public saves have a 512 KiB limit. Continuity must keep growing beyond
        # that cap instead of becoming unreadable after enough recorded turns.
        try:
            log = json.loads(self.path.read_text(encoding="utf-8-sig"),
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite")))
        except (OSError, ValueError) as exc:
            raise CampaignError(f"Impossibile leggere {self.path.name}: {exc}", "storage_error", 500) from exc
        require(isinstance(log, dict) and log.get("schema_version") == 1,
                "Formato del diario privato non valido.")
        require(log.get("campaign_id") == state["campaign_id"],
                "Il diario privato appartiene a un'altra campagna.")
        require(isinstance(log.get("events"), list) and isinstance(log.get("checkpoints"), list),
                "Cronologia privata non valida.")
        ids = set()
        for entry in [*log["events"], *log["checkpoints"]]:
            require(isinstance(entry, dict) and isinstance(entry.get("payload"), dict),
                    "Voce del diario privato non valida.")
            require(entry.get("kind") in {"event", "checkpoint"} and isinstance(entry.get("at"), str)
                    and isinstance(entry.get("captured", {}), dict), "Metadati del diario non validi.")
            payload, digest = _payload(entry["payload"], checkpoint=entry.get("kind") == "checkpoint")
            require(entry.get("digest") == digest and payload["id"] not in ids,
                    "Voce del diario danneggiata o ID duplicato.")
            ids.add(payload["id"])
            if payload["revision"] > state["revision"]:
                raise CampaignError("Il diario privato è più recente del salvataggio: riconciliare il ripristino.",
                                    "continuity_conflict", 409)
        for point in log["checkpoints"]:
            require(type(point.get("event_count")) is int and 0 <= point["event_count"] <= len(log["events"]),
                    "Indice del checkpoint non valido.")
        return log

    @staticmethod
    def _visible(entry: dict) -> dict:
        return {**copy.deepcopy(entry["payload"]), "at": entry["at"],
                **copy.deepcopy(entry.get("captured", {}))}

    def _record(self, value: dict, *, checkpoint: bool = False) -> dict:
        payload, digest = _payload(value, checkpoint=checkpoint)
        with self.store.locked():
            if (self.store.root / "master" / "pending-operation.json").exists():
                raise CampaignError("Completa prima l'operazione DM interrotta con tools/play.py recover.",
                                    "operation_pending", 503)
            state = self.store._read()
            require(payload["revision"] <= state["revision"],
                    "Non si può registrare una revisione futura prima del commit.")
            log = self._load_locked(state)
            for entry in [*log["events"], *log["checkpoints"]]:
                if entry["payload"]["id"] == payload["id"]:
                    if entry["digest"] != digest or (entry["kind"] == "checkpoint") != checkpoint:
                        raise CampaignError("ID del diario già usato con contenuto diverso.", "event_conflict", 409)
                    return {"ok": True, "id": payload["id"], "revision": payload["revision"],
                            "already_recorded": True}
            if checkpoint:
                require(payload["revision"] == state["revision"],
                        "Il checkpoint deve descrivere la revisione corrente.")
            else:
                previous_revision = max((entry["payload"]["revision"]
                                         for entry in [*log["events"][-1:], *log["checkpoints"][-1:]]), default=0)
                require(payload["revision"] >= previous_revision,
                        "Registra gli eventi in ordine di revisione; per una correzione usa la revisione corrente.")
            entry = {"kind": "checkpoint" if checkpoint else "event", "payload": payload,
                     "digest": digest, "at": now()}
            if payload["revision"] == state["revision"]:
                entry["captured"] = {key: copy.deepcopy(state[key]) for key in ("session", "clock")
                                     if key not in payload}
            if checkpoint:
                entry["event_count"] = len(log["events"])
                log["checkpoints"].append(entry)
            else:
                log["events"].append(entry)
            self.store._atomic_json(self.path, log)
            return {"ok": True, "id": payload["id"], "revision": payload["revision"],
                    "already_recorded": False}

    def append(self, value: dict) -> dict:
        return self._record(value)

    def checkpoint(self, value: dict) -> dict:
        """Mark rewritten handoff/memory references; keep every earlier event."""
        return self._record(value, checkpoint=True)

    def _context_locked(self, state: dict, limit: int = 20) -> dict:
        """Called with StateStore.locked() held, sharing the same public snapshot."""
        require(type(limit) is int and limit >= 0, "limit deve essere un intero non negativo; 0 legge tutto.")
        log = self._load_locked(state)
        point = log["checkpoints"][-1] if log["checkpoints"] else None
        start = point["event_count"] if point else 0
        events = log["events"][start:]
        # Earliest unread events first: a truncated read must not silently skip history.
        selected = events[:limit] if limit else events
        last_revision = max((entry["payload"]["revision"]
                             for entry in [*log["events"][-1:], *log["checkpoints"][-1:]]), default=None)
        return {"checkpoint": self._visible(point) if point else None,
                "events": [self._visible(entry) for entry in selected],
                "events_since_checkpoint": len(events), "remaining_count": len(events) - len(selected),
                "total_events": len(log["events"]), "path": "master/turn-log.json",
                "last_recorded_revision": last_revision, "public_revision": state["revision"],
                "public_revision_advanced": last_revision is not None and state["revision"] > last_revision}

    def context(self, limit: int = 20) -> dict:
        with self.store.locked():
            state = self.store._read()
            return {"revision": state["revision"], **self._context_locked(state, limit)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Continuità privata incrementale del DM.")
    parser.add_argument("--root", type=Path, default=BASE_DIR, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("append", "checkpoint"):
        sub.add_parser(name).add_argument("file", type=Path)
    context = sub.add_parser("context")
    context.add_argument("--limit", type=int, default=20, help="0: tutti gli eventi dopo il checkpoint.")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    try:
        log = TurnLog(args.root)
        if args.command == "context":
            result = log.context(args.limit)
        else:
            result = getattr(log, args.command)(read_json(args.file))
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
        return 0
    except (CampaignError, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(json.dumps({"error": str(exc), "code": getattr(exc, "code", "storage_error")},
                         ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
