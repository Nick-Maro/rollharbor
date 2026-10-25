"""Private, transactional 2014 spell and contest helpers; never a web API.

The JSON plan records the DM's checks and the players' actual decisions.  A
missing check fails before dice.  Only ordinary, source-verified cases run;
reactions, special defences and invented player choices are never inferred.
"""
from __future__ import annotations

import copy
from time import perf_counter
import unicodedata

from engine import MAX_ROLLS, integer, parse_dice, require, roll_dice
from tools.action_engine import _turn, _usage, _write_context
from tools.session_ops import (SessionOps, add_condition, entity, ensure_no_pending,
                               public_name, remove_conditions)

SPELLS = {
    "healing-word": {"names": ["Parola Guaritrice", "Healing Word"], "page": 153,
                     "action": "bonus_action_used", "sides": 4, "range_m": 18},
    "cure-wounds": {"names": ["Cura Ferite", "Cure Wounds"], "page": 132,
                    "action": "action_used", "sides": 8, "range_m": 1.5},
    "entangle": {"names": ["Intralciare", "Entangle"], "page": 140,
                 "action": "action_used", "range_m": 27},
}
INCAPACITATED = {"morto", "dead", "privo di sensi", "unconscious", "incosciente",
                "incapacitato", "incapacitated", "paralizzato", "paralyzed", "stordito", "stunned"}


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold().split("·")[0].strip())
                   if not unicodedata.combining(c))


def checked(spec, *names):
    checks = spec.get("checks", {})
    require(isinstance(checks, dict), "checks deve contenere le verifiche esplicite del DM.")
    for name in names:
        require(checks.get(name) is True, f"Verifica DM mancante: checks.{name}=true; non e una scelta automatica.")


def able(actor):
    require(actor.get("hp", 0) > 0 and not INCAPACITATED & {x.casefold() for x in actor.get("conditions", [])},
            "Il personaggio non puo agire: PF o condizione incapacitante.")


def statistic(actor, skill):
    abilities = actor.get("abilities", {})
    key = "str" if skill == "athletics" else "dex"
    if skill in actor.get("skills", {}):
        return integer(actor["skills"][skill], "bonus abilita", -30, 40)
    require(key in abilities, "Manca la caratteristica verificata: completare prima la scheda privata.")
    return (integer(abilities[key], key, 1, 30) - 10) // 2


def invalidate_position(state, target_id):
    """A resolved push must not leave an apparently confirmed old map pin."""
    flags = state.get("flags", {})
    table = flags.get("table_scene", {})
    boards = [flags.get("tactical_scene", {}), table.get("tactical", {})]
    for board in boards:
        for token in board.get("tokens", []):
            if token.get("entity_id", token.get("id")) == target_id:
                token["confirmed"] = False
    if "distances" in table:
        table["distances"] = [pair for pair in table["distances"] if target_id not in (pair.get("a"), pair.get("b"))]


def fiction_seconds(state, combat):
    hour, minute = map(int, state["clock"]["time"].split(":"))
    return (state["clock"]["day"] * 86400 + hour * 3600 + minute * 60 +
            combat.get("round_clock_remainder_seconds", 0))


