"""XP and explicit advancement remain transactional, without spending choices."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from character_builder import build_character
from engine import CampaignError, StateStore, validate_character
from test_engine import fixture


class SourceProgressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-progression-")
        self.root = Path(self.temp.name)
        fixture(self.root, party_size=4)
        self.store = StateStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def fill_group(self):
        for name in ("Ada", "Bruno", "Cleo", "Dario"):
            state, _ = self.store.choose_character("ranger", name)
        return state

    def test_new_characters_have_zero_xp_and_old_sheets_remain_accepted(self):
        character = build_character({"class_id": "fighter", "species_id": "human", "name": "Ada"})
        self.assertEqual(character["xp"], 0)
        validate_character(character)
        character.pop("xp")
        validate_character(character)
        _, prepared = self.store.choose_character("ranger", "Bruno")
        self.assertEqual(prepared["xp"], 0)

    def test_bad_xp_cannot_damage_a_saved_character(self):
        state, _ = self.store.choose_character("ranger", "Ada")
        for invalid in (-1, 0.5, True, "300", None, 10**9 + 1):
            with self.subTest(xp=invalid), self.assertRaises(CampaignError):
                self.store.commit({"character": {"xp": invalid}}, state["revision"])
            self.assertEqual(self.store.read(), state)

    def test_awarding_xp_does_not_auto_level_heal_or_choose_features(self):
        state, _ = self.store.choose_character("ranger", "Ada")
        state, _ = self.store.commit({"character": {"hp": 3, "resources": [
            {**state["character"]["resources"][0], "current": 0}]}}, state["revision"])
        before = copy.deepcopy(state["character"])
        state, _ = self.store.commit({"character": {"xp": 6500}}, state["revision"])
        self.assertEqual(state["character"], {**before, "xp": 6500})
        self.assertEqual(state["party"][0], state["character"])

    def test_levels_two_through_five_accept_explicit_class_resources_and_preserve_other_pcs(self):
        state = self.fill_group()
        others = copy.deepcopy(state["party"][1:])
        for level, xp in ((2, 300), (3, 900), (4, 2700), (5, 6500)):
            state, _ = self.store.commit({"character": {
                "level": level, "xp": xp, "max_hp": 12 + (level - 1) * 8,
                "proficiency": 3 if level == 5 else 2,
                "resources": [
                    {"id": "hit_die", "name": "Dadi vita d10", "current": 1, "max": level, "reset": "long"},
                    {"id": "wind", "name": f"Recuperare energie · 1d10+{level}", "current": 0, "max": 1, "reset": "short"},
                    {"id": "surge", "name": "Azione impetuosa", "current": 1, "max": 1, "reset": "short"}]}},
                state["revision"])
            self.assertEqual(state["character"]["hp"], 12, "A level change is not a rest")
            self.assertEqual(state["character"]["xp"], xp)
            self.assertEqual(state["character"]["resources"][1]["current"], 0)
            self.assertEqual(state["party"][1:], others)
            self.assertEqual(state["party"][0], state["character"])

    def test_party_total_is_shared_with_explicit_rounding_and_no_healing(self):
        state = self.fill_group()
        state, _ = self.store.commit({"character": {"hp": 3}}, state["revision"])
        before = copy.deepcopy(state["party"])
        state, result = self.store.award_xp(25, "risolto_01", "Un ostacolo superato", state["revision"])
        self.assertEqual([member["xp"] for member in state["party"]], [6] * 4)
        self.assertEqual(result["award"]["remainder"], 1)
        self.assertEqual(result["award"]["total_awarded"], 24)
        for old, member in zip(before, state["party"]):
            self.assertEqual(member, {**old, "xp": 6})
        self.assertEqual(state["character"], state["party"][0])
        self.assertIn("1 XP non assegnati", state["journal"][-1]["text"])

    def test_per_character_reward_is_idempotent_and_rejects_stale_or_reused_id(self):
        state = self.fill_group()
        revision = state["revision"]
        state, result = self.store.award_xp(75, "risolto_02", "Scelta riuscita", revision, per_character=True)
        self.assertFalse(result["already_awarded"])
        self.assertEqual([member["xp"] for member in state["party"]], [75] * 4)
        self.assertEqual(result["award"]["total_awarded"], 300)
        self.assertEqual(result["award"]["remainder"], 0)
        backups = len(list((self.root / "saves").glob("campaign-*.json")))
        again, result = self.store.award_xp(75, "risolto_02", "Scelta riuscita", state["revision"], per_character=True)
        self.assertTrue(result["already_awarded"])
        self.assertEqual(again, state)
        self.assertEqual(len(list((self.root / "saves").glob("campaign-*.json"))), backups)
        with self.assertRaises(CampaignError) as conflict:
            self.store.award_xp(75, "risolto_02", "Scelta riuscita", revision, per_character=True)
        self.assertEqual(conflict.exception.code, "revision_conflict")
        for amount, label, per_character in ((80, "Scelta riuscita", True),
                                             (75, "Un altro premio", True), (75, "Scelta riuscita", False)):
            with self.assertRaises(CampaignError):
                self.store.award_xp(amount, "risolto_02", label, state["revision"], per_character=per_character)
        self.assertEqual(self.store.read(), state)

    def test_legacy_sheets_gain_xp_and_restored_ledger_prevents_duplicate_awards(self):
        state = self.fill_group()
        party = copy.deepcopy(state["party"])
        for member in party:
            member.pop("xp")
        state, _ = self.store.commit({"party": party}, state["revision"])
        state, _ = self.store.award_xp(275, "risolto_03", "Un incarico risolto", state["revision"], per_character=True)
        imported, _ = self.store.restore(state, state["revision"])
        repeated, result = self.store.award_xp(275, "risolto_03", "Un incarico risolto", imported["revision"], per_character=True)
        self.assertTrue(result["already_awarded"])
        self.assertEqual(repeated, imported)
        self.assertEqual([member["xp"] for member in repeated["party"]], [275] * 4)
        self.assertEqual(repeated["character"], repeated["party"][0])

    def test_award_cli_uses_total_by_default_and_validates_before_writing(self):
        with self.assertRaises(CampaignError):
            self.store.award_xp(300, "incompleto", "Un premio", 0)
        state = self.fill_group()
        def cli(*args):
            process = subprocess.run([sys.executable, str(ROOT / "tools" / "dnd.py"), "--root", str(self.root),
                                      "award-xp", *args], capture_output=True, timeout=15)
            return process.returncode, json.loads(process.stdout or process.stderr)
        code, result = cli("300", "--award-id", "risolto_04", "--label", "Un obiettivo raggiunto",
                           "--expected-revision", str(state["revision"]))
        self.assertEqual(code, 0, result)
        self.assertEqual([member["xp"] for member in result["party_xp"]], [75] * 4)
        self.assertEqual(result["award"]["mode"], "party_total")
        before = self.store.read()
        code, result = cli("75", "--per-character", "--award-id", "risolto_05", "--label", "Un premio successivo",
                           "--expected-revision", str(state["revision"]))
        self.assertEqual(code, 1)
        self.assertEqual(result["code"], "revision_conflict")
        self.assertEqual(self.store.read(), before)

    def test_visible_npc_can_join_initiative_without_revealing_secret_stats(self):
        state = self.fill_group()
        member = state["party"][0]
        pg = {key: member[key] for key in ("id", "name", "hp", "max_hp", "ac")}
        pg["initiative"] = 14
        npc = {"id": "sagoma_01", "name": "Sagoma tra gli alberi", "initiative": 12}
        state, _ = self.store.commit({"combat": {"active": True, "round": 1,
            "turn_index": 0, "participants": [pg, npc]}}, state["revision"])
        self.assertEqual(self.store.table()["state"]["combat"]["participants"][1], npc)
        self.assertFalse({"hp", "max_hp", "ac"} & set(npc))
        state, _ = self.store.commit({"combat": {"participants": [pg, {**npc, "ac": 14}]}}, state["revision"])
        self.assertEqual(state["combat"]["participants"][1]["ac"], 14)

    def test_optional_npc_stats_never_allow_missing_pc_stats_or_invalid_values(self):
        state = self.fill_group()
        member = state["party"][0]
        pg = {key: member[key] for key in ("id", "name", "hp", "max_hp", "ac")}
        pg["initiative"] = 14
        npc = {"id": "sagoma_01", "name": "Sagoma tra gli alberi", "initiative": 12}
        invalid = [
            [pg, {**npc, "hp": 3}], [pg, {**npc, "max_hp": 5}],
            [pg, {**npc, "hp": 6, "max_hp": 5}], [pg, {**npc, "ac": 0}],
            [pg, {**npc, "hidden": True}],
            [{key: value for key, value in pg.items() if key not in {"hp", "max_hp", "ac"}}, npc],
            [{key: value for key, value in pg.items() if key != "ac"}, npc]]
        for participants in invalid:
            with self.subTest(participants=participants), self.assertRaises(CampaignError):
                self.store.commit({"combat": {"active": True, "round": 1,
                    "turn_index": 0, "participants": participants}}, state["revision"])
            self.assertEqual(self.store.read(), state)

    def test_life_drain_can_record_zero_maximum_only_for_a_dead_character(self):
        state = self.fill_group()
        state, _ = self.store.commit({"character": {"hp": 0, "max_hp": 0,
            "conditions": ["Morto"]}}, state["revision"])
        self.assertEqual(state["character"]["max_hp"], 0)
        self.assertEqual(state["character"]["hp"], 0)
        self.assertEqual(state["character"], state["party"][0])
        for patch in ({"hp": 1}, {"conditions": []}, {"conditions": ["incosciente"]}):
            with self.subTest(patch=patch), self.assertRaises(CampaignError):
                self.store.commit({"character": patch}, state["revision"])
            self.assertEqual(self.store.read(), state)

    def test_zero_maximum_for_living_or_positive_hp_character_is_rejected(self):
        state = self.fill_group()
        for patch in ({"hp": 0, "max_hp": 0},
                      {"hp": 0, "max_hp": 0, "conditions": ["incosciente"]},
                      {"hp": 1, "max_hp": 0, "conditions": ["Morto"]}):
            with self.subTest(patch=patch), self.assertRaises(CampaignError):
                self.store.commit({"character": patch}, state["revision"])
            self.assertEqual(self.store.read(), state)

    def test_dead_zero_maximum_combatants_remain_consistent_and_cannot_be_healed(self):
        state = self.fill_group()
        member = state["party"][0]
        pg = {key: member[key] for key in ("id", "name", "ac")}
        pg.update(hp=0, max_hp=0, initiative=14, conditions=["MORTO"])
        npc = {"id": "creatura_01", "name": "Creatura caduta", "initiative": 12,
               "hp": 0, "max_hp": 0, "conditions": ["morto"]}
        state, _ = self.store.commit({"character": {"hp": 0, "max_hp": 0, "conditions": ["MORTO"]},
            "combat": {"active": True, "round": 1, "turn_index": 0,
                       "participants": [pg, npc]}}, state["revision"])
        self.assertEqual(state["party"][0]["max_hp"], 0)
        self.assertEqual(state["combat"]["participants"][0]["max_hp"], 0)
        for invalid_npc in ({**npc, "conditions": []}, {**npc, "conditions": ["incosciente"]},
                            {**npc, "hp": 1}):
            with self.subTest(npc=invalid_npc), self.assertRaises(CampaignError):
                self.store.commit({"combat": {"participants": [pg, invalid_npc]}}, state["revision"])
            self.assertEqual(self.store.read(), state)
        with self.assertRaises(CampaignError):
            self.store.commit({"character": {"hp": 1},
                "combat": {"participants": [{**pg, "hp": 1}, npc]}}, state["revision"])
        self.assertEqual(self.store.read(), state)


if __name__ == "__main__":
    unittest.main()
