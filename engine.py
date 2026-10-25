"""Local, dependency-free campaign storage and dice for the human/chat DM.

The browser records intentions. Only a DM commit resolves them or changes fiction.
All writers cooperate through a process lock, then atomically replace the save.
"""
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable

from character_builder import build_character, catalog as character_catalog


MAX_STATE_BYTES = 512 * 1024
MAX_PENDING = 50
MAX_JOURNAL = 200
MAX_ROLLS = 100
MAX_BACKUPS = 30
MAX_XP_AWARDS = 1000
MAX_ROLL_BATCHES = 1000
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
DICE_RE = re.compile(r"^(\d{1,2})[dD](\d{1,3})([+-]\d{1,4})?$")
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class CampaignError(Exception):
    def __init__(self, message: str, code: str = "invalid_input", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CampaignError(message)


def text_field(value: Any, field: str, maximum: int = 4000, *, empty: bool = False) -> str:
    require(isinstance(value, str), f"{field}: serve un testo.")
    require((empty or bool(value.strip())) and len(value) <= maximum,
            f"{field}: lunghezza non valida (massimo {maximum}).")
    require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value),
            f"{field}: caratteri di controllo non consentiti.")
    require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), f"{field}: Unicode non valido.")
    return value


def integer(value: Any, field: str, low: int, high: int) -> int:
    require(type(value) is int and low <= value <= high,
            f"{field}: serve un intero tra {low} e {high}.")
    return value


def object_field(value: Any, field: str) -> dict:
    require(isinstance(value, dict), f"{field}: serve un oggetto.")
    return value


def list_field(value: Any, field: str, maximum: int) -> list:
    require(isinstance(value, list) and len(value) <= maximum,
            f"{field}: serve una lista con massimo {maximum} elementi.")
    return value


def identifier(value: Any, field: str) -> str:
    require(isinstance(value, str) and bool(ID_RE.fullmatch(value)), f"{field}: ID non valido.")
    return value


def finite_json(value: Any, depth: int = 0) -> None:
    require(depth <= 16, "Dati troppo annidati.")
    if value is None or type(value) in (str, bool, int):
        if isinstance(value, str):
            require(len(value) <= 16000, "Testo troppo lungo.")
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), "Testo Unicode non valido.")
        if type(value) is int:
            require(abs(value) <= 10**12, "Numero fuori limite.")
        return
    if type(value) is float:
        require(math.isfinite(value) and abs(value) <= 10**12, "Numero non valido.")
        return
    if isinstance(value, list):
        require(len(value) <= 1000, "Lista troppo lunga.")
        for child in value:
            finite_json(child, depth + 1)
        return
    if isinstance(value, dict):
        require(len(value) <= 200, "Oggetto troppo grande.")
        for key, child in value.items():
            require(isinstance(key, str) and len(key) <= 100, "Chiave non valida.")
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in key), "Chiave Unicode non valida.")
            finite_json(child, depth + 1)
        return
    raise CampaignError("Tipo di dato non valido.")


def parse_dice(expression: str, mode: str = "normal") -> tuple[int, int, int, str]:
    text_field(expression, "expression", 30)
    require(mode in ("normal", "advantage", "disadvantage"), "Modalità del tiro non valida.")
    normalized = expression.replace(" ", "").lower()
    match = DICE_RE.fullmatch(normalized)
    require(match is not None, "Usa una formula come 1d20+3 oppure 2d6+2.")
    count, sides = int(match.group(1)), int(match.group(2))
    modifier = int(match.group(3) or 0)
    require(1 <= count <= 30 and 2 <= sides <= 100 and abs(modifier) <= 1000,
            "Limiti del tiro: 1–30 dadi, 2–100 facce, modificatore ±1000.")
    require(mode == "normal" or (count == 1 and sides == 20),
            "Vantaggio e svantaggio richiedono un singolo d20.")
    return count, sides, modifier, normalized


def roll_dice(expression: str, label: str = "Tiro", mode: str = "normal") -> dict:
    count, sides, modifier, normalized = parse_dice(expression, mode)
    text_field(label, "label", 120)
    values = [secrets.randbelow(sides) + 1 for _ in range(2 if mode != "normal" else count)]
    kept = ([max(values)] if mode == "advantage" else
            [min(values)] if mode == "disadvantage" else values[:])
    return {"id": new_id("roll"), "expression": normalized, "label": label.strip(),
            "mode": mode, "dice": values, "kept": kept, "modifier": modifier,
            "total": sum(kept) + modifier, "at": now()}


