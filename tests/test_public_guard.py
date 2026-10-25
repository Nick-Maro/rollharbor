"""Publication checks inspect staged paths even when .gitignore hides them."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_public import check

ROOT = Path(__file__).resolve().parents[1]


class PublicationGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rollharbor-public-guard-")
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / ".gitignore").write_bytes((ROOT / "publication/.gitignore").read_bytes())
        self.add("README.md", "A public demo.\n")

    def tearDown(self):
        self.temp.cleanup()

    def add(self, relative, content):
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "-f", "--", relative], cwd=self.root, check=True)

    def test_private_untracked_runtime_does_not_block_public_source(self):
        (self.root / "data").mkdir()
        (self.root / "data/campaign.json").write_text('{"private":true}', encoding="utf-8")
        self.assertTrue(check(self.root)["ok"])

    def test_force_added_runtime_and_key_files_are_rejected_without_printing_values(self):
        for path in ("data/campaign.json", "master/note.md", "campaigns/private/ocr.txt",
                     ".env.production", "ssh/id_ed25519", "certs/server.key", "certs/server.pem"):
            self.add(path, "SENSITIVE_VALUE_ONLY_IN_TEST_FIXTURE")
        result = check(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["findings"]), 7)
        self.assertNotIn("SENSITIVE_VALUE_ONLY_IN_TEST_FIXTURE", json.dumps(result))

    def test_public_environment_examples_are_accepted(self):
        self.add(".env.example", "SERVER_PORT=8765\n")
        self.add(".env.template", "SERVER_PORT=8765\n")
        self.assertTrue(check(self.root)["ok"])

    def test_case_variants_of_private_paths_are_rejected(self):
        self.add("MASTER/secret.md", "Private example, no credentials.")
        self.add("HANDOFF.MD", "Private example, no credentials.")
        result = check(self.root)
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["findings"]), 2)
        self.assertTrue(all(item["reason"] == "private_runtime_path" for item in result["findings"]))

    def test_removing_ignore_protection_is_reported_even_without_private_files(self):
        (self.root / ".gitignore").write_text("", encoding="utf-8")
        result = check(self.root)
        self.assertFalse(result["ok"])
        self.assertTrue(all(item["reason"] == "runtime_ignore_rule_missing" for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
