"""NPC sequences run only against temporary fixtures, never the real save."""
from __future__ import annotations

import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError, StateStore
from tools.action_engine import ActionEngine
from tools import play
from tools.turn_log import TurnLog
from test_engine import fixture


class NpcMultiattackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-npc-sequence-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture(self.root, party_size=2)
        self.store = StateStore(self.root)
        self.store.choose_character("ranger", "Ada")
        state, _ = self.store.choose_character("ranger", "Berto")
        party = state["party"]
        for pc in party:
            pc.update({"hp": 10, "max_hp": 10, "ac": 15, "conditions": []})
        participants = [{"id": "npc_demo_guard", "name": "Guardia", "initiative": 20, "conditions": []}]
        participants += [{"id": pc["id"], "name": pc["name"], "initiative": 15-index,
                          "hp": pc["hp"], "max_hp": pc["max_hp"], "ac": pc["ac"], "conditions": []}
                         for index, pc in enumerate(party)]
        self.state, _ = self.store.commit({"party": party, "combat": {
            "active": True, "round": 1, "turn_index": 0, "participants": participants}}, state["revision"])
        self.private = {"creatures": [{"id": "npc_demo_guard", "name": "Nome segreto",
                                       "hp": 13, "max_hp": 27, "ac": 16, "conditions": [],
                                       "weapon_drawn": True, "wielded_weapon": "Spada lunga"}],
                        "pending_reactions": [], "timers": [], "reactions_available": {}}
        self.private_path = self.root / "master" / "COMBATTIMENTO.json"
        self.save_private()
        self.engine = ActionEngine(self.root)
        self.spec = {"actor": "npc_demo_guard", "profile": "demo_guard_longsword",
                     "source": "Original synthetic demo profile", "targets": ["Ada", "Berto"],
                     "nonlethal": True, "positions_checked": True, "reactions_checked": True,
                     "modifiers_checked": True}

    def save_private(self):
        self.private_path.write_text(json.dumps(self.private), encoding="utf-8")

    def run_action(self, **overrides):
        spec = {**self.spec, **overrides}
        return self.engine.resolve_npc_multiattack(spec, "npc_sequence", self.state["revision"])

    def update_party(self, **fields):
        state = self.store.read()
        for pc in state["party"]:
            pc.update(copy.deepcopy(fields))
            for participant in state["combat"]["participants"]:
                if participant["id"] == pc["id"]:
                    for key in ("hp", "max_hp", "ac", "conditions"):
                        participant[key] = copy.deepcopy(pc[key])
        self.state, _ = self.store.commit({"party": state["party"], "combat": state["combat"]}, state["revision"])

    def test_two_declared_targets_one_revision_no_turn_or_resources_changed(self):
        with patch("engine.secrets.randbelow", side_effect=[14, 2, 5]):
            result = self.run_action()
        current = self.store.read()
        self.assertEqual(result["revision"], self.state["revision"] + 1)
        self.assertEqual([pc["hp"] for pc in current["party"]], [6, 10])
        self.assertEqual(current["combat"]["turn_index"], 0)
        self.assertEqual(current["clock"], self.state["clock"])
        self.assertEqual([pc["resources"] for pc in current["party"]], [pc["resources"] for pc in self.state["party"]])
        self.assertEqual([item["hit"] for item in result["attacks"]], [True, False])
        self.assertEqual(len(result["rolls"]), 3)
        self.assertGreaterEqual(result["tool_elapsed_ms"], result["resolution_ms"])
        self.assertEqual(len(TurnLog(self.root).context()["events"]), 1)
        public_npc = current["combat"]["participants"][0]
        for key in ("hp", "max_hp", "ac"):
            self.assertNotIn(key, public_npc)
        self.assertNotIn("Nome segreto", json.dumps(current))

    def test_idempotent_retry_no_dice_no_second_damage(self):
        with patch("engine.secrets.randbelow", side_effect=[14, 2, 5]):
            first = self.run_action()
        saved = self.store.state_path.read_bytes()
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("reroll")):
            second = self.run_action()
        self.assertTrue(second["already_applied"])
        self.assertEqual(first["attacks"], second["attacks"])
        self.assertEqual(saved, self.store.state_path.read_bytes())

    def test_massive_critical_is_nonlethal_and_stops_remaining_attack(self):
        with patch("engine.secrets.randbelow", side_effect=[19, 7, 7]) as rng:
            result = self.run_action(targets=["Ada", "Ada"])
        self.assertEqual(rng.call_count, 3)
        self.assertEqual(result["attacks"][0]["damage"], 17)
        self.assertEqual(result["attacks"][0]["outcome"], "knocked_out")
        self.assertEqual(result["stop_reason"], "target_zero_hp")
        self.assertEqual(len(result["unrolled_attacks"]), 1)
        pc = self.store.read()["party"][0]
        self.assertEqual(pc["hp"], 0)
        self.assertTrue(pc["stable"])
        self.assertNotIn("Morto", pc["conditions"])
        self.assertEqual(self.store.read()["party"][1]["hp"], 10)
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("new action")):
            with self.assertRaises(CampaignError):
                self.engine.resolve_npc_multiattack(self.spec, "extra_sequence", result["revision"])

    def test_concentration_stops_before_second_attack_even_if_temp_hp_absorb(self):
        self.update_party(concentration={"spell": "Benedizione"}, temporary_hp=8,
                          saving_throws={"con": 2})
        with patch("engine.secrets.randbelow", side_effect=[14, 2]) as rng:
            result = self.run_action()
        self.assertEqual(rng.call_count, 2)
        self.assertEqual(result["stop_reason"], "concentration_save")
        self.assertEqual(len(result["unrolled_attacks"]), 1)
        self.assertEqual(self.store.read()["party"][0]["hp"], 10)
        combat = json.loads(self.private_path.read_text(encoding="utf-8"))
        self.assertEqual(combat["pending_resolution"]["dc"], 10)
        with self.assertRaises(CampaignError):
            self.engine.advance_turn({}, "blocked_next", result["revision"])
        # Once the save is resolved there is no hidden sequence to auto-resume.
        with patch("engine.secrets.randbelow", return_value=10):
            saved = self.engine.ops.execute("check", {"actor": "Ada", "save": "con"}, result["revision"], "con_save")
        self.assertEqual(self.store.read()["party"][1]["hp"], 10)
        with self.assertRaises(CampaignError):
            self.engine.resolve_npc_multiattack(self.spec, "must_not_resume", saved["revision"])

    def test_invalid_second_target_is_rejected_before_first_die(self):
        for target in ("npc_unknown", None, "npc_demo_guard"):
            with self.subTest(target=target), patch("tools.action_engine.roll_dice", side_effect=AssertionError("invalid rolled")):
                with self.assertRaises(CampaignError):
                    self.run_action(targets=["Ada", target])
        self.assertEqual(self.store.read()["revision"], self.state["revision"])

    def test_source_count_and_checks_cannot_be_overridden(self):
        for override in ({"source": "2024"}, {"profile": "invented"}, {"targets": ["Ada"]},
                         {"targets": ["Ada"] * 3}, {"positions_checked": False},
                         {"reactions_checked": False}, {"modifiers_checked": False}, {"nonlethal": None},
                         {"modes": ["advantage"]}, {"damage": "99d99"}):
            with self.subTest(override=override), patch("tools.action_engine.roll_dice", side_effect=AssertionError("invalid rolled")):
                with self.assertRaises(CampaignError):
                    self.run_action(**override)

    def test_weapon_must_already_be_drawn_and_match_source(self):
        for field, value in (("weapon_drawn", False), ("wielded_weapon", "Arco corto")):
            with self.subTest(field=field):
                self.private["creatures"][0][field] = value
                self.save_private()
                with patch("tools.action_engine.roll_dice", side_effect=AssertionError("invalid rolled")):
                    with self.assertRaises(CampaignError):
                        self.run_action()
                self.private["creatures"][0].update({"weapon_drawn": True, "wielded_weapon": "Spada lunga"})

    def test_available_reaction_cannot_be_bypassed_by_checked_flag(self):
        self.update_party(reaction="Parata")
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("reaction bypass")):
            with self.assertRaises(CampaignError):
                self.run_action()
        self.private["reactions_available"] = {pc["id"]: False for pc in self.state["party"]}
        self.save_private()
        with patch("engine.secrets.randbelow", side_effect=[0, 0]):
            self.assertEqual(len(self.run_action()["attacks"]), 2)

    def test_shield_spell_and_allied_defensive_reactions_are_not_preselected(self):
        self.update_party(spells={"prepared": ["Scudo"]})
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("spell bypass")):
            with self.assertRaises(CampaignError):
                self.run_action()
        self.update_party(spells={}, features=["Protezione: usa la tua reazione per proteggere un alleato."])
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("ally bypass")):
            with self.assertRaises(CampaignError):
                self.run_action(targets=["Ada", "Ada"])

    def test_pending_reactions_conditions_and_damage_defences_stop_before_dice(self):
        for extra in ({"resistances": ["tagliente"]}, {"damage_vulnerabilities": ["tagliente"]}):
            self.update_party(**extra)
            with patch("tools.action_engine.roll_dice", side_effect=AssertionError("defence bypass")):
                with self.assertRaises(CampaignError):
                    self.run_action()
            self.update_party(**{key: [] for key in extra})
        self.private["pending_reactions"] = [{"actor_id": "Ada"}]
        self.save_private()
        with self.assertRaises(CampaignError):
            self.run_action()
        self.private["pending_reactions"] = []
        self.private["creatures"][0]["conditions"] = ["Stordito"]
        self.save_private()
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("stunned attack")):
            with self.assertRaises(CampaignError):
                self.run_action()

    def test_no_profile_can_be_used_to_grant_player_extra_attacks(self):
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("PC multiattack")):
            with self.assertRaises(CampaignError):
                self.run_action(actor="Ada")

    def test_recovery_after_private_write_failure_never_rerolls(self):
        original = self.engine.ops.store._atomic_json
        def failing_write(path, value):
            if Path(path) == self.engine.ops.log.path:
                raise OSError("simulated private journal failure")
            return original(path, value)
        with patch.object(self.engine.ops.store, "_atomic_json", side_effect=failing_write), patch(
                "engine.secrets.randbelow", side_effect=[14, 2, 5]):
            with self.assertRaises(OSError):
                self.run_action()
        self.assertTrue(self.engine.ops.pending_path.exists())
        with patch("tools.action_engine.roll_dice", side_effect=AssertionError("recovery rerolled")):
            result = self.run_action()
        self.assertTrue(result["already_applied"])
        self.assertFalse(self.engine.ops.pending_path.exists())
        self.assertEqual([pc["hp"] for pc in self.store.read()["party"]], [6, 10])
        self.assertEqual(len(TurnLog(self.root).context()["events"]), 1)

    def test_cli_reads_plan_and_emits_one_compact_json_response(self):
        plan = self.root / "plan.json"
        plan.write_text(json.dumps(self.spec), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), patch(
                "engine.secrets.randbelow", side_effect=[0, 0]):
            code = play.main(["--root", str(self.root), "npc-multiattack", str(plan), "--id", "cli_sequence",
                              "--expected-revision", str(self.state["revision"])])
        self.assertEqual((code, err.getvalue()), (0, ""))
        self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertEqual(len(json.loads(out.getvalue())["attacks"]), 2)

    def test_brief_context_keeps_live_state_and_latest_history_without_mutation(self):
        log = TurnLog(self.root)
        for index in range(9):
            log.append({"id": f"history_{index}", "revision": self.state["revision"],
                        "public": f"Evento {index}", "dm": "Dettaglio riservato",
                        "pending": ["Ada: decisione"], "roll_ids": [],
                        "details": {"operation": "save", "parameters": {"party": self.state["party"]}}})
        before = {path: path.read_bytes() for path in (self.store.state_path, self.private_path, log.path)}
        result = play._brief_context(self.root)
        self.assertEqual(result["revision"], self.state["revision"])
        self.assertEqual(result["party"], self.state["party"])
        self.assertEqual(result["combat"], self.state["combat"])
        self.assertEqual(result["dm_context"]["combat"], self.private)
        continuity = result["dm_context"]["continuity"]
        self.assertEqual([e["id"] for e in continuity["events"]], [f"history_{i}" for i in range(5, 9)])
        self.assertEqual(continuity["omitted_earlier_events"], 5)
        self.assertEqual(continuity["history_mode"], "latest_only")
        self.assertEqual(continuity["events"][0]["details"], {"operation": "save"})
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertEqual(len(log.context(limit=0)["events"]), 9)

    def test_cli_brief_is_explicit_and_default_context_remains_unchanged(self):
        for extra, expected in ((["--brief"], "brief_hot_turn"), ([], None)):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = play.main(["--root", str(self.root), "context", *extra])
            self.assertEqual((code, err.getvalue()), (0, ""))
            result = json.loads(out.getvalue())
            self.assertEqual(result.get("context_mode"), expected)
            self.assertEqual(result["party"], self.state["party"])


if __name__ == "__main__":
    unittest.main()