def validate_character(character: Any) -> None:
    c = object_field(character, "character")
    finite_json(c)
    for key in ("id",):
        identifier(c.get(key), f"character.{key}")
    if "template_id" in c:
        identifier(c["template_id"], "character.template_id")
    for key in ("name", "species", "class"):
        text_field(c.get(key), f"character.{key}", 100)
    integer(c.get("level"), "character.level", 1, 20)
    # XP is optional for older saves. Awarding it does not choose class features
    # or advance a level: those remain explicit player/DM decisions.
    if "xp" in c:
        integer(c["xp"], "character.xp", 0, 10**9)
    maximum = integer(c.get("max_hp"), "character.max_hp", 0, 1000)
    integer(c.get("hp"), "character.hp", 0, maximum)
    if maximum == 0:
        conditions = list_field(c.get("conditions", []), "character.conditions", 30)
        require(any(isinstance(condition, str) and condition.casefold() == "morto"
                    for condition in conditions),
                "PF massimi a 0 richiedono PF a 0 e la condizione Morto; gestisci la causa con il master.")
    integer(c.get("ac"), "character.ac", 1, 40)
    speed = c.get("speed")
    require(type(speed) in (int, float) and math.isfinite(speed) and 0 <= speed <= 200,
            "character.speed: serve una velocità tra 0 e 200 metri.")
    integer(c.get("proficiency"), "character.proficiency", 1, 9)
    abilities = object_field(c.get("abilities"), "character.abilities")
    require(set(abilities) == {"str", "dex", "con", "int", "wis", "cha"}, "Servono le sei caratteristiche.")
    for key, value in abilities.items():
        integer(value, f"character.abilities.{key}", 1, 30)
    for key, value in object_field(c.get("skills"), "character.skills").items():
        identifier(key, "skill")
        integer(value, f"character.skills.{key}", -20, 40)
    for attack in list_field(c.get("attacks"), "character.attacks", 20):
        object_field(attack, "attack")
        text_field(attack.get("name"), "attack.name", 120)
        integer(attack.get("bonus"), "attack.bonus", -20, 40)
        parse_dice(attack.get("damage"))
    resources = list_field(c.get("resources"), "character.resources", 30)
    resource_ids = []
    for resource in resources:
        object_field(resource, "resource")
        resource_ids.append(identifier(resource.get("id"), "resource.id"))
        text_field(resource.get("name"), "resource.name", 120)
        maximum = integer(resource.get("max"), "resource.max", 0, 100)
        integer(resource.get("current"), "resource.current", 0, maximum)
        require(resource.get("reset") in ("short", "long"), "Riposo della risorsa non valido.")
    require(len(resource_ids) == len(set(resource_ids)), "ID risorsa duplicato.")
    for item in list_field(c.get("inventory"), "character.inventory", 100):
        object_field(item, "inventory item")
        text_field(item.get("name"), "inventory.name", 120)
        integer(item.get("qty"), "inventory.qty", 0, 10000)
    gold = c.get("gold")
    require(type(gold) in (int, float) and math.isfinite(gold) and 0 <= gold <= 10**9,
            "character.gold non valido.")
    text_field(c.get("description"), "character.description", 4000, empty=True)
    if "temporary_hp" in c:
        integer(c["temporary_hp"], "character.temporary_hp", 0, 1000)
    # These optional fields are rendered by the sheet. Reject malformed imports
    # here instead of letting one damaged sheet break every browser refresh.
    for key, maximum in (("conditions", 30), ("features", 100)):
        if key in c:
            for value in list_field(c[key], f"character.{key}", maximum):
                text_field(value, f"character.{key}[]", 4000)
    if "saving_throws" in c:
        saves = object_field(c["saving_throws"], "character.saving_throws")
        require(set(saves).issubset(abilities), "Tiro salvezza sconosciuto.")
        for key, value in saves.items():
            integer(value, f"character.saving_throws.{key}", -20, 40)
    if "saving_throw_proficiencies" in c:
        saves = list_field(c["saving_throw_proficiencies"], "character.saving_throw_proficiencies", 6)
        require(all(isinstance(key, str) and key in abilities for key in saves)
                and len(set(saves)) == len(saves), "Competenze nei TS non valide.")
    if "proficiencies" in c:
        for key, values in object_field(c["proficiencies"], "character.proficiencies").items():
            for value in list_field(values, f"character.proficiencies.{key}", 100):
                text_field(value, f"character.proficiencies.{key}[]", 300)
    if "spells" in c:
        spells = object_field(c["spells"], "character.spells")
        require(spells.get("ability") is None or (isinstance(spells.get("ability"), str)
                and spells["ability"] in abilities),
                "Caratteristica degli incantesimi non valida.")
        for key in ("cantrips", "known", "prepared"):
            if key in spells:
                for value in list_field(spells[key], f"character.spells.{key}", 100):
                    text_field(value, f"character.spells.{key}[]", 1000)
        for key in ("dc", "attack_bonus"):
            if spells.get(key) is not None:
                integer(spells[key], f"character.spells.{key}", -20, 50)
        if "notes" in spells:
            text_field(spells["notes"], "character.spells.notes", 4000, empty=True)
    if "death_saves" in c:
        saves = object_field(c["death_saves"], "character.death_saves")
        require(set(saves) <= {"successes", "failures"}, "Campi dei TS contro morte sconosciuti.")
        for key, value in saves.items():
            integer(value, f"character.death_saves.{key}", 0, 3)


def public_world(world: dict, state: dict) -> dict:
    """Merge public, improvised map additions held in the same atomic save.

    Locations in flags are public even before discovery, just like the base map.
    Never put secrets or unrevealed encounter details in either collection.
    """
    result = copy.deepcopy(world)
    flags = object_field(state.get("flags"), "flags")
    locations = list_field(result.get("locations"), "world.locations", 500)
    known = set()
    for location in locations:
        object_field(location, "world.location")
        location_id = identifier(location.get("id"), "world.location.id")
        require(location_id not in known, "ID luogo duplicato nel mondo.")
        known.add(location_id)
    additions = list_field(flags.get("public_locations", []), "flags.public_locations", 100)
    for location in additions:
        object_field(location, "public location")
        require(set(location) == {"id", "name", "type", "x", "y", "description", "actions"},
                "Luogo aggiunto: servono id, name, type, x, y, description e actions.")
        location_id = identifier(location.get("id"), "public location.id")
        require(location_id not in known, "ID luogo duplicato o già usato dalla mappa di base.")
        known.add(location_id)
        text_field(location.get("name"), "public location.name", 120)
        text_field(location.get("type"), "public location.type", 80)
        text_field(location.get("description"), "public location.description", 4000, empty=True)
        for axis, maximum in (("x", 1000), ("y", 680)):
            coordinate = location.get(axis)
            require(type(coordinate) in (int, float) and math.isfinite(coordinate)
                    and 0 <= coordinate <= maximum, f"public location.{axis}: usa un numero tra 0 e {maximum}.")
        for action in list_field(location.get("actions"), "public location.actions", 12):
            text_field(action, "public location.action", 500)
    result["locations"] = locations + copy.deepcopy(additions)
    base_paths = list_field(result.get("paths", []), "world.paths", 500)
    extra_paths = list_field(flags.get("public_paths", []), "flags.public_paths", 200)
    for path in base_paths + extra_paths:
        require(isinstance(path, list) and len(path) == 2
                and all(isinstance(end, str) and end in known for end in path)
                and path[0] != path[1], "Collegamento di mappa non valido: servono due luoghi distinti esistenti.")
    if extra_paths:
        result["paths"] = base_paths + copy.deepcopy(extra_paths)
    return result


