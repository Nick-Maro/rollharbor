"""Fast master tooling uses isolated saves and never changes the playable table."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError, StateStore
from test_engine import fixture


class FastTurnEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-fast-turn-")
        self.root = Path(self.temp.name)
        fixture(self.root)
        self.store = StateStore(self.root)
        self.state, self.character = self.store.choose_character("ranger", "Ada")
        self.specs = [{"expression": "1d20+3", "label": "Ada · Iniziativa"},
                      {"expression": "1d20", "label": "Guardia · Iniziativa"}]

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *arguments):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "dnd.py"),
                                 "--root", str(self.root), *map(str, arguments)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_context_reads_one_world_and_keeps_character_runtime_information(self):
        character = copy.deepcopy(self.character)
        character.update({"conditions": ["Avvelenato"], "temporary_hp": 4,
                          "death_saves": {"successes": 1, "failures": 0},
                          "custom_feature": {"uses": 2}, "creation": {"cosmetic": True}})
        self.store.commit({"party": [character]}, self.state["revision"])
        before = self.store.state_path.read_bytes()
        with patch.object(self.store, "world", wraps=self.store.world) as world:
            context = self.store.context()
        self.assertEqual(world.call_count, 1)
        expected = copy.deepcopy(character)
        expected.pop("creation")
        self.assertEqual(context["party"], [expected])
        self.assertNotIn("character", context)
        self.assertEqual(context["location"]["id"], context["location_id"])
        self.assertEqual(self.store.state_path.read_bytes(), before)

    def test_context_retains_old_referenced_dice_without_duplicate_recent_results(self):
        state, first = self.store.roll("1d20", "Prima iniziativa")
        for _ in range(8):
            state, last = self.store.roll("1d6")
        self.store.commit({"flags": {"combat_context": {
            "initiative_roll_ids": [first["id"], last["id"], "roll_not_available"]}}}, state["revision"])
        context = self.store.context(recent=2)
        self.assertEqual([roll["id"] for roll in context["referenced_rolls"]], [first["id"]])
        self.assertEqual(context["missing_referenced_roll_ids"], ["roll_not_available"])
        self.assertEqual(len(context["recent_rolls"]), 2)

    def test_batch_has_one_revision_one_backup_and_authentic_results(self):
        before_backups = len(list(self.store.saves_path.glob("campaign-r*.json")))
        with patch("engine.secrets.randbelow", side_effect=[19, 0]) as random:
            state, summary = self.store.roll_batch(self.specs, "initiative_001", self.state["revision"])
        self.assertEqual(random.call_count, 2)
        self.assertEqual(state["revision"], self.state["revision"] + 1)
        self.assertEqual([roll["total"] for roll in summary["rolls"]], [23, 1])
        self.assertEqual(summary["rolls"], state["rolls"])
        self.assertFalse(summary["already_rolled"])
        self.assertEqual(len(list(self.store.saves_path.glob("campaign-r*.json"))), before_backups + 1)

    def test_retry_survives_later_revisions_without_reroll_or_rewrite(self):
        state, original = self.store.roll_batch(self.specs, "initiative_001", self.state["revision"])
        state, _ = self.store.note("Un appunto successivo")
        before = self.store.state_path.read_bytes()
        with patch("engine.roll_dice", side_effect=AssertionError("A retry must never roll")):
            retried, summary = self.store.roll_batch(self.specs, "initiative_001", self.state["revision"])
        self.assertEqual(retried["revision"], state["revision"])
        self.assertEqual(summary["rolls"], original["rolls"])
        self.assertTrue(summary["already_rolled"])
        self.assertEqual(self.store.state_path.read_bytes(), before)

    def test_concurrent_same_request_only_draws_once(self):
        with patch("engine.secrets.randbelow", side_effect=[10, 11]) as random:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: self.store.roll_batch(
                    self.specs, "initiative_race", self.state["revision"]), range(2)))
        self.assertEqual(random.call_count, 2)
        self.assertEqual(results[0][1]["rolls"], results[1][1]["rolls"])
        self.assertEqual(self.store.read()["revision"], self.state["revision"] + 1)

    def test_changed_request_and_stale_new_request_do_not_draw(self):
        state, _ = self.store.roll_batch(self.specs, "initiative_001", self.state["revision"])
        before = self.store.state_path.read_bytes()
        changed = copy.deepcopy(self.specs)
        changed[0]["expression"] = "1d20+4"
        with patch("engine.roll_dice", side_effect=AssertionError("Invalid input cannot draw")):
            with self.assertRaises(CampaignError):
                self.store.roll_batch(changed, "initiative_001", state["revision"])
            with self.assertRaises(CampaignError) as conflict:
                self.store.roll_batch(self.specs, "another_request", self.state["revision"])
        self.assertEqual(conflict.exception.code, "revision_conflict")
        self.assertEqual(self.store.state_path.read_bytes(), before)

    def test_invalid_or_private_batch_is_rejected_before_any_draw(self):
        before = self.store.state_path.read_bytes()
        with patch("engine.roll_dice", side_effect=AssertionError("Validation must precede draws")):
            for specs in ([], self.specs + [{"expression": "invalid"}],
                          [{"expression": "1d20", "private": True}]):
                with self.subTest(specs=specs), self.assertRaises(CampaignError):
                    self.store.roll_batch(specs, "invalid_batch", self.state["revision"])
        self.assertEqual(self.store.state_path.read_bytes(), before)

    def test_receipts_are_not_evicted_when_capacity_is_reached(self):
        state, first = self.store.roll_batch(self.specs, "first", self.state["revision"])
        with patch("engine.MAX_ROLL_BATCHES", 1):
            with patch("engine.roll_dice", side_effect=AssertionError("Capacity checked before RNG")):
                with self.assertRaises(CampaignError):
                    self.store.roll_batch(self.specs, "second", state["revision"])
                _, replay = self.store.roll_batch(self.specs, "first", self.state["revision"])
        self.assertEqual(replay["rolls"], first["rolls"])

    def test_cli_context_is_private_but_table_does_not_load_master_notes(self):
        member = self.character
        combat = {"active": True, "round": 1, "turn_index": 0,
                  "participants": [{"id": member["id"], "name": member["name"],
                                    "initiative": 12, "hp": member["hp"],
                                    "max_hp": member["max_hp"], "ac": member["ac"]}]}
        self.store.commit({"combat": combat}, self.state["revision"])
        secret = {"npc": {"secret": "PRIVATE_COMBAT_DRAGON", "hp": 123}}
        (self.root / "master" / "COMBATTIMENTO.json").write_text(json.dumps(secret), encoding="utf-8")
        context = self.cli("context")
        self.assertEqual(context["dm_context"]["combat"], secret)
        self.assertIn("continuity", context["dm_context"])
        public = json.dumps(self.store.table())
        self.assertNotIn("PRIVATE_COMBAT_DRAGON", public)
        self.assertNotIn("dm_context", public)

    def test_cli_batch_and_compact_commit_keep_the_old_commit_contract(self):
        batch_file = self.root / "batch.json"
        batch_file.write_text(json.dumps(self.specs), encoding="utf-8")
        rolled = self.cli("roll-batch", batch_file, "--request-id", "cli_batch",
                          "--expected-revision", self.state["revision"])
        self.assertEqual(len(rolled["rolls"]), 2)
        patch_file = self.root / "patch.json"
        patch_file.write_text(json.dumps({"scene": {"text": "Ada osserva il carro."}}), encoding="utf-8")
        compact = self.cli("commit", patch_file, "--expected-revision", rolled["revision"], "--compact")
        self.assertNotIn("state", compact)
        full = self.cli("commit", patch_file, "--expected-revision", compact["revision"])
        self.assertEqual(full["state"]["revision"], compact["revision"])


if __name__ == "__main__":
    unittest.main()