def _effect_cleanup(state, combat):
    """Reconcile only effects owned by this module, preserving other sources."""
    effects = combat.get("spell_effects", [])
    remaining, ended, ended_effects = [], [], []
    participants = state["combat"]["participants"]
    current_id = participants[state["combat"]["turn_index"]]["id"] if participants else None
    all_entities = state["party"] + combat.get("creatures", [])
    by_id = {x["id"]: x for x in all_entities}
    for effect in effects:
        if effect.get("manager") != "action_toolkit":
            remaining.append(effect)
            continue
        caster = by_id.get(effect["caster_id"])
        concentration = caster.get("concentration") if caster is not None else None
        same_concentration = isinstance(concentration, dict) and concentration.get("effect_id") == effect["id"]
        expired = (state["combat"]["round"] > effect["expires_round"] or
                   (state["combat"]["round"] == effect["expires_round"] and current_id == effect["caster_id"]))
        if not state["combat"]["active"] or effect.get("combat_marker") != combat.get("id"):
            expired = fiction_seconds(state, combat) >= effect.get("expires_fiction_seconds", 10**15)
        if not same_concentration or expired or caster.get("hp", 0) == 0 or INCAPACITATED & {
                x.casefold() for x in caster.get("conditions", [])}:
            ended.append(effect["id"])
            ended_effects.append(effect)
            if same_concentration:
                caster.pop("concentration", None)
        else:
            remaining.append(effect)
    # Preserve ownership while another tracked source remains, including an
    # imported overlapping spell; transfer ownership so the last source clears.
    owned = {ident for effect in effects for ident in effect.get("condition_added_ids", [])}
    released = {ident for effect in ended_effects for ident in effect.get("restrained_ids", [])}
    for ident in released & owned:
        sources = [e for e in remaining if ident in e.get("restrained_ids", [])]
        if sources:
            if ident not in sources[0].get("condition_added_ids", []):
                sources[0].setdefault("condition_added_ids", []).append(ident)
        elif ident in by_id:
            remove_conditions(by_id[ident], {"trattenuto", "restrained"})
    if effects:
        combat["spell_effects"] = remaining
        managed_ids = {e["id"] for e in effects if e.get("manager") == "action_toolkit"}
        public = [e for e in state["flags"].get("effects", []) if e.get("id") not in managed_ids]
        public.extend({"id": e["id"], "name": "Intralciare", "caster_id": e["caster_id"],
                       "concentration": True, "duration_rounds": 10,
                       "remaining_rounds": max(0, e["expires_round"] - state["combat"]["round"]),
                       "remaining_seconds": max(0, e.get("expires_fiction_seconds", fiction_seconds(state, combat)) - fiction_seconds(state, combat)),
                       "expires_round": e["expires_round"], "expires_actor_id": e["caster_id"],
                       "target_ids": e["restrained_ids"], "area": e["area"], "difficult_terrain": True}
                      for e in remaining if e.get("manager") == "action_toolkit")
        state["flags"]["effects"] = public
    return ended


class ToolkitOps(SessionOps):
    """Keep effects coherent in the *same* normal SessionOps transaction.

    play.py uses this adapter also for next/check/damage/attack.  It neither
    advances time nor spends resources unless the original operation does.
    """
    def transact(self, kind, spec, request_id, expected_revision, callback):
        start, phases = perf_counter(), {}
        def wrapped(state, combat):
            before = perf_counter()
            phases["read_validate"] = (before - start) * 1000
            ended = _effect_cleanup(state, combat)
            if kind == "attack" and spec.get("action", "action") == "action":
                usage = combat.get("turn_usage", {})
                acting, _ = entity(state, combat, spec.get("actor"))
                require(not (usage.get("actor_id") == acting["id"] and usage.get("action_used") and
                             usage.get("action_kind") in {"cast_spell", "escape"}),
                        "L'azione e stata usata per magia/fuga, non per Attaccare.")
            result = callback(state, combat)
            ended.extend(_effect_cleanup(state, combat))
            if ended:
                result["effects_ended"] = sorted(set(ended))
                result["public"] = (result.get("public", "") + " Intralciare termina.").strip()
            phases["resolve"] = (perf_counter() - before) * 1000
            phases["after_callback"] = perf_counter()
            return result
        result = super().transact(kind, spec, request_id, expected_revision, wrapped)
        finish = perf_counter()
        # These are measured intervals, not estimates of model or network time.
        if "after_callback" in phases:
            timings = {"read_validate": phases["read_validate"], "resolve": phases["resolve"],
                       "validate_persist": (finish - phases["after_callback"]) * 1000,
                       "total": (finish - start) * 1000}
        else:
            timings = {"replay_total": (finish - start) * 1000}
        result["timings_ms"] = {k: round(v, 3) for k, v in timings.items()}
        return result