PARTY_FIELDS = {"party_size", "party", "active_character_id"}
STATE_FIELDS = {"schema_version", "revision", "campaign_id", "phase", "session", "location_id",
                "discovered", "character", "scene", "quests", "journal", "rolls", "pending_actions",
                "combat", "clock", "flags"} | PARTY_FIELDS
PATCH_FIELDS = STATE_FIELDS - {"schema_version", "revision", "campaign_id", "pending_actions", "rolls"}


def normalize_state(state: Any) -> dict:
    """Upgrade old solo saves in memory, preserving all player data and IDs."""
    s = copy.deepcopy(object_field(state, "state"))
    if not (set(s) & PARTY_FIELDS):
        character = s.get("character")
        s["party_size"] = 1
        s["party"] = [copy.deepcopy(character)] if isinstance(character, dict) else []
        s["active_character_id"] = character.get("id") if isinstance(character, dict) else None
    return s


def validate_state(state: Any, world: dict, campaign_id: str | None = None) -> None:
    s = normalize_state(state)
    finite_json(s)
    require(len(json.dumps(s, ensure_ascii=False).encode("utf-8")) <= MAX_STATE_BYTES,
            "Salvataggio troppo grande.")
    require(set(s) == STATE_FIELDS, "Campi del salvataggio mancanti o sconosciuti.")
    require(s.get("schema_version") == 1 and type(s.get("schema_version")) is int,
            "Versione del salvataggio non supportata.")
    identifier(s.get("campaign_id"), "campaign_id")
    require(s["campaign_id"] == world.get("id"), "La mappa appartiene a un'altra campagna.")
    require(campaign_id is None or s["campaign_id"] == campaign_id,
            "Il salvataggio appartiene a un'altra campagna.")
    integer(s.get("revision"), "revision", 0, 10**12)
    require(s.get("phase") in ("creation", "playing", "ended"), "Fase non valida.")
    integer(s.get("session"), "session", 1, 100000)
    locations = {place["id"] for place in public_world(world, s)["locations"]}
    require(isinstance(s.get("location_id"), str) and s["location_id"] in locations,
            "Luogo attuale sconosciuto.")
    discovered = list_field(s.get("discovered"), "discovered", len(locations))
    require(all(isinstance(place, str) and place in locations for place in discovered),
            "Luogo scoperto sconosciuto.")
    require(len(set(discovered)) == len(discovered), "Luogo scoperto duplicato.")
    require(s["location_id"] in discovered, "Il luogo attuale deve essere scoperto.")
    party_size = integer(s.get("party_size"), "party_size", 1, 4)
    party = list_field(s.get("party"), "party", party_size)
    for character in party:
        validate_character(character)
    party_ids = [character["id"] for character in party]
    require(len(set(party_ids)) == len(party_ids), "ID personaggio duplicato nel gruppo.")
    if party:
        active_id = identifier(s.get("active_character_id"), "active_character_id")
        active = next((character for character in party if character["id"] == active_id), None)
        require(active is not None, "Il personaggio attivo deve appartenere al gruppo.")
        require(s.get("character") == active, "La scheda attiva non coincide con il personaggio nel gruppo.")
    else:
        require(s.get("active_character_id") is None and s.get("character") is None,
                "Un gruppo vuoto non può avere un personaggio attivo.")
    require(s["phase"] != "playing" or len(party) == party_size,
            f"Prima di giocare servono tutti i {party_size} personaggi del gruppo.")
    scene = object_field(s.get("scene"), "scene")
    text_field(scene.get("title"), "scene.title", 200)
    text_field(scene.get("text"), "scene.text", 12000)
    for choice in list_field(scene.get("choices"), "scene.choices", 12):
        text_field(choice, "choice", 500)
    quest_ids = []
    for quest in list_field(s.get("quests"), "quests", 50):
        object_field(quest, "quest")
        quest_ids.append(identifier(quest.get("id"), "quest.id"))
        text_field(quest.get("title"), "quest.title", 200)
        text_field(quest.get("description"), "quest.description", 4000, empty=True)
        require(quest.get("status") in ("active", "completed", "failed"), "Stato missione non valido.")
    require(len(set(quest_ids)) == len(quest_ids), "ID missione duplicato.")
    for entry in list_field(s.get("journal"), "journal", MAX_JOURNAL):
        object_field(entry, "journal entry")
        identifier(entry.get("id"), "journal.id")
        text_field(entry.get("kind"), "journal.kind", 40)
        text_field(entry.get("title"), "journal.title", 200)
        text_field(entry.get("text"), "journal.text", 6000, empty=True)
        text_field(entry.get("at"), "journal.at", 60)
    for entry in list_field(s.get("rolls"), "rolls", MAX_ROLLS):
        object_field(entry, "roll")
        identifier(entry.get("id"), "roll.id")
        text_field(entry.get("label"), "roll.label", 120)
        text_field(entry.get("at"), "roll.at", 60)
        count, sides, modifier, _ = parse_dice(entry.get("expression"), entry.get("mode"))
        values = list_field(entry.get("dice"), "roll.dice", 30)
        require(len(values) == (count if entry["mode"] == "normal" else 2), "Numero di dadi non valido.")
        for value in values:
            integer(value, "roll.dice[]", 1, sides)
        kept = values if entry["mode"] == "normal" else [max(values) if entry["mode"] == "advantage" else min(values)]
        recorded_kept = list_field(entry.get("kept"), "roll.kept", 30)
        for value in recorded_kept:
            integer(value, "roll.kept[]", 1, sides)
        integer(entry.get("modifier"), "roll.modifier", -1000, 1000)
        require(recorded_kept == kept and entry["modifier"] == modifier,
                "Dettaglio del tiro non coerente.")
        require(type(entry.get("total")) is int and entry["total"] == sum(kept) + modifier,
                "Totale del tiro non coerente.")
    pending_ids = []
    for action in list_field(s.get("pending_actions"), "pending_actions", MAX_PENDING):
        object_field(action, "pending action")
        pending_ids.append(identifier(action.get("id"), "action.id"))
        text_field(action.get("text"), "action.text", 2000)
        text_field(action.get("at"), "action.at", 60)
    require(len(set(pending_ids)) == len(pending_ids), "ID azione duplicato.")
    combat = object_field(s.get("combat"), "combat")
    require(type(combat.get("active")) is bool, "combat.active non valido.")
    integer(combat.get("round"), "combat.round", 0, 10000)
    participants = list_field(combat.get("participants"), "combat.participants", 40)
    integer(combat.get("turn_index"), "combat.turn_index", 0, max(0, len(participants) - 1))
    require(not combat["active"] or bool(participants), "Un combattimento attivo richiede partecipanti.")
    require(not combat["active"] or s["phase"] == "playing", "Il combattimento richiede una partita in corso.")
    require(not combat["active"] or combat["round"] >= 1, "Il primo round di combattimento è 1.")
    members = {member["id"]: member for member in party}
    participant_ids = []
    for participant in participants:
        object_field(participant, "participant")
        participant_ids.append(identifier(participant.get("id"), "participant.id"))
        text_field(participant.get("name"), "participant.name", 120)
        integer(participant.get("initiative"), "participant.initiative", -30, 100)
        require(participant.get("hidden", False) is False,
                "Il combattimento è pubblico: conserva creature non percepite e statistiche segrete nei file master/.")
        is_member = participant["id"] in members
        # A visible NPC needs a public name and initiative, not its secret stats.
        # HP/max HP must be supplied together; AC can be disclosed independently.
        has_hp = "hp" in participant
        has_max_hp = "max_hp" in participant
        require(has_hp == has_max_hp, "participant: hp e max_hp devono essere presenti insieme.")
        require(not is_member or (has_hp and "ac" in participant),
                "Un PG in iniziativa richiede hp, max_hp e ac coerenti con la scheda.")
        if has_hp:
            maximum = integer(participant["max_hp"], "participant.max_hp", 0, 10000)
            integer(participant["hp"], "participant.hp", 0, maximum)
            if maximum == 0:
                conditions = list_field(participant.get("conditions", []), "participant.conditions", 20)
                require(any(isinstance(condition, str) and condition.casefold() == "morto"
                            for condition in conditions),
                        "Un combattente con PF massimi a 0 richiede PF a 0 e la condizione Morto.")
        if "ac" in participant:
            integer(participant["ac"], "participant.ac", 1, 50)
        for condition in list_field(participant.get("conditions", []), "participant.conditions", 20):
            text_field(condition, "condition", 80)
    require(len(participant_ids) == len(set(participant_ids)), "ID combattente duplicato.")
    if combat["active"]:
        for participant in participants:
            member = members.get(participant["id"])
            if member is not None:
                require(all(participant[key] == member[key] for key in ("hp", "max_hp", "ac"))
                        and participant.get("conditions", []) == member.get("conditions", []),
                        f"{member['name']}: PF, CA e condizioni devono coincidere fra scheda e combattimento.")
    clock = object_field(s.get("clock"), "clock")
    integer(clock.get("day"), "clock.day", 1, 1000000)
    require(isinstance(clock.get("time"), str) and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock["time"]),
            "clock.time: usa HH:MM.")
    text_field(clock.get("weather"), "clock.weather", 200)
    object_field(s.get("flags"), "flags")


