"""First launch and public export preserve real campaigns and exclude secrets."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import secrets
import subprocess
import tempfile
import unittest

from engine import CampaignError, StateStore
from tools.setup_demo import initialize
from tools.export_public import export

ROOT = Path(__file__).resolve().parents[1]


class DemoSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "table"
        shutil.copytree(ROOT / "examples/demo", self.root / "examples/demo")

    def tearDown(self):
        self.temp.cleanup()

    def test_first_launch_has_four_empty_seats_and_repeated_launch_preserves_progress(self):
        self.assertTrue(initialize(self.root)["initialized"])
        store = StateStore(self.root)
        state = store.read()
        self.assertEqual((state["party_size"], state["party"], state["revision"]), (4, [], 0))
        state, _ = store.create_character({"name": "Ada", "class_id": "fighter", "species_id": "human"})
        before = store.state_path.read_bytes()
        self.assertTrue(initialize(self.root)["preserved"])
        self.assertEqual(store.state_path.read_bytes(), before)
        self.assertEqual(store.read(), state)

    def test_partial_or_invalid_saves_are_never_replaced(self):
        (self.root / "data").mkdir()
        path = self.root / "data/world.json"
        path.write_text('{"sentinel": "KEEP"}', encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(CampaignError):
            initialize(self.root)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.root / "data/campaign.json").exists())

    def test_missing_template_fails_before_creating_either_save(self):
        (self.root / "examples/demo/CURRENT.md").unlink()
        with self.assertRaises(OSError):
            initialize(self.root)
        self.assertFalse((self.root / "data/campaign.json").exists())
        self.assertFalse((self.root / "data/world.json").exists())

    def test_existing_private_notes_and_simultaneous_launches_are_preserved(self):
        (self.root / "master").mkdir()
        notes = self.root / "master/MEMORIA.md"
        notes.write_text("PRIVATE_CANARY", encoding="utf-8")
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: initialize(self.root), range(2)))
        self.assertEqual(sum(item["initialized"] for item in results), 1)
        self.assertEqual(notes.read_text(encoding="utf-8"), "PRIVATE_CANARY")


class PublicExportTests(unittest.TestCase):
    def test_export_omits_history_secrets_sources_and_runtime_even_if_not_gitignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source"
            marker = "EXPORT_SECRET_" + secrets.token_hex(16)
            # Copy the source allowlist into an isolated tree; then plant canaries.
            export(ROOT, source)
            for name in ("master/password.txt", "data/campaign.json", "saves/snapshot.json",
                         "campaigns/commercial/ocr/page.txt", ".git/config", "private.pdf",
                         "docs/TAVOLO_LOCALE.md", ".env"):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(marker, encoding="utf-8")
            destination = Path(temporary) / "public"
            export(source, destination)
            self.assertFalse((destination / ".git").exists())
            for path in destination.rglob("*"):
                if path.is_file():
                    self.assertNotIn(marker.encode(), path.read_bytes(), str(path))
            self.assertTrue((destination / "examples/demo/world.json").exists())
            self.assertIn("Running this table", (destination / "AGENTS.md").read_text(encoding="utf-8"))
            catalog = json.loads((destination / "web/assets/maps/library.json").read_text(encoding="utf-8"))
            for entry in catalog["maps"]:
                for variant in entry["variants"]:
                    for kind in ("svg", "png"):
                        self.assertTrue((destination / "web" / variant[kind].lstrip("/")).is_file())
            self.assertEqual(initialize(destination)["campaign_id"], "demo")
            subprocess.run(["git", "init", "-q", str(destination)], check=True)
            for name in ("data/campaign.json", "master/MEMORIA.md", "handoff.md"):
                result = subprocess.run(["git", "check-ignore", name], cwd=destination, capture_output=True)
                self.assertEqual(result.returncode, 0, name)

    def test_export_refuses_existing_or_nested_destinations(self):
        with tempfile.TemporaryDirectory() as temporary:
            existing = Path(temporary)
            with self.assertRaises(ValueError):
                export(ROOT, existing)
            with self.assertRaises(ValueError):
                export(ROOT, ROOT / "bad-export")


if __name__ == "__main__":
    unittest.main()
