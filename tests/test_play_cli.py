"""CLI contracts only; combat and transactional rules are exercised by backend tests."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import CampaignError
from tools import play


class PlayCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dnd-play-cli-")
        self.root = Path(self.temp.name)
        self.action = Mock()
        self.session = Mock()
        self.action_module = types.ModuleType("tools.action_engine")
        self.action_module.ActionEngine = Mock(return_value=self.action)
        self.session_module = types.ModuleType("tools.session_ops")
        self.session_module.SessionOps = Mock(return_value=self.session)
        self.modules = patch.dict(sys.modules, {"tools.action_engine": self.action_module,
                                               "tools.session_ops": self.session_module})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.addCleanup(self.temp.cleanup)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = play.main(["--root", str(self.root), *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_attack_parses_unarmed_bonus_and_explicit_dm_checks(self):
        self.action.resolve_attack.return_value = {"revision": 12, "result": {"hit": True}}
        code, out, err = self.cli("attack", "d", "Gundren", "--attack", "pugno", "--bonus",
                                  "--melee", "--nonlethal", "--reactions-checked", "--modifiers-checked",
                                  "--id", "s1-r1-d-bonus", "--expected-revision", "11")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(out.splitlines()), 1)
        self.assertEqual(json.loads(out)["revision"], 12)
        self.action.resolve_attack.assert_called_once_with(
            {"actor": "d", "target": "Gundren", "attack": "pugno", "mode": "normal",
             "action": "martial_bonus", "nonlethal": True, "melee": True,
             "reactions_checked": True, "modifiers_checked": True}, "s1-r1-d-bonus", 11)

    def test_attack_index_and_pending_lethality_are_preserved(self):
        self.action.resolve_attack.return_value = {"revision": 12}
        code, _, err = self.cli("attack", "d", "Gundren", "--attack", "0", "--id", "attack-1",
                                "--expected-revision", "11")
        self.assertEqual((code, err), (0, ""))
        spec = self.action.resolve_attack.call_args.args[0]
        self.assertEqual(spec["attack"], 0)
        self.assertIsNone(spec["nonlethal"])
        self.assertNotIn("melee", spec)

    def test_mutations_require_revision_and_stable_id_before_backend_calls(self):
        code, out, err = self.cli("heal", "d", "4")
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(json.loads(err)["code"], "invalid_arguments")
        self.assertFalse(self.session.execute.called)
        code, _, err = self.cli("next", "--id", "next-1", "--expected-revision", "-1")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "invalid_arguments")

    def test_knockout_requires_an_explicit_choice_and_never_attacks(self):
        code, _, err = self.cli("knockout", "Gundren", "--id", "ko-1", "--expected-revision", "12")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "invalid_arguments")
        self.action.resolve_zero_hp.return_value = {"revision": 13}
        code, _, err = self.cli("knockout", "Gundren", "--nonlethal", "--id", "ko-1",
                                "--expected-revision", "12")
        self.assertEqual((code, err), (0, ""))
        self.action.resolve_zero_hp.assert_called_once_with({"target": "Gundren", "nonlethal": True}, "ko-1", 12)
        self.assertFalse(self.action.resolve_attack.called)

    def test_session_operations_keep_signed_resources_and_optional_fields(self):
        self.session.execute.return_value = {"revision": 15, "already_applied": False}
        commands = [
            (("heal", "d", "4"), "heal", {"target": "d", "amount": 4}),
            (("damage", "d", "4", "--type", "fuoco"), "damage",
             {"target": "d", "amount": 4, "damage_type": "fuoco"}),
            (("resource", "d", "Dadi Vita", "-1"), "resource",
             {"actor": "d", "resource": "Dadi Vita", "delta": -1}),
            (("condition", "d", "Prono", "--remove"), "condition",
             {"target": "d", "condition": "Prono", "remove": True}),
            (("check", "d", "--skill", "athletics", "--dc", "15", "--mode", "advantage"), "check",
             {"actor": "d", "skill": "athletics", "dc": 15, "mode": "advantage"}),
        ]
        for arguments, kind, spec in commands:
            with self.subTest(kind=kind):
                self.session.execute.reset_mock()
                code, out, err = self.cli(*arguments, "--id", "request-1", "--expected-revision", "14")
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(json.loads(out)["revision"], 15)
                self.session.execute.assert_called_once_with(kind, spec, 14, "request-1")

    def test_save_reads_bundle_without_generating_or_rewriting_player_choices(self):
        bundle = {"patch": {"scene": {"title": "Attesa"}}, "dm": "Un fatto riservato.",
                  "pending": ["d: scelta ancora aperta"], "resolve": []}
        path = self.root / "turn.json"
        path.write_text(json.dumps(bundle), encoding="utf-8")
        self.session.execute.return_value = {"revision": 15}
        code, _, err = self.cli("save", str(path), "--id", "save-1", "--expected-revision", "14")
        self.assertEqual((code, err), (0, ""))
        self.session.execute.assert_called_once_with("save", bundle, 14, "save-1")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), bundle)

    def test_saving_throw_uses_sheet_statistic_and_is_exclusive_with_checks(self):
        self.session.execute.return_value = {"revision": 15}
        code, _, err = self.cli("check", "d", "--save", "con", "--dc", "10",
                                "--id", "concentration-1", "--expected-revision", "14")
        self.assertEqual((code, err), (0, ""))
        self.session.execute.assert_called_once_with(
            "check", {"actor": "d", "mode": "normal", "save": "con", "dc": 10}, 14, "concentration-1")
        code, _, err = self.cli("check", "d", "--save", "con", "--ability", "con",
                                "--id", "invalid-1", "--expected-revision", "14")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(err)["code"], "invalid_arguments")

    def test_death_save_routes_declared_mode_without_advancing_the_turn(self):
        self.session.execute.return_value = {"revision": 15}
        code, _, err = self.cli("death", "d", "--mode", "advantage", "--id", "death-1",
                                "--expected-revision", "14")
        self.assertEqual((code, err), (0, ""))
        self.session.execute.assert_called_once_with("death", {"actor": "d", "mode": "advantage"}, 14, "death-1")
        self.assertFalse(self.action.advance_turn.called)

    def test_nonlethal_damage_declares_melee_explicitly(self):
        self.session.execute.return_value = {"revision": 15}
        code, _, err = self.cli("damage", "Gundren", "4", "--nonlethal", "--id", "damage-1",
                                "--expected-revision", "14")
        self.assertEqual((code, err), (0, ""))
        self.session.execute.assert_called_once_with(
            "damage", {"target": "Gundren", "amount": 4, "nonlethal": True, "melee": True}, 14, "damage-1")

    def test_context_recovers_then_delegates_in_process(self):
        self.session.recover.return_value = {"recovered": False}
        with patch("tools.dnd.main", return_value=0) as context:
            code, _, err = self.cli("context", "--recent", "3", "--pretty")
        self.assertEqual((code, err), (0, ""))
        self.session.recover.assert_called_once_with()
        context.assert_called_once_with(["--root", str(self.root), "context", "--recent", "3", "--pretty"])
        self.assertFalse(self.session.execute.called)

    def test_backend_conflicts_are_structured_errors_without_tracebacks(self):
        self.session.execute.side_effect = CampaignError("Revisione cambiata.", "revision_conflict", 409)
        code, out, err = self.cli("heal", "d", "4", "--id", "heal-1", "--expected-revision", "14")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(json.loads(err), {"error": "Revisione cambiata.", "code": "revision_conflict"})


if __name__ == "__main__":
    unittest.main()
