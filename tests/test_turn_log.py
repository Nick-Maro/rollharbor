"""Private continuity is durable without rewriting or changing the public save."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError, StateStore
from tools.turn_log import TurnLog
from test_engine import fixture


class TurnLogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-turn-log-")
        self.root = Path(self.temp.name)
        fixture(self.root)
        self.store = StateStore(self.root)
        self.log = TurnLog(self.root)
        self.initial_bytes = self.store.state_path.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def event(self, event_id="turn_001", **extra):
        return {"id": event_id, "revision": self.store.read()["revision"],
                "public": "Mira parla con il locandiere.", "dm": "Il PNG nasconde un dubbio.",
                "pending": [{"actor": "Mira", "intent": "Chiede una stanza"}],
                "references": ["handoff.md", "Fonte p. 4"], **extra}

    def test_append_is_private_durable_and_idempotent_across_instances(self):
        event = self.event()
        result = self.log.append(event)
        saved_bytes = self.log.path.read_bytes()
        self.assertFalse(result["already_recorded"])
        replay = TurnLog(self.root).append(dict(reversed(list(event.items()))))
        self.assertTrue(replay["already_recorded"])
        self.assertEqual(self.log.path.read_bytes(), saved_bytes)
        self.assertEqual(self.store.state_path.read_bytes(), self.initial_bytes)
        context = self.log.context()
        self.assertEqual(context["events"][0]["dm"], event["dm"])
        self.assertEqual(context["events"][0]["clock"], self.store.read()["clock"])
        self.assertFalse(list((self.root / "saves").glob("*")))

    def test_conflicting_replay_and_future_revision_do_not_touch_either_file(self):
        self.log.append(self.event())
        original = self.log.path.read_bytes()
        for event in (self.event(dm="Diverso"), self.event("future", revision=1)):
            with self.assertRaises(CampaignError):
                self.log.append(event)
        self.assertEqual(self.log.path.read_bytes(), original)
        self.assertEqual(self.store.state_path.read_bytes(), self.initial_bytes)

    def test_checkpoint_keeps_history_and_returns_only_later_events(self):
        self.log.append(self.event())
        checkpoint = {"id": "checkpoint_001", "revision": 0, "summary": "Ripresa dalla locanda",
                      "references": ["handoff.md", "master/MEMORIA.md"]}
        self.log.checkpoint(checkpoint)
        self.log.append(self.event("turn_002", dm="Serve ancora la risposta di Mira."))
        self.log.append(self.event("turn_003", dm="È ancora il medesimo momento."))
        limited = self.log.context(limit=1)
        self.assertEqual(limited["checkpoint"]["id"], "checkpoint_001")
        self.assertEqual(limited["events"][0]["id"], "turn_002")
        self.assertEqual(limited["remaining_count"], 1)
        self.assertEqual(limited["total_events"], 3)
        self.assertEqual(len(self.log.context(limit=0)["events"]), 2)
        self.assertTrue(self.log.checkpoint(checkpoint)["already_recorded"])
        self.assertEqual(len(json.loads(self.log.path.read_text(encoding="utf-8"))["events"]), 3)

    def test_replay_after_public_revision_changes_keeps_original_clock(self):
        event = self.event()
        self.log.append(event)
        self.store.commit({"clock": {"time": "18:00"}}, 0)
        self.assertTrue(self.log.append(event)["already_recorded"])
        self.assertEqual(self.log.context()["events"][0]["clock"]["time"], "17:30")
        with self.assertRaises(CampaignError):
            self.log.checkpoint({"id": "stale_checkpoint", "revision": 0})

    def test_concurrent_appends_keep_all_events_once(self):
        values = [self.event(f"parallel_{i}") for i in range(12)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda event: TurnLog(self.root).append(event), values + values))
        self.assertEqual(sum(not result["already_recorded"] for result in results), 12)
        self.assertEqual(self.log.context(limit=0)["total_events"], 12)

    def test_corrupt_or_wrong_campaign_log_is_not_overwritten(self):
        self.log.append(self.event())
        document = json.loads(self.log.path.read_text(encoding="utf-8"))
        for changed in ({**document, "campaign_id": "other"},
                        {**document, "events": [{**document["events"][0], "digest": "wrong"}]}):
            self.log.path.write_text(json.dumps(changed), encoding="utf-8")
            original = self.log.path.read_bytes()
            with self.assertRaises(CampaignError):
                self.log.append(self.event("new"))
            self.assertEqual(self.log.path.read_bytes(), original)

    def test_rollback_requires_explicit_reconciliation(self):
        self.store.commit({"scene": {"title": "Più tardi"}}, 0)
        self.log.append(self.event())
        self.store.state_path.write_bytes(self.initial_bytes)
        with self.assertRaises(CampaignError) as raised:
            self.log.context()
        self.assertEqual(raised.exception.code, "continuity_conflict")

    def test_continuity_is_not_truncated_by_public_save_size_limit(self):
        for index in range(6):
            self.log.append(self.event(f"long_{index}", details={"notes": "x" * 100000}))
        self.assertGreater(self.log.path.stat().st_size, 512 * 1024)
        self.assertEqual(TurnLog(self.root).context(limit=0)["total_events"], 6)
        self.assertEqual(self.store.state_path.read_bytes(), self.initial_bytes)

    def test_cli_unicode_json_and_no_future_writes(self):
        payload = self.root / "evento.json"
        payload.write_text(json.dumps(self.event(dm="È segreto: possibilità d'incontro.")), encoding="utf-8")
        command = [sys.executable, str(ROOT / "tools" / "turn_log.py"), "--root", str(self.root)]
        result = subprocess.run([*command, "append", str(payload)], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertTrue(json.loads(result.stdout)["ok"])
        result = subprocess.run([*command, "context"], capture_output=True, timeout=15)
        self.assertEqual(json.loads(result.stdout)["events"][0]["dm"], "È segreto: possibilità d'incontro.")
        payload.write_text(json.dumps(self.event("future", revision=1)), encoding="utf-8")
        result = subprocess.run([*command, "append", str(payload)], capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 1)
        self.assertIn("error", json.loads(result.stderr))


if __name__ == "__main__":
    unittest.main()
