"""Prepared combat tools are exercised only against temporary campaign copies."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError, StateStore
from tools.action_engine import ActionEngine, _monk_weapon
from tools.turn_log import TurnLog
from test_engine import fixture


class ActionEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-actions-")
        self.root = Path(self.temp.name)
        fixture(self.root)
        self.store = StateStore(self.root)
        state, pc = self.store.choose_character("ranger", "Ada")
        pc.update({"class_id": "monk", "class": "Monaco", "inventory": [],
                   "attacks": [{"name": "Colpo senz'armi · arti marziali", "bonus": 5, "damage": "1d4+3"},
                               {"name": "Dardo", "bonus": 5, "damage": "1d4+3"}]})
        self.actor_id = pc["id"]
        self.state, _ = self.store.commit({"party": [pc], "combat": {
            "active": True, "round": 1, "turn_index": 0, "participants": [
                {"id": pc["id"], "name": pc["name"], "initiative": 20,
                 "hp": pc["hp"], "max_hp": pc["max_hp"], "ac": pc["ac"], "conditions": []},
                {"id": "npc_guard", "name": "Guardia", "initiative": 10, "conditions": []}]}}, state["revision"])
        self.private_path = self.root / "master" / "COMBATTIMENTO.json"
        self.private = {"active": True, "id": "test_encounter", "public_revision": self.state["revision"],
                        "creatures": [{"id": "npc_guard", "name": "Nome segreto", "hp": 20, "max_hp": 20,
                                       "ac": 10, "conditions": []}], "pending_reactions": [], "timers": [],
                        "reactions_available": {pc["id"]: True, "npc_guard": True}}
        self.save_private()
        self.engine = ActionEngine(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def save_private(self):
        self.private_path.write_text(json.dumps(self.private), encoding="utf-8")

    def read_private(self):
        return json.loads(self.private_path.read_text(encoding="utf-8"))

    def attack(self, request="attack_001", revision=None, **extra):
        spec = {"actor": "Ada", "target": "Guardia", "attack": "pugno"}
        spec.update(extra)
        return self.engine.resolve_attack(spec, request, self.state["revision"] if revision is None else revision)

    def test_hit_saves_damage_dice_and_private_continuity_once(self):
        with patch("engine.secrets.randbelow", side_effect=[14, 3]):
            result = self.attack()
        self.assertEqual(result["damage"], 7)
        self.assertTrue(result["hit"])
        self.assertEqual(self.read_private()["creatures"][0]["hp"], 13)
        state = self.store.read()
        self.assertEqual(len(state["rolls"]), 2)
        self.assertEqual(state["revision"], self.state["revision"] + 1)
        npc = state["combat"]["participants"][1]
        self.assertNotIn("hp", npc)
        self.assertNotIn("ac", npc)
        encoded = json.dumps(state)
        self.assertNotIn("Nome segreto", encoded)
        self.assertEqual(len(TurnLog(self.root).context()["events"]), 1)

    def test_natural_one_always_misses_without_damage_roll(self):
        with patch("engine.secrets.randbelow", side_effect=[0]) as random:
            result = self.attack()
        self.assertFalse(result["hit"])
        self.assertEqual(result["damage"], 0)
        self.assertEqual(random.call_count, 1)
        self.assertEqual(self.read_private()["creatures"][0]["hp"], 20)

    def test_natural_twenty_doubles_dice_not_modifier(self):
        with patch("engine.secrets.randbelow", side_effect=[19, 3, 2]):
            result = self.attack()
        self.assertTrue(result["critical"])
        self.assertEqual(result["rolls"][1]["expression"], "2d4+3")
        self.assertEqual(result["damage"], 10)

    def test_advantage_keeps_high_d20_and_critical(self):
        with patch("engine.secrets.randbelow", side_effect=[0, 19, 0, 0]):
            result = self.attack(mode="advantage")
        self.assertEqual(result["rolls"][0]["dice"], [1, 20])
        self.assertTrue(result["critical"])

    def test_retry_same_operation_does_not_roll_or_apply_again(self):
        with patch("engine.secrets.randbelow", side_effect=[14, 0]):
            first = self.attack()
        state_after = self.store.state_path.read_bytes()
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("retry rerolled")):
            second = self.attack()
        self.assertTrue(second["already_applied"])
        self.assertEqual(second["rolls"], first["rolls"])
        self.assertEqual(self.store.state_path.read_bytes(), state_after)
        self.assertEqual(len(TurnLog(self.root).context()["events"]), 1)

    def test_duplicate_id_changed_content_and_stale_revision_do_not_roll(self):
        with patch("engine.secrets.randbelow", side_effect=[0]):
            self.attack()
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("invalid request rolled")):
            with self.assertRaises(CampaignError):
                self.attack(mode="advantage")
            with self.assertRaises(CampaignError):
                self.attack(request="different")

    def test_concurrent_duplicate_draws_once(self):
        with patch("engine.secrets.randbelow", side_effect=[0]) as random:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.attack(), range(2)))
        self.assertEqual(random.call_count, 1)
        self.assertEqual(results[0]["rolls"], results[1]["rolls"])

    def test_bonus_unarmed_requires_previous_eligible_attack_and_free_bonus(self):
        with self.assertRaises(CampaignError), patch("tools.action_engine.roll_dice", side_effect=AssertionError()):
            self.attack(action="martial_bonus")
        with patch("engine.secrets.randbelow", side_effect=[0]):
            first = self.attack()
        with patch("engine.secrets.randbelow", side_effect=[14, 0]):
            second = self.attack(request="bonus_001", revision=first["revision"], action="martial_bonus")
        self.assertTrue(second["hit"])
        usage = self.read_private()["turn_usage"]
        self.assertTrue(usage["action_used"])
        self.assertTrue(usage["bonus_action_used"])
        with self.assertRaises(CampaignError), patch("tools.action_engine.roll_dice", side_effect=AssertionError()):
            self.attack(request="bonus_again", revision=second["revision"], action="martial_bonus")

    def test_second_action_not_implicitly_granted(self):
        with patch("engine.secrets.randbelow", side_effect=[0]):
            first = self.attack()
        with self.assertRaises(CampaignError), patch("tools.action_engine.roll_dice", side_effect=AssertionError()):
            self.attack(request="attack_002", revision=first["revision"])

    def test_zero_hp_opens_choice_without_leaking_original_npc_hp(self):
        self.private["creatures"][0].update({"hp": 4, "max_hp": 4})
        self.save_private()
        with patch("engine.secrets.randbelow", side_effect=[14, 3]):
            result = self.attack()
        self.assertEqual(result["outcome"], "nonlethal_choice")
        private = self.read_private()
        self.assertEqual(private["pending_resolution"]["previous_hp"], 4)
        pending = self.store.read()["flags"]["combat_context"]["pending_resolution"]
        self.assertNotIn("previous_hp", pending)
        self.assertNotIn("max_hp", pending)
        with self.assertRaises(CampaignError):
            self.engine.advance_turn({}, "next_001", result["revision"])
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("KO rerolled")):
            ko = self.engine.resolve_zero_hp({"target": "Guardia", "nonlethal": True}, "ko_001", result["revision"])
        self.assertEqual(ko["outcome"], "knocked_out")
        creature = self.read_private()["creatures"][0]
        self.assertTrue(creature["stable"])
        self.assertIn("Privo di sensi", creature["conditions"])
        self.assertNotIn("Morto", creature["conditions"])
        self.assertNotIn("pending_resolution", self.read_private())
        self.assertNotIn("pending_resolution", self.store.read()["flags"]["combat_context"])

    def test_explicit_nonlethal_overrides_massive_damage(self):
        self.private["creatures"][0].update({"hp": 1, "max_hp": 1})
        self.save_private()
        with patch("engine.secrets.randbelow", side_effect=[14, 3]):
            result = self.attack(nonlethal=True)
        self.assertEqual(result["outcome"], "knocked_out")

    def test_concentrating_target_gets_save_window_even_when_temporary_hp_absorbs_damage(self):
        self.private["creatures"][0]["concentration"] = {"spell": "Secret"}
        self.private["creatures"][0]["temporary_hp"] = 9
        self.save_private()
        with patch("engine.secrets.randbelow", side_effect=[14, 3]):
            result = self.attack()
        self.assertEqual(result["outcome"], "concentration_save")
        self.assertEqual(self.read_private()["pending_resolution"]["dc"], 10)
        self.assertEqual(self.read_private()["creatures"][0]["hp"], 20)
        with self.assertRaises(CampaignError):
            self.engine.advance_turn({}, "next_blocked", result["revision"])

    def test_lethal_npc_can_use_death_saves_when_dm_explicitly_selects(self):
        self.private["creatures"][0].update({"hp": 4, "max_hp": 4})
        self.save_private()
        with patch("engine.secrets.randbelow", side_effect=[14, 3]):
            result = self.attack(nonlethal=False, death_saves=True)
        self.assertEqual(result["outcome"], "death_saves")
        self.assertNotIn("Morto", self.read_private()["creatures"][0]["conditions"])

    def test_ranged_nonlethal_rejected_before_rng(self):
        with self.assertRaises(CampaignError), patch("tools.action_engine.roll_dice", side_effect=AssertionError()):
            self.attack(attack="Dardo", melee=False, nonlethal=True)

    def test_reaction_requires_explicit_window_check_before_rng(self):
        self.private["creatures"][0]["reaction"] = "Parata con arma in mischia"
        self.save_private()
        with self.assertRaises(CampaignError), patch("tools.action_engine.roll_dice", side_effect=AssertionError()):
            self.attack()
        with patch("engine.secrets.randbelow", side_effect=[0]):
            result = self.attack(reactions_checked=True)
        self.assertFalse(result["hit"])

    def test_resistance_not_silently_ignored(self):
        self.private["creatures"][0]["resistances"] = ["contundente"]
        self.save_private()
        with self.assertRaises(CampaignError), patch("tools.action_engine.roll_dice", side_effect=AssertionError()):
            self.attack()

    def test_unknown_private_target_cannot_leak_to_public_rolls(self):
        self.private["creatures"].append({"id": "npc_secret", "name": "Cultista segreto", "hp": 4, "max_hp": 4, "ac": 10})
        self.save_private()
        with self.assertRaises(CampaignError), patch("tools.action_engine.roll_dice", side_effect=AssertionError()):
            self.attack(target="npc_secret")

    def test_temporary_hp_absorbed_before_real_hp(self):
        self.private["creatures"][0]["temporary_hp"] = 5
        self.save_private()
        with patch("engine.secrets.randbelow", side_effect=[14, 3]):
            self.attack()
        creature = self.read_private()["creatures"][0]
        self.assertEqual(creature["hp"], 18)
        self.assertEqual(creature["temporary_hp"], 0)

    def test_advance_changes_initiative_only_and_resets_reaction(self):
        original_party = copy.deepcopy(self.store.read()["party"])
        result = self.engine.advance_turn({"actor": "Ada"}, "next_001", self.state["revision"])
        state = self.store.read()
        self.assertEqual(result["actor_id"], "npc_guard")
        self.assertEqual(state["combat"]["turn_index"], 1)
        self.assertEqual(state["party"], original_party)
        self.assertTrue(self.read_private()["reactions_available"]["npc_guard"])
        self.assertEqual(state["clock"], self.state["clock"])

    def test_legacy_pending_knockout_resolves_without_new_dice(self):
        creature = self.private["creatures"][0]
        creature.update({"hp": 0, "max_hp": 4, "concentration": {"spell": "Secret"}, "zero_hp_resolution": {
            "pending": True, "attacker_id": self.actor_id, "damage": 7, "previous_hp": 4, "nonlethal": None}})
        self.private["pending_resolution"] = {"type": "melee_nonlethal_choice", "actor_id": self.actor_id,
                                               "target_id": "npc_guard", "damage": 7, "attack": "Testata", "roll_ids": []}
        self.save_private()
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("Legacy KO rerolled")):
            result = self.engine.resolve_zero_hp({"target": "Guardia", "nonlethal": True}, "ko_legacy", self.state["revision"])
        self.assertEqual(result["outcome"], "knocked_out")
        self.assertNotIn("concentration", self.read_private()["creatures"][0])

    def test_monk_weapon_names_do_not_match_heavy_weapon_substrings(self):
        for name in ("Ascia grande", "Lancia lunga", "Mazzafrusto", "Spada lunga"):
            self.assertFalse(_monk_weapon(name), name)
        for name in ("Spada corta · accurata", "Bastone", "Pugno"):
            self.assertTrue(_monk_weapon(name), name)

    def test_zero_hp_pc_can_end_turn_only_after_its_death_save_marker(self):
        state = self.store.read()
        state["party"][0].update({"hp": 0, "conditions": ["Privo di sensi", "A terra"]})
        state["combat"]["participants"][0].update({"hp": 0, "conditions": ["Privo di sensi", "A terra"]})
        state, _ = self.store.commit({"party": state["party"], "combat": state["combat"]}, state["revision"])
        with self.assertRaises(CampaignError):
            self.engine.advance_turn({}, "next_needs_save", state["revision"])
        self.private["death_save_turn"] = {"actor_id": self.actor_id, "round": 1, "turn_index": 0}
        self.save_private()
        result = self.engine.advance_turn({}, "next_after_save", state["revision"])
        self.assertEqual(result["actor_id"], "npc_guard")
        self.assertNotIn("death_save_turn", self.read_private())

    def test_round_wrap_accounts_for_six_seconds_and_clock_midnight(self):
        state = self.store.read()
        state["combat"].update({"turn_index": 1, "round": 10})
        state, _ = self.store.commit({"combat": state["combat"], "clock": {"time": "23:59"}}, state["revision"])
        self.private.update({"elapsed_seconds": 54, "round_clock_remainder_seconds": 54})
        self.save_private()
        result = self.engine.advance_turn({}, "next_midnight", state["revision"])
        self.assertEqual(result["round"], 11)
        self.assertEqual(self.store.read()["clock"]["time"], "00:00")
        self.assertEqual(self.store.read()["clock"]["day"], 2)
        self.assertEqual(self.read_private()["elapsed_seconds"], 60)


if __name__ == "__main__":
    unittest.main()
