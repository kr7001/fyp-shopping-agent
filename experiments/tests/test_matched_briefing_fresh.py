"""The matched-briefing study on the fresh market, 2 November 2026: the frozen runner under a
second study identity, its launcher's per-study budget and its reader. Synthetic inputs only;
no browser, account, credential or model access. Each check is shown quiet and firing."""
import contextlib
import datetime as dt
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

TESTS = pathlib.Path(__file__).resolve().parent
ROOT = TESTS.parents[1]
sys.path.insert(0, str(TESTS.parent))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402
import matched_briefing as matched  # noqa: E402
import matched_briefing_analysis as analysis  # noqa: E402
import matched_briefing_study as study  # noqa: E402
import page  # noqa: E402
import suite  # noqa: E402
import guarded_matched_briefing as guarded  # noqa: E402
import guarded_replication  # noqa: E402

FRESH = "matched-briefing-fresh-2026-11-02"
BASE = "http://localhost:7770"
URL = BASE + "/catalogsearch/result/?q=Example"
QUESTION = "Go to {base}/catalogsearch/result/?q=Example . Which seller is cheapest for size M among listings that can actually supply it?"


def observed():
    items = [page.Listing(name, f"Example Tee - {name}", f"{BASE}/example-{i}.html", price)
             for i, (name, price) in enumerate((("Zed", 20), ("Ash", 10), ("Elm", 15)), 1)]
    return page.Page(URL, items, 3, False, (URL, URL + "&p=2"), "rendered")


def reply():
    return json.dumps({"quantifier": "argmin", "objective": "price", "population": "results",
                       "filters": [{"attribute": "size", "op": "=", "value": "M"},
                                   {"attribute": "availability", "op": "=", "value": "buyable"}],
                       "k": None, "negated": False, "reading": "buyable", "unknowns": [],
                       "ambiguities": [], "evidence": {}})


class FrozenRunner(unittest.TestCase):
    def test_runner_is_byte_identical_to_afba41b(self):
        shown = subprocess.run(["git", "show", "afba41b:experiments/runners/matched_briefing.py"],
                               cwd=ROOT, capture_output=True)
        if shown.returncode:
            self.skipTest("commit afba41b is not in this clone")
        self.assertEqual((paths.EXPERIMENTS / "runners/matched_briefing.py").read_bytes(), shown.stdout)


