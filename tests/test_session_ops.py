"""Real disposable transactions, crash recovery and common 2014 effects."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from engine import CampaignError, StateStore
from tools.session_ops import SessionOps
from tools.turn_log import TurnLog
from test_engine import fixture


class SessionOpsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dnd-ops-")
        self.root = Path(self.temporary.name)
        fixture(self.root)
        self.store = StateStore(self.root)
        self.state, self.pc = self.store.choose_character("ranger", "Mira")
        self.ops = SessionOps(self.root)
        self.sequence = 0

    def tearDown(self):
        self.temporary.cleanup()

    def execute(self, kind, payload, request_id=None):
        self.sequence += 1
        return self.ops.execute(kind, payload, self.store.read()["revision"], request_id or f"test_{self.sequence}")

    def prepare_pc(self, **fields):
        state = self.store.read()
        payload = {"character": fields}
        if state["combat"]["active"]:
            combat = copy.deepcopy(state["combat"])
            for participant in combat["participants"]:
                if participant["id"] == self.pc["id"]:
                    for key in ("hp", "max_hp", "ac", "conditions"):
                        if key in fields:
                            participant[key] = fields[key]
            payload["combat"] = combat
        self.store.commit(payload, state["revision"])

    def prepare_combat(self, npc_public_hp=False):
        state = self.store.read()
        npc = {"id": "npc_dwarf", "name": "Un nano", "initiative": 4}
        if npc_public_hp:
            npc.update(hp=4, max_hp=4, ac=10)
        self.store.commit({"combat": {"active": True, "round": 1, "turn_index": 0,
                                      "participants": [{"id": self.pc["id"], "name": "Mira", "initiative": 10,
                                                        "hp": state["character"]["hp"], "max_hp": state["character"]["max_hp"],
                                                        "ac": state["character"]["ac"], "conditions": state["character"].get("conditions", [])}, npc]}}, state["revision"])
        self.store._atomic_json(self.ops.combat_path, {"creatures": [{"id": "npc_dwarf", "name": "SECRET_TRUE_NAME", "hp": 4, "max_hp": 4, "ac": 10}]})

    def test_heal_is_idempotent_and_public_private_log_are_coherent(self):
        self.prepare_pc(hp=3)
        revision = self.store.read()["revision"]
        response = self.execute("heal", {"target": "Mira", "amount": 5}, "heal_once")
        replay = SessionOps(self.root).execute("heal", {"target": "Mira", "amount": 5}, revision, "heal_once")
        self.assertTrue(replay["already_applied"])
        self.assertEqual(response["revision"], replay["revision"])
        self.assertEqual(self.store.read()["character"]["hp"], 8)
        self.assertEqual(TurnLog(self.root).context()["total_events"], 1)
        with self.assertRaises(CampaignError):
            self.execute("heal", {"target": "Mira", "amount": 6}, "heal_once")

    def test_stale_revision_rejected_before_callback(self):
        callback = unittest.mock.Mock()
        with self.assertRaises(CampaignError) as error:
            self.ops.transact("check", {}, "old", 0, callback)
        self.assertEqual(error.exception.code, "revision_conflict")
        callback.assert_not_called()

    def test_crash_after_public_write_recovers_without_reroll_or_duplicate(self):
        revision = self.store.read()["revision"]
        original = self.ops.store._atomic_json
        def interrupted(path, value):
            if path == self.ops.log.path:
                raise OSError("simulated interruption")
            original(path, value)
        spec = {"actor": "Mira", "ability": "str"}
        with patch.object(self.ops.store, "_atomic_json", side_effect=interrupted), patch("engine.secrets.randbelow", return_value=10) as random:
            with self.assertRaises(OSError):
                self.ops.execute("check", spec, revision, "interrupted")
            self.assertEqual(random.call_count, 1)
        self.assertTrue(self.ops.pending_path.exists())
        with self.assertRaises(CampaignError) as error:
            self.store.note("Should wait")
        self.assertEqual(error.exception.code, "operation_pending")
        with self.assertRaises(CampaignError):
            TurnLog(self.root).append({"id": "not_now", "revision": revision})
        with patch("tools.session_ops.roll_dice", side_effect=AssertionError("No reroll")):
            replay = SessionOps(self.root).execute("check", spec, revision, "interrupted")
        self.assertTrue(replay["already_applied"])
        self.assertFalse(self.ops.pending_path.exists())
        self.assertEqual(len(self.store.read()["rolls"]), 1)
        self.assertEqual(TurnLog(self.root).context()["total_events"], 1)

    def test_crash_before_public_write_recovers_prepared_effect(self):
        self.prepare_pc(hp=2)
        revision = self.store.read()["revision"]
        original = self.ops.store._atomic_json
        def interrupted(path, value):
            if path == self.ops.store.state_path:
                raise OSError("before public write")
            original(path, value)
        with patch.object(self.ops.store, "_atomic_json", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.ops.execute("heal", {"target": "Mira", "amount": 3}, revision, "pending_heal")
        self.assertEqual(self.store.read()["character"]["hp"], 2)
        result = SessionOps(self.root).recover()
        self.assertTrue(result["recovered"])
        self.assertEqual(self.store.read()["character"]["hp"], 5)
        self.assertFalse(SessionOps(self.root).recover()["recovered"])

    def test_corrupt_private_wal_is_not_applied(self):
        original = self.ops.store._atomic_json
        def interrupted(path, value):
            if path == self.ops.store.state_path:
                raise OSError("before write")
            original(path, value)
        with patch.object(self.ops.store, "_atomic_json", side_effect=interrupted):
            with self.assertRaises(OSError):
                self.execute("check", {"actor": "Mira", "ability": "str"})
        pending = json.loads(self.ops.pending_path.read_text(encoding="utf-8"))
        pending["log"]["events"] = []
        self.ops.pending_path.write_text(json.dumps(pending), encoding="utf-8")
        before = self.store.state_path.read_bytes()
        with self.assertRaises(CampaignError):
            self.ops.recover()
        self.assertEqual(self.store.state_path.read_bytes(), before)

    def test_parallel_retries_apply_once(self):
        self.prepare_pc(hp=1)
        revision = self.store.read()["revision"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: SessionOps(self.root).execute("heal", {"target": "Mira", "amount": 2}, revision, "parallel"), range(8)))
        self.assertEqual(sum(not r["already_applied"] for r in replies), 1)
        self.assertEqual(self.store.read()["character"]["hp"], 3)

    def test_healing_removes_stability_but_keeps_prone(self):
        self.prepare_pc(hp=0, conditions=["A terra", "Privo di sensi", "Stabilizzato"], stable=True,
                        death_saves={"successes": 2, "failures": 1})
        self.execute("heal", {"target": "Mira", "amount": 2})
        pc = self.store.read()["character"]
        self.assertEqual(pc["conditions"], ["A terra"])
        self.assertFalse(pc.get("stable"))
        self.assertEqual(pc["death_saves"], {"successes": 0, "failures": 0})

    def test_damage_and_condition_update_pc_combat_and_active_mirror(self):
        self.prepare_combat()
        self.execute("damage", {"target": "Mira", "amount": 3})
        self.execute("condition", {"target": "Mira", "condition": "Avvelenato"})
        state = self.store.read()
        self.assertEqual(state["character"], state["party"][0])
        self.assertEqual(state["combat"]["participants"][0]["hp"], state["character"]["hp"])
        self.assertEqual(state["combat"]["participants"][0]["conditions"], ["Avvelenato"])

    def test_npc_public_alias_and_existing_hp_are_kept_coherent(self):
        self.prepare_combat(npc_public_hp=True)
        self.execute("damage", {"target": "Un nano", "amount": 2})
        state = self.store.read()
        self.assertEqual(state["combat"]["participants"][1]["hp"], 2)
        self.assertNotIn("SECRET_TRUE_NAME", json.dumps(state))

    def test_hidden_npc_effect_does_not_publish_identity(self):
        self.store._atomic_json(self.ops.combat_path, {"creatures": [{"id": "hidden", "name": "SECRET", "hp": 4, "max_hp": 4}]})
        before = self.store.state_path.read_bytes()
        with self.assertRaises(CampaignError):
            self.execute("heal", {"target": "hidden", "amount": 1})
        self.assertEqual(self.store.state_path.read_bytes(), before)

    def test_resource_cannot_be_overspent_or_overfilled(self):
        for delta in (-2, 1):
            with self.assertRaises(CampaignError):
                self.execute("resource", {"actor": "Mira", "resource": "wind", "delta": delta})
        self.execute("resource", {"actor": "Mira", "resource": "wind", "delta": -1})
        self.assertEqual(self.store.read()["character"]["resources"][0]["current"], 0)

    def test_concentration_uses_all_damage_even_temporary_and_save_clears_pending(self):
        self.prepare_pc(temporary_hp=30, conditions=["Concentrazione: Benedizione"], saving_throws={"con": 2})
        result = self.execute("damage", {"target": "Mira", "amount": 30})
        self.assertEqual(result["pending"][0]["dc"], 15)
        self.assertEqual(self.store.read()["character"]["hp"], self.pc["hp"])
        with patch("engine.secrets.randbelow", return_value=0):
            response = self.execute("check", {"actor": "Mira", "save": "con"})
        self.assertFalse(response["success"])
        self.assertFalse(self.store.read()["character"]["conditions"])
        private = json.loads(self.ops.combat_path.read_text(encoding="utf-8"))
        self.assertNotIn("pending_resolution", private)

    def test_checks_do_not_auto_succeed_on_natural_twenty(self):
        with patch("engine.secrets.randbelow", return_value=19):
            result = self.execute("check", {"actor": "Mira", "ability": "str", "dc": 30})
        self.assertFalse(result["success"])

    def test_massive_damage_kills_and_healing_does_not_resurrect(self):
        self.execute("damage", {"target": "Mira", "amount": 30})
        self.assertIn("Morto", self.store.read()["character"]["conditions"])
        with self.assertRaises(CampaignError):
            self.execute("heal", {"target": "Mira", "amount": 10})

    def test_death_save_one_is_two_failures_and_twenty_restores_one_hp(self):
        self.prepare_pc(hp=0, conditions=["Privo di sensi", "A terra"], death_saves={"successes": 0, "failures": 0})
        with patch("engine.secrets.randbelow", return_value=0):
            self.execute("death", {"actor": "Mira"})
        self.assertEqual(self.store.read()["character"]["death_saves"]["failures"], 2)
        with patch("engine.secrets.randbelow", return_value=19):
            self.execute("death", {"actor": "Mira"})
        self.assertEqual(self.store.read()["character"]["hp"], 1)
        self.assertEqual(self.store.read()["character"]["conditions"], ["A terra"])

    def test_death_save_cannot_repeat_during_same_combat_turn(self):
        self.prepare_combat()
        self.prepare_pc(hp=0, conditions=["Privo di sensi"], death_saves={"successes": 0, "failures": 0})
        # Keep public combat and party coherent before testing the operation.
        state = self.store.read()
        state["combat"]["participants"][0]["hp"] = 0
        self.store._atomic_json(self.store.state_path, state)
        with patch("engine.secrets.randbelow", return_value=10):
            self.execute("death", {"actor": "Mira"})
        with self.assertRaises(CampaignError):
            self.execute("death", {"actor": "Mira"})

    def test_save_bundle_private_stats_never_enter_public_state(self):
        result = self.execute("save", {"patch": {"scene": {"text": "Una scelta libera."}},
                                      "public": "Il gruppo esplora.", "dm": "SECRET_PLAN",
                                      "private_combat": {"creatures": [{"id": "hidden", "name": "SECRET_NPC", "hp": 20, "max_hp": 20}]}})
        self.assertTrue(result["revision"])
        self.assertNotIn("SECRET", json.dumps(self.store.read()))
        self.assertEqual(TurnLog(self.root).context()["events"][0]["dm"], "SECRET_PLAN")


if __name__ == "__main__":
    unittest.main()
