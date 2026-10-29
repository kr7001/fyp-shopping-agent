"""Dated supplementary guard checks using temporary files; no accounts or models."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import guarded_matched_briefing as guarded


class GuardConfigTests(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory()
        self.addCleanup(self.owner.cleanup)
        self.root = Path(self.owner.name)
        self.protocol_path = self.root / "protocol.json"
        self.config_path = self.root / "config.json"
        self.schedule = [{"slot": i + 1,
                          "arm": "full-block" if i % 2 == 0 else "matched-briefing",
                          "task": f"task-{i // 4}", "repeat": 1 + (i // 2) % 2}
                         for i in range(16)]
        self.protocol = {"study_id": guarded.STUDY, "status": "frozen", "schedule": self.schedule}
        self.protocol_path.write_text(json.dumps(self.protocol))
        self.config = {"study_id": guarded.STUDY, "round": 1, "cap_usd": 10,
                       "deadline": guarded.LATEST.isoformat(), "repo": str(self.root),
                       "protocol": "protocol.json",
                       "hashes": {"protocol.json": guarded.original.sha(self.protocol_path)},
                       "steps": [{"kind": "paid", "study_slot": slot} for slot in self.schedule]}

    def write(self, config=None):
        self.config_path.write_text(json.dumps(config if config is not None else self.config))
        return self.config_path

    def test_exact_scope_and_schedule_accepted(self):
        cfg, protocol = guarded.validate_config(self.write())
        self.assertEqual(cfg, self.config)
        self.assertEqual(protocol, self.protocol)

    def test_wrong_study_round_prior_scope_and_cap_refused(self):
        for changed in ({"study_id": "original-claim"}, {"round": 2}, {"round": None},
                        {"prior_round": None}, {"prior_round": {}}, {"cap_usd": 11},
                        {"cap_usd": 9}, {"cap_usd": 0}):
            with self.subTest(changed=changed), self.assertRaises(guarded.original.Stop):
                guarded.validate_config(self.write({**self.config, **changed}))

    def test_deadline_timezone_and_latest_bound(self):
        for deadline in ("2026-10-30T12:00:01+08:00", "2026-10-30T12:00:00"):
            with self.subTest(deadline=deadline), self.assertRaises(guarded.original.Stop):
                guarded.validate_config(self.write({**self.config, "deadline": deadline}))
        for deadline in ("2026-10-30T11:59:59+08:00", "2026-10-30T04:00:00+00:00"):
            guarded.validate_config(self.write({**self.config, "deadline": deadline}))

    def test_unfrozen_changed_protocol_and_schedule_refused(self):
        protocol = {**self.protocol, "status": "prepared"}
        self.protocol_path.write_text(json.dumps(protocol))
        cfg = {**self.config, "hashes": {"protocol.json": guarded.original.sha(self.protocol_path)}}
        with self.assertRaises(guarded.original.Stop):
            guarded.validate_config(self.write(cfg))
        self.protocol_path.write_text(json.dumps(self.protocol))
        self.protocol_path.write_text(self.protocol_path.read_text() + " ")
        with self.assertRaises(guarded.original.Stop):
            guarded.validate_config(self.write())
        self.protocol_path.write_text(json.dumps(self.protocol))
        for steps in (self.config["steps"][:-1], list(reversed(self.config["steps"])),
                      self.config["steps"] + [self.config["steps"][0]]):
            with self.subTest(count=len(steps)), self.assertRaises(guarded.original.Stop):
                guarded.validate_config(self.write({**self.config, "steps": steps}))

    def test_deadline_override_scoped_even_when_constructor_fails(self):
        before = guarded.original.AUTHORIZED_DEADLINE
        observed = []

        def constructor(instance, *args, **kwargs):
            observed.append(guarded.original.AUTHORIZED_DEADLINE)
            instance.repo = self.root

        with mock.patch.object(guarded.original.Guard, "__init__", constructor):
            instance = guarded.MatchedGuard(self.write(), account_command=["unused-synthetic"])
        self.assertEqual(observed, [guarded.LATEST])
        self.assertEqual(instance.protocol_sha, guarded.original.sha(self.protocol_path))
        self.assertEqual(guarded.original.AUTHORIZED_DEADLINE, before)
        with mock.patch.object(guarded.original.Guard, "__init__", side_effect=guarded.original.Stop("test")):
            with self.assertRaises(guarded.original.Stop):
                guarded.MatchedGuard(self.write())
        self.assertEqual(guarded.original.AUTHORIZED_DEADLINE, before)


class OutputIdentityTests(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory()
        self.addCleanup(self.owner.cleanup)
        self.root = Path(self.owner.name)
        self.output = self.root / "suite.json"
        self.guard = object.__new__(guarded.MatchedGuard)
        self.guard.protocol_sha = "a" * 64
        self.slot = {"slot": 2, "arm": "matched-briefing", "task": "test", "repeat": 1}
        self.step = {"kind": "paid", "study_slot": self.slot}
        self.identity = {"study_id": guarded.STUDY, "protocol_id": guarded.STUDY,
                         "protocol_sha256": self.guard.protocol_sha,
                         "wrapper_id": "matched-briefing-v1", "condition": "matched-briefing",
                         "arm": "matched-briefing", "slot_id": 2}

    def validate(self, identity=None):
        identity = self.identity if identity is None else identity
        self.output.write_text(json.dumps({**identity, "rows": [
            {**identity, "task": "test", "repeat": 1, "log": "test-1.log"}]}))
        expected = {"batch": str(self.root), "output": str(self.output)}
        with mock.patch.object(guarded.original.Guard, "validate_output", return_value=expected) as parent:
            actual = self.guard.validate_output(self.step, self.root / "launch.log", set())
        parent.assert_called_once()
        return actual, expected

    def test_actual_runner_top_level_identity_accepted(self):
        # matched_briefing.Session stamps these at top level, with no matched_study object.
        actual, expected = self.validate()
        self.assertEqual(actual, expected)
        self.assertNotIn("matched_study", json.loads(self.output.read_text()))

    def test_wrong_slot_condition_protocol_and_study_refused(self):
        for changed in ({"slot_id": 1}, {"slot_id": "2"}, {"condition": "full-block"},
                        {"protocol_sha256": "b" * 64}, {"study_id": "original-claim"}):
            with self.subTest(changed=changed), self.assertRaises(guarded.original.Stop):
                self.validate({**self.identity, **changed})

    def test_missing_top_level_identity_not_rescued_by_nested_stamp(self):
        with self.assertRaises(guarded.original.Stop):
            self.validate({"matched_study": self.identity})


class KeyContextTests(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory()
        self.addCleanup(self.owner.cleanup)
        self.root = Path(self.owner.name)
        self.agent = self.root / "agent/agent-core"
        self.agent.mkdir(parents=True)
        # These are deliberately fake local values. Tests never inspect real .env files.
        self.secret = "synthetic-private-marker"
        (self.root / ".env").write_text("OPENROUTER_API_KEY=" + self.secret + "\n")

    def check(self, environment=None, error=False):
        with contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            if error:
                with self.assertRaises(guarded.original.Stop) as caught:
                    guarded.check_key_context(self.root, environment or {})
                self.assertNotIn(self.secret, str(caught.exception))
                self.assertNotIn("different-private-marker", str(caught.exception))
            else:
                guarded.check_key_context(self.root, environment or {})
        self.assertEqual(output.getvalue() + errors.getvalue(), "")

    def test_matching_executor_aliases_accepted(self):
        for alias in ("API_KEY", "MODEL_API_KEY", "OPENROUTER_API_KEY"):
            with self.subTest(alias=alias):
                (self.agent / ".env").write_text(alias + "=" + self.secret + "\n")
                self.check()
                self.check({alias: self.secret, "OPENROUTER_API_KEY": self.secret})

    def test_different_effective_alias_or_monitor_key_refused_without_output(self):
        (self.agent / ".env").write_text("OPENROUTER_API_KEY=" + self.secret + "\n")
        for environment in ({"API_KEY": "different-private-marker"},
                            {"MODEL_API_KEY": "different-private-marker"},
                            {"OPENROUTER_API_KEY": "different-private-marker"}):
            with self.subTest(alias=next(iter(environment))):
                self.check(environment, error=True)
        (self.agent / ".env").write_text("API_KEY=different-private-marker\n")
        self.check(error=True)
        # Environment is the executor's actual override, so matching it is allowed.
        self.check({"API_KEY": self.secret})

    def test_parser_dotenv_convention_and_duplicates_fail_closed(self):
        (self.agent / ".env").write_text("API_KEY=" + self.secret + "\n")
        for contents in (f'OPENROUTER_API_KEY="{self.secret}"\n',
                         f"export OPENROUTER_API_KEY={self.secret}\n",
                         f"OPENROUTER_API_KEY={self.secret}\nOPENROUTER_API_KEY={self.secret}\n",
                         "OPENROUTER_API_KEY=\n"):
            with self.subTest(case=contents.split("=", 1)[0]):
                (self.root / ".env").write_text(contents)
                self.check(error=True)


class ReviewPreparationTests(unittest.TestCase):
    def fixture(self, state="complete", completed=None):
        owner = tempfile.TemporaryDirectory()
        self.addCleanup(owner.cleanup)
        root = Path(owner.name)
        config = {"preparation_status": "review-status.json", "preparation_log": "review.log",
                  "protocol": "protocol.json", "review_sheet": "review.csv",
                  "review_html": "review.html", "manifest": "runs.manifest", "hashes": {},
                  "verification_receipt": "receipt.json", "expected_head": "a" * 40,
                  "steps": [{"id": "slot-1"}]}
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config))
        config_hash = guarded.original.sha(config_path)
        (root / "receipt.json").write_text(json.dumps({"status": "PASS", "head": "a" * 40,
                                                       "config_sha256": config_hash}))
        status_path = root / "paid-status.json"
        status_path.write_text(json.dumps({"status": state, "completed_steps": (
            ["slot-1"] if completed is None else completed)}))
        return types.SimpleNamespace(config=config, repo=root, config_path=config_path,
                                     config_hash=config_hash, status_path=status_path)

    def test_completed_schedule_creates_only_blind_sheet_and_reader(self):
        guard = self.fixture()
        before = guard.status_path.read_bytes()
        with mock.patch.object(guarded.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as run:
            self.assertEqual(guarded.prepare_review(guard), 0)
        self.assertEqual(run.call_count, 2)
        first, second = [call.args[0] for call in run.call_args_list]
        for argv in (first, second):
            self.assertIn("--sheet", argv)
            self.assertNotIn("--hand", argv)
            self.assertNotIn("--score", argv)
        self.assertIn("--output", second)
        self.assertIn("matched_briefing_analysis.py", first[1])
        self.assertIn("hand_review.py", second[1])
        self.assertEqual(guard.status_path.read_bytes(), before)
        status = json.loads((guard.repo / guard.config["preparation_status"]).read_text())
        self.assertEqual((status["status"], status["paid_runs_repeated"]), ("complete", False))

    def test_incomplete_or_failed_preparation_preserves_paid_state(self):
        for state, completed, code, expected_calls in (
                ("running", None, 0, 0), ("complete", [], 0, 0), ("complete", None, 1, 1)):
            with self.subTest(state=state, completed=completed, command_exit=code):
                guard = self.fixture(state, completed)
                before = guard.status_path.read_bytes()
                with mock.patch.object(guarded.subprocess, "run", return_value=types.SimpleNamespace(returncode=code)) as run:
                    self.assertEqual(guarded.prepare_review(guard), 3)
                self.assertEqual(run.call_count, expected_calls)
                self.assertEqual(guard.status_path.read_bytes(), before)
                status = json.loads((guard.repo / guard.config["preparation_status"]).read_text())
                self.assertEqual((status["status"], status["paid_runs_repeated"]), ("failed", False))


if __name__ == "__main__":
    unittest.main()
