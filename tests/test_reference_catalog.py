"""Public rules cards cover character-creator output without campaign spoilers."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from character_builder import CLASSES, SPECIES, build_character

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("node"), "Node is required to inspect browser catalog")
class ReferenceCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        script = "global.window={};require('./web/rules-catalog.js');process.stdout.write(JSON.stringify(window.DndRulesCatalog));"
        cls.catalog = json.loads(subprocess.check_output(["node", "-e", script], cwd=ROOT, encoding="utf-8"))
        cls.entries = cls.catalog["entries"]
        cls.names = {text.casefold() for entry in cls.entries for text in [entry["title"], *entry["aliases"]]}

    def test_schema_has_unique_public_cards_and_edition(self):
        self.assertEqual(self.catalog["version"], "2014")
        self.assertEqual(len({entry["id"] for entry in self.entries}), len(self.entries))
        for entry in self.entries:
            self.assertIn(entry["kind"], {"spell", "item", "weapon", "armor", "feature", "condition", "rule"})
            self.assertTrue(entry["summary"])
            self.assertTrue(entry["source"]["url"].startswith("https://"))
            self.assertIsInstance(entry["details"], list)
            for fact in entry["facts"]:
                self.assertTrue(fact["label"])
                self.assertIsInstance(fact["value"], str)

    def test_every_creator_inventory_spell_and_resource_is_documented(self):
        for class_id in CLASSES:
            for species_id in SPECIES:
                character = build_character({"class_id": class_id, "species_id": species_id, "name": "QA"})
                for item in character["inventory"]:
                    self.assertIn(item["name"].casefold(), self.names)
                for group in ("cantrips", "known", "prepared"):
                    for spell in character["spells"][group]:
                        self.assertIn(spell.split(" · ")[0].casefold(), self.names)
                for resource in character["resources"]:
                    self.assertIn(resource["id"].casefold(), self.names)

    def test_shield_spell_and_equipment_are_separate(self):
        shields = [entry for entry in self.entries if entry["title"] == "Scudo"]
        self.assertEqual({entry["kind"] for entry in shields}, {"spell", "armor"})
        spell = next(entry for entry in shields if entry["kind"] == "spell")
        self.assertIn("reazione", spell["mechanics"]["casting_time"])

    def test_entangle_is_concentration_and_guidance_is_free_cantrip(self):
        cards = {entry["id"]: entry for entry in self.entries}
        self.assertTrue(cards["spell-entangle"]["mechanics"]["concentration"])
        self.assertEqual(cards["spell-guidance"]["mechanics"]["level"], 0)
        self.assertIn("Nessuno slot", [fact["value"] for fact in cards["spell-guidance"]["facts"]])

    def test_non_srd_spell_is_attributed_to_its_actual_source(self):
        agathys = next(entry for entry in self.entries if entry["id"] == "spell-armor-agathys")
        self.assertIn("2014", agathys["source"]["label"])
        self.assertNotIn("SRD", agathys["source"]["label"])


if __name__ == "__main__":
    unittest.main()
