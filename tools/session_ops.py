"""Prepared DM operations with one lock and recoverable public/private saves.

The write-ahead file contains already resolved results: recovery never calls the
operation again and therefore never rolls dice again. It is private to the DM.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from engine import (CampaignError, StateStore, MAX_ROLLS, MAX_STATE_BYTES,
                    PATCH_FIELDS, deep_merge, finite_json, identifier, integer,
                    now, require, roll_dice, text_field, validate_state)
from tools.turn_log import TurnLog, _payload


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def private_json(path, default):
    if not path.exists():
        return copy.deepcopy(default)
    with path.open(encoding="utf-8") as source:
        value = json.load(source)
    finite_json(value)
    return value


def entity(state, combat, selector):
    """Select a unique actor without guessing names or creating NPC statistics."""
    text_field(selector, "target", 120)
    choices = [(p, True) for p in state["party"]]
    choices += [(p, False) for p in combat.get("creatures", [])]
    exact = [pair for pair in choices if pair[0].get("id") == selector]
    matches = exact or [pair for pair in choices if pair[0].get("name", "").casefold() == selector.casefold()]
    # Public short names can identify an existing private NPC, never its stats.
    if not matches:
        ids = {p["id"] for p in state["combat"]["participants"]
               if p.get("name", "").casefold() == selector.casefold()}
        matches = [pair for pair in choices if pair[0].get("id") in ids]
    require(len(matches) == 1, "Nome non trovato o ambiguo: usa un ID esatto; i PNG richiedono la scheda privata verificata.")
    if not matches[0][1]:
        public = next((p for p in state["combat"]["participants"] if p["id"] == matches[0][0]["id"]), None)
        require(public is not None, "PNG non manifestato: usa save con private_combat per effetti riservati.")
    return matches[0]


def public_name(state, target):
    participant = next((p for p in state["combat"]["participants"] if p["id"] == target["id"]), None)
    return participant["name"] if participant else target["name"]


def sync(state, combat):
    by_id = {p["id"]: p for p in state["party"]}
    if state.get("active_character_id") in by_id:
        state["character"] = copy.deepcopy(by_id[state["active_character_id"]])
    for participant in state["combat"]["participants"]:
        pc = by_id.get(participant["id"])
        if pc:
            for key in ("hp", "max_hp", "ac"):
                participant[key] = pc[key]
            participant["conditions"] = copy.deepcopy(pc.get("conditions", []))
        else:
            npc = next((p for p in combat.get("creatures", []) if p.get("id") == participant["id"]), None)
            if npc is not None and "conditions" in npc:
                participant["conditions"] = copy.deepcopy(npc["conditions"])
            if npc is not None and "hp" in participant:
                participant["hp"], participant["max_hp"] = npc["hp"], npc["max_hp"]
    state["rolls"] = state["rolls"][-MAX_ROLLS:]


def remove_conditions(target, names):
    target["conditions"] = [v for v in target.get("conditions", []) if v.casefold() not in names]


def add_condition(target, condition):
    if condition.casefold() not in {v.casefold() for v in target.get("conditions", [])}:
        target.setdefault("conditions", []).append(condition)


def ensure_no_pending(state, combat):
    pending = state.get("flags", {}).get("combat_context", {}).get("pending_resolution")
    require(not pending and not combat.get("pending_resolution") and not combat.get("pending_reactions"),
            "Completa prima la scelta o reazione in sospeso; non applicare un nuovo effetto nel mezzo della risoluzione.")


def validate_private(combat):
    require(isinstance(combat, dict), "Registro combattimento privato non valido.")
    finite_json(combat)
    creatures = combat.get("creatures", [])
    require(isinstance(creatures, list), "creatures deve essere una lista privata.")
    ids = set()
    for creature in creatures:
        require(isinstance(creature, dict), "Scheda PNG non valida.")
        ident = identifier(creature.get("id"), "creature.id")
        require(ident not in ids, "ID PNG duplicato.")
        ids.add(ident)
        text_field(creature.get("name"), "creature.name", 120)
        if "hp" in creature or "max_hp" in creature:
            maximum = integer(creature.get("max_hp"), "creature.max_hp", 0, 100000)
            integer(creature.get("hp"), "creature.hp", 0, maximum)
        if "ac" in creature:
            integer(creature["ac"], "creature.ac", 0, 100)


class SessionOps:
    def __init__(self, root):
        self.store = StateStore(root)
        self.root = self.store.root
        self.receipts_path = self.root / "master" / "operations.json"
        self.pending_path = self.root / "master" / "pending-operation.json"
        self.combat_path = self.root / "master" / "COMBATTIMENTO.json"
        self.log = TurnLog(self.root)

    def _recover_locked(self):
        if not self.pending_path.exists():
            return {"recovered": False}
        pending = private_json(self.pending_path, {})
        require(pending.get("schema_version") == 1, "Transazione sospesa non valida.")
        current = self.store._read()
        require(pending.get("campaign_id") == current["campaign_id"], "Transazione di un'altra campagna.")
        target = pending["state"]
        require(pending.get("effects_hash") == digest({key: pending[key] for key in ("combat", "log", "receipts")}),
                "Dati privati della transazione sospesa danneggiati.")
        validate_state(target, self.store.world(), current["campaign_id"])
        require(digest(target) == pending["target_hash"], "Transazione sospesa danneggiata.")
        current_hash = digest(current)
        require(current_hash in (pending["base_hash"], pending["target_hash"]),
                "Il salvataggio diverge dalla transazione sospesa: riconciliare senza sovrascrivere la partita.")
        if current_hash == pending["base_hash"]:
            require(target["revision"] == current["revision"] + 1, "Revisione della transazione non valida.")
            self.store._backup(current)
            self.store._atomic_json(self.store.state_path, target)
        # Fixed destinations only: no path supplied by an operation is executed.
        if pending["combat"] is not None:
            self.store._atomic_json(self.combat_path, pending["combat"])
        self.store._atomic_json(self.log.path, pending["log"])
        self.store._atomic_json(self.receipts_path, pending["receipts"])
        self.pending_path.unlink()
        return {"recovered": True, "id": pending["id"], "revision": target["revision"]}

    def recover(self):
        with self.store.locked():
            return self._recover_locked()

    def transact(self, kind, spec, request_id, expected_revision, callback):
        identifier(request_id, "id")
        integer(expected_revision, "expected_revision", 0, 10**12)
        require(isinstance(spec, dict), "Serve un oggetto di parametri.")
        finite_json(spec)
        request_hash = digest({"kind": kind, "spec": spec})
        with self.store.locked():
            self._recover_locked()
            current = self.store._read()
            receipts = private_json(self.receipts_path, {"schema_version": 1, "campaign_id": current["campaign_id"], "operations": {}})
            require(receipts.get("campaign_id") == current["campaign_id"] and isinstance(receipts.get("operations"), dict),
                    "Registro operazioni non valido o di un'altra campagna.")
            previous = receipts["operations"].get(request_id)
            if previous:
                require(previous["request_hash"] == request_hash, "ID gia usato con un'altra operazione: non ripetere gli effetti.")
                require(previous["response"]["operation_revision"] <= current["revision"],
                        "Registro piu recente del salvataggio: riconciliare il ripristino.")
                return {**copy.deepcopy(previous["response"]), "revision": current["revision"], "already_applied": True}
            if current["revision"] != expected_revision:
                raise CampaignError(f"Revisione attesa {expected_revision}, attuale {current['revision']}: rileggi il contesto.", "revision_conflict", 409)
            state = copy.deepcopy(current)
            combat = private_json(self.combat_path, {})
            before_combat = copy.deepcopy(combat)
            validate_private(combat)
            # Check continuity before any callback draws dice.
            log = self.log._load_locked(current)
            result = callback(state, combat)
            require(isinstance(result, dict), "Esito operazione non valido.")
            finite_json(result)
            public = result.get("public", "")
            if public:
                text_field(public, "public", 6000)
                StateStore.event(state, "Il master racconta", public)
            state["revision"] = current["revision"] + 1
            require(state["campaign_id"] == current["campaign_id"] and state["schema_version"] == current["schema_version"],
                    "L'operazione non puo cambiare campagna o schema.")
            if state["phase"] == "playing":
                state["flags"]["character_creation_locked"] = True
            sync(state, combat)
            validate_private(combat)
            validate_state(state, self.store.world(), current["campaign_id"])
            require(len(json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8")) <= MAX_STATE_BYTES,
                    "Salvataggio pubblico troppo grande.")
            if combat:
                combat["public_revision"] = state["revision"]
            payload = {"id": request_id, "revision": state["revision"],
                       "public": public, "dm": result.get("dm", ""),
                       "roll_ids": [r["id"] if isinstance(r, dict) else r for r in result.get("rolls", [])],
                       "pending": result.get("pending", []), "references": result.get("references", []),
                       "details": {"operation": kind, "parameters": spec}}
            payload, checksum = _payload(payload)
            require(all(e["payload"]["id"] != request_id for e in log["events"] + log["checkpoints"]),
                    "ID gia presente nel diario privato: usa l'ID della richiesta corretta.")
            log["events"].append({"kind": "event", "payload": payload, "digest": checksum, "at": now(),
                                  "captured": {"session": state["session"], "clock": copy.deepcopy(state["clock"])}})
            response = {"revision": state["revision"], "operation_revision": state["revision"],
                        "id": request_id, "already_applied": False, **result}
            receipts["operations"][request_id] = {"request_hash": request_hash, "response": response}
            pending = {"schema_version": 1, "campaign_id": current["campaign_id"], "id": request_id,
                       "base_hash": digest(current), "target_hash": digest(state), "state": state,
                       "combat": combat if combat or before_combat else None, "log": log, "receipts": receipts}
            pending["effects_hash"] = digest({key: pending[key] for key in ("combat", "log", "receipts")})
            self.store._atomic_json(self.pending_path, pending)
            self._recover_locked()
            return response

    def execute(self, kind, payload, expected_revision, request_id):
        handlers = {"heal": self._heal, "damage": self._damage, "resource": self._resource,
                    "condition": self._condition, "check": self._check, "death": self._death, "save": self._save}
        require(kind in handlers, "Operazione non supportata.")
        return self.transact(kind, payload, request_id, expected_revision,
                             lambda state, combat: handlers[kind](state, combat, payload))

    @staticmethod
    def _heal(state, combat, spec):
        ensure_no_pending(state, combat)
        amount = integer(spec.get("amount"), "amount", 1, 100000)
        target, _ = entity(state, combat, spec.get("target"))
        require(not {"morto", "dead"} & {c.casefold() for c in target.get("conditions", [])}, "Una cura non resuscita un morto.")
        old = target["hp"]
        target["hp"] = min(target["max_hp"], old + amount)
        if target["hp"] > 0:
            remove_conditions(target, {"incosciente", "privo di sensi", "unconscious", "stabile", "stable", "stabilizzato"})
            target.pop("stable", None)
            if "death_saves" in target:
                target["death_saves"] = {"successes": 0, "failures": 0}
        gained = target["hp"] - old
        return {"public": f"{public_name(state, target)} recupera {gained} PF.", "target_id": target["id"], "healed": gained,
                "dm": "Applicata soltanto la cura gia risolta; nessuno slot, oggetto o riposo automatico."}

    @staticmethod
    def _damage(state, combat, spec):
        ensure_no_pending(state, combat)
        amount = integer(spec.get("amount"), "amount", 0, 100000)
        target, pc = entity(state, combat, spec.get("target"))
        require(not {"morto", "dead"} & {c.casefold() for c in target.get("conditions", [])}, "Il bersaglio e gia morto.")
        nonlethal = spec.get("nonlethal", False)
        require(type(nonlethal) is bool, "nonlethal deve essere booleano.")
        if nonlethal:
            require(spec.get("melee") is True, "Il KO non letale richiede un colpo in mischia gia risolto: conferma melee=true.")
        temporary = target.get("temporary_hp", 0)
        absorbed = min(temporary, amount)
        if temporary:
            target["temporary_hp"] = temporary - absorbed
        remaining = amount - absorbed
        previous = target["hp"]
        require(not (previous == 0 and temporary > 0 and amount > 0),
                "Danni a zero PF con PF temporanei: il DM deve arbitrare l'effetto con save.")
        target["hp"] = max(0, previous - remaining)
        if remaining and target["hp"] == 0:
            add_condition(target, "A terra")
            if nonlethal:
                add_condition(target, "Privo di sensi")
                add_condition(target, "Stabile")
                target["stable"] = True
                target["death_saves"] = {"successes": 0, "failures": 0}
            elif remaining - previous >= target["max_hp"]:
                add_condition(target, "Morto")
                if pc:
                    target["death_saves"] = {"successes": 0, "failures": 3}
            elif pc:
                add_condition(target, "Privo di sensi")
                remove_conditions(target, {"stabile", "stable", "stabilizzato"})
                target.pop("stable", None)
                saves = target.setdefault("death_saves", {"successes": 0, "failures": 0})
                if previous == 0:
                    saves["failures"] = min(3, saves["failures"] + (2 if spec.get("critical") else 1))
                    if saves["failures"] == 3:
                        add_condition(target, "Morto")
            else:
                # A DM may instead prepare death saves for a significant NPC.
                require(not target.get("uses_death_saves") and not target.get("death_saves_allowed"), "PNG con TS morte: risolvi esplicitamente il suo stato con save.")
                add_condition(target, "Morto")
        pending = []
        concentrating = target.get("concentration") or target.get("concentrating") or any(
            "concentrazione" in c.casefold() or "concentration" in c.casefold() for c in target.get("conditions", []))
        if amount and concentrating:
            if target["hp"] == 0:
                target["conditions"] = [c for c in target["conditions"] if "concentrazione" not in c.casefold() and "concentration" not in c.casefold()]
                target.pop("concentration", None)
                target.pop("concentrating", None)
            else:
                dc = max(10, amount // 2)
                pending = [{"type": "concentration_save", "actor_id": target["id"], "dc": dc}]
                combat["pending_resolution"] = pending[0]
                state["flags"].setdefault("combat_context", {})["pending_resolution"] = copy.deepcopy(pending[0])
        return {"public": f"{public_name(state, target)} subisce {amount} danni" + (f" ({absorbed} assorbiti dai PF temporanei)." if absorbed else "."),
                "dm": "Danno gia determinato dal DM; nessuna resistenza, vulnerabilita o reazione inventata.",
                "target_id": target["id"], "damage": amount, "absorbed": absorbed, "pending": pending}

    @staticmethod
    def _resource(state, combat, spec):
        ensure_no_pending(state, combat)
        target, _ = entity(state, combat, spec.get("actor"))
        selector = text_field(spec.get("resource"), "resource", 150).casefold()
        matches = [r for r in target.get("resources", []) if selector in (r["id"].casefold(), r["name"].casefold())]
        require(len(matches) == 1, "Risorsa non trovata o ambigua: usa il suo ID.")
        resource = matches[0]
        delta = integer(spec.get("delta"), "delta", -100, 100)
        require(0 <= resource["current"] + delta <= resource["max"], "Risorsa insufficiente o oltre il massimo.")
        resource["current"] += delta
        return {"public": f"{public_name(state, target)}: {resource['name']} {resource['current']}/{resource['max']}.",
                "actor_id": target["id"], "resource": copy.deepcopy(resource)}

    @staticmethod
    def _condition(state, combat, spec):
        ensure_no_pending(state, combat)
        target, _ = entity(state, combat, spec.get("target"))
        condition = text_field(spec.get("condition"), "condition", 200).strip()
        require(type(spec.get("remove", False)) is bool, "remove deve essere booleano.")
        if spec.get("remove", False):
            remove_conditions(target, {condition.casefold()})
        else:
            add_condition(target, condition)
        return {"public": f"{public_name(state, target)}: " + ("termina " if spec.get("remove", False) else "riceve ") + condition + ".",
                "target_id": target["id"], "conditions": copy.deepcopy(target["conditions"])}

    @staticmethod
    def _check(state, combat, spec):
        target, _ = entity(state, combat, spec.get("actor"))
        pending = combat.get("pending_resolution") or state.get("flags", {}).get("combat_context", {}).get("pending_resolution")
        concentration = (isinstance(pending, dict) and pending.get("type") == "concentration_save"
                         and pending.get("actor_id") == target["id"] and spec.get("save") == "con")
        if not concentration:
            ensure_no_pending(state, combat)
        require(sum(bool(spec.get(key)) for key in ("skill", "ability", "save")) == 1,
                "Scegli una sola abilita, caratteristica o tiro salvezza.")
        if spec.get("skill"):
            key = spec["skill"]
            require(key in target.get("skills", {}), "Abilita non presente: usa un ID della scheda.")
            bonus = target["skills"][key]
        elif spec.get("save"):
            key = spec["save"]
            require(key in target.get("saving_throws", {}), "TS non presente: serve il bonus verificato nella scheda.")
            bonus = target["saving_throws"][key]
        else:
            key = spec["ability"]
            require(key in target.get("abilities", {}), "Caratteristica non presente: usa str/dex/con/int/wis/cha.")
            bonus = (target["abilities"][key] - 10) // 2
        dc = pending["dc"] if concentration else spec.get("dc")
        require(not concentration or spec.get("dc", dc) == dc, "La CD di concentrazione e gia fissata dai danni.")
        if dc is not None:
            integer(dc, "dc", 0, 100)
        label = text_field(spec.get("label", f"{public_name(state, target)}: {key}"), "label", 120)
        rolled = roll_dice(f"1d20{bonus:+d}", label, spec.get("mode", "normal"))
        state["rolls"].append(rolled)
        result = {"actor_id": target["id"], "rolls": [rolled],
                  "public": f"{label}: {rolled['total']}.", "dm": "Prova ordinaria: 1 e 20 naturali non impongono fallimento o successo automatici."}
        if dc is not None:
            result.update(dc=dc, success=rolled["total"] >= dc)
        if concentration:
            if not result["success"]:
                target["conditions"] = [c for c in target.get("conditions", []) if "concentrazione" not in c.casefold() and "concentration" not in c.casefold()]
                target.pop("concentration", None)
                target.pop("concentrating", None)
            combat.pop("pending_resolution", None)
            state["flags"].setdefault("combat_context", {}).pop("pending_resolution", None)
            result["public"] += " Concentrazione " + ("mantenuta." if result["success"] else "interrotta.")
        return result

    @staticmethod
    def _death(state, combat, spec):
        ensure_no_pending(state, combat)
        target, pc = entity(state, combat, spec.get("actor"))
        require(pc or target.get("death_saves_allowed") or target.get("uses_death_saves"), "PNG senza TS morte concordati.")
        conditions = {c.casefold() for c in target.get("conditions", [])}
        require(target["hp"] == 0 and not target.get("stable") and not conditions & {"morto", "dead", "stabile", "stable", "stabilizzato"},
                "Il TS morte richiede zero PF e una creatura viva non stabile.")
        active = state["combat"]
        marker = {"actor_id": target["id"], "round": active["round"], "turn_index": active["turn_index"]}
        if active["active"]:
            require(active["participants"][active["turn_index"]]["id"] == target["id"], "Il TS morte si effettua all'inizio del proprio turno.")
            require(combat.get("death_save_turn") != marker, "Il TS morte di questo turno e gia stato effettuato.")
        saves = target.setdefault("death_saves", {"successes": 0, "failures": 0})
        require(max(saves.values()) < 3, "Esito dei TS morte gia raggiunto.")
        rolled = roll_dice("1d20", public_name(state, target) + ": TS morte", spec.get("mode", "normal"))
        state["rolls"].append(rolled)
        if active["active"]:
            combat["death_save_turn"] = marker
        face = rolled["kept"][0]
        if face == 20:
            target["hp"] = 1
            target["death_saves"] = {"successes": 0, "failures": 0}
            remove_conditions(target, {"incosciente", "privo di sensi", "unconscious", "stabile", "stable", "stabilizzato"})
            outcome = "riprende conoscenza con 1 PF"
        else:
            key = "successes" if face >= 10 else "failures"
            saves[key] = min(3, saves[key] + (2 if face == 1 else 1))
            if saves["failures"] == 3:
                add_condition(target, "Morto")
                outcome = "muore"
            elif saves["successes"] == 3:
                add_condition(target, "Stabilizzato")
                target["stable"] = True
                target["death_saves"] = {"successes": 0, "failures": 0}
                outcome = "si stabilizza, restando privo di sensi"
            else:
                outcome = f"ha {saves['successes']} successi e {saves['failures']} fallimenti"
        return {"public": f"{public_name(state, target)}: TS morte {face}, {outcome}.", "rolls": [rolled], "actor_id": target["id"]}

    @staticmethod
    def _save(state, combat, spec):
        allowed = {"patch", "public", "dm", "pending", "references", "resolve", "private_combat"}
        require(not set(spec) - allowed, "Campi save non riconosciuti.")
        patch = spec.get("patch", {})
        require(isinstance(patch, dict) and set(patch) <= PATCH_FIELDS, "Patch non valida o contenente campi riservati.")
        resolve = spec.get("resolve", [])
        require(isinstance(resolve, list) and len(set(resolve)) == len(resolve), "resolve non valido.")
        require(set(resolve) <= {a["id"] for a in state["pending_actions"]}, "Azione non piu in attesa.")
        updated = deep_merge(state, patch)
        if {"party", "character", "active_character_id"} & set(patch):
            StateStore._sync_party_patch(updated, patch)
        updated["pending_actions"] = [a for a in state["pending_actions"] if a["id"] not in resolve]
        private_patch = spec.get("private_combat", {})
        require(isinstance(private_patch, dict), "private_combat deve essere un oggetto riservato.")
        private = deep_merge(combat, private_patch)
        combat.clear()
        combat.update(private)
        state.clear()
        state.update(updated)
        require(bool(patch) or bool(private_patch) or bool(resolve) or bool(spec.get("public")) or bool(spec.get("dm")), "Nessun effetto da salvare.")
        return {"public": spec.get("public", ""), "dm": spec.get("dm", ""), "pending": spec.get("pending", []),
                "references": spec.get("references", []), "resolved": resolve}
