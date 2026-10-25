"""Small, reusable 2014 combat operations for the local DM, never web APIs.

This resolves a *declared* attack. The DM still checks position, targeting,
cover, visibility, spells and special traits before calling it. Unsupported
defences stop before dice; no player decision is supplied by this module.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
from time import perf_counter

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))
from engine import CampaignError, MAX_ROLLS, integer, parse_dice, require, roll_dice

RULES = "SRD 5.1 (2014): Making an Attack, Critical Hits, Damage and Healing, Knocking a Creature Out; Monk: Martial Arts."


def _lookup(state: dict, private: dict, reference: str) -> tuple[dict, bool]:
    require(isinstance(reference, str) and reference.strip(), "Indica un ID o nome del partecipante.")
    pool = [(pc, True) for pc in state["party"]]
    pool.extend((npc, False) for npc in private.get("creatures", []))
    exact = [entry for entry in pool if entry[0].get("id") == reference]
    if exact:
        return exact[0]
    names = {part["id"]: part["name"].casefold() for part in state["combat"]["participants"]}
    matches = [entry for entry in pool if reference.casefold() in {
        entry[0].get("name", "").casefold(), names.get(entry[0].get("id"))}]
    require(len(matches) == 1, "Nome assente o ambiguo: usa l'ID del partecipante.")
    return matches[0]


def _turn(state: dict, private: dict, actor: dict, *, allow_pending=False) -> None:
    combat = state["combat"]
    require(combat["active"] and combat["participants"], "Non c'è un combattimento attivo.")
    require(combat["participants"][combat["turn_index"]]["id"] == actor["id"], "Non è il turno di questo personaggio.")
    if not allow_pending:
        public_pending = state.get("flags", {}).get("combat_context", {}).get("pending_resolution")
        require(not public_pending and not private.get("pending_resolution") and not private.get("pending_reactions"),
                "Prima risolvi la scelta o reazione ancora aperta.")


def _sync(state: dict, entity: dict, pc: bool) -> None:
    for participant in state["combat"]["participants"]:
        if participant["id"] == entity["id"]:
            participant["conditions"] = copy.deepcopy(entity.get("conditions", []))
            if pc:
                for key in ("hp", "max_hp", "ac"):
                    participant[key] = entity[key]
            # Updating a private NPC must never reveal its original HP/AC.
            elif "hp" in participant:
                participant["hp"] = entity["hp"]
                participant["max_hp"] = entity["max_hp"]


def _conditions(entity: dict, *, add=(), remove=()) -> None:
    removed = {item.casefold() for item in remove}
    conditions = [item for item in entity.get("conditions", []) if item.casefold() not in removed]
    for item in add:
        if item.casefold() not in {value.casefold() for value in conditions}:
            conditions.append(item)
    entity["conditions"] = conditions


def _class(entity: dict) -> str:
    return entity.get("class_id", entity.get("class", "")).casefold()


def _monk(entity: dict) -> bool:
    return _class(entity) in {"monk", "monaco"}


def _unarmed(name: str) -> bool:
    return name.casefold() in {"unarmed", "pugno", "pugni", "testata", "calcio", "colpo senz'armi", "colpo senz’armi"} or "senz'armi" in name.casefold()


def _monk_weapon(name: str) -> bool:
    name = name.casefold().split("·", 1)[0].strip()
    return _unarmed(name) or name in (
        "spada corta", "shortsword", "bastone", "quarterstaff", "randello", "club",
        "pugnale", "dagger", "lancia", "spear", "martello leggero", "light hammer",
        "ascia", "ascia a una mano", "handaxe", "falcetto", "sickle", "mazza", "mace")


def _public_name(state: dict, entity: dict) -> str:
    participant = next((item for item in state["combat"]["participants"] if item["id"] == entity["id"]), None)
    require(participant is not None, "La creatura non è tra i partecipanti percepiti: gestisci prima la scoperta con il DM.")
    return participant["name"]


def _attack_profile(actor: dict, selector, spec: dict) -> tuple[dict, bool, bool]:
    attacks = actor.get("attacks", [])
    if isinstance(selector, str) and _unarmed(selector):
        found = next((item for item in attacks if _unarmed(item["name"])), None)
        if found:
            profile = copy.deepcopy(found)
            profile["name"] = selector
        else:
            modifier = (actor.get("abilities", {}).get("str", actor.get("strength", 10)) - 10) // 2
            profile = {"name": selector, "bonus": modifier + actor.get("proficiency", 2),
                       "fixed_damage": max(0, 1 + modifier)}
    elif type(selector) is int:
        require(0 <= selector < len(attacks), "Indice dell'attacco non presente nella scheda.")
        profile = copy.deepcopy(attacks[selector])
    else:
        require(isinstance(selector, str), "attack deve essere un nome o indice da zero.")
        matches = [item for item in attacks if item["name"].casefold() == selector.casefold()]
        require(len(matches) == 1, "Attacco non presente o ambiguo: usa nome esatto o indice.")
        profile = copy.deepcopy(matches[0])
    unarmed = _unarmed(profile["name"])
    melee = True if unarmed else spec.get("melee", profile.get("melee"))
    require(type(melee) is bool, "Specifica melee=true/false: la scheda non distingue questo attacco.")
    integer(profile.get("bonus"), "bonus attacco", -100, 100)
    if "fixed_damage" not in profile:
        count, sides, bonus, _ = parse_dice(profile.get("damage"))
        parse_dice(f"{count * 2}d{sides}{bonus:+d}")
    if unarmed and _monk(actor):
        equipment = " ".join(item["name"].casefold() for item in actor.get("inventory", []) if item.get("qty", 0))
        require(spec.get("martial_arts_eligible") is True or not any(word in equipment for word in (
            "scudo", "shield", "armatura", "armor", "cuoio", "cotta", "leather", "mail")),
            "Arti marziali richiede assenza di armature e scudo: verifica l'equipaggiamento indossato.")
    return profile, melee, _monk(actor) and melee and _monk_weapon(profile["name"])


def _usage(state: dict, private: dict, actor: dict) -> dict:
    usage = private.get("turn_usage", {})
    if usage.get("actor_id") != actor["id"]:
        usage = {"actor_id": actor["id"], "action_used": False, "bonus_action_used": False}
    return copy.deepcopy(usage)


def _write_context(state: dict, private: dict) -> None:
    context = state["flags"].setdefault("combat_context", {})
    for key in ("turn_usage", "pending_resolution"):
        if private.get(key) is not None:
            if key == "pending_resolution":
                # The private record also contains original NPC HP. Flags are
                # public, so only already perceived decision metadata belongs here.
                context[key] = {field: copy.deepcopy(value) for field, value in private[key].items()
                                if field in {"type", "actor_id", "target_id", "attack", "roll_ids"}}
            else:
                context[key] = copy.deepcopy(private[key])
        else:
            context.pop(key, None)
    current = state["combat"]
    actor_id = current["participants"][current["turn_index"]]["id"]
    context["awaiting_actor_id"] = actor_id
    private.update({"round": current["round"], "turn_index": current["turn_index"], "awaiting_actor_id": actor_id})


def _zero(entity: dict, pc: bool, nonlethal: bool, *, damage: int, previous_hp: int,
          allow_death_saves=None) -> str:
    entity["hp"] = 0
    entity.pop("concentration", None)
    entity.pop("concentrating", None)
    entity["conditions"] = [condition for condition in entity.get("conditions", [])
                            if not condition.casefold().startswith(("concentrazione", "concentration"))]
    if nonlethal:
        _conditions(entity, add=("Privo di sensi", "A terra", "Stabilizzato"), remove=("Morto",))
        entity["death_saves"] = {"successes": 0, "failures": 0}
        entity["stable"] = True
        return "knocked_out"
    massive = max(0, damage - previous_hp) >= entity["max_hp"]
    use_saves = pc or (entity.get("death_saves_allowed", False) if allow_death_saves is None else allow_death_saves)
    entity["stable"] = False
    entity["death_saves"] = {"successes": 0, "failures": 0}
    if massive or not use_saves:
        _conditions(entity, add=("Morto", "A terra"), remove=("Stabilizzato", "Privo di sensi"))
        return "dead"
    _conditions(entity, add=("Privo di sensi", "A terra"), remove=("Morto", "Stabilizzato"))
    return "death_saves"


def _apply_attack(state, private, actor, target, target_pc, profile, *, mode, melee,
                  nonlethal, death_saves=None):
    """Resolve one already validated attack inside the caller's transaction."""
    actor_name, target_name = _public_name(state, actor), _public_name(state, target)
    attack = roll_dice(f"1d20{profile['bonus']:+d}", f"{actor_name}: {profile['name']} contro {target_name}"[:120], mode)
    critical = attack["kept"][0] == 20
    hit = attack["kept"][0] != 1 and (critical or attack["total"] >= target["ac"])
    rolls, damage, outcome = [attack], 0, "miss"
    concentrating = target.get("concentration") or target.get("concentrating") or any(
        value.casefold().startswith(("concentrazione", "concentration")) for value in target.get("conditions", []))
    if hit:
        outcome = "hit"
        if "fixed_damage" in profile:
            damage = profile["fixed_damage"]
        else:
            count, sides, bonus, _ = parse_dice(profile["damage"])
            rolled_damage = roll_dice(f"{count * (2 if critical else 1)}d{sides}{bonus:+d}",
                                      f"{actor_name}: danni {profile['name']}"[:120])
            rolls.append(rolled_damage)
            damage = max(0, rolled_damage["total"])
        previous_hp, temporary = target["hp"], target.get("temporary_hp", 0)
        absorbed = min(temporary, damage)
        if temporary:
            target["temporary_hp"] = temporary - absorbed
        hp_damage = damage - absorbed
        target["hp"] = max(0, previous_hp - hp_damage)
        if target["hp"] == 0:
            zero = {"pending": melee and nonlethal is None, "attacker_id": actor["id"],
                    "damage": hp_damage, "previous_hp": previous_hp, "nonlethal": nonlethal}
            target["zero_hp_resolution"] = zero
            if zero["pending"]:
                outcome = "nonlethal_choice"
                _conditions(target, add=("A terra",))
                private["pending_resolution"] = {"type": "melee_nonlethal_choice", "actor_id": actor["id"],
                    "target_id": target["id"], "attack": profile["name"], "damage": hp_damage,
                    "previous_hp": previous_hp, "roll_ids": [roll["id"] for roll in rolls]}
            else:
                outcome = _zero(target, target_pc, bool(nonlethal), damage=hp_damage,
                                previous_hp=previous_hp, allow_death_saves=death_saves)
        elif damage > 0 and concentrating:
            outcome = "concentration_save"
            private["pending_resolution"] = {"type": "concentration_save", "actor_id": target["id"],
                "dc": max(10, damage // 2), "roll_ids": [roll["id"] for roll in rolls]}
        _sync(state, target, target_pc)
    state["rolls"] = (state["rolls"] + rolls)[-MAX_ROLLS:]
    return {"attack": attack, "hit": hit, "critical": critical, "damage": damage,
            "outcome": outcome, "rolls": rolls}


class ActionEngine:
    def __init__(self, root: str | Path):
        from tools.session_ops import SessionOps
        self.ops = SessionOps(root)

    def resolve_npc_multiattack(self, spec: dict, request_id: str, expected_revision: int) -> dict:
        """One declared, source-checked NPC action; never decide PC reactions.

        Only sequences with no applicable reactive defence may be batched. A
        concentration window or zero HP closes the sequence permanently: any
        remaining attacks are recorded as unrolled, never retried or retargeted.
        """
        from tools.npc_profiles import NPC_MULTIATTACK_PROFILES
        started = perf_counter()
        require(isinstance(spec, dict) and set(spec) <= {
            "actor", "profile", "source", "targets", "modes", "nonlethal",
            "positions_checked", "reactions_checked", "modifiers_checked"},
            "Campi Multiattacco PNG non riconosciuti.")
        require(isinstance(spec.get("profile"), str) and spec["profile"] in NPC_MULTIATTACK_PROFILES,
                "Profilo PNG non verificato: prepara prima una voce da fonte, senza inventare classi o livelli.")
        profile = copy.deepcopy(NPC_MULTIATTACK_PROFILES[spec["profile"]])
        require(spec.get("source") == profile["source"], "La fonte dichiarata non coincide con il profilo verificato.")
        require(type(spec.get("nonlethal")) is bool, "Il DM deve dichiarare nonlethal=true/false prima dei tiri.")
        for key in ("positions_checked", "reactions_checked", "modifiers_checked"):
            require(spec.get(key) is True, f"Prima verifica {key}: il comando non arbitra distanze o finestre di reazione.")
        attacks = profile["attacks"]
        targets = spec.get("targets")
        require(isinstance(targets, list) and len(targets) == len(attacks),
                "Dichiara esattamente i bersagli dei colpi previsti dalla fonte, nell'ordine.")
        modes = spec.get("modes", ["normal"] * len(attacks))
        require(isinstance(modes, list) and len(modes) == len(attacks), "Serve una modalità per ogni attacco.")
        for mode in modes:
            parse_dice("1d20", mode)
        for attack in attacks:
            require(attack.get("melee") is True, "Questo percorso supporta soltanto il Multiattacco in mischia verificato.")
            integer(attack.get("bonus"), "bonus attacco PNG", -100, 100)
            count, sides, bonus, _ = parse_dice(attack.get("damage"))
            parse_dice(f"{count * 2}d{sides}{bonus:+d}")

        def apply(state, private):
            actor, actor_pc = _lookup(state, private, spec.get("actor"))
            _turn(state, private, actor)
            require(not actor_pc and actor["id"] == profile["actor_id"], "Il profilo appartiene a un PNG diverso; non concede attacchi ai PG.")
            actor_name = _public_name(state, actor)
            require(actor.get("hp", 0) > 0, "Il PNG a zero PF non può attaccare.")
            incapacitated = {"incapacitato", "incapacitated", "stordito", "stunned", "paralizzato", "paralyzed",
                             "pietrificato", "petrified", "privo di sensi", "incosciente", "unconscious", "morto", "dead"}
            require(not incapacitated.intersection(c.casefold() for c in actor.get("conditions", [])),
                    "La condizione del PNG gli impedisce di usare questa azione.")
            require(actor.get("weapon_drawn") is True and isinstance(actor.get("wielded_weapon"), str)
                    and actor["wielded_weapon"].casefold() in profile["weapon_names"],
                    "Estrai e registra prima l'arma impugnata; il comando non compie interazioni con oggetti.")
            usage = _usage(state, private, actor)
            require(not usage.get("action_used"), "L'azione del PNG è già stata usata; non concede attacchi aggiuntivi.")
            declared = []
            # Validate *every* declared target before drawing the first die.
            for reference in targets:
                target, pc = _lookup(state, private, reference)
                _public_name(state, target)
                require(target["id"] != actor["id"], "Il PNG non può attaccare sé stesso con questo comando.")
                integer(target.get("max_hp"), "PF massimi bersaglio", 1, 1000)
                integer(target.get("hp"), "PF bersaglio", 1, target["max_hp"])
                integer(target.get("ac"), "CA bersaglio", 1, 40)
                integer(target.get("temporary_hp", 0), "PF temporanei bersaglio", 0, 100000)
                require(not any(target.get(key) for key in ("resistances", "immunities", "damage_resistances",
                            "damage_immunities", "vulnerabilities", "damage_vulnerabilities")),
                        "Difese ai danni presenti: risolvi individualmente con il DM prima dei tiri.")
                declared.append((target, pc))
            # A known reactive defence must never be bypassed with a generic
            # checked flag. Reactions of allies can matter too (Protection).
            for creature in list(state["party"]) + list(private.get("creatures", [])):
                if creature["id"] == actor["id"] or private.get("reactions_available", {}).get(creature["id"]) is False:
                    continue
                spells = creature.get("spells") or {}
                spell_names = [name.casefold() for key in ("prepared", "known") for name in spells.get(key, [])] if isinstance(spells, dict) else []
                feature_text = " ".join(str(value) for value in creature.get("features", [])).casefold()
                known = creature.get("reaction") or creature.get("reactions") or any(
                    name in {"scudo", "shield", "rimprovero infernale", "hellish rebuke"} for name in spell_names) or any(
                    word in feature_text for word in ("reazione", "reaction", "schivata prodigiosa", "uncanny dodge", "parata", "parry"))
                require(not known, "Reazione disponibile registrata: usa attacchi individuali e risolvi ogni finestra; non scegliere per il PG.")
            results, rolls, public_lines, pending = [], [], [], []
            stop_reason = None
            for index, ((target, pc), attack, mode) in enumerate(zip(declared, attacks, modes)):
                result = _apply_attack(state, private, actor, target, pc, attack,
                                       mode=mode, melee=True, nonlethal=spec["nonlethal"])
                rolls.extend(result["rolls"])
                results.append({"index": index, "target_id": target["id"], "target_name": _public_name(state, target),
                                "attack_name": attack["name"], **result})
                text = f"{actor_name}: {attack['name']} contro {_public_name(state, target)}; tiro {result['attack']['total']}, "
                public_lines.append(text + (f"colpisce per {result['damage']} danni." if result["hit"] else "manca."))
                if result["outcome"] == "concentration_save":
                    pending = [f"{_public_name(state, target)}: TS Costituzione CD {private['pending_resolution']['dc']} per la concentrazione."]
                    stop_reason = "concentration_save"
                elif target["hp"] == 0:
                    stop_reason = "target_zero_hp"
                if stop_reason:
                    break
            unrolled = [{"index": index, "target_id": target["id"], "attack_name": attacks[index]["name"]}
                        for index, (target, _) in enumerate(declared) if index >= len(results)]
            usage.update({"action_used": True, "action_kind": "npc_multiattack", "action_attack_count": len(results),
                          "martial_arts_eligible": False, "multiattack_profile": spec["profile"],
                          "unrolled_attacks": copy.deepcopy(unrolled), "multiattack_stop_reason": stop_reason})
            private["turn_usage"] = usage
            _write_context(state, private)
            if pending:
                public_lines.extend(pending)
            if unrolled:
                public_lines.append("Multiattacco interrotto: i colpi restanti non vengono tirati né assegnati ad altri bersagli.")
            public = " ".join(public_lines)
            state["scene"].update({"title": "Combattimento", "text": public,
                                  "choices": ["Risolvo il tiro salvezza per la concentrazione"] if pending else ["Descrivo la prossima azione"]})
            return {"public": public, "dm": "Profilo di fonte verificato; colpi residui eventualmente rinunciati definitivamente. Nessuna reazione, risorsa, movimento o fine turno automatica.",
                    "actor_id": actor["id"], "profile": spec["profile"], "attacks": results,
                    "unrolled_attacks": unrolled, "stop_reason": stop_reason, "rolls": rolls, "pending": pending,
                    "references": [profile["source"], RULES], "resolution_ms": round((perf_counter() - started) * 1000, 3)}
        result = self.ops.transact("npc_multiattack", spec, request_id, expected_revision, apply)
        return {**result, "tool_elapsed_ms": round((perf_counter() - started) * 1000, 3)}

    def resolve_attack(self, spec: dict, request_id: str, expected_revision: int) -> dict:
        require(isinstance(spec, dict), "Serve un oggetto attacco.")
        require(set(spec) <= {"actor", "target", "attack", "mode", "action", "nonlethal", "melee",
                              "reactions_checked", "modifiers_checked", "martial_arts_eligible", "death_saves"},
                "Campo dell'attacco non riconosciuto.")
        def apply(state, private):
            actor, actor_pc = _lookup(state, private, spec.get("actor"))
            target, target_pc = _lookup(state, private, spec.get("target"))
            _turn(state, private, actor)
            actor_name, target_name = _public_name(state, actor), _public_name(state, target)
            require(actor["id"] != target["id"], "Un attacco contro sé stessi richiede arbitraggio del DM.")
            require(actor.get("hp", 0) > 0 and target.get("hp", 0) > 0,
                    "PF a zero: risolvi prima stabilizzazione, morte o l'eventuale attacco alla creatura inerme.")
            integer(target.get("max_hp"), "PF massimi bersaglio", 1, 1000)
            integer(target.get("hp"), "PF bersaglio", 1, target["max_hp"])
            integer(target.get("ac"), "CA bersaglio", 1, 40)
            integer(target.get("temporary_hp", 0), "PF temporanei bersaglio", 0, 100000)
            nonlethal = spec.get("nonlethal")
            require(nonlethal is None or type(nonlethal) is bool, "nonlethal deve essere true, false o null.")
            require("death_saves" not in spec or type(spec["death_saves"]) is bool, "death_saves deve essere true/false.")
            mode = spec.get("mode", "normal")
            parse_dice("1d20", mode)
            profile, melee, eligible = _attack_profile(actor, spec.get("attack", 0), spec)
            require(nonlethal is not True or melee, "Il KO volontario richiede un attacco in mischia.")
            # These require adjudication; accepting a flag records the DM's
            # prior check, rather than guessing effects from prose descriptions.
            conditions = actor.get("conditions", []) + target.get("conditions", [])
            require(not conditions or spec.get("modifiers_checked") is True,
                    "Condizioni presenti: verifica vantaggio/svantaggio e altri effetti prima dell'attacco.")
            defenses = any(target.get(key) for key in ("resistances", "immunities", "damage_resistances", "damage_immunities", "vulnerabilities"))
            require(not defenses, "Resistenze/immunità richiedono una risoluzione dei danni specifica del DM.")
            reactions = target.get("reaction") or target.get("reactions")
            require(not reactions or spec.get("reactions_checked") is True,
                    "Il bersaglio dispone di una reazione registrata: risolvi esplicitamente la sua finestra prima di proseguire.")
            usage = _usage(state, private, actor)
            action = spec.get("action", "action")
            require(action in {"action", "martial_bonus"}, "Azione supportata: action o martial_bonus.")
            if action == "martial_bonus":
                require(_monk(actor) and _unarmed(profile["name"]), "L'azione bonus marziale richiede un colpo senz'armi da monaco.")
                require(usage.get("martial_arts_eligible") and usage.get("action_used"),
                        "Serve prima l'azione Attaccare con arma da monaco o colpo senz'armi.")
                require(not usage.get("bonus_action_used"), "Azione bonus già usata.")
                usage["bonus_action_used"] = True
            else:
                count = usage.get("action_attack_count", 1 if usage.get("action_used") else 0)
                class_name = _class(actor)
                require(not actor.get("class_levels"), "Multiclasse: verifica esplicitamente il numero di attacchi con il DM.")
                extra = class_name in {"fighter", "guerriero", "monk", "monaco", "barbarian", "barbaro", "paladin", "paladino", "ranger"} and actor.get("level", 1) >= 5
                maximum = 2 if extra else 1
                if class_name in {"fighter", "guerriero"} and actor.get("level", 1) >= 11:
                    maximum = 4 if actor["level"] >= 20 else 3
                require(count < maximum, "Attacchi dell'azione già esauriti; nessuna azione o risorsa extra consumata automaticamente.")
                usage.update({"action_used": True, "action_attack_count": count + 1,
                              "martial_arts_eligible": bool(usage.get("martial_arts_eligible") or eligible)})
            # All preconditions are checked before drawing the first die.
            result = _apply_attack(state, private, actor, target, target_pc, profile,
                                   mode=mode, melee=melee, nonlethal=nonlethal,
                                   death_saves=spec.get("death_saves"))
            attack, hit, critical, damage, outcome, rolls = (
                result[key] for key in ("attack", "hit", "critical", "damage", "outcome", "rolls"))
            private["turn_usage"] = usage
            _write_context(state, private)
            public = f"{actor_name}: {profile['name']} contro {target_name}; tiro {attack['total']}, "
            public += f"colpisce per {damage} danni." if hit else "manca."
            pending = [f"{actor_name}: scegliere KO non letale o colpo letale."] if outcome == "nonlethal_choice" else []
            if outcome == "concentration_save":
                pending = [f"{target_name}: tiro salvezza di Costituzione CD {max(10, damage // 2)} per mantenere la concentrazione."]
                public += " " + pending[0]
            elif pending:
                public += " Scelta del colpo non letale ancora aperta."
            choices = ["Scelgo un colpo non letale", "Colpisco per uccidere"] if outcome == "nonlethal_choice" else ["Descrivo la prossima azione"]
            if outcome == "concentration_save":
                choices = ["Risolvo il tiro salvezza per la concentrazione"]
            state["scene"].update({"title": "Combattimento", "text": public,
                                  "choices": choices})
            return {"public": public, "dm": f"CA verificata nel registro privato; esito {outcome}. Nessun bottino o azione altrui assegnati.",
                    "actor_id": actor["id"], "target_id": target["id"], "hit": hit, "critical": critical,
                    "damage": damage, "outcome": outcome, "rolls": rolls, "pending": pending, "references": [RULES]}
        return self.ops.transact("attack", spec, request_id, expected_revision, apply)

    def resolve_zero_hp(self, spec: dict, request_id: str, expected_revision: int) -> dict:
        require(isinstance(spec, dict) and set(spec) <= {"target", "nonlethal", "death_saves"}, "Campi KO non riconosciuti.")
        require(type(spec.get("nonlethal")) is bool, "La scelta nonlethal deve essere esplicita (true/false).")
        require("death_saves" not in spec or type(spec["death_saves"]) is bool, "death_saves deve essere true/false.")
        def apply(state, private):
            pending = private.get("pending_resolution", {})
            require(pending.get("type") == "melee_nonlethal_choice", "Non c'è una scelta di colpo in mischia da risolvere.")
            target, pc = _lookup(state, private, spec.get("target"))
            require(target["id"] == pending.get("target_id") and target["hp"] == 0, "Bersaglio diverso dalla scelta pendente.")
            actor, _ = _lookup(state, private, pending["actor_id"])
            _turn(state, private, actor, allow_pending=True)
            actor_name, target_name = _public_name(state, actor), _public_name(state, target)
            zero = target.get("zero_hp_resolution", {})
            damage = pending.get("damage", zero.get("damage"))
            previous_hp = pending.get("previous_hp", zero.get("previous_hp"))
            require(type(damage) is int and type(previous_hp) is int, "Mancano i danni originali: non tirare di nuovo, riconcilia il registro.")
            outcome = _zero(target, pc, spec["nonlethal"], damage=damage, previous_hp=previous_hp,
                            allow_death_saves=spec.get("death_saves"))
            zero.update({"pending": False, "nonlethal": spec["nonlethal"], "outcome": outcome})
            target["zero_hp_resolution"] = zero
            del private["pending_resolution"]
            _sync(state, target, pc)
            _write_context(state, private)
            text = {"knocked_out": "è privo di sensi ma stabile", "dead": "muore", "death_saves": "è privo di sensi e deve effettuare i tiri salvezza contro morte"}[outcome]
            public = f"{actor_name} conclude il colpo: {target_name} {text}."
            state["scene"].update({"title": "Combattimento", "text": public, "choices": ["Concludo il turno", "Descrivo un'altra azione consentita"]})
            tutorial = state["flags"].get("tutorial", {})
            if tutorial.get("active") is False and "awaiting" in tutorial:
                tutorial["awaiting"] = f"Turno di {actor_name}; scelta non letale risolta, nessun turno successivo ancora giocato."
            return {"public": public, "dm": f"Scelta risolta senza nuovi dadi; esito {outcome}. Nessun furto automatico.",
                    "target_id": target["id"], "outcome": outcome, "rolls": [], "pending": [], "references": [RULES]}
        return self.ops.transact("knockout", spec, request_id, expected_revision, apply)

    def advance_turn(self, spec: dict, request_id: str, expected_revision: int) -> dict:
        require(isinstance(spec, dict) and set(spec) <= {"actor"}, "Campi avanzamento turno non riconosciuti.")
        def apply(state, private):
            combat = state["combat"]
            require(combat["active"] and combat["participants"], "Nessun combattimento attivo.")
            current_id = combat["participants"][combat["turn_index"]]["id"]
            actor, pc = _lookup(state, private, spec.get("actor", current_id))
            _turn(state, private, actor)
            require(not private.get("timers"), "Scadenze registrate: il DM deve risolverle prima di avanzare automaticamente.")
            names = {value.casefold() for value in actor.get("conditions", [])}
            stable = actor.get("stable") or bool(names & {"stabile", "stabilizzato", "stable"})
            dead = bool(names & {"morto", "dead"})
            marker = {"actor_id": actor["id"], "round": combat["round"], "turn_index": combat["turn_index"]}
            save_resolved = private.get("death_save_turn") == marker
            require(not (pc and actor["hp"] == 0 and not stable and not dead and not save_resolved),
                    "Prima risolvi il tiro salvezza contro morte del PG di turno.")
            combat["turn_index"] = (combat["turn_index"] + 1) % len(combat["participants"])
            if combat["turn_index"] == 0:
                combat["round"] += 1
                private["elapsed_seconds"] = private.get("elapsed_seconds", 0) + 6
                seconds = private.get("round_clock_remainder_seconds", 0) + 6
                minutes, private["round_clock_remainder_seconds"] = divmod(seconds, 60)
                if minutes:
                    hour, minute = map(int, state["clock"]["time"].split(":"))
                    days, minute_of_day = divmod(hour * 60 + minute + minutes, 1440)
                    state["clock"]["day"] += days
                    state["clock"]["time"] = f"{minute_of_day // 60:02d}:{minute_of_day % 60:02d}"
            private.pop("death_save_turn", None)
            next_actor = combat["participants"][combat["turn_index"]]
            private["turn_usage"] = {"actor_id": next_actor["id"], "action_used": False, "bonus_action_used": False}
            private.setdefault("reactions_available", {})[next_actor["id"]] = True
            _write_context(state, private)
            public = f"Round {combat['round']}: tocca a {next_actor['name']}."
            state["scene"].update({"title": "Combattimento", "text": public, "choices": ["Descrivo la mia azione"]})
            if state["flags"].get("tutorial", {}).get("active") is False:
                state["flags"]["tutorial"]["awaiting"] = public
            return {"public": public, "dm": "Solo passaggio d'iniziativa: nessuna azione di PG o PNG inventata.",
                    "round": combat["round"], "turn_index": combat["turn_index"], "actor_id": next_actor["id"],
                    "rolls": [], "pending": [], "references": [RULES]}
        return self.ops.transact("next", spec, request_id, expected_revision, apply)
