"""Character rules and transactional creation; all saves stay in temporary folders."""
from __future__ import annotations

import copy
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from character_builder import ABILITY_IDS, BACKGROUNDS, CLASSES, SKILLS, SPECIES, build_character, catalog
from engine import CampaignError, StateStore, validate_character
from server import LocalServer
from test_engine import fixture


def payload(class_id="fighter", species_id="human", name="Un avventuriero"):
    return {"class_id": class_id, "species_id": species_id, "name": name}


class BuilderRulesTests(unittest.TestCase):
    def test_every_class_and_species_has_legal_level_one_sheet(self):
        for class_id, cls in CLASSES.items():
            for species_id, species in SPECIES.items():
                with self.subTest(class_id=class_id, species_id=species_id):
                    c = build_character(payload(class_id, species_id))
                    validate_character(c)
                    self.assertEqual(c["level"], 1)
                    self.assertEqual(c["proficiency"], 2)
                    base = cls["recommended_abilities"]
                    self.assertEqual(c["abilities"], {k: base[k] + species["bonuses"].get(k, 0) for k in ABILITY_IDS})
                    con = (c["abilities"]["con"] - 10) // 2
                    self.assertEqual(c["max_hp"], cls["hit_die"] + con + (species_id == "hill_dwarf") + (class_id == "sorcerer"))
                    self.assertEqual(c["hp"], c["max_hp"])
                    for ability in ABILITY_IDS:
                        self.assertEqual(c["saving_throws"][ability], (c["abilities"][ability] - 10) // 2 + (2 if ability in cls["saving_throws"] else 0))
                    self.assertEqual(len(c["background_skills"]), 2)
                    self.assertTrue(c["features"])

    def test_actual_srd_armor_formulas_and_heavy_armor_requirement(self):
        def ac(kind):
            return build_character(payload(kind))
        self.assertEqual(ac("barbarian")["ac"], 14)  # Dex 14 + Con 15 -> 2 + 2
        self.assertEqual(ac("monk")["ac"], 15)  # Dex 16 + Wis 15
        self.assertEqual(ac("sorcerer")["ac"], 15)  # Natural AC 13 + Dex 14
        self.assertEqual(ac("wizard")["ac"], 12)
        for kind in ("fighter", "cleric", "paladin"):
            self.assertEqual(ac(kind)["ac"], 18)
        custom = payload("fighter")
        custom["abilities"] = dict(zip(ABILITY_IDS, [8, 15, 14, 13, 12, 10]))
        human = build_character(custom)
        self.assertEqual(human["speed"], 6)
        custom["species_id"] = "hill_dwarf"
        self.assertEqual(build_character(custom)["speed"], 7.5)

    def test_standard_array_is_really_player_assignable(self):
        request = payload("wizard", "high_elf")
        request["abilities"] = dict(zip(ABILITY_IDS, [10, 15, 12, 14, 8, 13]))
        c = build_character(request)
        self.assertEqual(c["abilities"], dict(zip(ABILITY_IDS, [10,17,12,15,8,13])))
        self.assertEqual(c["ac"], 13)
        self.assertEqual(c["spells"]["dc"], 12)
        self.assertEqual(len(c["spells"]["prepared"]), 3)
        self.assertEqual(c["creation"]["base_abilities"], request["abilities"])

    def test_level_one_magic_counts_and_no_phantom_attack_rolls(self):
        expectations = {"bard": (2,4,2), "cleric": (3,0,2), "druid": (2,0,2),
                        "sorcerer": (4,2,2), "warlock": (2,2,1), "wizard": (3,6,2)}
        for kind, (cantrips, known, slots) in expectations.items():
            c = build_character(payload(kind))
            self.assertEqual(len(c["spells"]["cantrips"]), cantrips)
            self.assertEqual(len(c["spells"]["known"]), known)
            slot = next(r for r in c["resources"] if "slot" in r["id"])
            self.assertEqual(slot["current"], slots)
            self.assertEqual(slot["reset"], "short" if kind == "warlock" else "long")
        for kind in ("barbarian", "fighter", "monk", "paladin", "ranger", "rogue"):
            self.assertFalse(any("slot" in r["id"] for r in build_character(payload(kind))["resources"]))
        for kind in ("bard", "cleric"):
            attacks = build_character(payload(kind))["attacks"]
            self.assertFalse(any("Fiamma Sacra" in a["name"] or "Beffa Crudele" in a["name"] for a in attacks))
        firebolt = next(a for a in build_character(payload("wizard"))["attacks"] if a["name"].startswith("Dardo di Fuoco"))
        self.assertEqual(firebolt["damage"], "1d10+0")

    def test_spells_prepared_have_minimum_one_for_low_mental_score(self):
        for kind, mental in (("cleric","wis"), ("druid","wis"), ("wizard","int")):
            request = payload(kind)
            request["abilities"] = dict(zip(ABILITY_IDS, [15,14,13,12,10,8]))
            swap = next(k for k, value in request["abilities"].items() if value == 8)
            request["abilities"][swap], request["abilities"][mental] = request["abilities"][mental], 8
            c = build_character(request)
            self.assertEqual(len(c["spells"]["prepared"]), 3 if kind == "cleric" else 1)

    def test_rogue_expertise_and_duplicate_proficiencies(self):
        c = build_character(payload("rogue", "high_elf"))
        self.assertEqual(c["skills"]["stealth"], 7)
        self.assertEqual(c["skills"]["sleight_of_hand"], 7)
        # Four class, one species, two background; no proficiency disappears.
        trained = [key for key, (_, ability) in SKILLS.items()
                   if c["skills"][key] > (c["abilities"][ability]-10)//2]
        self.assertEqual(len(trained), 7)
        self.assertEqual(len(set(c["proficiencies"]["languages"])), len(c["proficiencies"]["languages"]))

    def test_small_barbarian_has_no_heavy_starting_weapon(self):
        for species in ("lightfoot_halfling", "rock_gnome"):
            c = build_character(payload("barbarian", species))
            self.assertTrue(c["attacks"][0]["name"].startswith("Ascia da battaglia"))
            self.assertEqual(c["attacks"][0]["damage"].split("+")[0], "1d10")

    def test_elf_martial_spell_metadata_has_real_intelligence_bonus(self):
        c = build_character(payload("fighter", "high_elf"))
        self.assertEqual(c["spells"]["ability"], "int")
        self.assertEqual(c["spells"]["dc"], 9)
        self.assertEqual(c["spells"]["attack_bonus"], 1)
        self.assertEqual(len(c["spells"]["cantrips"]), 1)
        self.assertIn("non richiede attacchi", c["spells"]["notes"])

    def test_invalid_user_choices_are_rejected(self):
        wrong = [
            {"class_id": "artificer"}, {"class_id": []}, {"species_id": "dragon"}, {"species_id": {}},
            {"name": ""}, {"name": "a" * 81}, {"description": "x"*2001}, {"name": "x\x00y"},
            {"abilities": dict.fromkeys(ABILITY_IDS, 15)},
            {"abilities": dict(zip(ABILITY_IDS,[15,14,13,12,10,True]))},
            {"abilities": {"str":15}}, {"skills": ["arcana","history"]},
            {"skills": ["athletics","athletics"]}, {"skills": ["athletics"]},
            {"skills": [[],"perception"]}, {"background_id":"inventato"}, {"gold":999999},
        ]
        for patch in wrong:
            with self.subTest(patch=patch):
                with self.assertRaises(ValueError):
                    build_character({**payload(), **patch})

    def test_catalog_returns_independent_metadata(self):
        public = catalog()
        self.assertEqual(len(public["classes"]), 12)
        self.assertEqual(len(public["species"]), 5)
        public["classes"][0]["recommended_abilities"]["str"] = 99
        self.assertEqual(CLASSES["barbarian"]["recommended_abilities"]["str"], 15)


class BuilderStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        fixture(self.root, party_size=4)
        self.store = StateStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_four_players_can_repeat_classes_and_then_edit_preserving_everything(self):
        state = None
        for index in range(4):
            state, _ = self.store.create_character(payload("bard", "human", f"Bardo {index+1}"))
        self.assertEqual(state["phase"], "playing")
        self.assertEqual(len({c["id"] for c in state["party"]}), 4)
        self.assertTrue(self.store.character_options()["can_edit_characters"])
        state, pending = self.store.queue_action("Tutti: ci presentiamo")
        state, _ = self.store.roll("1d20", "Prova dei dadi")
        old = copy.deepcopy(state)
        changed_id = state["party"][2]["id"]
        state, c = self.store.rebuild_character(changed_id, payload("monk", "hill_dwarf", "Nuovo"), state["revision"])
        self.assertEqual(c["id"], changed_id)
        self.assertEqual(state["party"][:2], old["party"][:2])
        self.assertEqual(state["party"][3], old["party"][3])
        self.assertEqual(state["character"], old["character"])
        for key in ("pending_actions","rolls","scene","quests","discovered","clock"):
            self.assertEqual(state[key], old[key])
        self.assertEqual(state["pending_actions"][0]["id"], pending["id"])
        with self.assertRaises(CampaignError): self.store.create_character(payload())

    def test_rebuild_active_character_updates_mirror_and_legacy_template(self):
        state, old = self.store.choose_character("ranger")
        state, new = self.store.rebuild_character(old["id"], payload("warlock"), state["revision"])
        self.assertEqual(state["active_character_id"], old["id"])
        self.assertEqual(state["character"], new)
        self.assertEqual(state["phase"], "creation")
        self.assertNotIn("template_id", new)

    def test_stale_rebuild_does_not_write_or_restore_resources(self):
        state, c = self.store.create_character(payload())
        revision = state["revision"]
        self.store.note("Un appunto")
        current = self.store.read()
        with self.assertRaises(CampaignError) as error:
            self.store.rebuild_character(c["id"], payload("wizard"), revision)
        self.assertEqual(error.exception.code,"revision_conflict")
        self.assertEqual(self.store.read(), current)

    def test_master_consequence_locks_editor_even_without_journal_event(self):
        for _ in range(4): state, c = self.store.create_character(payload())
        state, _ = self.store.commit({"scene":{"text":"Siete ora al portone."}},state["revision"])
        self.assertFalse(self.store.character_options()["can_edit_characters"])
        current = copy.deepcopy(state)
        with self.assertRaises(CampaignError):
            self.store.rebuild_character(c["id"],payload("wizard"),state["revision"])
        self.assertEqual(self.store.read(),current)

    def test_invalid_build_and_unknown_character_preserve_save(self):
        state, _ = self.store.create_character(payload())
        with self.assertRaises(CampaignError): self.store.create_character({**payload(),"skills":[]})
        self.assertEqual(self.store.read(),state)
        with self.assertRaises(CampaignError): self.store.rebuild_character("pc_unknown",payload(),state["revision"])
        self.assertEqual(self.store.read(),state)


class BuilderHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        fixture(self.root, party_size=4)
        self.server = LocalServer(("127.0.0.1",0), self.root)
        self.thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, data=None):
        connection = http.client.HTTPConnection("127.0.0.1",self.server.server_port,timeout=3)
        body = json.dumps(data) if data is not None else None
        connection.request(method,path,body,{"Content-Type":"application/json"})
        response = connection.getresponse()
        result = json.loads(response.read())
        connection.close()
        return response.status,result

    def test_options_create_rebuild_revision_and_mixed_template_fields(self):
        status, options = self.request("GET","/api/character-options")
        self.assertEqual(status,200)
        self.assertEqual(len(options["classes"]),12)
        status, result = self.request("POST","/api/character",payload("barbarian","hill_dwarf","Kara"))
        self.assertEqual(status,200)
        old = result["character"]
        status, result = self.request("POST","/api/character-rebuild",{**payload("wizard","high_elf","Luce"),"character_id":old["id"],"expected_revision":1})
        self.assertEqual(status,200)
        self.assertEqual(result["character"]["id"],old["id"])
        self.assertEqual(result["state"]["character"]["class"],"Mago")
        status, _ = self.request("POST","/api/character-rebuild",{**payload(),"character_id":old["id"],"expected_revision":1})
        self.assertEqual(status,409)
        status, _ = self.request("POST","/api/character",{**payload(),"template_id":"ranger"})
        self.assertEqual(status,400)
        status, _ = self.request("POST","/api/character-rebuild",{**payload(),"character_id":old["id"]})
        self.assertEqual(status,400)


if __name__ == "__main__":
    unittest.main()
