"""Real temporary saves and HTTP requests; never writes the playable campaign."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError, MAX_BACKUPS, StateStore, parse_dice, roll_dice, validate_state
from server import LocalServer, MAX_BODY_BYTES


def fixture(root: Path, party_size=1):
    (root / "data").mkdir()
    character = {
        "id": "ranger", "name": "Mira", "species": "Umana", "class": "Guerriera",
        "level": 1, "hp": 12, "max_hp": 12, "ac": 16, "speed": 9, "proficiency": 2,
        "abilities": {"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8},
        "skills": {"perception": 3}, "attacks": [{"name": "Spada", "bonus": 5, "damage": "1d8+3"}],
        "resources": [{"id": "wind", "name": "Recuperare energie", "current": 1, "max": 1, "reset": "short"}],
        "inventory": [{"name": "Corda", "qty": 1}], "gold": 10, "description": "Una viaggiatrice."
    }
    world = {"id": "nebbia", "title": "Test", "subtitle": "Prova",
             "locations": [{"id": "valdombra", "name": "Valdombra", "type": "town", "x": 10, "y": 20,
                            "description": "Una città.", "actions": ["Entro"]},
                           {"id": "crocevia", "name": "Crocevia", "type": "road", "x": 30, "y": 40,
                            "description": "Una strada.", "actions": ["Procedo"]}],
             "paths": [["valdombra", "crocevia"]], "character_templates": [character]}
    state = {"schema_version": 1, "revision": 0, "campaign_id": "nebbia", "phase": "creation", "session": 1,
             "location_id": "valdombra", "discovered": ["valdombra", "crocevia"], "character": None,
             "party_size": party_size, "party": [], "active_character_id": None,
             "scene": {"title": "L'inizio", "text": "Una pioggia leggera.", "choices": ["Entro in locanda"]},
             "quests": [{"id": "rain", "title": "Pioggia", "description": "Trova riparo.", "status": "active"}],
             "journal": [], "rolls": [], "pending_actions": [],
             "combat": {"active": False, "round": 0, "turn_index": 0, "participants": []},
             "clock": {"day": 1, "time": "17:30", "weather": "Pioggia sottile"}, "flags": {}}
    for name, data in (("world", world), ("campaign", state)):
        (root / "data" / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    (root / "web").mkdir()
    (root / "web" / "index.html").write_text("<!doctype html><title>Il tavolo</title>", encoding="utf-8")
    (root / "master").mkdir()
    (root / "master" / "secrets.md").write_text("SECRET_DRAGON", encoding="utf-8")
    return state, world


class DiceTests(unittest.TestCase):
    def test_parsing_and_limits(self):
        self.assertEqual(parse_dice(" 2D6 + 3 "), (2, 6, 3, "2d6+3"))
        for expression in ("__import__('os')", "1d20;exit", "0d20", "31d6", "1d1", "1d101", "1d20+1001", "1d20-1001", "1d20+1d6"):
            with self.subTest(expression=expression), self.assertRaises(CampaignError):
                parse_dice(expression)
        for expression in ("2d20", "1d6"):
            with self.assertRaises(CampaignError):
                parse_dice(expression, "advantage")

    def test_advantage_disadvantage_keep_exactly_one_d20(self):
        with patch("engine.secrets.randbelow", side_effect=[0, 19]):
            result = roll_dice("1d20+3", "Percezione", "advantage")
        self.assertEqual(result["dice"], [1, 20])
        self.assertEqual(result["kept"], [20])
        self.assertEqual(result["total"], 23)
        with patch("engine.secrets.randbelow", side_effect=[0, 19]):
            result = roll_dice("1d20-2", "Furtività", "disadvantage")
        self.assertEqual(result["kept"], [1])
        self.assertEqual(result["total"], -1)
        with patch("engine.secrets.randbelow", side_effect=[0, 5]):
            result = roll_dice("2d6+2")
        self.assertEqual(result["total"], 9)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-test-")
        self.root = Path(self.temp.name)
        self.initial, self.world = fixture(self.root)
        self.store = StateStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_character_then_intention_and_atomic_master_resolution(self):
        with self.assertRaises(CampaignError):
            self.store.queue_action("Entro")
        state, character = self.store.choose_character("ranger", "Nadia")
        self.assertEqual(character["name"], "Nadia")
        self.assertEqual(state["phase"], "playing")
        with self.assertRaises(CampaignError):
            self.store.choose_character("ranger")
        state, action = self.store.queue_action("Ascolto alla porta")
        self.assertEqual(state["scene"], self.initial["scene"], "Intentions do not adjudicate the story")
        revised, _ = self.store.commit({"scene": {"text": "Senti dei passi."}, "flags": {"heard": True}},
                                       state["revision"], [action["id"]], "Nadia sente dei passi.")
        self.assertEqual(revised["scene"]["title"], "L'inizio")
        self.assertEqual(revised["scene"]["text"], "Senti dei passi.")
        self.assertFalse(revised["pending_actions"])
        self.assertEqual(revised["journal"][-1]["text"], "Nadia sente dei passi.")
        self.assertTrue(list((self.root / "saves").glob("campaign-*.json")))

    def test_stale_revision_cannot_overwrite_new_action(self):
        state, _ = self.store.choose_character("ranger")
        old_revision = state["revision"]
        new_state, action = self.store.queue_action("Mi nascondo")
        with self.assertRaises(CampaignError) as error:
            self.store.commit({"clock": {"time": "18:00"}}, old_revision)
        self.assertEqual(error.exception.code, "revision_conflict")
        self.assertEqual(self.store.read(), new_state)
        self.assertEqual(self.store.read()["pending_actions"][0]["id"], action["id"])

    def test_invalid_patch_leaves_state_unchanged(self):
        for patch_value in ({"revision": 100}, {"pending_actions": []}, {"location_id": "unknown"},
                            {"clock": {"time": "35:70"}}, {"combat": {"active": True}},
                            {"character": {"hp": -1}}, {"flags": {"bad": float("nan")}}):
            with self.subTest(patch=patch_value), self.assertRaises(CampaignError):
                self.store.commit(patch_value, 0)
            self.assertEqual(self.store.read(), self.initial)

    def test_import_is_validated_and_revision_remains_monotonic(self):
        self.store.note("Da conservare nel backup")
        imported = copy.deepcopy(self.initial)
        imported["revision"] = 999999
        state, _ = self.store.restore(imported)
        self.assertEqual(state["revision"], 2)
        self.assertEqual(state["journal"][-1]["kind"], "system")
        wrong_campaign = copy.deepcopy(imported)
        wrong_campaign["campaign_id"] = "other"
        with self.assertRaises(CampaignError):
            self.store.restore(wrong_campaign)
        self.assertEqual(self.store.read(), state)
        invalid = copy.deepcopy(imported)
        invalid["location_id"] = {}
        with self.assertRaises(CampaignError):
            validate_state(invalid, self.world)

    def test_concurrent_threads_keep_every_action(self):
        self.store.choose_character("ranger")
        def enqueue(number):
            # Separate store instances must still share their path lock.
            return StateStore(self.root).queue_action(f"Azione {number}")
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(enqueue, range(24)))
        state = self.store.read()
        self.assertEqual(state["revision"], 25)
        self.assertEqual(len(state["pending_actions"]), 24)
        self.assertEqual(len({a["id"] for a in state["pending_actions"]}), 24)
        self.assertEqual(sorted(s[0]["revision"] for s in results), list(range(2, 26)))

    def test_separate_cli_processes_share_lock(self):
        processes = [subprocess.Popen([sys.executable, str(ROOT / "tools" / "dnd.py"), "--root", str(self.root),
                                       "note", f"Processo {i}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for i in range(8)]
        for process in processes:
            stdout, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, stderr.decode("utf-8", errors="replace"))
            self.assertIn("revision", json.loads(stdout))
        state = self.store.read()
        self.assertEqual(state["revision"], 8)
        self.assertEqual(len(state["journal"]), 8)

    def test_backup_retention_and_snapshot_does_not_change_revision(self):
        for i in range(MAX_BACKUPS + 3):
            self.store.note(f"Nota {i}")
        revision = self.store.read()["revision"]
        path = self.store.snapshot()
        self.assertTrue(path.is_file())
        self.assertEqual(self.store.read()["revision"], revision)
        self.assertEqual(len(list((self.root / "saves").glob("campaign-*.json"))), MAX_BACKUPS)

    def test_tampered_roll_rejected_on_import(self):
        state, _ = self.store.roll("1d20+3", "Percezione", "advantage")
        state["rolls"][0]["total"] = 999
        with self.assertRaises(CampaignError):
            self.store.restore(state)

    def test_legacy_solo_is_upgraded_in_memory_without_rewriting_save(self):
        legacy = copy.deepcopy(self.initial)
        for key in ("party_size", "party", "active_character_id"):
            del legacy[key]
        legacy["character"] = copy.deepcopy(self.world["character_templates"][0])
        legacy["phase"] = "playing"
        original_bytes = json.dumps(legacy).encode("utf-8")
        self.store.state_path.write_bytes(original_bytes)
        normalized = self.store.read()
        self.assertEqual(normalized["party_size"], 1)
        self.assertEqual(normalized["party"], [legacy["character"]])
        self.assertEqual(normalized["active_character_id"], "ranger")
        self.assertEqual(self.store.state_path.read_bytes(), original_bytes)


class PartyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-party-")
        self.root = Path(self.temp.name)
        self.initial, self.world = fixture(self.root, party_size=4)
        self.store = StateStore(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def fill_group(self):
        for name in ("Ada", "Bruno", "Carla", "Dario"):
            state, _ = self.store.choose_character("ranger", name)
        return state

    def test_four_members_reusing_templates_are_distinct_and_preserved(self):
        first, character = self.store.choose_character("ranger", "Ada")
        self.assertEqual(first["phase"], "creation")
        self.assertEqual(first["character"], character)
        self.assertEqual(character["template_id"], "ranger")
        self.assertNotEqual(character["id"], "ranger")
        with self.assertRaises(CampaignError):
            self.store.queue_action("Partiamo")
        for name in ("Bruno", "Carla", "Dario"):
            state, _ = self.store.choose_character("ranger", name)
        self.assertEqual(state["phase"], "playing")
        self.assertEqual([member["name"] for member in state["party"]], ["Ada", "Bruno", "Carla", "Dario"])
        self.assertEqual(len({member["id"] for member in state["party"]}), 4)
        self.assertEqual(state["character"], character)
        with self.assertRaises(CampaignError):
            self.store.choose_character("ranger", "Quinto")
        self.assertEqual(self.store.read(), state)

    def test_active_selection_changes_only_alias_and_revision(self):
        before = self.fill_group()
        selected = before["party"][2]
        after, character = self.store.active_character(selected["id"])
        self.assertEqual(character, selected)
        self.assertEqual(after["character"], selected)
        self.assertEqual(after["party"], before["party"])
        self.assertEqual(after["journal"], before["journal"])
        self.assertEqual(after["revision"], before["revision"] + 1)
        with self.assertRaises(CampaignError):
            self.store.active_character("pc_nonexistent")
        self.assertEqual(self.store.read(), after)

    def test_master_updates_canonical_party_and_active_character_consistently(self):
        before = self.fill_group()
        state, _ = self.store.commit({"character": {"hp": 8}}, before["revision"])
        self.assertEqual(state["party"][0]["hp"], 8)
        self.assertEqual(state["character"], state["party"][0])
        self.assertEqual(state["party"][1]["hp"], 12)
        # Selecting and modifying in the same patch must target the newly selected member.
        state, _ = self.store.commit({"active_character_id": state["party"][1]["id"],
                                      "character": {"hp": 5}}, state["revision"])
        self.assertEqual(state["character"]["name"], "Bruno")
        self.assertEqual(state["party"][1]["hp"], 5)
        self.assertEqual(state["party"][0]["hp"], 8)
        members = copy.deepcopy(state["party"])
        members[1]["hp"] = 3
        members[3]["hp"] = 7
        state, _ = self.store.commit({"party": members}, state["revision"])
        self.assertEqual(state["character"], members[1])
        self.assertEqual(state["party"][3]["hp"], 7)

    def test_invalid_party_updates_leave_all_members_unchanged(self):
        state = self.fill_group()
        duplicate = copy.deepcopy(state["party"])
        duplicate[1]["id"] = duplicate[0]["id"]
        invalid_patches = [
            {"party": duplicate}, {"party_size": 3}, {"party_size": 5},
            {"active_character_id": "pc_missing"}, {"character": {"id": "pc_new"}},
            {"party": state["party"], "character": {"hp": 1}},
            {"party": state["party"][:1]}, {"party": []},
        ]
        for patch_value in invalid_patches:
            with self.subTest(patch=patch_value), self.assertRaises(CampaignError):
                self.store.commit(patch_value, state["revision"])
            self.assertEqual(self.store.read(), state)
        mismatch = copy.deepcopy(state)
        mismatch["character"]["hp"] = 1
        with self.assertRaises(CampaignError):
            self.store.restore(mismatch)
        self.assertEqual(self.store.read(), state)

    def test_concurrent_fourth_and_fifth_additions_cannot_overfill(self):
        for name in ("Ada", "Bruno", "Carla"):
            self.store.choose_character("ranger", name)
        def add(name):
            try:
                return StateStore(self.root).choose_character("ranger", name)[1]
            except CampaignError:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(add, ("Dario", "Elena")))
        self.assertEqual(sum(outcome is not None for outcome in outcomes), 1)
        state = self.store.read()
        self.assertEqual(state["revision"], 4)
        self.assertEqual(len(state["party"]), 4)
        self.assertEqual(state["phase"], "playing")

    def test_separate_processes_add_four_members_without_lost_sheets(self):
        processes = [subprocess.Popen([sys.executable, str(ROOT / "tools" / "dnd.py"), "--root", str(self.root),
                                       "character", "ranger", "--name", f"Giocatore {i}"],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for i in range(4)]
        for process in processes:
            _, stderr = process.communicate(timeout=20)
            self.assertEqual(process.returncode, 0, stderr.decode("utf-8", errors="replace"))
        state = self.store.read()
        self.assertEqual(state["revision"], 4)
        self.assertEqual(len(state["party"]), 4)
        self.assertEqual(len({member["id"] for member in state["party"]}), 4)
        self.assertEqual({member["name"] for member in state["party"]}, {f"Giocatore {i}" for i in range(4)})
        self.assertEqual(state["phase"], "playing")


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-http-")
        self.root = Path(self.temp.name)
        self.initial, self.world = fixture(self.root)
        self.server = LocalServer(("127.0.0.1", 0), self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None, raw=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        request_headers = dict(headers or {})
        if payload is not None:
            raw = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, raw, request_headers)
        response = connection.getresponse()
        body = response.read()
        result = (response.status, dict(response.getheaders()), body)
        connection.close()
        return result

    def test_health_world_static_and_export(self):
        status, headers, raw = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["app"], "dnd-local-master")
        self.assertEqual(json.loads(raw)["workspace"], str(self.root.resolve()))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(json.loads(self.request("GET", "/api/world")[2]), self.world)
        self.assertIn(b"Il tavolo", self.request("GET", "/")[2])
        status, headers, raw = self.request("GET", "/api/export")
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertEqual(json.loads(raw), self.initial)

    def test_secret_and_path_traversal_inaccessible(self):
        for path in ("/master/secrets.md", "/data/campaign.json", "/engine.py", "/saves/a.json",
                     "/../master/secrets.md", "/%2e%2e/master/secrets.md", "/%5c..%5cmaster%5csecrets.md",
                     "/api/../master/secrets.md", "/.campaign.lock"):
            with self.subTest(path=path):
                status, _, raw = self.request("GET", path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"SECRET_DRAGON", raw)

    def test_character_queue_roll_note_and_import(self):
        status, _, raw = self.request("POST", "/api/character", {"template_id": "ranger", "name": "Luce"})
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["character"]["name"], "Luce")
        status, _, raw = self.request("POST", "/api/action", {"text": "Cerco impronte"})
        self.assertEqual(status, 200, raw)
        response = json.loads(raw)
        self.assertEqual(response["state"]["scene"], self.initial["scene"])
        self.assertEqual(response["action"]["text"], "Cerco impronte")
        status, _, raw = self.request("POST", "/api/roll", {"expression": "1d20+3", "mode": "advantage"})
        self.assertEqual(status, 200, raw)
        self.assertEqual(len(json.loads(raw)["roll"]["dice"]), 2)
        status, _, raw = self.request("POST", "/api/note", {"text": "Il fabbro porta un anello"})
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["note"]["kind"], "note")
        imported = copy.deepcopy(self.initial)
        imported["revision"] = 12345
        status, _, raw = self.request("POST", "/api/import", {"state": imported, "expected_revision": 4})
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["state"]["revision"], 5)
        imported["campaign_id"] = "wrong"
        self.assertEqual(self.request("POST", "/api/import", {"state": imported, "expected_revision": 5})[0], 400)

    def test_host_origin_content_type_and_body_limits(self):
        self.assertEqual(self.request("GET", "/api/state", headers={"Host": "attacker.example"})[0], 403)
        for origin in ("https://evil.example", "null", "http://127.0.0.1:1", "http://localhost:bad"):
            with self.subTest(origin=origin):
                self.assertEqual(self.request("POST", "/api/note", {"text": "no"}, {"Origin": origin})[0], 403)
        good = {"Origin": f"http://127.0.0.1:{self.port}"}
        self.assertEqual(self.request("POST", "/api/note", {"text": "ok"}, good)[0], 200)
        self.assertEqual(self.request("POST", "/api/note", raw=b'{"text":"no"}', headers={"Content-Type": "text/plain"})[0], 415)
        oversized = {"Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1)}
        self.assertEqual(self.request("POST", "/api/note", raw=b"", headers=oversized)[0], 413)
        self.assertEqual(self.request("POST", "/api/note", raw=b"{", headers={"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/note", {"text": ""})[0], 400)
        self.assertEqual(self.request("POST", "/api/note", {"text": "hello", "arbitrary": 4})[0], 400)
        self.assertEqual(self.server.store.read()["revision"], 1)

    def test_four_person_party_api_preserves_roster_and_selects_active_sheet(self):
        # Configure only the temporary fixture as a four-person game.
        self.server.store.commit({"party_size": 4}, 0)
        ids = []
        for name in ("Ada", "Bruno", "Carla", "Dario"):
            status, _, raw = self.request("POST", "/api/character", {"template_id": "ranger", "name": name})
            self.assertEqual(status, 200, raw)
            result = json.loads(raw)
            ids.append(result["character"]["id"])
        self.assertEqual(len(set(ids)), 4)
        self.assertEqual(result["state"]["phase"], "playing")
        previous_journal = result["state"]["journal"]
        status, _, raw = self.request("POST", "/api/active-character", {"character_id": ids[2]})
        self.assertEqual(status, 200, raw)
        result = json.loads(raw)
        self.assertEqual(result["character"]["name"], "Carla")
        self.assertEqual(result["state"]["active_character_id"], ids[2])
        self.assertEqual(result["state"]["journal"], previous_journal)
        self.assertEqual(len(result["state"]["party"]), 4)
        self.assertEqual(self.request("POST", "/api/active-character", {"character_id": "missing"})[0], 400)
        self.assertEqual(self.request("POST", "/api/character", {"template_id": "ranger"})[0], 400)


if __name__ == "__main__":
    unittest.main()
