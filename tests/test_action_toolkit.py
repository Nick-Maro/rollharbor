"""Atomic spells/contests/effects on temporary tables; never the real save."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from engine import CampaignError, StateStore
from tools.action_engine import ActionEngine
from tools.action_toolkit import ActionToolkit, ToolkitOps
from tools.encounter_prep import inspect_scene, validate_catalog
from tools.turn_log import TurnLog
from test_engine import fixture

ROOT = Path(__file__).resolve().parents[1]


class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-toolkit-")
        self.root = Path(self.temp.name)
        fixture(self.root)
        self.store = StateStore(self.root)
        state, pc = self.store.choose_character("ranger", "Ada")
        pc.update(class_id="druid", hp=3,
                  spells={"ability": "wis", "dc": 11,
                          "prepared": ["Parola Guaritrice", "Cura Ferite", "Intralciare"]},
                  resources=[{"id": "spell_slot_1", "name": "Slot 1", "current": 2, "max": 2, "reset": "long"}])
        self.actor_id = pc["id"]
        state, _ = self.store.commit({"party": [pc], "combat": {
            "active": True, "round": 1, "turn_index": 0, "participants": [
                {"id": pc["id"], "name": "Ada", "initiative": 20, "hp": pc["hp"], "max_hp": pc["max_hp"], "ac": pc["ac"], "conditions": []},
                {"id": "guard", "name": "Guardia", "initiative": 10, "conditions": []}]}}, state["revision"])
        self.private = {"creatures": [{"id": "guard", "name": "Nome segreto", "hp": 20, "max_hp": 20, "ac": 15,
                                      "abilities": {"str": 13, "dex": 10}, "conditions": []}],
                        "pending_reactions": [], "timers": []}
        self.path = self.root / "master" / "COMBATTIMENTO.json"
        self.write_private()
        self.tool = ActionToolkit(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def write_private(self):
        self.path.write_text(json.dumps(self.private), encoding="utf-8")

    def private_now(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def cast_plan(self, spell="healing-word"):
        return {"actor": "Ada", "target": "Ada", "spell": spell, "slot_level": 1, "distance_m": 0,
                "checks": {k: True for k in ["declared", "components", "reactions", "modifiers", "bonus_spell_rule",
                                             "range", "target_type", "visibility", "area", "all_creatures", "concentration_choice"]}}

    def run_cast(self, spec=None, ident="cast"):
        return self.tool.heal_spell(spec or self.cast_plan(), ident, self.store.read()["revision"])

    def entangle(self, ident="entangle"):
        spec = self.cast_plan("entangle")
        spec.update(area={"description": "Quadrato sul terreno davanti al carro", "side_m": 6},
                    targets=[{"target": "Guardia"}])
        return self.tool.entangle(spec, ident, self.store.read()["revision"])

    def contest_plan(self, kind="grapple"):
        return {"actor": "Ada", "target": "Guardia", "kind": kind, "defense": "athletics", "distance_m": 1.5,
                "checks": {k: True for k in ["declared", "range", "modifiers", "reactions", "defense_choice", "size", "free_hand"]}}

    def test_healing_roll_slot_action_hp_and_journal_once(self):
        revision = self.store.read()["revision"]
        with patch("engine.secrets.randbelow", return_value=2):
            result = self.run_cast()
        self.assertEqual(result["healed"], 4)
        pc = self.store.read()["character"]
        self.assertEqual(pc["hp"], 7)
        self.assertEqual(pc["resources"][0]["current"], 1)
        self.assertTrue(self.private_now()["turn_usage"]["bonus_action_used"])
        self.assertEqual(TurnLog(self.root).context()["total_events"], 1)
        with patch("tools.action_toolkit.roll_dice", side_effect=AssertionError("reroll")):
            replay = self.tool.heal_spell(self.cast_plan(), "cast", revision)
        self.assertTrue(replay["already_applied"])
        self.assertEqual(replay["rolls"], result["rolls"])
        self.assertIn("timings_ms", result)

    def test_stale_revision_and_missing_components_stop_before_rng(self):
        plan = self.cast_plan()
        plan["checks"].pop("components")
        before = self.store.state_path.read_bytes()
        with patch("tools.action_toolkit.roll_dice", side_effect=AssertionError("dice")):
            with self.assertRaises(CampaignError):
                self.run_cast(plan)
            with self.assertRaises(CampaignError):
                self.tool.heal_spell(self.cast_plan(), "stale", 0)
        self.assertEqual(self.store.state_path.read_bytes(), before)

    def test_preflight_is_read_only_and_does_not_roll(self):
        before = self.store.state_path.read_bytes()
        private = self.path.read_bytes()
        with patch("engine.secrets.randbelow", side_effect=AssertionError("dice")):
            result = self.tool.preflight("heal-spell", self.cast_plan())
        self.assertTrue(result["ready"])
        self.assertEqual(self.store.state_path.read_bytes(), before)
        self.assertEqual(self.path.read_bytes(), private)
        self.assertFalse(self.tool.ops.receipts_path.exists())

    def test_no_slot_and_out_of_range_fail_before_rng(self):
        plan = self.cast_plan()
        plan["distance_m"] = 19
        with patch("tools.action_toolkit.roll_dice", side_effect=AssertionError("dice")):
            with self.assertRaises(CampaignError):
                self.run_cast(plan)
        state = self.store.read()
        pc = state["character"]
        pc["resources"][0]["current"] = 0
        self.store.commit({"party": [pc]}, state["revision"])
        with patch("tools.action_toolkit.roll_dice", side_effect=AssertionError("dice")):
            with self.assertRaises(CampaignError):
                self.run_cast()

    def test_bonus_spell_blocks_other_levelled_cast(self):
        with patch("engine.secrets.randbelow", return_value=1):
            self.run_cast()
        with patch("tools.action_toolkit.roll_dice", side_effect=AssertionError("dice")):
            with self.assertRaises(CampaignError):
                self.run_cast(self.cast_plan("cure-wounds"), "second")

    def test_grapple_tie_fails_and_does_not_grant_martial_bonus(self):
        # Ada STR+3, guard STR+1: 5+3 = 7+1.
        with patch("engine.secrets.randbelow", side_effect=[4, 6]):
            result = self.tool.contest(self.contest_plan(), "tie", self.store.read()["revision"])
        self.assertFalse(result["success"])
        self.assertNotIn("Afferrato", self.private_now()["creatures"][0]["conditions"])
        self.assertFalse(self.private_now()["turn_usage"]["martial_arts_eligible"])

    def test_grapple_requires_defender_choice_and_free_hand_before_rng(self):
        for key in ("defense_choice", "free_hand"):
            plan = self.contest_plan()
            plan["checks"][key] = False
            with patch("tools.action_toolkit.roll_dice", side_effect=AssertionError("dice")):
                with self.assertRaises(CampaignError):
                    self.tool.contest(plan, "missing_" + key, self.store.read()["revision"])

    def test_grapple_success_keeps_npc_hp_and_name_private(self):
        with patch("engine.secrets.randbelow", side_effect=[18, 0]):
            result = self.tool.contest(self.contest_plan(), "grapple", self.store.read()["revision"])
        self.assertTrue(result["success"])
        state = self.store.read()
        self.assertIn("Afferrato", state["combat"]["participants"][1]["conditions"])
        self.assertNotIn("hp", state["combat"]["participants"][1])
        self.assertNotIn("Nome segreto", json.dumps(state))

    def test_escape_uses_new_contest_and_preserves_on_tie(self):
        self.private["grapples"] = {self.actor_id: {"grappler_id": "guard", "reach_m": 1.5}}
        self.write_private()
        plan = self.contest_plan("escape")
        plan["actor_skill"] = "acrobatics"
        with patch("engine.secrets.randbelow", side_effect=[0, 0]):
            result = self.tool.contest(plan, "escape", self.store.read()["revision"])
        self.assertTrue(result["success"])  # DEX+2 beats STR+1 even at natural 1.
        self.assertIsNone(self.private_now()["grapples"][self.actor_id])
        self.assertEqual(self.private_now()["turn_usage"]["action_kind"], "escape")

    def test_entangle_tracks_slot_conditions_concentration_and_public_timer(self):
        with patch("engine.secrets.randbelow", return_value=0):
            result = self.entangle()
        private, state = self.private_now(), self.store.read()
        self.assertEqual(state["character"]["resources"][0]["current"], 1)
        self.assertEqual(private["spell_effects"][0]["expires_round"], 11)
        self.assertIn("Trattenuto", private["creatures"][0]["conditions"])
        self.assertEqual(state["flags"]["effects"][0]["remaining_rounds"], 10)
        self.assertEqual(result["restrained_ids"], ["guard"])
        self.assertNotIn("Nome segreto", json.dumps(state))

    def test_entangle_does_not_block_next_and_expires_after_ten_rounds(self):
        with patch("engine.secrets.randbelow", return_value=0):
            self.entangle()
        engine = ActionEngine(self.root)
        engine.ops = ToolkitOps(self.root)
        for i in range(20):
            engine.advance_turn({}, f"next_{i}", self.store.read()["revision"])
        state = self.store.read()
        self.assertEqual(state["combat"]["round"], 11)
        self.assertEqual(state["flags"]["effects"], [])
        self.assertNotIn("concentration", state["character"])
        self.assertNotIn("Trattenuto", self.private_now()["creatures"][0]["conditions"])

    def test_concentration_failure_removes_effect_and_restrained_atomically(self):
        with patch("engine.secrets.randbelow", return_value=0):
            self.entangle()
        # Mimic a pending save from the ordinary damage operation.
        ops = ToolkitOps(self.root)
        ops.execute("damage", {"target": "Ada", "amount": 1}, self.store.read()["revision"], "hit")
        pc = self.store.read()["character"]
        pc["saving_throws"] = {"con": 2}
        self.store.commit({"party": [pc]}, self.store.read()["revision"])
        with patch("engine.secrets.randbelow", return_value=0):
            ops.execute("check", {"actor": "Ada", "save": "con"}, self.store.read()["revision"], "concentration")
        self.assertEqual(self.store.read()["flags"]["effects"], [])
        self.assertNotIn("Trattenuto", self.private_now()["creatures"][0]["conditions"])

    def test_concentration_voluntary_end_has_no_action_cost(self):
        with patch("engine.secrets.randbelow", return_value=0):
            result = self.entangle()
        before_usage = self.private_now()["turn_usage"]
        self.tool.effect({"actor": "Ada", "effect_id": result["effect_id"], "kind": "end-concentration",
                          "checks": {"declared": True}}, "end", self.store.read()["revision"])
        self.assertEqual(self.private_now()["turn_usage"], before_usage)
        self.assertEqual(self.store.read()["flags"]["effects"], [])

    def test_unknown_reaction_pending_blocks_all_casts(self):
        self.private["pending_reactions"] = [{"actor": "guard"}]
        self.write_private()
        with patch("tools.action_toolkit.roll_dice", side_effect=AssertionError("dice")):
            with self.assertRaises(CampaignError):
                self.run_cast()

    def test_legacy_pc_without_verified_save_is_not_rolled_at_wrong_bonus(self):
        spec = self.cast_plan("entangle")
        spec.update(area={"description": "Intorno al carro", "side_m": 6}, targets=[{"target": "Ada"}])
        with patch("tools.action_toolkit.roll_dice", side_effect=AssertionError("wrong save rolled")):
            with self.assertRaisesRegex(CampaignError, "saving_throws"):
                self.tool.entangle(spec, "legacy", self.store.read()["revision"])

    def test_second_entangle_cannot_overwrite_an_existing_restraint_source(self):
        self.private["creatures"][0]["conditions"] = ["Trattenuto"]
        self.write_private()
        with patch("tools.action_toolkit.roll_dice", side_effect=AssertionError("dice")):
            with self.assertRaisesRegex(CampaignError, "altra fonte"):
                self.entangle()

    def test_shove_away_invalidates_old_position_and_distance(self):
        state = self.store.read()
        self.store.commit({"flags": {"tactical_scene": {"tokens": [{"id": "guard", "entity_id": "guard", "x": 1, "y": 1, "confirmed": True}]},
                                     "table_scene": {"distances": [{"a": self.actor_id, "b": "guard", "metres": 1.5}]}}}, state["revision"])
        plan = self.contest_plan("shove-away")
        plan["checks"]["destination"] = True
        plan["destination"] = "Un metro e mezzo lontano da Ada, verso la strada"
        with patch("engine.secrets.randbelow", side_effect=[18, 0]):
            self.tool.contest(plan, "push", self.store.read()["revision"])
        flags = self.store.read()["flags"]
        self.assertFalse(flags["tactical_scene"]["tokens"][0]["confirmed"])
        self.assertEqual(flags["table_scene"]["distances"], [])

    def test_entangle_expires_by_fiction_clock_after_combat_ends(self):
        with patch("engine.secrets.randbelow", return_value=0):
            self.entangle()
        ToolkitOps(self.root).execute("save", {"patch": {"combat": {"active": False}, "clock": {"time": "17:31"}}},
                                      self.store.read()["revision"], "end_combat")
        self.assertEqual(self.store.read()["flags"]["effects"], [])
        self.assertNotIn("Trattenuto", self.private_now()["creatures"][0]["conditions"])

    def test_imported_overlapping_effect_ownership_transfers_then_cleans_last_source(self):
        with patch("engine.secrets.randbelow", return_value=0):
            first = self.entangle()
        self.private = self.private_now()
        second = copy.deepcopy(self.private["spell_effects"][0])
        second.update(id="entangle_second", caster_id="guard", condition_added_ids=[])
        self.private["spell_effects"].append(second)
        self.private["creatures"][0]["concentration"] = {"effect_id": second["id"]}
        self.write_private()
        self.tool.effect({"actor": "Ada", "effect_id": first["effect_id"], "kind": "end-concentration", "checks": {"declared": True}},
                         "end_first", self.store.read()["revision"])
        self.assertIn("Trattenuto", self.private_now()["creatures"][0]["conditions"])
        self.assertIn("guard", self.private_now()["spell_effects"][0]["condition_added_ids"])
        self.tool.effect({"actor": "Guardia", "effect_id": second["id"], "kind": "end-concentration", "checks": {"declared": True}},
                         "end_second", self.store.read()["revision"])
        self.assertNotIn("Trattenuto", self.private_now()["creatures"][0]["conditions"])

    def test_disciple_of_life_adds_verified_bonus_without_extra_dice(self):
        state = self.store.read()
        pc = state["character"]
        pc["features"] = ["Discepolo della Vita: 2 + livello dell'incantesimo alle cure."]
        self.store.commit({"party": [pc]}, state["revision"])
        with patch("engine.secrets.randbelow", return_value=2) as rng:
            result = self.run_cast()
        self.assertEqual(result["healed"], 7)  # d4 3 + WIS 1 + Disciple 3.
        self.assertEqual(rng.call_count, 1)

    def test_entangle_escape_is_plain_strength_and_uses_the_action(self):
        state = self.store.read()
        pc = state["character"]
        pc["saving_throws"] = {"str": 5}
        pc["skills"]["athletics"] = 9
        self.store.commit({"party": [pc]}, state["revision"])
        spec = self.cast_plan("entangle")
        spec.update(area={"description": "Intorno ad Ada", "side_m": 6}, targets=[{"target": "Ada"}])
        with patch("engine.secrets.randbelow", return_value=0):
            result = self.tool.entangle(spec, "self_entangle", self.store.read()["revision"])
        engine = ActionEngine(self.root)
        engine.ops = ToolkitOps(self.root)
        engine.advance_turn({}, "next_guard", self.store.read()["revision"])
        engine.advance_turn({}, "next_ada", self.store.read()["revision"])
        with patch("engine.secrets.randbelow", return_value=7):
            escaped = self.tool.effect({"actor": "Ada", "effect_id": result["effect_id"], "kind": "escape-entangle",
                                        "checks": {"declared": True, "modifiers": True, "reactions": True}},
                                       "escape_plants", self.store.read()["revision"])
        self.assertEqual(escaped["rolls"][0]["expression"], "1d20+3")
        self.assertTrue(escaped["success"])
        self.assertTrue(self.private_now()["turn_usage"]["action_used"])
        self.assertNotIn("Trattenuto", self.store.read()["character"]["conditions"])

    def test_source_catalog_valid_and_inspect_does_not_write(self):
        directory = self.root / "campaigns" / "nebbia" / "prepared"
        directory.mkdir(parents=True)
        source = ROOT / "examples" / "demo" / "encounters.json"
        catalog = json.loads(source.read_text(encoding="utf-8"))
        catalog["campaign_id"] = "nebbia"
        (directory / "encounters.json").write_text(json.dumps(catalog), encoding="utf-8")
        counts = validate_catalog(catalog)
        self.assertEqual(counts, {"profiles": 0, "scenes": 1})
        before = self.store.state_path.read_bytes()
        result = inspect_scene(self.root, "porto", preflight=True)
        self.assertEqual(len(result["scene"]["roster"]), 0)
        self.assertTrue(result["dm_only"])
        self.assertFalse(result["preflight"]["ready_to_prepare"])
        self.assertEqual(self.store.state_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
