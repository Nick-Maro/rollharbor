"""Campaign preparation and reveals use private fixtures, never the playable save."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError, StateStore
from tools import campaign
from test_engine import fixture


class CampaignToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="dnd-campaign-qa-")
        self.root = Path(self.temporary.name)
        fixture(self.root)
        self.pack = self.root / "campaigns/nebbia"
        self.pack.mkdir(parents=True)
        entries = []
        for place_id, connections in (("hidden_room", ["trail", "clearing"]),
                                      ("trail", []), ("clearing", []), ("village_inn", [])):
            entries.append({"refpage": 1, "precondition": "Only reveal after a declared discovery.",
                            "connect": connections, "location": {
                                "id": place_id, "name": place_id, "type": "site", "x": 100, "y": 100,
                                "description": "Original synthetic test location.", "actions": ["Observe."]}})
        self.write_json(self.pack / "locations-private.json", {"campaign_id": "nebbia", "locations": entries})
        self.pdf = self.root / "source.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n1 0 obj <</Type /Pages /Count 3>> endobj\n"
                             b"2 0 obj <</Type /Page>> endobj\n"
                             b"3 0 obj <</Type/Page>> endobj\n"
                             b"4 0 obj <</Type /Page>> endobj\n%%EOF")
        digest = hashlib.sha256(self.pdf.read_bytes()).hexdigest()
        self.manifest = {"title": "Fixture source", "path": "source.pdf", "sha256": digest,
                         "page_count": 3, "ocr_path": "campaigns/nebbia/ocr"}
        self.write_json(self.pack / "source.json", self.manifest)
        ocr = self.pack / "ocr"
        ocr.mkdir()
        self.write_json(ocr / "manifest.json", {"sha256": digest, "pages": 3})
        for n in range(1, 4):
            (ocr / f"page-{n:03d}.txt").write_text(f"PAGINA PDF {n} / 3 — OCR DA VERIFICARE\nTest\n", encoding="utf-8")
        self.store = StateStore(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    @staticmethod
    def write_json(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def catalog(self):
        return campaign.load_catalog(self.pack, "nebbia")

    def reveal(self, place_id, revision=None):
        table = self.store.table()
        return campaign.reveal_location(self.store, table, self.catalog(), place_id,
                                         table["state"]["revision"] if revision is None else revision)

    def test_reveal_preserves_party_scene_clock_and_private_notes(self):
        before = self.store.read()
        world_bytes = self.store.world_path.read_bytes()
        result = self.reveal("hidden_room")
        after = self.store.read()
        self.assertEqual(after["revision"], before["revision"] + 1)
        for key in ("party", "active_character_id", "location_id", "clock", "scene", "journal"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(self.store.world_path.read_bytes(), world_bytes)
        self.assertIn("hidden_room", after["discovered"])
        self.assertEqual(result["connected_to"], [])  # Both trail sites remain private.
        location = after["flags"]["public_locations"][0]
        self.assertNotIn("precondition", location)
        self.assertNotIn("refpage", location)
        self.assertNotIn("clearing", {row["id"] for row in self.store.table()["world"]["locations"]})

    def test_connections_only_include_already_public_locations(self):
        self.reveal("trail")
        result = self.reveal("hidden_room")
        self.assertEqual(result["connected_to"], ["trail"])
        self.assertEqual(self.store.read()["flags"]["public_paths"][-1], ["hidden_room", "trail"])

    def test_repeated_reveal_is_noop_but_stale_revision_is_rejected(self):
        first = self.reveal("village_inn")
        before = self.store.read()
        files = list((self.root / "saves").glob("*.json"))
        result = self.reveal("village_inn")
        self.assertTrue(result["already_revealed"])
        self.assertEqual(self.store.read(), before)
        self.assertEqual(list((self.root / "saves").glob("*.json")), files)
        with self.assertRaises(CampaignError) as caught:
            self.reveal("village_inn", first["revision"] - 1)
        self.assertEqual(caught.exception.code, "revision_conflict")
        self.assertEqual(self.store.read(), before)

    def test_existing_location_with_different_text_is_not_overwritten(self):
        original = next(row["location"] for row in self.catalog()["locations"] if row["location"]["id"] == "village_inn")
        changed = copy.deepcopy(original)
        changed["description"] = "The master changed the visible location during play."
        self.store.add_location(changed, 0, discover=True)
        before = self.store.read()
        with self.assertRaises(CampaignError):
            self.reveal("village_inn")
        self.assertEqual(self.store.read(), before)

    def test_existing_undiscovered_location_can_be_discovered(self):
        location = next(row["location"] for row in self.catalog()["locations"] if row["location"]["id"] == "village_inn")
        self.store.add_location(location, 0, discover=False)
        self.reveal("village_inn")
        state = self.store.read()
        self.assertIn("village_inn", state["discovered"])
        self.assertEqual(len(state["flags"]["public_locations"]), 1)
        self.assertEqual(state["location_id"], "valdombra")

    def test_catalog_campaign_mismatch_and_private_field_leak_are_rejected(self):
        path = self.pack / "locations-private.json"
        catalog = json.loads(path.read_text(encoding="utf-8"))
        catalog["campaign_id"] = "other_campaign"
        self.write_json(path, catalog)
        with self.assertRaises(CampaignError):
            self.catalog()
        catalog["campaign_id"] = "nebbia"
        catalog["locations"][0]["location"]["secret"] = "A private clue"
        self.write_json(path, catalog)
        with self.assertRaises(CampaignError):
            self.catalog()

    def test_source_integrity_checks_hash_pages_and_ocr(self):
        self.assertTrue(campaign.verify_source(self.root, self.pack)["ok"])
        self.assertEqual(campaign.source_info(self.root, self.pack)["ocr"]["available"], 3)
        self.pdf.write_bytes(self.pdf.read_bytes() + b"changed")
        result = campaign.verify_source(self.root, self.pack)
        self.assertFalse(result["ok"])
        self.assertFalse(result["sha256_matches"])
        self.assertEqual(result["actual_page_count"], 3)
        (self.pack / "ocr/page-002.txt").unlink()
        result = campaign.verify_source(self.root, self.pack)
        self.assertFalse(result["ocr"]["complete"])
        self.assertEqual(result["ocr"]["missing"], [2])
        self.manifest["page_count"] = 4
        self.write_json(self.pack / "source.json", self.manifest)
        self.assertFalse(campaign.verify_source(self.root, self.pack)["ok"])

    def test_manifest_paths_must_stay_within_workspace(self):
        self.manifest["path"] = "../outside.pdf"
        self.write_json(self.pack / "source.json", self.manifest)
        with self.assertRaises(CampaignError):
            campaign.source_info(self.root, self.pack)

    def test_cli_json_and_list_alias(self):
        for command in ("info", "verify", "list"):
            run = subprocess.run([sys.executable, str(ROOT / "tools/campaign.py"), "--root", str(self.root), command],
                                 capture_output=True, text=True, encoding="utf-8", timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            payload = json.loads(run.stdout)
            self.assertEqual(payload["campaign_id"], "nebbia")
            if command == "list":
                self.assertTrue(payload["private"])
        run = subprocess.run([sys.executable, str(ROOT / "tools/campaign.py"), "--root", str(self.root),
                              "reveal", "village_inn", "--expected-revision", "0"],
                             capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["location_id"], "village_inn")


if __name__ == "__main__":
    unittest.main()