class ActionToolkit:
    def __init__(self, root):
        self.ops = ToolkitOps(root)

    @staticmethod
    def _spell_preflight(state, combat, spec):
        ensure_no_pending(state, combat)
        spell = spec.get("spell")
        require(spell in SPELLS, "Incantesimo non supportato: usare un piano specifico verificato.")
        profile = SPELLS[spell]
        actor, pc = entity(state, combat, spec.get("actor"))
        require(pc, "Questo percorso supporta gli incantatori PG con scheda completa.")
        _turn(state, combat, actor)
        able(actor)
        checked(spec, "declared", "components", "reactions", "modifiers", "bonus_spell_rule", "range")
        spells = actor.get("spells", {})
        names = spells.get("prepared", []) if actor.get("class_id", "").casefold() in {
            "cleric", "druid", "wizard"} or spells.get("prepared") else spells.get("known", [])
        aliases = {normalized(n) for n in profile["names"]}
        require(any(normalized(n) in aliases for n in names), "Incantesimo non preparato/conosciuto nella scheda.")
        ability = spells.get("ability")
        require(ability in actor.get("abilities", {}), "Caratteristica da incantatore assente.")
        modifier = (actor["abilities"][ability] - 10) // 2
        require(not (actor.get("class_id") == "cleric" and actor.get("level", 1) >= 6),
                "Chierico avanzato: Guaritore Benedetto/Guarigione Suprema richiedono il percorso specifico.")
        level = integer(spec.get("slot_level", 1), "slot_level", 1, 9)
        resource_id = spec.get("resource", f"spell_slot_{level}")
        require(resource_id in {f"spell_slot_{level}", f"pact_slot_{level}"}, "Lo slot deve corrispondere al livello dichiarato.")
        resource = next((r for r in actor.get("resources", []) if r["id"] == resource_id), None)
        require(resource is not None and resource["current"] > 0, "Slot esaurito o non presente.")
        usage = _usage(state, combat, actor)
        require(not usage.get(profile["action"]), "Azione richiesta gia usata in questo turno.")
        require(not usage.get("bonus_spell_cast"), "Dopo una magia bonus il turno consente solo trucchetti da un'azione.")
        if spell == "healing-word":
            require(not usage.get("leveled_spell_cast"), "Magia di livello gia lanciata: Parola Guaritrice non consentita in questo turno.")
        distance = spec.get("distance_m")
        require(type(distance) in (int, float) and 0 <= distance <= profile["range_m"], "Distanza mancante o fuori portata.")
        return actor, profile, resource, modifier, level, usage

    def heal_spell(self, spec, request_id, expected_revision):
        def apply(state, combat):
            actor, profile, resource, modifier, level, usage = self._spell_preflight(state, combat, spec)
            require(spec["spell"] in {"healing-word", "cure-wounds"}, "Usare entangle per Intralciare.")
            checked(spec, "target_type")
            target, _ = entity(state, combat, spec.get("target"))
            require(not {"morto", "dead"} & {v.casefold() for v in target.get("conditions", [])}, "La cura non resuscita.")
            require(normalized(target.get("creature_type", "")) not in {"undead", "non morto", "construct", "costrutto"},
                    "Questa cura non ha effetto su non morti o costrutti.")
            if spec["spell"] == "healing-word":
                checked(spec, "visibility")
            rolled = roll_dice(f"{level}d{profile['sides']}{modifier:+d}",
                               f"{public_name(state, actor)}: {profile['names'][0]}"[:120])
            features = " ".join(str(v) for v in actor.get("features", []))
            disciple = "discepolo della vita" in normalized(features) or "disciple of life" in normalized(features)
            amount = max(0, rolled["total"] + (2 + level if disciple else 0))
            result = (SessionOps._heal(state, combat, {"target": target["id"], "amount": amount}) if amount else
                      {"public": f"{public_name(state, target)} non recupera PF.", "target_id": target["id"], "healed": 0})
            resource["current"] -= 1
            usage[profile["action"]] = True
            usage["leveled_spell_cast"] = spec["spell"]
            if spec["spell"] == "healing-word":
                usage["bonus_spell_cast"] = True
            else:
                usage.update(action_kind="cast_spell", martial_arts_eligible=False)
            combat["turn_usage"] = usage
            _write_context(state, combat)
            state["rolls"].append(rolled)
            result.update(actor_id=actor["id"], spell=spec["spell"], slot_level=level, rolls=[rolled],
                          dm="Magia dichiarata dal giocatore; componenti, reazioni, tipo e portata verificati dal DM.",
                          references=[f"SRD 5.1 (2014), p. {profile['page']}"])
            result["public"] = f"{public_name(state, actor)} lancia {profile['names'][0]}. " + result["public"]
            return result
        return self.ops.transact("heal-spell", spec, request_id, expected_revision, apply)

    def contest(self, spec, request_id, expected_revision):
        def apply(state, combat):
            ensure_no_pending(state, combat)
            actor, _ = entity(state, combat, spec.get("actor"))
            target, _ = entity(state, combat, spec.get("target"))
            require(actor["id"] != target["id"], "Serve un altro partecipante.")
            _turn(state, combat, actor)
            able(actor)
            checked(spec, "declared", "range", "modifiers", "reactions", "defense_choice")
            kind = spec.get("kind")
            require(kind in {"grapple", "shove-prone", "shove-away", "escape"}, "Contesa non supportata.")
            skill = spec.get("actor_skill", "athletics")
            defense = spec.get("defense")
            require(skill in {"athletics", "acrobatics"} and defense in {"athletics", "acrobatics"}, "Scegli Athletics o Acrobatics esplicitamente.")
            if kind != "escape":
                require(skill == "athletics", "Presa e spinta usano Forza (Atletica).")
                checked(spec, "size")
                if kind == "grapple":
                    checked(spec, "free_hand")
                    require(not combat.get("grapples", {}).get(target["id"]),
                            "Presa multipla: usare il DM; non sovrascrivere un altro legame.")
                require(target.get("hp", 0) > 0 and not INCAPACITATED & {v.casefold() for v in target.get("conditions", [])},
                        "Bersaglio incapacitato: risolvere con il DM senza contesa automatica.")
                require(type(spec.get("distance_m")) in (int, float) and 0 <= spec["distance_m"] <= 1.5,
                        "Questo profilo supporta portata normale di 1,5 metri.")
            else:
                require(defense == "athletics", "Chi mantiene la presa usa Atletica.")
                link = combat.get("grapples", {}).get(actor["id"])
                require(isinstance(link, dict) and link.get("grappler_id", link.get("source_id")) == target["id"],
                        "Presa strutturata assente o mantenuta da un'altra creatura.")
            bonus_actor, bonus_target = statistic(actor, skill), statistic(target, defense)
            usage = _usage(state, combat, actor)
            # This prepared path intentionally supports one-attack actions only.
            require(not usage.get("action_used"), "Azione gia usata; gli attacchi extra richiedono arbitraggio separato.")
            require(kind == "escape" or (not actor.get("class_levels") and actor.get("level", 1) < 5),
                    "Attacchi Extra/multiclasse: usare il percorso specifico, senza perdere attacchi.")
            if kind == "shove-away":
                checked(spec, "destination")
                require(isinstance(spec.get("destination"), str) and spec["destination"].strip(), "Descrivi la destinazione verificata a 1,5 m.")
                require(isinstance(spec.get("broken_grapples", []), list), "broken_grapples deve essere una lista di ID gia verificati.")
                for ident in spec.get("broken_grapples", []):
                    affected, _ = entity(state, combat, ident)
                    link = combat.get("grapples", {}).get(affected["id"])
                    require(isinstance(link, dict) and (affected["id"] == target["id"] or link.get("grappler_id", link.get("source_id")) == target["id"]),
                            "Presa da interrompere non associata al bersaglio spostato.")
            rolls = []
            for who, bonus, mode in [(actor, bonus_actor, spec.get("actor_mode", "normal")),
                                     (target, bonus_target, spec.get("defense_mode", "normal"))]:
                parse_dice("1d20", mode)
            for who, bonus, mode in [(actor, bonus_actor, spec.get("actor_mode", "normal")),
                                     (target, bonus_target, spec.get("defense_mode", "normal"))]:
                rolls.append(roll_dice(f"1d20{bonus:+d}", f"{public_name(state, who)}: {kind}"[:120], mode))
            success = rolls[0]["total"] > rolls[1]["total"]
            if success:
                grapples = combat.setdefault("grapples", {})
                if kind == "grapple":
                    add_condition(target, "Afferrato")
                    grapples[target["id"]] = {"grappler_id": actor["id"], "reach_m": 1.5, "speed_m": 0}
                elif kind == "escape":
                    grapples[actor["id"]] = None
                    remove_conditions(actor, {"afferrato", "grappled"})
                elif kind == "shove-prone":
                    add_condition(target, "A terra")
                else:
                    combat.setdefault("position_notes", {})[target["id"]] = spec["destination"]
                    invalidate_position(state, target["id"])
                    for ident in spec.get("broken_grapples", []):
                        affected, _ = entity(state, combat, ident)
                        grapples[affected["id"]] = None
                        remove_conditions(affected, {"afferrato", "grappled"})
            usage.update(action_used=True, action_kind="escape" if kind == "escape" else "attack",
                         martial_arts_eligible=False)
            if kind != "escape":
                usage["action_attack_count"] = 1
            combat["turn_usage"] = usage
            _write_context(state, combat)
            state["rolls"] = (state["rolls"] + rolls)[-MAX_ROLLS:]
            return {"public": f"{public_name(state, actor)}: {kind}, {rolls[0]['total']} contro {rolls[1]['total']}; " +
                              ("riesce." if success else "non riesce. La parita conserva la situazione."),
                    "actor_id": actor["id"], "target_id": target["id"], "success": success, "rolls": rolls,
                    "dm": "Difesa scelta esplicitamente; nessun consumo di reazioni, movimento o altre risorse.",
                    "references": ["SRD 5.1 (2014), pp. 95-96"]}
        return self.ops.transact("contest", spec, request_id, expected_revision, apply)

    def entangle(self, spec, request_id, expected_revision):
        def apply(state, combat):
            actor, profile, resource, modifier, level, usage = self._spell_preflight(state, combat, spec)
            require(spec["spell"] == "entangle", "Questo comando prepara Intralciare.")
            checked(spec, "area", "all_creatures", "concentration_choice")
            require(not actor.get("concentration") and not actor.get("concentrating") and not any(
                "concentrazione" in c.casefold() or "concentration" in c.casefold() for c in actor.get("conditions", [])),
                "Terminare esplicitamente la concentrazione precedente prima di questo comando.")
            area = spec.get("area")
            require(isinstance(area, dict) and isinstance(area.get("description"), str) and area["description"].strip() and
                    area.get("side_m") == 6, "Area pubblica: description e side_m=6, quadrato sul terreno.")
            targets = spec.get("targets")
            require(isinstance(targets, list) and len(targets) <= 40, "Elencare tutte le creature nell'area, anche alleate.")
            dc = integer(actor.get("spells", {}).get("dc"), "CD incantesimo", 1, 40)
            planned, ids = [], set()
            for item in targets:
                require(isinstance(item, dict), "Profilo bersaglio non valido.")
                target, target_pc = entity(state, combat, item.get("target"))
                require(target["id"] not in ids, "Bersaglio duplicato nell'area.")
                ids.add(target["id"])
                require(not {"trattenuto", "restrained"} & {c.casefold() for c in target.get("conditions", [])},
                        "Bersaglio gia trattenuto da altra fonte: serve arbitraggio esplicito per non perdere quel legame.")
                require(not any(target.get(k) for k in ("condition_immunities", "magic_resistance", "legendary_resistance")),
                        "Difese speciali: risolvere i TS singolarmente con il DM.")
                bonus = target.get("saving_throws", {}).get("str")
                if bonus is None:
                    require(not target_pc, "PG senza TS Forza verificato: completare saving_throws prima del tiro; non ignorare competenze di classe.")
                    require("str" in target.get("abilities", {}), "Bonus TS Forza assente dalla scheda verificata.")
                    bonus = (target["abilities"]["str"] - 10) // 2
                mode = item.get("mode", "normal")
                parse_dice("1d20", mode)
                require(not INCAPACITATED & {v.casefold() for v in target.get("conditions", [])},
                        "Creature incapaci con fallimenti automatici: usare il percorso manuale verificato.")
                planned.append((target, integer(bonus, "TS Forza", -30, 40), mode))
            rolls, restrained = [], []
            for target, bonus, mode in planned:
                rolled = roll_dice(f"1d20{bonus:+d}", f"{public_name(state, target)}: TS Forza Intralciare"[:120], mode)
                rolls.append(rolled)
                if rolled["total"] < dc:
                    add_condition(target, "Trattenuto")
                    restrained.append(target["id"])
            effect_id = "entangle_" + request_id
            effect = {"id": effect_id, "manager": "action_toolkit", "spell": "entangle", "caster_id": actor["id"],
                      "dc": dc, "area": copy.deepcopy(area), "restrained_ids": restrained,
                      "condition_added_ids": restrained[:], "expires_round": state["combat"]["round"] + 10,
                      "expires_fiction_seconds": fiction_seconds(state, combat) + 60, "combat_marker": combat.get("id")}
            combat.setdefault("spell_effects", []).append(effect)
            actor["concentration"] = {"spell": "Intralciare", "effect_id": effect_id}
            resource["current"] -= 1
            usage.update(action_used=True, action_kind="cast_spell", leveled_spell_cast="entangle", martial_arts_eligible=False)
            combat["turn_usage"] = usage
            _write_context(state, combat)
            state["rolls"] = (state["rolls"] + rolls)[-MAX_ROLLS:]
            return {"public": f"{public_name(state, actor)} lancia Intralciare: l'area diventa terreno difficile. " +
                              ("Sono trattenuti: " + ", ".join(public_name(state, t) for t, _, _ in planned if t["id"] in restrained) + "." if restrained else "Nessuna creatura resta trattenuta."),
                    "actor_id": actor["id"], "effect_id": effect_id, "dc": dc, "rolls": rolls,
                    "restrained_ids": restrained, "slot_level": level, "references": ["SRD 5.1 (2014), p. 140"],
                    "dm": "Solo TS iniziali; entrare dopo non richiede un TS. Fuga: azione e prova Forza contro CD, non Atletica. Scadenza a inizio turno del lanciatore dopo dieci round."}
        return self.ops.transact("entangle", spec, request_id, expected_revision, apply)

    def effect(self, spec, request_id, expected_revision):
        """Release concentration or make Entangle's action Strength check."""
        def apply(state, combat):
            ensure_no_pending(state, combat)
            actor, _ = entity(state, combat, spec.get("actor"))
            effect = next((e for e in combat.get("spell_effects", []) if e["id"] == spec.get("effect_id") and e.get("manager") == "action_toolkit"), None)
            require(effect is not None, "Effetto gia terminato o non gestito da questo strumento.")
            checked(spec, "declared")
            if spec.get("kind") == "end-concentration":
                require(actor["id"] == effect["caster_id"], "Solo il lanciatore puo interrompere volontariamente la concentrazione.")
                actor.pop("concentration", None)
                return {"public": f"{public_name(state, actor)} interrompe la concentrazione.", "rolls": []}
            require(spec.get("kind") == "escape-entangle", "Scelta effetto non supportata.")
            _turn(state, combat, actor)
            able(actor)
            checked(spec, "modifiers", "reactions")
            require(actor["id"] in effect["restrained_ids"], "Il personaggio non e trattenuto da questo incantesimo.")
            usage = _usage(state, combat, actor)
            require(not usage.get("action_used"), "Azione gia utilizzata.")
            require("str" in actor.get("abilities", {}), "Manca Forza nella scheda.")
            bonus = (actor["abilities"]["str"] - 10) // 2
            rolled = roll_dice(f"1d20{bonus:+d}", f"{public_name(state, actor)}: liberarsi da Intralciare"[:120], spec.get("mode", "normal"))
            success = rolled["total"] >= effect["dc"]
            if success:
                effect["restrained_ids"].remove(actor["id"])
                remove_conditions(actor, {"trattenuto", "restrained"})
            usage.update(action_used=True, action_kind="escape", martial_arts_eligible=False)
            combat["turn_usage"] = usage
            _write_context(state, combat)
            state["rolls"].append(rolled)
            return {"public": f"{public_name(state, actor)}: prova di Forza {rolled['total']}, " +
                              ("si libera dalle piante." if success else "resta trattenuto."), "success": success,
                    "rolls": [rolled], "references": ["SRD 5.1 (2014), p. 140"]}
        return self.ops.transact("effect", spec, request_id, expected_revision, apply)

    def preflight(self, kind, spec):
        """Run full validation on disposable copies, with no dice or writes."""
        from engine import CampaignError
        class StopBeforeDice(Exception):
            pass
        # Capture callbacks by using a local adapter rather than patching RNG.
        captured = {}
        original = self.ops.transact
        def capture(operation, payload, request_id, expected_revision, callback):
            captured.update(callback=callback, operation=operation)
        self.ops.transact = capture
        try:
            {"heal-spell": self.heal_spell, "contest": self.contest, "entangle": self.entangle}[kind](spec, "preflight", 0)
        finally:
            self.ops.transact = original
        # Every resolver completes checks before its first roll.  Patch only
        # this module's roll symbol, in a CLI-only synchronous operation.
        global roll_dice
        real_roll = roll_dice
        def no_roll(*args, **kwargs):
            raise StopBeforeDice()
        start = perf_counter()
        with self.ops.store.locked():
            state = self.ops.store._read()
            from tools.session_ops import private_json
            combat = private_json(self.ops.combat_path, {})
            if self.ops.pending_path.exists():
                return {"ready": False, "reason": "Transazione interrotta: eseguire recover prima del preflight.", "read_only": True}
            roll_dice = no_roll
            try:
                captured["callback"](copy.deepcopy(state), copy.deepcopy(combat))
            except StopBeforeDice:
                return {"ready": True, "read_only": True, "revision": state["revision"], "kind": kind,
                        "preflight_ms": round((perf_counter() - start) * 1000, 3)}
            except CampaignError as exc:
                return {"ready": False, "read_only": True, "revision": state["revision"], "reason": str(exc)}
            finally:
                roll_dice = real_roll
        return {"ready": True, "read_only": True, "revision": state["revision"], "kind": kind}