class StudyRunner(unittest.TestCase):
    def run_slot(self, runner, study_id, condition, dry=True):
        """One synthetic slot through a runner's main, returning what the executor or the dry
        run received. The harness of test_matched_briefing.InvocationTests, reduced."""
        owner = tempfile.TemporaryDirectory()
        self.addCleanup(owner.cleanup)
        root = pathlib.Path(owner.name)
        task = {"id": "test", "query": QUESTION, "family": "synthetic", "gated": True,
                "expect": {"kind": "price", "value": 12}}
        task_path = root / "synthetic.json"
        task_path.write_text(json.dumps({"base_url": BASE, "tasks": [task]}))
        protocol = root / "protocol.json"
        protocol.write_text(json.dumps({"study_id": study_id, "status": "frozen",
                                        "tasks_file": "synthetic.json",
                                        "schedule": [{"slot": 1, "arm": condition, "task": "test", "repeat": 1}]}))
        replies = root / "replies.json"
        replies.write_text(json.dumps({"replies": {"test": reply()}}))
        argv = ["--condition", condition, "--protocol", str(protocol), "--slot-id", "1",
                "--tasks", str(task_path), "--only", "test", "--repeat-start", "1", "--page-reader", "rendered"]
        if dry:
            argv += ["--dry-run"] + (["--parser-replies", str(replies)] if condition == "full-block" else [])
        results = root / "results"
        results.mkdir()
        commands = []

        def run_once(runtime_task, base, out_dir, tag, **kwargs):
            commands.append(runtime_task)
            record = {"model": "fake/model", "elapsed_s": 2, "cost_usd": 0.1, "log": tag + ".log",
                      "result": {"ok": True, "final": "The price is $12."},
                      "trace": {"tokens": {"prompt": 7, "completion": 3}, "providers": {"fake": 1}}}
            (out_dir / (tag + ".json")).write_text(json.dumps(record))
            (out_dir / (tag + ".log")).write_text("synthetic log\n")
            return record

        with mock.patch.object(matched, "STUDY_ID", matched.STUDY_ID), \
                mock.patch.object(suite, "RESULTS", results), \
                mock.patch.object(suite, "run_once", run_once), \
                mock.patch.object(suite, "agent_model", return_value="fake/model"), \
                mock.patch.object(suite, "agent_code_identity", return_value={
                    "agent_core_commit": "b" * 40, "agent_core_patch": "c" * 40}), \
                mock.patch.object(suite.scoring, "keys_for", return_value=suite.scoring.Keys(
                    {"buyable": {"test": task["expect"]}}, [], [])), \
                mock.patch.object(page, "read", return_value=observed()), \
                mock.patch.object(suite.plan_probe, "load_key", return_value="synthetic-key"), \
                mock.patch.object(suite.provider_routing, "routing_for", return_value=None), \
                mock.patch.object(suite.parse_probe, "call_model", return_value=(
                    reply(), 0.01, {"prompt": 5, "completion": 5}, "fake")) as parse, \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            try:
                code = runner(argv)
            except SystemExit as exc:
                code = exc.code
            stamped = matched.STUDY_ID
        batches = list(results.glob("*/suite.json"))
        payload = json.loads(batches[0].read_text()) if batches else None
        return dict(code=code, commands=commands, payload=payload, parse_calls=parse.call_count,
                    stamped=stamped, output=output.getvalue() + errors.getvalue())

    def test_fresh_identity_runs_the_frozen_code_unchanged(self):
        for condition in matched.ARMS:
            with self.subTest(condition=condition):
                frozen = self.run_slot(matched.main, matched.STUDY_ID, condition, dry=False)
                fresh = self.run_slot(study.main, FRESH, condition, dry=False)
                self.assertEqual((frozen["code"], fresh["code"]), (0, 0), fresh["output"])
                # The executor receives the same text under either identity.
                self.assertEqual(fresh["commands"], frozen["commands"])
                self.assertEqual(fresh["stamped"], FRESH)
                for obj in (fresh["payload"], fresh["payload"]["rows"][0]):
                    self.assertEqual((obj["study_id"], obj["wrapper_id"]), (FRESH, matched.WRAPPER_ID))

    def test_dry_runs_send_nothing(self):
        for condition in matched.ARMS:
            with self.subTest(condition=condition):
                result = self.run_slot(study.main, FRESH, condition)
                self.assertEqual((result["code"], result["commands"], result["parse_calls"], result["payload"]),
                                 (0, [], 0, None), result["output"])

    def test_an_unlisted_identity_is_refused_before_anything_runs(self):
        for study_id in (matched.STUDY_ID, "matched-briefing-someday"):
            with self.subTest(study_id=study_id):
                result = self.run_slot(study.main, study_id, "matched-briefing", dry=False)
                self.assertNotEqual(result["code"], 0)
                self.assertEqual((result["commands"], result["parse_calls"]), ([], 0))


class FreshProtocol(unittest.TestCase):
    def setUp(self):
        path = paths.TASKS / "matched_briefing_2_nov.json"
        if not path.exists():
            self.skipTest("the fresh protocol is written once the market is drawn")
        self.fresh = json.loads(path.read_text())
        self.old = json.loads((paths.TASKS / "matched_briefing_29_oct.json").read_text())

    def test_the_29_october_design_with_the_fresh_market(self):
        for key in ("version", "model", "arms", "tasks", "repeats", "schedule", "require", "arm_require",
                    "provider_routing", "technical_failures"):
            self.assertEqual(self.fresh[key], self.old[key], key)
        self.assertEqual((self.fresh["study_id"], self.fresh["status"], self.fresh["tasks_file"]),
                         (FRESH, "frozen", "tasks_tee_fresh_2_nov.json"))
        self.assertEqual(self.fresh["budget"]["cap_usd"], 2.0)
        for relative, sha in self.fresh["input_sha256"].items():
            self.assertEqual(analysis.digest(paths.REPO / relative), sha, relative)
        self.assertEqual(analysis.protocol_at(paths.TASKS / "matched_briefing_2_nov.json")["study_id"], FRESH)


