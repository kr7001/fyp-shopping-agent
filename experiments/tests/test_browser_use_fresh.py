"""The fresh-market Browser Use stage of 2 November 2026: synthetic inputs only, no paid,
model, account or browser call. Each check is shown quiet on a good case and firing on a
planted fault."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments"))
import paths  # noqa: E402,F401
import browser_use_fetches as fetches_module  # noqa: E402
import browser_use_transfer as study  # noqa: E402
import guarded_browser_use as guard  # noqa: E402
import page  # noqa: E402

COHORT = "966e711a49660893edc93b6d34306df4f458df97"
# The repeats 2-3 cohort's eight Quenby questions as its command held them: the SHA-256 of
# json.dumps(questions, sort_keys=True), read from that command (attempt2-command.json,
# SHA-256 d92255c2...) on 2 November 2026.
COHORT_QUESTIONS_SHA256 = "5709b5ba00a96ad8a1766f5aeecb93ef4e3399b482679e9780776c822e901fe5"
TRANSFER = ROOT / "experiments/runners/browser_use_transfer.py"


def question(name, brand="Rookmere"):
    url = f"http://localhost:7770/catalogsearch/result/?q={brand}"
    return {"id": name, "query": f"Go to {url} . Synthetic question {name}", "start_url": url}


def fresh_config(repo):
    base = Path(repo) / guard.FRESH_NOTES
    return {"stage": guard.FRESH_STAGE, "study_budget_id": guard.FRESH_BUDGET, "repo": str(repo),
            "attempt": 1, "carryover_usd": 0, "shared_cap_usd": 3.0, "cap_usd": 3.0, "estimate_usd": 1.5,
            "minimum_balance_usd": 20.2117632, "legacy_unsettled_reserve_usd": .2117632,
            "deadline": "2026-11-03T12:00:00+08:00", "questions": [question(t) for t in study.TASK_IDS],
            "repeats": [1, 2], "clock_s": 2700,
            **{field: str(base / name) for field, name in {
                "ledger_path": "study-a.ledger.json", "status_path": "study-a.status.json",
                "output_dir": "study-a.results", "log_path": "study-a.log"}.items()}}


class Questions(unittest.TestCase):
    def test_quenby_task_file_reproduces_the_cohort_questions(self):
        tasks = json.loads((paths.TASKS / "tasks_tee_replication_28_oct.json").read_text())
        made = guard.runtime_questions(tasks, study.TASK_IDS)
        self.assertEqual(hashlib.sha256(json.dumps(made, sort_keys=True).encode()).hexdigest(),
                         COHORT_QUESTIONS_SHA256)
        self.assertTrue(all(set(q) == study.QUESTION_FIELDS for q in made))

    def test_a_question_that_does_not_open_the_results_page_is_refused(self):
        tasks = json.loads((paths.TASKS / "tasks_tee_replication_28_oct.json").read_text())
        for task in tasks["tasks"]:
            if task["id"] == "tee-top-3":
                task["query"] = task["query"].replace("Go to ", "Open ", 1)
        with self.assertRaisesRegex(guard.Stop, "results page"):
            guard.runtime_questions(tasks, study.TASK_IDS)


class Market(unittest.TestCase):
    """The fresh market is the protocol's: the first seed from 1002 its picker accepted, drawn
    under the committed protocol, with its questions as the generator writes them."""

    def setUp(self):
        self.fixture = ROOT / "env/fixtures/tee_fresh_2_nov.json"
        if not self.fixture.exists():
            self.skipTest("the fresh market is drawn after the protocol commit")

    def test_drawn_from_the_protocols_stream(self):
        search = json.loads((ROOT / "env/manifests/tee_fresh_2_nov-search.json").read_text())
        # The search record cites the protocol at the path it had when it was frozen. The file has
        # since moved to fresh-market-protocol/, with the same bytes.
        protocol = ROOT / "fresh-market-protocol/protocol.md"
        self.assertEqual(search["claim_selection"], {"start_seed": 1002, "protocol": "notes/fresh-market-2-nov/protocol.md",
                                                     "protocol_sha256": guard.sha(protocol)})
        self.assertEqual([t["seed"] for t in search["tried"]][0], 1002)
        self.assertEqual(search["tried"][-1]["outcome"], "accepted")
        self.assertTrue(all(t["outcome"] != "accepted" for t in search["tried"][:-1]))
        generated = json.loads(self.fixture.read_text())["_generated"]
        self.assertEqual((generated["seed"], generated["brand"], generated["sku_prefix"], generated["design"],
                          generated["version"], generated["phrasings"]),
                         (search["tried"][-1]["seed"], search["brand"], "IGR-FM02", "B", 4, "claim"))
        self.assertEqual(generated["search"], search)

    def test_questions_and_keys_regenerate_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            tasks, readings = Path(folder) / "tasks_tee_fresh_2_nov.json", Path(folder) / "readings_tee_fresh_2_nov.json"
            subprocess.run([sys.executable, "env/generate_aplus_tasks.py", "--fixture", "env/fixtures/tee_fresh_2_nov.json",
                            "--out", str(tasks), "--readings-out", str(readings)],
                           cwd=ROOT, check=True, capture_output=True)
            self.assertEqual(tasks.read_bytes(), (paths.TASKS / tasks.name).read_bytes())
            self.assertEqual(readings.read_bytes(), (paths.TASKS / readings.name).read_bytes())


class AgentFacing(unittest.TestCase):
    def test_current_definitions_are_the_pinned_ones(self):
        self.assertEqual(guard.agent_facing_digests(TRANSFER.read_text()), guard.AGENT_FACING)

    def test_pinned_digests_are_the_cohorts_at_966e711(self):
        shown = subprocess.run(["git", "show", f"{COHORT}:experiments/runners/browser_use_transfer.py"],
                               cwd=ROOT, capture_output=True, text=True)
        if shown.returncode:
            self.skipTest("the cohort's commit is not in this clone")
        self.assertEqual(guard.agent_facing_digests(shown.stdout), guard.AGENT_FACING)

    def test_the_parser_call_and_the_runner_files_are_the_cohorts(self):
        # The block arm's parser settings and call sit inside execute_study, which gained the
        # fresh stage; the lines from the block test to the query build must be the cohort's.
        def block(source):
            start = source.index('            if slot["condition"] == "block":')
            return source[start:source.index("query, decision = await asyncio.to_thread(build_query", start)]
        shown = subprocess.run(["git", "show", f"{COHORT}:experiments/runners/browser_use_transfer.py"],
                               cwd=ROOT, capture_output=True, text=True)
        if shown.returncode:
            self.skipTest("the cohort's commit is not in this clone")
        self.assertEqual(block(TRANSFER.read_text()), block(shown.stdout))
        self.assertIn('parser_config = {**config, "temperature": 0, "frequency_penalty": None, "top_p": None}',
                      block(TRANSFER.read_text()))
        for name in ("experiments/runners/browser_use_runner.py", "experiments/browser-use-macos-py311.lock.txt",
                     "experiments/paths.py"):
            with self.subTest(name=name):
                old = subprocess.run(["git", "show", f"{COHORT}:{name}"], cwd=ROOT, capture_output=True).stdout
                self.assertEqual((ROOT / name).read_bytes(), old)

    def test_a_changed_definition_is_caught(self):
        source = TRANSFER.read_text()
        for old, new in (('return COMMON_BRIEFING + "\\n\\n" + question["query"], None',
                          'return question["query"], None'),
                         ('rate="bound")', 'rate="every")'),
                         ("ARMS = (\"baseline\", \"block\")", "ARMS = (\"block\", \"baseline\")")):
            with self.subTest(old=old):
                self.assertEqual(source.count(old), 1)
                self.assertNotEqual(guard.agent_facing_digests(source.replace(old, new)), guard.AGENT_FACING)
        with self.assertRaisesRegex(guard.Stop, "twice"):
            guard.agent_facing_digests(source + "\n\ndef build_query():\n    pass\n")


class Preview(unittest.TestCase):
    def test_32_slots_repeat_two_reverses_repeat_one(self):
        plan = study.preview(fresh_config(ROOT))
        rows = plan["slots"]
        self.assertEqual((plan["study_id"], plan["batch_id"], plan["paid_calls"]),
                         (guard.FRESH_BUDGET, guard.FRESH_BUDGET, 0))
        self.assertEqual(len(rows), 32)
        self.assertEqual(len({row["id"] for row in rows}), 32)
        self.assertTrue(all(row["phase"] == "transfer" and row["clock_s"] == 2700 for row in rows))
        for i, name in enumerate(study.TASK_IDS):
            first = rows[2 * i]
            self.assertEqual(first["id"], f"transfer-{name}-r1-{first['condition']}")
            self.assertEqual(first["condition"], "baseline" if (i + 1) % 2 else "block")
            self.assertEqual([r["condition"] for r in rows[16 + 2 * i:18 + 2 * i]],
                             [r["condition"] for r in reversed(rows[2 * i:2 * i + 2])])

    def test_other_repeats_clock_or_question_set_refused(self):
        good = fresh_config(ROOT)
        for change in ({"repeats": [2, 3]}, {"repeats": [1]}, {"clock_s": 1800},
                       {"questions": good["questions"][:-1]},
                       {"questions": list(reversed(good["questions"]))}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "fresh market"):
                study.preview({**good, **change})


class Budget(unittest.TestCase):
    def test_own_single_attempt_cap_paths_and_deadline(self):
        good = fresh_config(ROOT)
        guard.validate_fresh_budget(good)
        for change in ({"cap_usd": 3.5}, {"cap_usd": 2}, {"shared_cap_usd": 2}, {"attempt": 2},
                       {"carryover_usd": .1}, {"estimate_usd": 1.6}, {"minimum_balance_usd": 20},
                       {"legacy_unsettled_reserve_usd": 0}, {"study_budget_id": guard.REPEAT_BUDGET},
                       {"prior_ledger_files": ["prior.json"]}, {"ledger_path": "/tmp/elsewhere.json"},
                       {"output_dir": str(ROOT / "notes/browser-use-repeat-1-nov/attempt1.results")},
                       {"deadline": "2026-11-03T12:00:01+08:00"}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_fresh_budget({**good, **change})

    def test_ledger_identity_and_hard_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = {**fresh_config(folder), "deadline": "2099-01-01T00:00:00+08:00", "model": "test/model",
                   "provider": {"max_price": {"prompt": .2, "completion": .5, "request": 0}},
                   "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096,
                   "allowed_served_providers": ["Test"]}
            with mock.patch.object(guard, "validate_fresh_budget"):
                budget = guard.CallBudget(cfg, Path(folder) / "ledger.json", lambda: {"usage": 10, "remaining": 50})
            self.assertEqual((budget.state["study_budget_id"], budget.state["attempt"], budget.state["shared_cap_usd"]),
                             (guard.FRESH_BUDGET, 1, 3.0))
            metadata = {"model": "test/model", "provider": cfg["provider"], "prompt_bytes": 100,
                        "max_output_tokens": 4096, "nontext_or_plugins": False}
            budget.state["charged_usd"] = 2.78
            budget.before_call(metadata)  # 2.78 + 0.2118 is still under USD 3
            with self.assertRaisesRegex(guard.Stop, "cap"):
                budget.before_call(metadata)  # a second request in flight would pass it

    def test_one_launch_claim_per_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = fresh_config(folder)
            Path(cfg["ledger_path"]).parent.mkdir(parents=True)
            command = Path(folder) / "command.json"
            command.write_text(json.dumps(cfg))
            guard.claim_repeat_launch(cfg, command)
            marker = json.loads(Path(cfg["ledger_path"]).with_name("study-a.launch.json").read_text())
            self.assertEqual((marker["study_budget_id"], marker["config_sha256"]),
                             (guard.FRESH_BUDGET, guard.sha(command)))
            with self.assertRaisesRegex(guard.Stop, "already claimed"):
                guard.claim_repeat_launch(cfg, command)

    def test_browser_build_drift_stops_the_fresh_stage(self):
        cfg = {**fresh_config(ROOT), "browser_executable": "synthetic", "preflight_browser_version": "156.0.8078.79"}
        same = types.SimpleNamespace(stdout="Google Chrome 156.0.8078.79")
        with mock.patch.object(guard.subprocess, "run", return_value=same):
            guard.verify_browser_version(cfg)
        moved = types.SimpleNamespace(stdout="Google Chrome 156.0.8078.80")
        with mock.patch.object(guard.subprocess, "run", return_value=moved), \
                self.assertRaisesRegex(guard.Stop, "build changed"):
            guard.verify_browser_version(cfg)


class Identity(unittest.TestCase):
    """A synthetic checkout holding the files the identity check reads."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        frozen = ["experiments/runners/browser_use_runner.py", "experiments/paths.py",
                  "experiments/box/box.py", "requirements.lock"]
        for name in frozen + ["tools/guarded_browser_use.py", "experiments/runners/browser_use_fetches.py"]:
            self.write(name, f"synthetic {name}\n")
        target = self.repo / "experiments/runners/browser_use_transfer.py"
        shutil.copy(TRANSFER, target)
        tasks = {"base_url": "http://localhost:7770", "brand": "Rookmere", "fixture": "tee_fresh_2_nov.json",
                 "tasks": [{"id": t, "query": f"Go to {{base}}/catalogsearch/result/?q=Rookmere . Synthetic question {t}",
                            "expect": {"kind": "secret key the agent never sees"}} for t in study.TASK_IDS]}
        self.write("experiments/tasks/tasks_tee_fresh_2_nov.json", json.dumps(tasks))
        self.write("env/manifests/tee_fresh_2_nov-search.json", json.dumps({
            "brand": "Rookmere", "sku_prefix": "IGR-FM02", "tried": [{"seed": 1002, "outcome": "accepted"}]}))
        self.write("env/fixtures/tee_fresh_2_nov.json", "{}")
        settings = {"python": "/venv/python", "page_python": "/venv/python", "model": "deepseek/deepseek-v4-flash",
                    "provider": {"order": ["gmicloud"]}, "allowed_served_providers": ["GMICloud"],
                    "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096,
                    "max_steps": 150, "clock_s": 2700, "llm_timeout": 120, "temperature": 0.2,
                    "frequency_penalty": 0.1, "top_p": None, "use_vision": False, "browser_executable": "chrome",
                    "preflight_browser_version": "156.0.8078.79", "max_failures": 5,
                    "dependencies_lock": "requirements.lock"}
        reference = {**settings, "questions": [question(t, "Quenby") for t in study.TASK_IDS],
                     "hashes": {name: guard.sha(self.repo / name) for name in frozen}}
        self.write("reference.json", json.dumps(reference))
        self.cfg = {**fresh_config(self.repo), **settings, "reference_config_file": "reference.json",
                    "preflight_receipt": "preflight.json", "tasks_file": "experiments/tasks/tasks_tee_fresh_2_nov.json",
                    "questions": guard.runtime_questions(tasks, study.TASK_IDS),
                    "market_files": ["env/fixtures/tee_fresh_2_nov.json", "env/manifests/tee_fresh_2_nov-search.json"],
                    "market": {"fixture": "env/fixtures/tee_fresh_2_nov.json", "brand": "Rookmere",
                               "sku_prefix": "IGR-FM02", "seed": 1002,
                               "search_record": "env/manifests/tee_fresh_2_nov-search.json"}}
        self.receipt = {"verdict": "PASS", "study_id": guard.FRESH_BUDGET, "model_calls": 0,
                        "browser_version": "156.0.8078.79", "dependencies_match_frozen_lock": True,
                        "shop_check": {"checks": 60, "failed": 0},
                        "source_sha256": {name: guard.sha(self.repo / name) for name in (
                            "tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                            "experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py")}}
        self.write("preflight.json", json.dumps(self.receipt))
        for patch in (mock.patch.object(guard, "FRESH_REFERENCE_SHA256", guard.sha(self.repo / "reference.json")),
                      mock.patch.object(guard, "verify_browser_version")):
            patch.start()
            self.addCleanup(patch.stop)

    def write(self, name, text):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def test_the_cohorts_condition_on_the_fresh_market_passes(self):
        guard.validate_fresh_identity(self.cfg)

    def test_a_changed_setting_or_question_is_refused(self):
        changed_question = [dict(q) for q in self.cfg["questions"]]
        changed_question[3]["query"] += " Please hurry."
        for change in ({"temperature": 0.5}, {"max_steps": 151}, {"python": "/other/python"},
                       {"repeats": [2, 3]}, {"observation_contract": "variant-observation-v1"},
                       {"questions": changed_question}, {"questions": self.cfg["questions"][::-1]},
                       {"market": {**self.cfg["market"], "brand": "Quenby"}},
                       {"market": {**self.cfg["market"], "seed": 1003}},
                       {"market_files": ["env/fixtures/tee_fresh_2_nov.json"]}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_fresh_identity({**self.cfg, **change})

    def test_a_changed_adapter_block_or_agent_facing_definition_is_refused(self):
        for name, text, message in (
                ("experiments/runners/browser_use_runner.py", "an observation fix\n", "frozen adapter"),
                ("experiments/box/new_rule.py", "a new block file\n", "frozen adapter"),
                ("experiments/paths.py", "other import paths\n", "frozen adapter")):
            with self.subTest(name=name):
                before = (self.repo / name).read_text() if (self.repo / name).exists() else None
                self.write(name, text)
                with self.assertRaisesRegex(guard.Stop, message):
                    guard.validate_fresh_identity(self.cfg)
                if before is None:
                    (self.repo / name).unlink()
                else:
                    self.write(name, before)
        transfer = self.repo / "experiments/runners/browser_use_transfer.py"
        transfer.write_text(transfer.read_text().replace('rate="bound")', 'rate="every")'))
        with self.assertRaisesRegex(guard.Stop, "agent-facing"):
            guard.validate_fresh_identity(self.cfg)

    def test_reference_and_preflight_must_be_the_bound_ones(self):
        self.write("preflight.json", json.dumps({**self.receipt, "shop_check": {"checks": 60, "failed": 1}}))
        with self.assertRaisesRegex(guard.Stop, "preflight"):
            guard.validate_fresh_identity(self.cfg)
        stale = {**self.receipt, "source_sha256": {**self.receipt["source_sha256"],
                                                   "experiments/runners/browser_use_fetches.py": "0" * 64}}
        self.write("preflight.json", json.dumps(stale))
        with self.assertRaisesRegex(guard.Stop, "predate"):
            guard.validate_fresh_identity(self.cfg)
        self.write("reference.json", "{}")
        with self.assertRaisesRegex(guard.Stop, "cohort's exact command"):
            guard.validate_fresh_identity(self.cfg)


class ConfigAndReceipt(unittest.TestCase):
    command = ["python", "tools/guarded_browser_use.py", "--config", "config.json", "--execute"]

    def test_only_the_verifiers_review_of_the_exact_command_passes(self):
        receipt = {"verdict": "PASS", "config_sha256": "hash", "head": "head", "request_bound_verified": True,
                   "verifier": "claude", "independent": True, "command": self.command}
        cfg = {"stage": guard.FRESH_STAGE}
        guard.validate_review_receipt(cfg, receipt, "head", "hash", self.command)
        for change in ({"verifier": "codex-independent"}, {"independent": False},
                       {"command": self.command[:-1]}, {"head": "other"}, {"verdict": "FAIL"}):
            with self.subTest(change=change), self.assertRaises(guard.Stop):
                guard.validate_review_receipt(cfg, {**receipt, **change}, "head", "hash", self.command)

    def test_whole_configuration_check_with_cap_three_and_every_input_bound(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder).resolve()  # as the launcher resolves it (/private/var on macOS)
            cfg = {**fresh_config(repo), "version": 1, "model": "test/model",
                   "provider": {"max_price": {"prompt": .2, "completion": .5, "request": 0}},
                   "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096,
                   "allowed_served_providers": ["Test"], "deadline": "2026-11-03T12:00:00+08:00",
                   "protocol_file": "protocol.md", "dependencies_lock": "lock.txt", "runtime_input_files": [],
                   "reference_config_file": "reference.json", "analysis_plan_file": "plan.md",
                   "preflight_receipt": "preflight.json", "tasks_file": "tasks.json",
                   "market_files": ["fixture.json"], "questions_file": str(repo / "questions.json"),
                   "python": "python", "verification_receipt": str(repo / "receipt.json"),
                   "approval_record": str(repo / "approval.json")}
            (repo / "experiments/box").mkdir(parents=True)
            names = ["tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                     "experiments/runners/browser_use_runner.py", "protocol.md", "lock.txt",
                     "reference.json", "plan.md", "preflight.json", "experiments/paths.py",
                     "experiments/runners/browser_use_fetches.py", "tasks.json", "fixture.json", "questions.json"]
            cfg["hashes"] = {name: "synthetic" for name in names}
            path = repo / "config.json"
            path.write_text(json.dumps(cfg))
            command = ["python", str(repo / "tools/guarded_browser_use.py"), "--config", str(path), "--execute"]
            (repo / "receipt.json").write_text(json.dumps({
                "verdict": "PASS", "config_sha256": guard.sha(path), "head": "head", "request_bound_verified": True,
                "verifier": "claude", "independent": True, "command": command}))
            approval = {"approved": True, "config_sha256": guard.sha(path), "command": command,
                        "user_message": "Yes, unattended, cap $10"}
            (repo / "approval.json").write_text(json.dumps(approval))
            with mock.patch.object(guard, "ROOT", repo.resolve()), \
                    mock.patch.object(guard.time, "time", return_value=guard.deadline_epoch("2026-11-02T09:00:00+08:00")), \
                    mock.patch.object(guard, "verify_identity", return_value="head"), \
                    mock.patch.object(guard, "validate_fresh_identity") as identity:
                self.assertEqual(guard.validate_config(path, require_approval=True)["cap_usd"], 3.0)
                identity.assert_called_once()
                (repo / "approval.json").write_text(json.dumps({**approval, "approved": False}))
                with self.assertRaisesRegex(guard.Stop, "approval"):
                    guard.validate_config(path, require_approval=True)
                for unbound in ("experiments/runners/browser_use_fetches.py", "fixture.json", "tasks.json"):
                    with self.subTest(unbound=unbound):
                        missing = {**cfg, "hashes": {k: v for k, v in cfg["hashes"].items() if k != unbound}}
                        path.write_text(json.dumps(missing))
                        with self.assertRaisesRegex(guard.Stop, "hash-bound"):
                            guard.validate_config(path)
                path.write_text(json.dumps({**cfg, "cap_usd": 3.01, "shared_cap_usd": 3.01}))
                with self.assertRaises(guard.Stop):
                    guard.validate_config(path)


def response(url, kind="fetch", status=200, body="", main=False, fails=False):
    frame = types.SimpleNamespace()
    frame.page = types.SimpleNamespace(main_frame=frame if main else object())
    text = mock.AsyncMock(side_effect=RuntimeError("body gone")) if fails else mock.AsyncMock(return_value=body)
    return types.SimpleNamespace(url=url, status=status, text=text,
                                 request=types.SimpleNamespace(resource_type=kind, frame=frame))


PRODUCT = '<body class="page-product-configurable catalog-product-view"><div class="product-info-main">x</div></body>'
SHOP = "http://localhost:7770"


class ScriptFetches(unittest.IsolatedAsyncioTestCase):
    async def test_counts_script_reads_of_candidate_product_pages_only(self):
        seen = fetches_module.ScriptFetches([f"{SHOP}/a.html", f"{SHOP}/b.html", f"{SHOP}/c.html", f"{SHOP}/d.html"])
        for item in (response(f"{SHOP}/a.html", body=PRODUCT),                       # counted
                     response(f"{SHOP}/a.html", kind="xhr", body=PRODUCT),           # same page again
                     response(f"{SHOP}/b.html", kind="document", body=PRODUCT),      # subframe, counted
                     response(f"{SHOP}/c.html", kind="document", body=PRODUCT, main=True),  # navigation
                     response(f"{SHOP}/d.html", status=404, body=PRODUCT),           # not reached
                     response(f"{SHOP}/d.html", body="<body>not a product</body>"),  # not a product page
                     response(f"{SHOP}/other.html", body=PRODUCT),                   # not a candidate
                     response(f"{SHOP}/a.html", kind="image", body=PRODUCT),         # not a script read
                     response("data:text/html,x", body=PRODUCT)):                    # not a URL of the shop
            await seen.observe(item)
        record = seen.record()
        self.assertEqual(record["script_fetched"], 2)
        self.assertEqual(record["script_fetched_urls"], [f"{SHOP}/a.html", f"{SHOP}/b.html"])
        self.assertEqual([e["kind"] for e in record["script_events"]],
                         ["fetch", "xhr", "subframe-document", "fetch", "fetch"])
        self.assertTrue(record["complete"])

    async def test_a_lost_reading_is_recorded_never_raised(self):
        seen = fetches_module.ScriptFetches([f"{SHOP}/a.html"])
        await seen.observe(response(f"{SHOP}/a.html", fails=True))
        self.assertEqual((seen.record()["script_fetched"], seen.record()["script_errors"], seen.record()["complete"]),
                         (0, ["RuntimeError"], False))

    async def test_recording_adds_one_listener_and_puts_the_browser_back(self):
        handlers, closed = [], []

        @asynccontextmanager
        async def research_browser(config, recorder):
            context = types.SimpleNamespace(on=lambda event, handler: handlers.append((event, handler)))
            try:
                yield context, "cdp"
            finally:
                closed.append(True)

        adapter = types.SimpleNamespace(research_browser=research_browser)
        with fetches_module.recording(adapter, [f"{SHOP}/a.html"]) as seen:
            async with adapter.research_browser({}, None) as (context, cdp):
                self.assertEqual([event for event, _ in handlers], ["response"])
                handlers[0][1](response(f"{SHOP}/a.html", body=PRODUCT))
            self.assertEqual(closed, [True])
        self.assertIs(adapter.research_browser, research_browser)
        self.assertEqual(seen.record()["script_fetched"], 1)  # read before the browser closed
        with self.assertRaises(RuntimeError):
            with fetches_module.recording(adapter, []):
                raise RuntimeError("trial failed")
        self.assertIs(adapter.research_browser, research_browser)


class Execution(unittest.IsolatedAsyncioTestCase):
    async def test_32_trials_with_market_identity_and_script_fetches_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            cfg = {**fresh_config(folder), "environment_file": "unused", "expected_head": "head",
                   "market": {"fixture": "env/fixtures/tee_fresh_2_nov.json", "brand": "Rookmere", "seed": 1002}}
            budget = types.SimpleNamespace(state={"calls": [], "inflight": {}, "blocked_reason": None})
            trials = []

            async def run(trial, *_args, **_kwargs):
                trials.append(trial)
                outcome = "failed" if len(trials) == 1 else "answered"
                return {"outcome": outcome, "cost_usd": 0, "trace": {"measurement_valid": True},
                        "answer": "synthetic answer", "agent_errors": ["max steps reached"]}

            @asynccontextmanager
            async def research_browser(config, recorder):
                yield types.SimpleNamespace(on=lambda *a: None), "cdp"

            adapter = types.SimpleNamespace(create_llm=mock.Mock(), close_llm=mock.AsyncMock(), run_trial=run,
                                            configure_private_runtime=mock.Mock(), research_browser=research_browser)
            observed = page.Page(cfg["questions"][0]["start_url"], [page.Listing(
                "A", "Rookmere tee", "http://localhost:7770/a.html", 9)], total=1, next_page=False, reader="rendered")
            with mock.patch.dict(sys.modules, {"browser_use_runner": adapter,
                                               "browser_use.llm.messages": types.SimpleNamespace(UserMessage=mock.Mock())}), \
                    mock.patch.dict(study.os.environ, {"IGR_BROWSER_USE_GUARD": "test",
                                                       "IGR_BROWSER_USE_CONFIG_SHA256": "hash"}), \
                    mock.patch.object(study, "validate_config", return_value=cfg), \
                    mock.patch.object(study, "sha", return_value="hash"), \
                    mock.patch.object(study, "read_key", return_value="SYNTHETIC"), \
                    mock.patch.object(study, "CallBudget", return_value=budget), \
                    mock.patch.object(study, "read_observation", return_value=observed), \
                    mock.patch.object(study, "verify_browser_version"), \
                    mock.patch.object(study, "technical_gate", side_effect=AssertionError("no diagnostic gate")), \
                    mock.patch.object(study, "build_query", return_value=("synthetic unchanged query", None)):
                completed = await study.execute_study("unused")
            self.assertEqual((len(completed), len(trials)), (32, 32))
            self.assertIs(adapter.research_browser, research_browser)
            output = Path(cfg["output_dir"])
            record = json.loads((output / f"{completed[0]}.json").read_text())
            self.assertEqual((record["study_id"], record["batch_id"], record["market"], record["config_sha256"],
                              record["head"], record["outcome"]),
                             (guard.FRESH_BUDGET, guard.FRESH_BUDGET, cfg["market"], "hash", "head", "failed"))
            self.assertEqual(record["script_fetches"]["script_fetched"], 0)
            schedule = json.loads((output / "schedule.json").read_text())
            self.assertEqual(schedule["study_id"], guard.FRESH_BUDGET)
            self.assertFalse((output / "development-gate.json").exists())


if __name__ == "__main__":
    unittest.main()


class LaunchInputs(unittest.TestCase):
    """tools/fresh_market_launch.py: the preflight receipt passes only on passing logs, the
    matching dependency list and the bound browser build; configurations need committed code."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import fresh_market_launch as launch
        self.launch = launch
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        notes = self.repo / "notes/fresh-market-2-nov"
        (notes / "reference").mkdir(parents=True)
        (notes / "reference/attempt2-command.json").write_text(json.dumps({
            "browser_executable": "chrome", "preflight_browser_version": "156.0.8078.79",
            "dependencies_lock": "lock.txt"}))
        (self.repo / "lock.txt").write_text("browser-use==0.13.14\n")
        (notes / "installed-packages.txt").write_text("browser-use==0.13.14\n")
        for name in ("tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                     "experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py"):
            (self.repo / name).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / name).write_text(name)
        self.tests = notes / "tests.log"
        self.tests.write_text("....\n----------------------------------------------------------------------\nRan 4 tests in 0.1s\n\nOK\n")
        self.shop = notes / "shop.log"
        self.shop.write_text("Mon Nov  2\ntee_fresh_2_nov.json: Rookmere, 45 listings, prefix IGR-FM02\n"
                             "  [pass] results pages\n\n61 checks, 0 failed\n")
        for patch in (mock.patch.object(launch, "ROOT", self.repo), mock.patch.object(launch, "NOTES", notes),
                      mock.patch.object(launch, "chrome_build", return_value="156.0.8078.79")):
            patch.start()
            self.addCleanup(patch.stop)

    def receipt(self):
        path = self.launch.preflight(self.tests, self.shop)
        receipt = json.loads(path.read_text())
        path.unlink()
        return receipt

    def test_passing_logs_give_a_pass(self):
        receipt = self.receipt()
        self.assertEqual((receipt["verdict"], receipt["shop_check"]["checks"], receipt["synthetic_tests"]["run"]),
                         ("PASS", 61, 4))
        self.assertEqual(receipt["model_calls"], 0)

    def test_a_failed_check_a_package_or_a_browser_build_gives_a_fail(self):
        self.shop.write_text(self.shop.read_text().replace("0 failed", "1 failed"))
        self.assertEqual(self.receipt()["verdict"], "FAIL")
        self.shop.write_text(self.shop.read_text().replace("1 failed", "0 failed"))
        (self.repo / "notes/fresh-market-2-nov/installed-packages.txt").write_text("browser-use==0.13.15\n")
        self.assertEqual(self.receipt()["verdict"], "FAIL")
        (self.repo / "notes/fresh-market-2-nov/installed-packages.txt").write_text("browser-use==0.13.14\n")
        with mock.patch.object(self.launch, "chrome_build", return_value="157.0.0.1"):
            self.assertEqual(self.receipt()["verdict"], "FAIL")
        self.assertEqual(self.receipt()["verdict"], "PASS")

    def test_failing_tests_or_another_market_are_refused(self):
        self.tests.write_text(self.tests.read_text().replace("OK", "FAILED (failures=1)"))
        with self.assertRaises(SystemExit):
            self.launch.preflight(self.tests, self.shop)
        self.tests.write_text(self.tests.read_text().replace("FAILED (failures=1)", "OK"))
        self.shop.write_text(self.shop.read_text().replace("tee_fresh_2_nov.json: Rookmere", "tee_dev.json: Thurlby"))
        with self.assertRaises(SystemExit):
            self.launch.preflight(self.tests, self.shop)

    def test_configurations_need_committed_code(self):
        status = types.SimpleNamespace(stdout=" M tools/guarded_browser_use.py\n")
        with mock.patch.object(self.launch.subprocess, "run", return_value=status), \
                self.assertRaisesRegex(SystemExit, "commit first"):
            self.launch.head()


def runner_tests():
    """The adapter tests' loopback shop and configuration, loaded from their file."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("fresh_runner_tests", Path(__file__).with_name("test_browser_use_runner.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless(os.environ.get("IGR_BROWSER_USE_INTEGRATION") == "1",
                     "opt-in offline local-browser integration check")
class ScriptFetchesInChrome(unittest.IsolatedAsyncioTestCase):
    """The listener on the real research browser and the installed Chrome, on a loopback shop:
    known script reads must be found, the navigation counter must not change, and nothing
    else may be counted. No model and no shop of the project's."""

    async def test_known_script_reads_are_found_and_navigation_is_untouched(self):
        helpers = runner_tests()
        adapter = helpers.runner
        with helpers.local_shop() as (base, _, _):
            cfg = helpers.config(base)
            cfg["candidate_urls"] = [base + path for path in ("/product", "/variant", "/count/1", "/disabled", "/missing")]
            recorder = adapter.NavigationRecorder(cfg["candidate_urls"])
            original = adapter.research_browser
            with fetches_module.recording(adapter, cfg["candidate_urls"]) as seen:
                async with adapter.research_browser(cfg, recorder) as (context, _):
                    page = context.pages[0]
                    await page.goto(base + "/start")
                    await page.goto(base + "/product")
                    await page.evaluate("(url) => fetch(url).then(r => r.text())", base + "/variant")
                    await page.evaluate("""(url) => new Promise(done => { const x = new XMLHttpRequest();
                        x.onload = () => done(x.status); x.open('GET', url); x.send(); })""", base + "/count/1")
                    await page.evaluate("(url) => fetch(url).then(r => r.text())", base + "/missing")
                    await page.evaluate("(url) => fetch(url).then(r => r.text())", base + "/start")
                    await page.evaluate("""(url) => new Promise(done => { const f = document.createElement('iframe');
                        f.onload = () => done(true); f.src = url; document.body.appendChild(f); })""", base + "/disabled")
                    await asyncio.sleep(.3)
            self.assertIs(adapter.research_browser, original)
        navigation, script = recorder.record(), seen.record()
        self.assertEqual((navigation["opened"], navigation["observation_errors"]), (1, []))
        self.assertEqual(script["script_fetched_urls"], sorted(base + p for p in ("/variant", "/count/1", "/disabled")))
        self.assertEqual(sorted(e["kind"] for e in script["script_events"]),
                         ["fetch", "fetch", "subframe-document", "xhr"])
        self.assertTrue(any(e["url"] == base + "/missing" and not e["product_document"] for e in script["script_events"]))
        self.assertTrue(script["complete"])
