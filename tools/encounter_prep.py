"""Read-only DM encounter preparation, outside every public server route."""
from __future__ import annotations

import copy
from pathlib import Path
from time import perf_counter

from engine import StateStore, integer, parse_dice, read_json, require


def validate_catalog(catalog):
    require(catalog.get("schema_version") == 1 and catalog.get("visibility") == "dm_only", "Catalogo privato non valido.")
    profiles, scenes = catalog.get("profiles", {}), catalog.get("scenes", {})
    require(isinstance(profiles, dict) and isinstance(scenes, dict), "Profili e scene devono essere oggetti.")
    for key, profile in profiles.items():
        integer(profile.get("ac"), f"{key}.ac", 1, 40)
        integer(profile.get("max_hp"), f"{key}.max_hp", 1, 1000)
        require(profile.get("references"), f"Profilo {key}: fonte assente.")
        for attack in profile.get("attacks", []):
            integer(attack.get("bonus"), f"{key}.bonus", -30, 40)
            parse_dice(attack["damage"])
            require(type(attack.get("melee")) is bool, "Specificare mischia/distanza.")
    for key, scene in scenes.items():
        require(scene.get("references"), f"Scena {key}: fonte assente.")
        require(set(scene.get("profile_ids", [])) <= set(profiles), f"Scena {key}: profilo sconosciuto.")
        for creature in scene.get("roster", []):
            require(creature["profile"] in scene["profile_ids"], "Creatura non compresa nei profili della scena.")
    return {"profiles": len(profiles), "scenes": len(scenes)}


def inspect_scene(root, scene_id, *, preflight=False):
    started = perf_counter()
    campaign_id = StateStore(root).read()["campaign_id"]
    path = Path(root) / "campaigns" / campaign_id / "prepared" / "encounters.json"
    catalog = read_json(path)
    require(catalog.get("campaign_id") == campaign_id, "Il catalogo non corrisponde alla campagna attiva.")
    counts = validate_catalog(catalog)
    require(scene_id in catalog["scenes"], "Scena non preparata. Disponibili: " + ", ".join(catalog["scenes"]))
    scene = copy.deepcopy(catalog["scenes"][scene_id])
    result = {"read_only": True, "dm_only": True, "source": catalog["source"], "scene_id": scene_id,
              "scene": scene, "profiles": {k: catalog["profiles"][k] for k in scene["profile_ids"]},
              "catalog": counts, "notice": "Preparazione, non copione: non attiva incontri, non tira dadi e non cambia la fiction."}
    if preflight:
        store = StateStore(root)
        with store.locked():
            state = store._read()
            missing = []
            if (Path(root) / "master" / "pending-operation.json").exists():
                missing.append("Recuperare la transazione interrotta prima di giocare.")
            if state["campaign_id"] != catalog["campaign_id"]:
                missing.append("La campagna salvata non corrisponde al catalogo preparato.")
            if len(state["party"]) != 4:
                missing.append("Completare le quattro schede senza inventare personaggi.")
            if state["combat"]["active"]:
                missing.append("Combattimento gia attivo: questa consultazione non lo sostituisce.")
            result["preflight"] = {"revision": state["revision"], "blockers": missing,
                                   "ready_to_prepare": not missing,
                                   "party": [{"id": p["id"], "name": p["name"], "level": p["level"],
                                              "hp": p["hp"], "max_hp": p["max_hp"]} for p in state["party"]],
                                   "decisions_still_required": scene.get("dm_checks", [])}
    result["preparation_ms"] = round((perf_counter() - started) * 1000, 3)
    return result