def deep_merge(base: dict, patch: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def read_json(path: Path) -> Any:
    try:
        require(path.stat().st_size <= MAX_STATE_BYTES, f"File troppo grande: {path.name}")
        return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite")))
    except CampaignError:
        raise
    except (OSError, ValueError) as exc:
        raise CampaignError(f"Impossibile leggere {path.name}: {exc}", "storage_error", 500) from exc


class StateStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.state_path = self.root / "data" / "campaign.json"
        self.world_path = self.root / "data" / "world.json"
        self.saves_path = self.root / "saves"
        self.lock_path = self.root / "data" / ".campaign.lock"
        with _LOCKS_GUARD:
            self._thread_lock = _LOCKS.setdefault(os.path.normcase(str(self.state_path)), threading.RLock())

    @contextmanager
    def locked(self):
        with self._thread_lock:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            with self.lock_path.open("a+b") as handle:
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                deadline = time.monotonic() + 15
                if os.name == "nt":
                    import msvcrt
                    while True:
                        try:
                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                            break
                        except OSError as exc:
                            if time.monotonic() >= deadline:
                                raise CampaignError("Salvataggio occupato. Riprova.", "storage_busy", 503) from exc
                            time.sleep(0.025)
                    try:
                        yield
                    finally:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    while True:
                        try:
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError as exc:
                            if time.monotonic() >= deadline:
                                raise CampaignError("Salvataggio occupato. Riprova.", "storage_busy", 503) from exc
                            time.sleep(0.025)
                    try:
                        yield
                    finally:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def world(self) -> dict:
        world = read_json(self.world_path)
        require(isinstance(world, dict), "Mondo non valido.")
        # This is the only world file the server exposes; master/ is never read here.
        return world

    def _read(self) -> dict:
        state = normalize_state(read_json(self.state_path))
        validate_state(state, self.world())
        return state

    def read(self) -> dict:
        with self.locked():
            return self._read()

    @staticmethod
    def has_started(state: dict) -> bool:
        flags = state.get("flags", {})
        return bool(flags.get("started") or flags.get("adventure_started")
                    or flags.get("character_creation_locked")
                    or state["combat"]["active"]
                    or any(entry["kind"] == "master" for entry in state["journal"]))

    @classmethod
    def _status(cls, state: dict) -> dict:
        return {"revision": state["revision"], "phase": state["phase"],
                "started": cls.has_started(state), "party_count": len(state["party"]),
                "party_size": state["party_size"],
                "group_ready": len(state["party"]) == state["party_size"],
                "can_edit_characters": cls.can_edit_characters(state),
                "session": state["session"], "active_character_id": state["active_character_id"],
                "pending_count": len(state["pending_actions"]),
                "combat_active": state["combat"]["active"], "location_id": state["location_id"]}

    def status(self) -> dict:
        return self._status(self.read())

    def table(self) -> dict:
        """One lock, one revision for scene, dynamic map and onboarding status."""
        with self.locked():
            state = self._read()
            return {"state": state, "world": public_world(self.world(), state),
                    "status": self._status(state)}

    def _context_locked(self, state: dict, world: dict, *, recent: int = 6) -> dict:
        """Project a DM turn snapshot without repeating the active PC or history.

        The caller owns the campaign lock and supplies the state/world snapshot.
        Runtime character fields, including custom features, remain intact; only
        character-creation bookkeeping is omitted. No private files are read here.
        """
        integer(recent, "recent", 0, MAX_ROLLS)
        current_world = public_world(world, state)
        known = [place for place in current_world["locations"] if place["id"] in state["discovered"]]
        flags = copy.deepcopy(state["flags"])
        flags.pop("roll_batches", None)  # Receipts can be large and are not current fiction.
        flags.pop("public_locations", None)
        flags.pop("public_paths", None)
        referenced = set()

        def references(value):
            if isinstance(value, str) and value.startswith("roll_"):
                referenced.add(value)
            elif isinstance(value, dict):
                for child in value.values():
                    references(child)
            elif isinstance(value, list):
                for child in value:
                    references(child)

        references(state["combat"])
        references(flags)
        recent_rolls = state["rolls"][-recent:] if recent else []
        recent_ids = {roll["id"] for roll in recent_rolls}
        available_ids = {roll["id"] for roll in state["rolls"]}
        party = copy.deepcopy(state["party"])
        for character in party:
            character.pop("creation", None)
        return {"revision": state["revision"], "campaign_id": state["campaign_id"],
                "phase": state["phase"], "started": self.has_started(state), "session": state["session"],
                "party_size": state["party_size"], "active_character_id": state["active_character_id"],
                "location_id": state["location_id"],
                "location": next(place for place in known if place["id"] == state["location_id"]),
                "known_locations": [{"id": place["id"], "name": place["name"]} for place in known],
                "discovered": copy.deepcopy(state["discovered"]),
                "party": party, "scene": copy.deepcopy(state["scene"]),
                "combat": copy.deepcopy(state["combat"]), "clock": copy.deepcopy(state["clock"]),
                "quests": copy.deepcopy(state["quests"]), "flags": flags,
                "pending_actions": copy.deepcopy(state["pending_actions"]),
                "recent_journal": copy.deepcopy(state["journal"][-3:]),
                "recent_rolls": copy.deepcopy(recent_rolls),
                "referenced_rolls": [copy.deepcopy(roll) for roll in state["rolls"]
                                     if roll["id"] in referenced - recent_ids],
                "missing_referenced_roll_ids": sorted(referenced - available_ids)}

    def context(self, *, recent: int = 6) -> dict:
        """One coherent compact public snapshot for local master tooling."""
        with self.locked():
            world = self.world()
            state = normalize_state(read_json(self.state_path))
            validate_state(state, world)
            return self._context_locked(state, world, recent=recent)

    @staticmethod
    def _atomic_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        descriptor, temporary = tempfile.mkstemp(prefix=".save-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _backup(self, state: dict) -> Path:
        self.saves_path.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        path = self.saves_path / f"campaign-r{state['revision']:08d}-{stamp}-{secrets.token_hex(3)}.json"
        self._atomic_json(path, state)
        backups = sorted(self.saves_path.glob("campaign-r*-*.json"), key=lambda p: p.stat().st_mtime_ns)
        for old in backups[:-MAX_BACKUPS]:
            old.unlink()
        return path

    def snapshot(self) -> Path:
        with self.locked():
            return self._backup(self._read())

    def mutate(self, callback: Callable[[dict], Any], expected_revision: int | None = None) -> tuple[dict, Any]:
        with self.locked():
            if (self.root / "master" / "pending-operation.json").exists():
                raise CampaignError("Operazione DM interrotta: esegui tools/play.py recover prima di altre modifiche.",
                                    "operation_pending", 503)
            current = self._read()
            if expected_revision is not None:
                integer(expected_revision, "expected_revision", 0, 10**12)
                if current["revision"] != expected_revision:
                    raise CampaignError(
                        f"Revisione non aggiornata: attesa {expected_revision}, attuale {current['revision']}. Rileggi lo stato.",
                        "revision_conflict", 409)
            state = copy.deepcopy(current)
            result = callback(state)
            if state == current:
                return current, result
            state["revision"] = current["revision"] + 1
            validate_state(state, self.world(), current["campaign_id"])
            self._backup(current)
            self._atomic_json(self.state_path, state)
            return state, result

    @staticmethod
    def event(state: dict, title: str, text: str, kind: str = "master") -> dict:
        entry = {"id": new_id("entry"), "kind": kind, "title": title, "text": text, "at": now()}
        state["journal"] = (state["journal"] + [entry])[-MAX_JOURNAL:]
        return entry

    def queue_action(self, text: str) -> tuple[dict, dict]:
        text_field(text, "text", 2000)
        def update(state):
            require(state["phase"] == "playing", f"Completate prima i {state['party_size']} personaggi del gruppo. Potete intanto parlarne in chat.")
            require(len(state["pending_actions"]) < MAX_PENDING, "Coda piena: il master deve risolvere le azioni in attesa.")
            action = {"id": new_id("action"), "text": text.strip(), "at": now()}
            state["pending_actions"].append(action)
            return action
        return self.mutate(update)

    def choose_character(self, template_id: str, name: str | None = None,
                         expected_revision: int | None = None) -> tuple[dict, dict]:
        identifier(template_id, "template_id")
        if name is not None:
            text_field(name, "name", 80)
        def update(state):
            require(state["phase"] == "creation" and len(state["party"]) < state["party_size"],
                    "Il gruppo è già completo.")
            template = next((c for c in self.world().get("character_templates", []) if c.get("id") == template_id), None)
            require(template is not None, "Personaggio predefinito sconosciuto.")
            character = copy.deepcopy(template)
            character["id"] = new_id("pc")
            character["template_id"] = template_id
            character.setdefault("xp", 0)
            if name is not None:
                character["name"] = name.strip()
            validate_character(character)
            state["party"].append(character)
            if state["active_character_id"] is None:
                state["active_character_id"] = character["id"]
                state["character"] = copy.deepcopy(character)
            state["phase"] = "playing" if len(state["party"]) == state["party_size"] else "creation"
            self.event(state, "Un nuovo avventuriero", f"{character['name']}, {character['species']} {character['class']}, entra nella storia.", "character")
            return character
        return self.mutate(update, expected_revision)

    @staticmethod
    def can_edit_characters(state: dict) -> bool:
        """Only before the first DM consequence; UI activity is not fictional play."""
        return (state["phase"] in ("creation", "playing")
                and not state["combat"]["active"]
                and not StateStore.has_started(state)
                and all(member["level"] == 1 for member in state["party"])
                and all(member["hp"] == member["max_hp"]
                        and not member.get("conditions")
                        and all(r["current"] == r["max"] for r in member["resources"])
                        for member in state["party"])
                and not any(entry["kind"] == "master" for entry in state["journal"]))

    def character_options(self) -> dict:
        result = character_catalog()
        state = self.read()
        result["can_edit_characters"] = self.can_edit_characters(state)
        result["revision"] = state["revision"]
        return result

    @staticmethod
    def _build_character(payload: dict, character_id: str | None = None) -> dict:
        try:
            character = build_character(payload, character_id)
        except (ValueError, TypeError) as exc:
            raise CampaignError(str(exc)) from None
        validate_character(character)
        return character

    def create_character(self, payload: dict, expected_revision: int | None = None) -> tuple[dict, dict]:
        character = self._build_character(payload)
        def update(state):
            require(state["phase"] == "creation" and len(state["party"]) < state["party_size"],
                    "Il gruppo è già completo: usate Modifica per cambiare una scheda prima dell'inizio.")
            state["party"].append(character)
            if state["active_character_id"] is None:
                state["active_character_id"] = character["id"]
                state["character"] = copy.deepcopy(character)
            state["phase"] = "playing" if len(state["party"]) == state["party_size"] else "creation"
            self.event(state, "Un nuovo avventuriero", f"{character['name']}, {character['species']} {character['class']}, entra nella storia.", "character")
            return character
        return self.mutate(update, expected_revision)

    def rebuild_character(self, character_id: str, payload: dict, expected_revision: int) -> tuple[dict, dict]:
        identifier(character_id, "character_id")
        integer(expected_revision, "expected_revision", 0, 10**12)
        character = self._build_character(payload, character_id)
        def update(state):
            require(self.can_edit_characters(state),
                    "L'avventura è già iniziata. Concordate cambiamenti di classe o scheda con il master in chat; progressi e risorse restano salvati.")
            index = next((i for i, member in enumerate(state["party"]) if member["id"] == character_id), None)
            require(index is not None, "Il personaggio non appartiene al gruppo.")
            state["party"][index] = character
            if state["active_character_id"] == character_id:
                state["character"] = copy.deepcopy(character)
            self.event(state, "Scheda modificata prima dell'inizio", f"{character['name']}: {character['species']} {character['class']}. Gli altri membri del gruppo restano invariati.", "character")
            return character
        return self.mutate(update, expected_revision)

    def active_character(self, character_id: str) -> tuple[dict, dict]:
        identifier(character_id, "character_id")
        def update(state):
            selected = next((character for character in state["party"] if character["id"] == character_id), None)
            require(selected is not None, "Il personaggio non appartiene al gruppo.")
            state["active_character_id"] = character_id
            state["character"] = copy.deepcopy(selected)
            return selected
        return self.mutate(update)

    def roll(self, expression: str, label: str = "Tiro", mode: str = "normal") -> tuple[dict, dict]:
        result = roll_dice(expression, label, mode)
        def update(state):
            state["rolls"] = (state["rolls"] + [result])[-MAX_ROLLS:]
            return result
        return self.mutate(update)

    def roll_batch(self, specifications: list[dict], request_id: str,
                   expected_revision: int) -> tuple[dict, dict]:
        """Record independent public rolls in one commit, with durable retry IDs.

        Receipts are never evicted: exhaustion fails before drawing dice. Private
        rolls and dependent choices deliberately use the separate existing path.
        """
        identifier(request_id, "request_id")
        integer(expected_revision, "expected_revision", 0, 10**12)
        list_field(specifications, "rolls", 30)
        require(bool(specifications), "Il batch deve contenere almeno un tiro.")
        specs = []
        for entry in specifications:
            object_field(entry, "roll")
            require(set(entry) <= {"expression", "label", "mode"},
                    "Il batch accetta soltanto expression, label e mode pubblici; usa roll --private per i segreti.")
            mode = entry.get("mode", "normal")
            _, _, _, expression = parse_dice(entry.get("expression"), mode)
            label = text_field(entry.get("label", "Tiro"), "label", 120).strip()
            specs.append({"expression": expression, "label": label, "mode": mode})

        def update(state):
            batches = list_field(state["flags"].get("roll_batches", []), "flags.roll_batches", MAX_ROLL_BATCHES)
            require(all(isinstance(entry, dict) and isinstance(entry.get("id"), str)
                        and isinstance(entry.get("rolls"), list) for entry in batches),
                    "Registro batch non valido.")
            previous = next((entry for entry in batches if entry["id"] == request_id), None)
            if previous is not None:
                require(previous.get("specs") == specs,
                        "Questo request-id è già usato con tiri diversi: non rilanciare lo stesso evento.")
                return {"request_id": request_id, "batch_revision": previous["revision"],
                        "already_rolled": True, "rolls": copy.deepcopy(previous["rolls"])}
            if state["revision"] != expected_revision:
                raise CampaignError(
                    f"Revisione non aggiornata: attesa {expected_revision}, attuale {state['revision']}. Rileggi lo stato.",
                    "revision_conflict", 409)
            require(len(batches) < MAX_ROLL_BATCHES,
                    "Registro batch completo: conserva le ricevute e usa roll per i nuovi tiri.")
            # Conservative bound includes the duplicate public recent history,
            # indentation and receipt overhead, before any random draw occurs.
            estimated = len(json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"))
            estimated += len(json.dumps(specs, ensure_ascii=False, indent=2).encode("utf-8")) * 2
            estimated += 4096 + sum(2048 + parse_dice(spec["expression"], spec["mode"])[0] * 32 for spec in specs)
            require(estimated <= MAX_STATE_BYTES,
                    "Spazio ricevute batch esaurito: conserva il registro e usa roll per i nuovi tiri.")
            rolls = [roll_dice(spec["expression"], spec["label"], spec["mode"]) for spec in specs]
            state["rolls"] = (state["rolls"] + rolls)[-MAX_ROLLS:]
            receipt = {"id": request_id, "specs": specs, "rolls": rolls, "revision": state["revision"] + 1}
            state["flags"]["roll_batches"] = batches + [receipt]
            return {"request_id": request_id, "batch_revision": receipt["revision"],
                    "already_rolled": False, "rolls": copy.deepcopy(rolls)}
        # The replay check intentionally precedes revision comparison, while the
        # first execution still checks its expected revision inside this lock.
        return self.mutate(update)

    def private_roll(self, expression: str, label: str = "Tiro del master", mode: str = "normal") -> dict:
        """Private adjudication never enters public state, export or revision history."""
        result = roll_dice(expression, label, mode)
        with self.locked():
            path = self.root / "master" / "rolls-private.json"
            history = read_json(path) if path.exists() else []
            list_field(history, "private rolls", 500)
            self._atomic_json(path, (history + [result])[-500:])
        return result

    def award_xp(self, amount: int, award_id: str, label: str, expected_revision: int,
                 *, per_character: bool = False) -> tuple[dict, dict]:
        """Award a resolved, public reward once, without choosing level benefits.

        The default amount is the whole party's reward. Fractions are rounded
        down per PC and the unassigned remainder is reported, never hidden.
        """
        integer(amount, "amount", 1, 10**9)
        identifier(award_id, "award_id")
        label = text_field(label, "label", 200).strip()
        integer(expected_revision, "expected_revision", 0, 10**12)
        require(type(per_character) is bool, "per_character deve essere un booleano.")
        mode = "per_character" if per_character else "party_total"
        def update(state):
            require(state["phase"] == "playing" and len(state["party"]) == state["party_size"],
                    "Completate il gruppo prima di assegnare l'esperienza.")
            flags = state["flags"]
            awards = list_field(flags.get("xp_awards", []), "flags.xp_awards", MAX_XP_AWARDS)
            require(all(isinstance(entry, dict) and isinstance(entry.get("id"), str)
                        for entry in awards), "Registro delle ricompense XP non valido.")
            previous = next((entry for entry in awards if entry["id"] == award_id), None)
            if previous is not None:
                require(previous.get("amount") == amount and previous.get("mode") == mode
                        and previous.get("label") == label,
                        "Questo ID ricompensa è già usato con dati diversi. Controlla il registro XP.")
                return {"award": copy.deepcopy(previous), "already_awarded": True}
            require(len(awards) < MAX_XP_AWARDS,
                    "Registro XP completo: conserva gli ID assegnati e concorda un nuovo archivio con il master.")
            count = len(state["party"])
            share = amount if per_character else amount // count
            remainder = 0 if per_character else amount % count
            require(share > 0, "Il totale deve assegnare almeno 1 XP a ogni personaggio.")
            award = {"id": award_id, "label": label, "amount": amount, "mode": mode,
                     "per_character": share, "total_awarded": share * count, "remainder": remainder,
                     "recipients": [member["id"] for member in state["party"]], "at": now()}
            for member in state["party"]:
                member["xp"] = member.get("xp", 0) + share
            state["character"] = copy.deepcopy(next(member for member in state["party"]
                                                      if member["id"] == state["active_character_id"]))
            flags["xp_awards"] = awards + [award]
            flags["character_creation_locked"] = True
            text = f"{label}: {share} XP a ciascuno dei {count} personaggi."
            if remainder:
                text += f" Restano {remainder} XP non assegnati per l'arrotondamento per difetto."
            self.event(state, "Esperienza guadagnata", text)
            return {"award": copy.deepcopy(award), "already_awarded": False}
        return self.mutate(update, expected_revision)

    def start(self, expected_revision: int, scene: dict | None = None) -> tuple[dict, dict]:
        """Begin once on the master's instruction, without moving or choosing actions."""
        integer(expected_revision, "expected_revision", 0, 10**12)
        if scene is not None:
            object_field(scene, "scene")
            require(set(scene) == {"title", "text", "choices"},
                    "La scena iniziale richiede title, text e choices.")
        def update(state):
            require(state["phase"] != "ended", "La campagna è conclusa: concordate il seguito in chat.")
            require(len(state["party"]) == state["party_size"],
                    f"Servono i {state['party_size']} personaggi scelti dai giocatori per iniziare.")
            if self.has_started(state):
                require(scene is None, "L'avventura è già avviata: usa commit per aggiornare la scena corrente.")
                return {"started": True, "already_started": True}
            state["phase"] = "playing"
            state["flags"]["started"] = True
            state["flags"]["character_creation_locked"] = True
            if scene is not None:
                state["scene"] = copy.deepcopy(scene)
            self.event(state, "La campagna comincia", "Il gruppo è pronto. Il master conduce la partita nella chat.", "system")
            return {"started": True, "already_started": False}
        return self.mutate(update, expected_revision)

    def add_location(self, location: dict, expected_revision: int, *,
                     connect: list[str] | None = None, discover: bool = False) -> tuple[dict, dict]:
        object_field(location, "location")
        integer(expected_revision, "expected_revision", 0, 10**12)
        require(type(discover) is bool, "discover deve essere un booleano.")
        connect = [] if connect is None else list_field(connect, "connect", 100)
        require(all(isinstance(item, str) for item in connect) and len(set(connect)) == len(connect),
                "Collegamenti duplicati o non validi.")
        def update(state):
            flags = state["flags"]
            flags["public_locations"] = flags.get("public_locations", []) + [copy.deepcopy(location)]
            if connect:
                flags["public_paths"] = flags.get("public_paths", []) + [[location.get("id"), item] for item in connect]
            if discover:
                state["discovered"].append(location.get("id"))
            return {"location_id": location.get("id"), "discovered": discover}
        return self.mutate(update, expected_revision)

    def note(self, text: str) -> tuple[dict, dict]:
        text_field(text, "text", 6000)
        def update(state):
            return self.event(state, "Appunto del giocatore", text.strip(), "note")
        return self.mutate(update)

    def commit(self, patch: dict, expected_revision: int, resolve: list[str] | None = None,
               event: str | None = None) -> tuple[dict, dict]:
        integer(expected_revision, "expected_revision", 0, 10**12)
        object_field(patch, "patch")
        require(set(patch).issubset(PATCH_FIELDS), "Il patch contiene campi riservati o sconosciuti.")
        finite_json(patch)
        resolve = resolve or []
        require(isinstance(resolve, list) and len(resolve) <= MAX_PENDING, "Lista azioni non valida.")
        for action_id in resolve:
            identifier(action_id, "resolve")
        require(len(set(resolve)) == len(resolve), "ID azione duplicato.")
        if event is not None:
            text_field(event, "event", 6000)
        require(bool(patch) or bool(resolve) or event is not None, "Nessuna modifica da salvare.")
        def update(state):
            known = {a["id"] for a in state["pending_actions"]}
            require(set(resolve).issubset(known), "Una delle azioni da risolvere non è in attesa.")
            updated = deep_merge(state, patch)
            if {"party", "character", "active_character_id"} & set(patch):
                self._sync_party_patch(updated, patch)
            # Metadata and agreed character preparation are not fictional play.
            # Narrative consequences still lock rebuilding, even without a diary
            # event, so it cannot be used to restore spent resources.
            fiction_fields = {"scene", "location_id", "discovered", "quests", "combat", "clock"}
            fiction_changed = any(updated[key] != state[key] for key in fiction_fields)
            before_members = {member["id"]: member for member in state["party"]}
            for member in updated["party"]:
                before = before_members.get(member.get("id"))
                if before is None:
                    continue
                fiction_changed |= any(member.get(key) != before.get(key)
                                       for key in ("level", "xp", "hp", "temporary_hp", "conditions", "death_saves"))
                before_resources = {resource["id"]: resource["current"] for resource in before["resources"]}
                if isinstance(member.get("resources"), list):
                    fiction_changed |= any(isinstance(resource, dict) and resource.get("id") in before_resources
                                           and resource.get("current") != before_resources[resource["id"]]
                                           for resource in member["resources"])
            if state["phase"] == "playing" and (fiction_changed or resolve or event is not None):
                flags = object_field(updated.setdefault("flags", {}), "flags")
                flags["character_creation_locked"] = True
            updated["pending_actions"] = [a for a in state["pending_actions"] if a["id"] not in resolve]
            if event is not None:
                self.event(updated, "Il master racconta", event)
            state.clear()
            state.update(updated)
            return {"resolved": resolve}
        return self.mutate(update, expected_revision)

    @staticmethod
    def _sync_party_patch(updated: dict, patch: dict) -> None:
        party = list_field(updated.get("party"), "party", 4)
        for character in party:
            object_field(character, "party member")
            identifier(character.get("id"), "party member.id")
        if not party:
            require(updated.get("active_character_id") is None,
                    "Imposta active_character_id a null quando svuoti il gruppo.")
            require("character" not in patch or patch["character"] is None,
                    "Un gruppo vuoto non può avere una scheda attiva.")
            updated["character"] = None
            return
        active_id = identifier(updated.get("active_character_id"), "active_character_id")
        index = next((i for i, member in enumerate(party) if member["id"] == active_id), None)
        require(index is not None, "Il personaggio attivo deve appartenere al gruppo.")
        selected = party[index]
        if "character" in patch:
            character_patch = object_field(patch["character"], "character patch")
            merged = deep_merge(selected, character_patch)
            require(merged.get("id") == active_id, "Non cambiare l'ID della scheda attiva: modifica il gruppo esplicitamente.")
            if "party" in patch:
                require(merged == selected, "Il patch character è in conflitto con il gruppo canonico.")
            else:
                party[index] = merged
                selected = merged
        updated["character"] = copy.deepcopy(selected)

    def restore(self, incoming: dict, expected_revision: int | None = None) -> tuple[dict, dict]:
        # Import is replacement, never merge. Validate before touching any file.
        incoming = normalize_state(incoming)
        def update(state):
            validate_state(incoming, self.world(), state["campaign_id"])
            revision = state["revision"]
            state.clear()
            state.update(incoming)
            state["revision"] = revision
            self.event(state, "Salvataggio importato", "Ripristinata una copia della campagna.", "system")
            return {"imported": True}
        return self.mutate(update, expected_revision)