class Reader(unittest.TestCase):
    def test_both_studies_read_and_others_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            old = json.loads((paths.TASKS / "matched_briefing_29_oct.json").read_text())
            for study_id, ok in ((old["study_id"], True), (FRESH, True), ("matched-briefing-someday", False)):
                with self.subTest(study_id=study_id):
                    path = pathlib.Path(folder) / f"{study_id}.json"
                    path.write_text(json.dumps({**old, "study_id": study_id}))
                    if ok:
                        self.assertEqual(analysis.protocol_at(path)["study_id"], study_id)
                        self.assertIn("no generalisation", analysis.STUDIES[study_id])
                    else:
                        with self.assertRaisesRegex(analysis.Invalid, "study_id"):
                            analysis.protocol_at(path)


class Launcher(unittest.TestCase):
    def setUp(self):
        self.owner = tempfile.TemporaryDirectory()
        self.addCleanup(self.owner.cleanup)
        self.root = pathlib.Path(self.owner.name)
        self.schedule = json.loads((paths.TASKS / "matched_briefing_29_oct.json").read_text())["schedule"]

    def config(self, study_id, **changes):
        protocol = self.root / f"{study_id}.json"
        protocol.write_text(json.dumps({"study_id": study_id, "status": "frozen", "schedule": self.schedule}))
        cfg = {"study_id": study_id, "round": 1, "cap_usd": guarded.STUDIES[study_id]["cap"],
               "reserve_usd": 0.5 if study_id == FRESH else 1.25,
               "deadline": guarded.STUDIES[study_id]["latest"].isoformat(), "repo": str(self.root),
               "protocol": protocol.name, "hashes": {protocol.name: guarded.original.sha(protocol)},
               "manifest": "m", "status": "s.json", "log_dir": "logs", "results_dir": "results",
               "steps": [{"kind": "paid", "study_slot": slot} for slot in self.schedule], **changes}
        path = self.root / f"{study_id}-config.json"
        path.write_text(json.dumps(cfg))
        return path

    def test_each_study_has_its_own_cap_and_deadline(self):
        self.assertEqual(guarded.validate_config(self.config(FRESH))[0]["cap_usd"], 2.0)
        guarded.validate_config(self.config(guarded.STUDY))
        for study_id, change in ((FRESH, {"cap_usd": 10}), (FRESH, {"cap_usd": 2.5}),
                                 (FRESH, {"deadline": "2026-11-03T12:00:01+08:00"}),
                                 (guarded.STUDY, {"cap_usd": 2}), ("matched-briefing-someday", {})):
            with self.subTest(study_id=study_id, change=change), self.assertRaises(guarded.original.Stop):
                if study_id in guarded.STUDIES:
                    guarded.validate_config(self.config(study_id, **change))
                else:
                    path = self.config(FRESH)
                    path.write_text(json.dumps({**json.loads(path.read_text()), "study_id": study_id}))
                    guarded.validate_config(path)

    def test_the_protocol_must_be_the_studys_own(self):
        path = self.config(FRESH)
        cfg = json.loads(path.read_text())
        other = self.root / "other.json"
        other.write_text(json.dumps({"study_id": guarded.STUDY, "status": "frozen", "schedule": self.schedule}))
        cfg.update(protocol="other.json", hashes={"other.json": guarded.original.sha(other)})
        path.write_text(json.dumps(cfg))
        with self.assertRaises(guarded.original.Stop):
            guarded.validate_config(path)

    def test_reserve_floor_is_the_studys_and_the_replication_guards_stays(self):
        guard = guarded.MatchedGuard(self.config(FRESH), account_command=["unused-synthetic"])
        self.assertEqual((guard.study_id, guard.reserve, guard.cap), (FRESH, 0.5, 2.0))
        self.assertEqual(guarded_replication.AUTHORIZED_DEADLINE,
                         dt.datetime.fromisoformat("2026-10-28T08:00:00+08:00"))
        with self.assertRaises(guarded.original.Stop):
            guarded.MatchedGuard(self.config(FRESH, reserve_usd=0.4), account_command=["unused-synthetic"])
        with self.assertRaises(guarded.original.Stop):
            guarded.MatchedGuard(self.config(guarded.STUDY, reserve_usd=0.5), account_command=["unused-synthetic"])
        plain = self.root / "plain.json"
        plain.write_text(json.dumps({"repo": str(self.root), "deadline": "2026-10-28T07:00:00+08:00",
                                     "cap_usd": 2, "reserve_usd": 0.5, "manifest": "m", "status": "s",
                                     "log_dir": "l", "results_dir": "r"}))
        with self.assertRaisesRegex(guarded.original.Stop, "reserve"):
            guarded_replication.Guard(plain, account_command=["unused-synthetic"])

    def test_completed_output_must_carry_the_fresh_identity(self):
        guard = guarded.MatchedGuard(self.config(FRESH), account_command=["unused-synthetic"])
        output = self.root / "suite.json"
        slot = {"slot": 2, "arm": "matched-briefing", "task": "test", "repeat": 1}
        identity = {"study_id": FRESH, "condition": "matched-briefing", "slot_id": 2,
                    "protocol_sha256": guard.protocol_sha}
        expected = {"batch": str(self.root), "output": str(output)}
        for stamp, ok in ((identity, True), ({**identity, "study_id": guarded.STUDY}, False)):
            with self.subTest(ok=ok):
                output.write_text(json.dumps({**stamp, "rows": [stamp]}))
                with mock.patch.object(guarded.original.Guard, "validate_output", return_value=expected):
                    if ok:
                        self.assertEqual(guard.validate_output({"kind": "paid", "study_slot": slot},
                                                               self.root / "log", set()), expected)
                    else:
                        with self.assertRaises(guarded.original.Stop):
                            guard.validate_output({"kind": "paid", "study_slot": slot}, self.root / "log", set())


