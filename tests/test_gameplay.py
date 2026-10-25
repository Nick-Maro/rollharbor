"""Live master workflows run entirely on temporary, isolated campaign copies."""
from __future__ import annotations

import copy
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError, StateStore
from server import LocalServer
from test_engine import fixture


def new_location(**changes):
    return {"id": "bottega", "name": "La bottega di Ilaria", "type": "shop", "x": 250, "y": 180,
            "description": "Una bottega scoperta seguendo una proposta dei giocatori.",
            "actions": ["Chiediamo se occorre una mano."], **changes}


class LiveMasterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-live-")
        self.root = Path(self.temp.name)
        self.initial, self.world = fixture(self.root, party_size=4)
        self.store = StateStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def fill_group(self):
        for name in ("Alba", "Berto", "Cleo", "Dario"):
            state, _ = self.store.choose_character("ranger", name)
        return state

    def cli(self, *arguments):
        result = subprocess.run([sys.executable, str(ROOT / "tools" / "dnd.py"), "--root", str(self.root),
                                 *arguments], capture_output=True, timeout=15)
        return result.returncode, json.loads(result.stdout or result.stderr)

    def test_start_requires_complete_group_and_never_resets_a_running_scene(self):
        with self.assertRaises(CampaignError):
            self.store.start(0)
        self.assertEqual(self.store.read(), self.initial)
        state = self.fill_group()
        status = self.store.status()
        self.assertTrue(status["group_ready"])
        self.assertFalse(status["started"])
        self.assertTrue(status["can_edit_characters"])
        self.assertEqual(status["party_count"], 4)
        before = copy.deepcopy(state)
        state, result = self.store.start(state["revision"])
        self.assertFalse(result["already_started"])
        for key in ("party", "scene", "clock", "location_id", "pending_actions", "session"):
            self.assertEqual(state[key], before[key])
        self.assertTrue(self.store.status()["started"])
        self.assertFalse(self.store.status()["can_edit_characters"])
        state, result = self.store.start(state["revision"])
        self.assertTrue(result["already_started"])
        self.assertEqual(state["revision"], before["revision"] + 1)
        with self.assertRaises(CampaignError):
            self.store.start(state["revision"], {"title": "Reset", "text": "Reset", "choices": []})
        self.assertEqual(self.store.read(), state)

    def test_start_cli_preserves_pending_and_rejects_stale_revision(self):
        state = self.fill_group()
        state, action = self.store.queue_action("Tutti: osserviamo senza muoverci.")
        scene = {"title": "Un giorno nuovo", "text": "Nessuno vi ha ancora imposto una decisione.", "choices": []}
        path = self.root / "master" / "inizio.json"
        path.write_text(json.dumps(scene), encoding="utf-8")
        code, result = self.cli("start", "--expected-revision", "4", "--scene", str(path))
        self.assertEqual(code, 1)
        self.assertEqual(result["code"], "revision_conflict")
        self.assertEqual(self.store.read(), state)
        code, result = self.cli("start", "--expected-revision", str(state["revision"]), "--scene", str(path))
        self.assertEqual(code, 0, result)
        self.assertEqual(result["scene"], scene)
        self.assertEqual(self.store.read()["pending_actions"], [action])
        code, status = self.cli("status")
        self.assertEqual(code, 0)
        self.assertTrue(status["started"])
        self.assertEqual(status["pending_count"], 1)

    def test_preparation_flags_and_spell_choices_do_not_lock_editor_but_spending_does(self):
        state = self.fill_group()
        state, _ = self.store.commit({"flags": {"session_preferences": "negoziazione ed esplorazione"},
                                      "character": {"description": "Passato scelto da Alba."}}, state["revision"])
        self.assertTrue(self.store.status()["can_edit_characters"])
        state, _ = self.store.commit({"character": {"resources": [
            {**state["character"]["resources"][0], "current": 0}]}}, state["revision"])
        self.assertFalse(self.store.status()["can_edit_characters"])
        state, _ = self.store.commit({"character": {"resources": [
            {**state["character"]["resources"][0], "current": 1}]}}, state["revision"])
        self.assertFalse(self.store.status()["can_edit_characters"], "Restoring a resource must not unlock a live sheet")

    def test_no_op_selection_does_not_invalidate_an_in_progress_master_commit(self):
        state = self.fill_group()
        after, _ = self.store.active_character(state["active_character_id"])
        self.assertEqual(after, state)
        self.store.commit({"flags": {"ready": True}}, state["revision"])

    def test_improvised_location_can_be_added_discovered_and_used_without_rewriting_world(self):
        state = self.fill_group()
        base_bytes = self.store.world_path.read_bytes()
        code, result = self.cli("location-add", str(self._location_file()), "--expected-revision", str(state["revision"]),
                                "--connect", "valdombra", "--discover")
        self.assertEqual(code, 0, result)
        table = self.store.table()
        self.assertEqual(table["world"]["locations"][-1], new_location())
        self.assertIn(["bottega", "valdombra"], table["world"]["paths"])
        self.assertIn("bottega", table["state"]["discovered"])
        self.assertEqual(table["state"]["location_id"], "valdombra", "Adding a pin is not travelling")
        self.assertEqual(table["status"]["revision"], table["state"]["revision"])
        self.assertEqual(self.store.world_path.read_bytes(), base_bytes)
        state, _ = self.store.commit({"location_id": "bottega"}, table["state"]["revision"])
        self.assertEqual(state["location_id"], "bottega")
        restored, _ = self.store.restore(state, state["revision"])
        self.assertEqual(restored["flags"]["public_locations"], [new_location()])

    def _location_file(self):
        path = self.root / "master" / "luogo.json"
        path.write_text(json.dumps(new_location()), encoding="utf-8")
        return path

    def test_bad_map_changes_and_stale_location_add_preserve_all_state(self):
        state = self.fill_group()
        for location, connect in ((new_location(id="valdombra"), []), (new_location(x=1001), []),
                                  (new_location(y=-1), []), (new_location(x=True), []),
                                  (new_location(actions="Faccio"), []), (new_location(), ["unknown"])):
            with self.subTest(location=location, connect=connect), self.assertRaises(CampaignError):
                self.store.add_location(location, state["revision"], connect=connect, discover=True)
            self.assertEqual(self.store.read(), state)
        self.store.note("Una modifica arrivata mentre si prepara il luogo.")
        current = self.store.read()
        with self.assertRaises(CampaignError) as error:
            self.store.add_location(new_location(), state["revision"])
        self.assertEqual(error.exception.code, "revision_conflict")
        self.assertEqual(self.store.read(), current)

    def test_switching_base_map_cannot_silently_change_the_campaign_under_a_save(self):
        state = self.fill_group()
        wrong_world = {**self.world, "id": "different_campaign"}
        self.store.world_path.write_text(json.dumps(wrong_world), encoding="utf-8")
        with self.assertRaises(CampaignError):
            self.store.table()
        self.store.world_path.write_text(json.dumps(self.world), encoding="utf-8")
        self.assertEqual(self.store.read(), state)

    def test_combat_requires_a_real_round_and_consistent_party_hp_and_conditions(self):
        state = self.fill_group()
        member = state["party"][0]
        participant = {key: member[key] for key in ("id", "name", "max_hp", "hp", "ac")}
        participant.update(initiative=14, conditions=[])
        combat = {"active": True, "round": 1, "turn_index": 0, "participants": [participant]}
        with self.assertRaises(CampaignError):
            self.store.commit({"combat": {**combat, "round": 0}}, state["revision"])
        state, _ = self.store.commit({"combat": combat}, state["revision"])
        current = copy.deepcopy(state)
        with self.assertRaises(CampaignError):
            self.store.commit({"character": {"hp": 3}}, state["revision"])
        with self.assertRaises(CampaignError):
            self.store.commit({"character": {"conditions": ["avvelenato"]}}, state["revision"])
        self.assertEqual(self.store.read(), current)
        participant.update(hp=3, conditions=["avvelenato"])
        state, _ = self.store.commit({"character": {"hp": 3, "conditions": ["avvelenato"]},
                                      "combat": {"participants": [participant]}}, state["revision"])
        self.assertEqual(state["party"][0]["hp"], 3)
        self.assertEqual(state["combat"]["participants"][0]["hp"], 3)

    def test_malformed_optional_sheet_fields_cannot_poison_import(self):
        state = self.fill_group()
        bad = [{"features": "un testo"}, {"conditions": [False]}, {"spells": {"ability": []}},
               {"spells": {"cantrips": "Dardo"}}, {"proficiencies": {"tools": "Liuto"}},
               {"saving_throws": {"str": True}}, {"death_saves": {"failures": 4}}]
        for extra in bad:
            incoming = copy.deepcopy(state)
            incoming["party"][0].update(extra)
            incoming["character"] = copy.deepcopy(incoming["party"][0])
            with self.subTest(extra=extra), self.assertRaises(CampaignError):
                self.store.restore(incoming, state["revision"])
            self.assertEqual(self.store.read(), state)

    def test_private_dice_do_not_leak_to_state_export_or_revision(self):
        state = self.fill_group()
        before = self.store.state_path.read_bytes()
        code, result = self.cli("roll", "1d20+4", "--label", "Percezione segreta del custode", "--private")
        self.assertEqual(code, 0, result)
        self.assertTrue(result["private"])
        self.assertEqual(self.store.state_path.read_bytes(), before)
        self.assertEqual(self.store.read(), state)
        log = json.loads((self.root / "master" / "rolls-private.json").read_text(encoding="utf-8"))
        self.assertEqual(log[-1], result["roll"])
        self.assertNotIn("custode", json.dumps(self.store.table()))


class LiveHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-live-http-")
        self.root = Path(self.temp.name)
        fixture(self.root, party_size=4)
        self.server = LocalServer(("127.0.0.1", 0), self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, data=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request(method, path, json.dumps(data) if data is not None else None,
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response.status, json.loads(raw)

    def test_health_table_and_status_support_live_client_without_private_files(self):
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["api_version"], 3)
        self.assertGreater(health["pid"], 0)
        self.assertEqual(len(health["runtime_fingerprint"]), 64)
        status, table = self.request("GET", "/api/table")
        self.assertEqual(status, 200)
        self.assertEqual(table["world"]["id"], table["state"]["campaign_id"])
        self.assertEqual(table["status"]["revision"], table["state"]["revision"])
        self.assertFalse(table["status"]["started"])
        self.assertEqual(self.request("GET", "/api/status")[1], table["status"])

    def test_http_import_requires_revision_and_cannot_erase_newly_queued_actions(self):
        for name in ("Alba", "Berto", "Cleo", "Dario"):
            self.server.store.choose_character("ranger", name)
        incoming = self.server.store.read()
        self.assertEqual(self.request("POST", "/api/import", {"state": incoming})[0], 400)
        self.assertEqual(self.request("POST", "/api/import", {"state": incoming, "expected_revision": None})[0], 400)
        current, action = self.server.store.queue_action("Cleo: aspetto una risposta.")
        status, response = self.request("POST", "/api/import", {"state": incoming, "expected_revision": incoming["revision"]})
        self.assertEqual(status, 409)
        self.assertEqual(response["code"], "revision_conflict")
        self.assertEqual(self.server.store.read(), current)
        self.assertEqual(self.server.store.read()["pending_actions"], [action])

    def test_template_revision_guard_matches_custom_character_guard(self):
        self.server.store.note("Un aggiornamento concorrente.")
        status, result = self.request("POST", "/api/character", {"template_id": "ranger", "expected_revision": 0})
        self.assertEqual(status, 409)
        self.assertEqual(result["code"], "revision_conflict")
        self.assertEqual(self.server.store.read()["party"], [])


if __name__ == "__main__":
    unittest.main()
