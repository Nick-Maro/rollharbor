"""Prepared, private DM operations: one short command, dice and durable continuity.

This module is a CLI only. It is deliberately not imported by the public server.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from engine import CampaignError, read_json  # noqa: E402
from tools.dnd import JsonParser, emit  # noqa: E402


def _revision(value: str) -> int:
    try:
        revision = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("serve una revisione intera") from exc
    if revision < 0:
        raise argparse.ArgumentTypeError("la revisione deve essere almeno zero")
    return revision


def _attack_selector(value: str) -> str | int:
    return int(value) if value.isascii() and value.isdecimal() else value


def _transaction(parser):
    parser.add_argument("--id", required=True, dest="request_id",
                        help="ID stabile della richiesta. Riutilizzarlo soltanto per ritentare la stessa operazione.")
    parser.add_argument("--expected-revision", required=True, type=_revision,
                        help="Revisione ottenuta dal contesto o dall'ultima operazione riuscita.")


def _lethality(parser, *, required=False):
    group = parser.add_mutually_exclusive_group(required=required)
    group.add_argument("--nonlethal", dest="nonlethal", action="store_const", const=True,
                       help="Scelta del giocatore: KO stabile quando un attacco in mischia porta a zero PF.")
    group.add_argument("--lethal", dest="nonlethal", action="store_const", const=False,
                       help="Scelta del giocatore: applica le conseguenze letali previste dalle regole.")
    parser.set_defaults(nonlethal=None)


def _death_saves(parser):
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--death-saves", dest="death_saves", action="store_const", const=True,
                       help="Il DM concede i TS morte a questo PNG importante; i PG li seguono normalmente.")
    group.add_argument("--no-death-saves", dest="death_saves", action="store_const", const=False,
                       help="Il DM applica al PNG la morte a zero PF, salvo KO non letale.")
    parser.set_defaults(death_saves=None)


def build_parser():
    parser = JsonParser(
        description="Strumenti pronti per il DM: risolvono l'operazione scelta, senza decidere per i giocatori.",
        epilog=("Esempi: attack d Gundren --attack pugno --id s1-r1-d-pugno --expected-revision 28; "
                "knockout Gundren --nonlethal --id s1-r1-d-ko --expected-revision 29. "
                "I numeri sono esempi: usare sempre la revisione corrente. Contesto e risultati sono riservati al DM."))
    parser.add_argument("--root", type=Path, default=BASE_DIR,
                        help="Cartella del tavolo (prima del sottocomando); normalmente rilevata automaticamente.")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=JsonParser)
    context = sub.add_parser("context", help="Unica lettura compatta: stato pubblico, schede e continuità privata.")
    context.add_argument("--recent", type=_revision, default=6, help="Numero di tiri pubblici recenti (predefinito: 6).")
    context.add_argument("--pretty", action="store_true", help="JSON su più righe.")
    context.add_argument("--brief", action="store_true",
                         help="Solo turni nella chat già informata: ultimi 4 eventi e tiri, mantenendo schede e combattimento completo. Non usare per riprendere una chat.")
    sub.add_parser("recover", help="Completa una transazione interrotta già registrata, senza ripetere dadi o scelte.")

    attack = sub.add_parser("attack", help="Attacco singolo e danni quando dovuti; salva azione e diario.")
    attack.add_argument("actor", help="ID del personaggio o nome univoco.")
    attack.add_argument("target", help="ID del bersaglio o nome univoco.")
    attack.add_argument("--attack", type=_attack_selector, default=0,
                        help="Nome o indice zero-based dell'attacco in scheda; pugno/testata/unarmed per colpo senz'armi.")
    attack.add_argument("--mode", choices=("normal", "advantage", "disadvantage"), default="normal")
    attack.add_argument("--bonus", action="store_true", help="Colpo senz'armi bonus di Arti Marziali, se disponibile.")
    melee = attack.add_mutually_exclusive_group()
    melee.add_argument("--melee", dest="melee", action="store_const", const=True,
                       help="Attacco in mischia, quando il profilo dell'arma non lo specifica.")
    melee.add_argument("--ranged", dest="melee", action="store_const", const=False,
                       help="Attacco a distanza; non consente la scelta di KO in mischia.")
    attack.set_defaults(melee=None)
    attack.add_argument("--reactions-checked", action="store_true",
                        help="Il DM ha già risolto o escluso le difese reattive pertinenti; non decide per i PG.")
    attack.add_argument("--modifiers-checked", action="store_true",
                        help="Il DM ha già verificato condizioni, resistenze e modificatori pertinenti.")
    attack.add_argument("--martial-arts-eligible", action="store_true",
                        help="Il DM conferma che il monaco non indossa armatura né impugna scudo.")
    _lethality(attack)
    _death_saves(attack)
    _transaction(attack)

    multiattack = sub.add_parser("npc-multiattack", help="Multiattacco PNG da profilo verificato, bersagli dichiarati e salvataggio unico.")
    multiattack.add_argument("file", type=Path,
                             help="Bundle privato con actor, profile, source, targets, nonlethal e verifiche del DM.")
    _transaction(multiattack)

    knockout = sub.add_parser("knockout", help="Risolve la scelta pendente a zero PF usando i dadi già tirati.")
    knockout.add_argument("target", help="ID del bersaglio o nome univoco.")
    _lethality(knockout, required=True)
    _death_saves(knockout)
    _transaction(knockout)

    next_turn = sub.add_parser("next", help="Conclude il turno corrente, senza far agire automaticamente altri partecipanti.")
    next_turn.add_argument("--actor", help="ID o nome del partecipante atteso; protegge dal saltare il turno sbagliato.")
    _transaction(next_turn)

    heal = sub.add_parser("heal", help="Applica cure di quantità già risolta, senza spendere risorse automaticamente.")
    heal.add_argument("target", help="ID o nome univoco.")
    heal.add_argument("amount", type=_revision, help="PF di cura già determinati dal DM.")
    _transaction(heal)
    damage = sub.add_parser("damage", help="Applica danni già determinati; non lancia attacchi o sceglie reazioni.")
    damage.add_argument("target", help="ID o nome univoco.")
    damage.add_argument("amount", type=_revision, help="Danni finali dopo resistenze e altri modificatori.")
    damage.add_argument("--type", dest="damage_type", help="Tipo di danno già verificato (descrittivo).")
    _lethality(damage)
    _transaction(damage)
    resource = sub.add_parser("resource", help="Spende o recupera una risorsa indicata, entro i limiti della scheda.")
    resource.add_argument("actor", help="ID o nome univoco del PG.")
    resource.add_argument("resource", help="ID o nome univoco della risorsa.")
    resource.add_argument("delta", type=int, help="Variazione firmata: -1 spende un uso, 1 ne recupera uno.")
    _transaction(resource)
    condition = sub.add_parser("condition", help="Aggiunge o rimuove una condizione già risolta dal DM.")
    condition.add_argument("target", help="ID o nome univoco.")
    condition.add_argument("condition", help="Nome della condizione; usare virgolette per più parole.")
    condition.add_argument("--remove", action="store_true", help="Rimuove la condizione invece di aggiungerla.")
    _transaction(condition)
    check = sub.add_parser("check", help="Prova pubblica: bonus dalla scheda, dadi, confronto con CD se indicata.")
    check.add_argument("actor", help="ID o nome univoco del PG.")
    statistic = check.add_mutually_exclusive_group(required=True)
    statistic.add_argument("--ability", help="Chiave caratteristica, per esempio str o dex.")
    statistic.add_argument("--skill", help="Chiave competenza presente nella scheda.")
    statistic.add_argument("--save", dest="saving_throw", help="Caratteristica del tiro salvezza, per esempio con per la concentrazione.")
    check.add_argument("--dc", type=_revision, help="CD fissata dal DM prima del tiro.")
    check.add_argument("--mode", choices=("normal", "advantage", "disadvantage"), default="normal")
    check.add_argument("--label", help="Etichetta pubblica senza informazioni segrete.")
    _transaction(check)
    death = sub.add_parser("death", help="Tiro salvezza contro morte del partecipante a zero PF nel suo turno.")
    death.add_argument("actor", help="ID o nome univoco del partecipante.")
    death.add_argument("--mode", choices=("normal", "advantage", "disadvantage"), default="normal")
    _transaction(death)
    save = sub.add_parser("save", help="Patch e continuità insieme da un bundle JSON, per azioni libere e casi complessi.")
    save.add_argument("file", type=Path,
                      help="JSON: {patch:{...}, public?:testo, dm?:testo, pending?:[], references?:[], resolve?:[], private_combat?:{...}}.")
    _transaction(save)
    for name, description in (
        ("heal-spell", "Cura Ferite/Parola Guaritrice: dadi, slot, azione, cura e diario atomici."),
        ("contest", "Presa, spinta o fuga: contesa con difesa scelta esplicitamente."),
        ("entangle", "Intralciare: area dichiarata, slot, TS, concentrazione e scadenza."),
        ("effect", "Interrompi concentrazione o tenta di liberarti da Intralciare."),
    ):
        command = sub.add_parser(name, help=description)
        command.add_argument("file", type=Path, help="Piano JSON privato con scelte e verifiche del DM.")
        _transaction(command)
    preflight = sub.add_parser("preflight", help="Verifica un piano senza dadi, risorse o modifiche.")
    preflight.add_argument("kind", choices=("heal-spell", "contest", "entangle"))
    preflight.add_argument("file", type=Path)
    prepare = sub.add_parser("prepare", help="Consulta una scena preparata privata; non attiva incontri o copioni.")
    prepare.add_argument("scene", nargs="?", default="goblin-arrows")
    prepare.add_argument("--preflight", action="store_true", help="Aggiungi verifiche read-only del gruppo e della continuita.")
    return parser


def _run(args):
    if args.command in {"heal-spell", "contest", "entangle", "effect"}:
        from tools.action_toolkit import ActionToolkit
        toolkit = ActionToolkit(args.root)
        operation = getattr(toolkit, "heal_spell" if args.command == "heal-spell" else args.command)
        return operation(read_json(args.file), args.request_id, args.expected_revision)
    if args.command == "preflight":
        from tools.action_toolkit import ActionToolkit
        return ActionToolkit(args.root).preflight(args.kind, read_json(args.file))
    if args.command == "prepare":
        from tools.encounter_prep import inspect_scene
        return inspect_scene(args.root, args.scene, preflight=args.preflight)
    if args.command in {"attack", "npc-multiattack", "knockout", "next"}:
        from tools.action_engine import ActionEngine
        engine = ActionEngine(args.root)
        if type(engine.ops).__module__ == "tools.session_ops":
            from tools.action_toolkit import ToolkitOps
            engine.ops = ToolkitOps(args.root)
    if args.command == "attack":
        spec = {"actor": args.actor, "target": args.target, "attack": args.attack,
                "mode": args.mode, "action": "martial_bonus" if args.bonus else "action",
                "nonlethal": args.nonlethal, "reactions_checked": args.reactions_checked,
                "modifiers_checked": args.modifiers_checked}
        if args.melee is not None:
            spec["melee"] = args.melee
        if args.martial_arts_eligible:
            spec["martial_arts_eligible"] = True
        if args.death_saves is not None:
            spec["death_saves"] = args.death_saves
        return engine.resolve_attack(spec, args.request_id, args.expected_revision)
    if args.command == "npc-multiattack":
        return engine.resolve_npc_multiattack(read_json(args.file), args.request_id, args.expected_revision)
    if args.command == "knockout":
        spec = {"target": args.target, "nonlethal": args.nonlethal}
        if args.death_saves is not None:
            spec["death_saves"] = args.death_saves
        return engine.resolve_zero_hp(spec, args.request_id, args.expected_revision)
    if args.command == "next":
        spec = {"actor": args.actor} if args.actor is not None else {}
        return engine.advance_turn(spec, args.request_id, args.expected_revision)
    from tools.session_ops import SessionOps
    if args.command in {"heal", "damage"}:
        payload = {"target": args.target, "amount": args.amount}
        if args.command == "damage":
            if args.damage_type is not None:
                payload["damage_type"] = args.damage_type
            if args.nonlethal is not None:
                payload["nonlethal"] = args.nonlethal
                if args.nonlethal:
                    payload["melee"] = True
    elif args.command == "resource":
        payload = {"actor": args.actor, "resource": args.resource, "delta": args.delta}
    elif args.command == "condition":
        payload = {"target": args.target, "condition": args.condition, "remove": args.remove}
    elif args.command == "check":
        payload = {"actor": args.actor, "mode": args.mode}
        if args.ability is not None:
            payload["ability"] = args.ability
        elif args.skill is not None:
            payload["skill"] = args.skill
        else:
            payload["save"] = args.saving_throw
        if args.dc is not None:
            payload["dc"] = args.dc
        if args.label is not None:
            payload["label"] = args.label
    elif args.command == "death":
        payload = {"actor": args.actor, "mode": args.mode}
    elif args.command == "save":
        payload = read_json(args.file)
    else:
        raise CampaignError("Comando sconosciuto.", "invalid_arguments")
    operations = SessionOps(args.root)
    if type(operations).__module__ == "tools.session_ops":
        from tools.action_toolkit import ToolkitOps
        operations = ToolkitOps(args.root)
    return operations.execute(args.command, payload, args.expected_revision, args.request_id)


def _brief_context(root):
    """Explicitly partial history for a DM already following this chat.

    Rules, statistics, resources, pending choices and private combat are kept.
    Only event parameter snapshots and older history are omitted; the durable
    log remains intact and the output reports exactly how much was excluded.
    """
    from engine import StateStore, normalize_state, validate_state
    from tools.turn_log import TurnLog
    store = StateStore(root)
    with store.locked():
        world = store.world()
        state = normalize_state(read_json(store.state_path))
        validate_state(state, world)
        result = store._context_locked(state, world, recent=4)
        continuity = TurnLog(root)._context_locked(state, limit=0)
        events = continuity["events"]
        selected = events[-4:]
        for event in selected:
            # These are copied projections of the private log, never its file.
            if isinstance(event.get("details"), dict):
                event["details"] = {key: value for key, value in event["details"].items() if key != "parameters"}
        continuity.update({"events": selected, "remaining_count": len(events) - len(selected),
                           "omitted_earlier_events": len(events) - len(selected),
                           "history_mode": "latest_only", "event_parameters_omitted": True})
        result["dm_context"] = {"continuity": continuity}
        if state["combat"]["active"]:
            path = Path(root) / "master" / "COMBATTIMENTO.json"
            result["dm_context"]["combat"] = read_json(path) if path.exists() else None
            if not path.exists():
                result["dm_context"]["combat_notes_missing"] = True
        result["context_mode"] = "brief_hot_turn"
        result["history_notice"] = "Cronologia parziale: usare solo nella chat già informata; per una nuova chat usare context senza --brief."
        return result


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in {"context", "recover"}:
            from tools.session_ops import SessionOps
            recovery = SessionOps(args.root).recover()
            if args.command == "recover":
                emit(recovery, compact=True)
                return 0
            if args.brief:
                emit(_brief_context(args.root), compact=not args.pretty)
                return 0
            # Reuse the existing locked aggregate in-process: no second Python startup.
            from tools.dnd import main as context_main
            arguments = ["--root", str(args.root), "context", "--recent", str(args.recent)]
            if args.pretty:
                arguments.append("--pretty")
            return context_main(arguments)
        emit(_run(args), compact=True)
        return 0
    except (CampaignError, OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        emit({"error": str(exc), "code": getattr(exc, "code", "storage_error")}, error=True, compact=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