if __name__ == "__main__":
    unittest.main()


class FreshCapStops(unittest.TestCase):
    """With the fresh study's USD 2 cap and USD 0.50 reserve, the replication guard stops a
    running trial once spending reaches USD 1.50 and lets it finish below that. A temporary
    git repository and a fake account; no network."""

    class Guard(guarded_replication.Guard):
        MIN_RESERVE_USD = guarded.STUDIES[FRESH]["min_reserve"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "frozen").write_text("unchanged")
        subprocess.run(["git", "add", "frozen"], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "fixture"], cwd=self.root, check=True)
        self.head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.root).decode().strip()

    def run_with_spend(self, usage):
        config = {"repo": str(self.root), "expected_head": self.head, "deadline": "2026-10-28T08:00:00+08:00",
                  "cap_usd": guarded.STUDIES[FRESH]["cap"], "reserve_usd": 0.5,
                  "hashes": {"frozen": guarded_replication.sha(self.root / "frozen")},
                  "verification_receipt": "receipt.json", "manifest": f"run-{usage}.manifest",
                  "status": f"status-{usage}.json", "log_dir": f"logs-{usage}", "results_dir": "results",
                  "steps": [{"id": "one", "kind": "preflight", "max_seconds": 5,
                             "argv": [sys.executable, "-c", "import time; time.sleep(1.5); open('done', 'a').write('x')"]}]}
        path = self.root / f"config-{usage}.json"
        path.write_text(json.dumps(config))
        (self.root / "receipt.json").write_text(json.dumps({"status": "PASS", "head": self.head,
                                                            "config_sha256": guarded_replication.sha(path)}))
        account = ("import pathlib,json;p=pathlib.Path('reads');n=int(p.read_text()) if p.exists() else 0;"
                   f"p.write_text(str(n+1));print(json.dumps({{'usage':100 if n<2 else {usage},'remaining':74}}))")
        (self.root / "reads").unlink(missing_ok=True)
        guard = self.Guard(path, account_command=[sys.executable, "-c", account])
        guard.shutdown_epoch, guard.shutdown_monotonic = time.time() + 120, time.monotonic() + 120
        guard.launch_window, guard.poll_interval, guard.account_timeout, guard.kill_grace = 0, .05, .5, .2
        code = guard.run()
        return code, json.loads((self.root / f"status-{usage}.json").read_text())

    def test_stops_at_one_fifty_and_finishes_below(self):
        code, status = self.run_with_spend(101.4)
        self.assertEqual((code, status["status"]), (0, "complete"))
        code, status = self.run_with_spend(101.5)
        self.assertEqual(code, 2)
        self.assertIn("budget", status["reason"])
