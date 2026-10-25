"""Master's CLI. Run from any directory: python tools/dnd.py --help."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from engine import CampaignError, StateStore, normalize_state, read_json, validate_state  # noqa: E402


def emit(value, *, error=False, compact=False):
    stream = sys.stderr if error else sys.stdout
    # JSON stays readable in Windows consoles and piped files, even with Unicode names.
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")
    print(json.dumps(value, ensure_ascii=False, indent=None if compact else 2,
                     separators=(",", ":") if compact else None, allow_nan=False), file=stream)


class JsonParser(argparse.ArgumentParser):
    def error(self, message):
        emit({"error": message, "code": "invalid_arguments"}, error=True)
        raise SystemExit(2)


def build_parser():
    parser = JsonParser(description="D&D locale: stato, dadi, salvataggi e aggiornamenti del master.")
    parser.add_argument("--root", type=Path, default=BASE_DIR, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True, parser_class=JsonParser)
    sub.add_parser("show", help="Legge lo stato corrente con revisione.")
    sub.add_parser("status", help="Stato del tavolo: gruppo pronto, avvio, revisione e intenzioni pendenti.")
    sub.add_parser("pending", help="Mostra le intenzioni del giocatore ancora da risolvere.")
    context = sub.add_parser("context", help="Contesto compatto del turno DM: stato coerente e note private, mai una API web.")
    context.add_argument("--recent", type=int, default=6, help="Ultimi tiri pubblici, oltre ai tiri ancora riferiti dalla scena.")
    context.add_argument("--pretty", action="store_true", help="Formatta il JSON su più righe.")
    sub.add_parser("validate", help="Controlla il salvataggio senza modificarlo.")
    sub.add_parser("snapshot", help="Crea una copia del salvataggio corrente.")
    roll = sub.add_parser("roll", help="Lancia e registra dadi verificabili.")
    roll.add_argument("expression", help="Esempio: 1d20+3 oppure 2d6+2")
    roll.add_argument("--label", default="Tiro")
    roll.add_argument("--mode", choices=("normal", "advantage", "disadvantage"), default="normal")
    roll.add_argument("--private", action="store_true", help="Tiro riservato in master/rolls-private.json; non compare nella plancia.")
    batch = sub.add_parser("roll-batch", help="Tiri pubblici indipendenti in una transazione; stesso ID non rilancia mai.")
    batch.add_argument("file", type=Path, help="Array JSON di {expression,label?,mode?}; massimo 30, nessun segreto.")
    batch.add_argument("--request-id", required=True)
    batch.add_argument("--expected-revision", type=int, required=True)
    xp = sub.add_parser("award-xp", help="Assegna una ricompensa XP una sola volta, senza avanzare automaticamente di livello.")
    xp.add_argument("amount", type=int, help="XP TOTALI del gruppo, divisi in parti uguali arrotondate per difetto; --per-character cambia in premio per ogni PG.")
    xp.add_argument("--per-character", action="store_true", help="AMOUNT è il premio a ciascun personaggio, non il totale del gruppo.")
    xp.add_argument("--award-id", required=True, help="ID pubblico univoco del premio già risolto; impedisce doppie assegnazioni.")
    xp.add_argument("--label", required=True, help="Descrizione pubblica di ciò che il gruppo ha già risolto, senza segreti futuri.")
    xp.add_argument("--expected-revision", type=int, required=True)
    character = sub.add_parser("character", help="Aggiunge al gruppo un personaggio predefinito.")
    character.add_argument("template_id")
    character.add_argument("--name")
    character.add_argument("--expected-revision", type=int)
    start = sub.add_parser("start", help="Avvia una volta il gruppo completo senza scegliere le azioni dei PG.")
    start.add_argument("--expected-revision", type=int, required=True)
    start.add_argument("--scene", type=Path, help="JSON pubblico con title, text, choices. Se omesso, conserva la scena.")
    location = sub.add_parser("location-add", help="Aggiunge un luogo pubblico improvvisato senza teletrasportare il gruppo.")
    location.add_argument("file", type=Path, help="JSON con id,name,type,x,y,description,actions; coordinate nella mappa 1000×680.")
    location.add_argument("--expected-revision", type=int, required=True)
    location.add_argument("--connect", action="append", default=[], metavar="LOCATION_ID")
    location.add_argument("--discover", action="store_true", help="Rivela il luogo nella mappa; altrimenti resta non scoperto.")
    sub.add_parser("character-options", help="Mostra dodici classi, specie e scelte del creatore.")
    create = sub.add_parser("character-create", help="Aggiunge una scheda personalizzata da un file JSON.")
    create.add_argument("file", type=Path)
    create.add_argument("--expected-revision", type=int)
    rebuild = sub.add_parser("character-rebuild", help="Modifica una scheda prima dell'inizio, conservando gli altri PG.")
    rebuild.add_argument("character_id")
    rebuild.add_argument("file", type=Path)
    rebuild.add_argument("--expected-revision", type=int, required=True)
    active = sub.add_parser("active", help="Seleziona la scheda di un membro del gruppo.")
    active.add_argument("character_id")
    note = sub.add_parser("note", help="Aggiunge un appunto al diario.")
    note.add_argument("text")
    action = sub.add_parser("action", help="Registra un'intenzione del giocatore, senza risolverla.")
    action.add_argument("text")
    commit = sub.add_parser("commit", help="Applica un patch del master alla revisione letta.")
    commit.add_argument("patch", type=Path, help="File JSON: oggetti uniti ricorsivamente, liste sostituite.")
    commit.add_argument("--expected-revision", type=int, required=True)
    commit.add_argument("--resolve", action="append", default=[], metavar="ACTION_ID",
                        help="Rimuove l'azione risolta; ripetibile.")
    commit.add_argument("--event", help="Aggiunge il racconto al diario nella stessa transazione.")
    commit.add_argument("--compact", action="store_true", help="Restituisce esito e revisione senza ripetere tutto il salvataggio.")
    restore = sub.add_parser("import", help="Ripristina un salvataggio valido con backup automatico.")
    restore.add_argument("file", type=Path)
    restore.add_argument("--expected-revision", type=int)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    store = StateStore(args.root)
    try:
        if args.command == "show":
            result = store.read()
        elif args.command == "status":
            result = store.status()
        elif args.command == "pending":
            state = store.read()
            result = {"revision": state["revision"], "pending_actions": state["pending_actions"]}
        elif args.command == "context":
            from tools.turn_log import TurnLog
            with store.locked():
                world = store.world()
                state = normalize_state(read_json(store.state_path))
                validate_state(state, world)
                result = store._context_locked(state, world, recent=args.recent)
                result["dm_context"] = {"continuity": TurnLog(args.root)._context_locked(state)}
                if state["combat"]["active"]:
                    combat_path = args.root / "master" / "COMBATTIMENTO.json"
                    result["dm_context"]["combat"] = read_json(combat_path) if combat_path.exists() else None
                    if not combat_path.exists():
                        result["dm_context"]["combat_notes_missing"] = True
        elif args.command == "validate":
            state = store.read()
            result = {"ok": True, "campaign_id": state["campaign_id"], "revision": state["revision"]}
        elif args.command == "snapshot":
            result = {"ok": True, "path": str(store.snapshot())}
        elif args.command == "roll":
            if args.private:
                result = {"private": True, "roll": store.private_roll(args.expression, args.label, args.mode)}
            else:
                state, roll = store.roll(args.expression, args.label, args.mode)
                result = {"revision": state["revision"], "roll": roll}
        elif args.command == "roll-batch":
            state, summary = store.roll_batch(read_json(args.file), args.request_id, args.expected_revision)
            result = {"revision": state["revision"], **summary}
        elif args.command == "character":
            state, character = store.choose_character(args.template_id, args.name, args.expected_revision)
            result = {"revision": state["revision"], "character": character}
        elif args.command == "award-xp":
            state, summary = store.award_xp(args.amount, args.award_id, args.label, args.expected_revision,
                                            per_character=args.per_character)
            result = {"revision": state["revision"], **summary,
                      "party_xp": [{"id": member["id"], "name": member["name"],
                                    "level": member["level"], "xp": member.get("xp", 0)}
                                   for member in state["party"]]}
        elif args.command == "start":
            state, summary = store.start(args.expected_revision, read_json(args.scene) if args.scene else None)
            result = {"revision": state["revision"], **summary, "status": store._status(state), "scene": state["scene"]}
        elif args.command == "location-add":
            state, summary = store.add_location(read_json(args.file), args.expected_revision,
                                                connect=args.connect, discover=args.discover)
            result = {"revision": state["revision"], **summary}
        elif args.command == "character-options":
            result = store.character_options()
        elif args.command == "character-create":
            state, character = store.create_character(read_json(args.file), args.expected_revision)
            result = {"revision": state["revision"], "character": character}
        elif args.command == "character-rebuild":
            state, character = store.rebuild_character(args.character_id, read_json(args.file), args.expected_revision)
            result = {"revision": state["revision"], "character": character}
        elif args.command == "active":
            state, character = store.active_character(args.character_id)
            result = {"revision": state["revision"], "character": character}
        elif args.command == "note":
            state, note = store.note(args.text)
            result = {"revision": state["revision"], "note": note}
        elif args.command == "action":
            state, action = store.queue_action(args.text)
            result = {"revision": state["revision"], "action": action}
        elif args.command == "commit":
            state, summary = store.commit(read_json(args.patch), args.expected_revision, args.resolve, args.event)
            result = {"revision": state["revision"], **summary}
            if not args.compact:
                result["state"] = state
        elif args.command == "import":
            state, _ = store.restore(read_json(args.file), args.expected_revision)
            result = {"revision": state["revision"], "state": state}
        else:
            raise CampaignError("Comando sconosciuto.")
        emit(result, compact=args.command == "context" and not args.pretty)
        return 0
    except (CampaignError, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        emit({"error": str(exc), "code": getattr(exc, "code", "storage_error")}, error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
