"""The stage command generator (24 October 2026): stage 1's plan and estimates from the
analysis file and the task file, the pilot's plan, the emitted text the guard reads, and a dry
run of each chain's mechanics in a stub tree (tests/stage_stubs.py) driving every exit code,
the cap gate, the watchdog, the voids loop, the reading tests and the pilot's summary.

The chains run for real here, against stubs: no model is called and no shop is touched. Each
fault named was planted with a fresh bytecode cache and seen to fail its test (LESSONS 31,
39). The slow cases, the watchdog and a whole stage, are kept to a few seconds each.
"""
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

import claim  # noqa: E402  (its manifest parser, which must accept every line the chains write)
import stage_plan  # noqa: E402
import stage_stubs  # noqa: E402

DEEPSEEK = stage_stubs.DEEPSEEK
ARMS = ["shipped", "open everything (product)", "the block (rules)", "the block (model)"]


class ThePlan(unittest.TestCase):
    def setUp(self):
        self.analysis = stage_stubs.analysis_file()
        self.claim = stage_stubs.task_file("Wexcombe", held=True)

    def test_the_sets_come_from_the_analysis_file_and_the_task_file_never_a_flag(self):
        self.assertEqual(stage_plan.resolve_set("templates", self.analysis, self.claim), stage_stubs.TEE + stage_stubs.DECLINES)
        self.assertEqual(stage_plan.resolve_set("held_out", self.analysis, self.claim), [h for h, _ in stage_stubs.HELD])
        # tee-promo-check has gated: true in the task file and is not in the gated set.
        gated = stage_plan.resolve_set("gated", self.analysis, self.claim)
        self.assertEqual(gated, stage_stubs.GATED)
        self.assertNotIn("tee-promo-check", gated)
        self.assertTrue(next(t for t in self.claim["tasks"] if t["id"] == "tee-promo-check")["gated"])
        with self.assertRaisesRegex(ValueError, "no set 'nonsense'"):
            stage_plan.resolve_set("nonsense", self.analysis, self.claim)
        with self.assertRaisesRegex(ValueError, "names tasks the task file lacks: tee-top-3"):
            stage_plan.resolve_set("gated", self.analysis, {**self.claim, "tasks": self.claim["tasks"][:7]})

    def test_stage_1_rotates_the_arms_and_keeps_invocations_small(self):
        plan = stage_plan.stage1_invocations(self.analysis, self.claim, DEEPSEEK, chunk=8)
        rounds = {r: [inv.arm for inv in plan if inv.round == r] for r in (1, 2, 3)}
        first = {r: list(dict.fromkeys(arms)) for r, arms in rounds.items()}
        self.assertEqual(first[1], ARMS)
        self.assertEqual(first[2], ARMS[1:] + ARMS[:1])
        self.assertEqual(first[3], ARMS[2:] + ARMS[:2])
        for inv in plan:
            arm = stage_plan.suite_arm(self.analysis, inv.arm)
            if arm in stage_plan.BLOCK_ARMS:
                self.assertLessEqual(len(inv.questions), 8)
            else:
                self.assertEqual(len(inv.questions), 1)
        # Shipped: 13 x 3; open everything: 8 x 3; each block arm: 13 templates in 8 + 5 per
        # round, the 12 held-out in 8 + 4 in round 1 alone.
        by_arm = {arm: sum(len(inv.questions) for inv in plan if inv.arm == arm) for arm in ARMS}
        self.assertEqual(by_arm, {"shipped": 39, "open everything (product)": 24,
                                  "the block (rules)": 51, "the block (model)": 51})
        self.assertEqual(len(plan), 39 + 24 + 2 * (3 * 2 + 2))
        held = [inv for inv in plan if inv.questions[0].startswith("rw")]
        self.assertEqual({inv.round for inv in held}, {1})
        self.assertEqual([inv.round for inv in plan], sorted(inv.round for inv in plan))

    def test_the_pilots_twelve_runs_in_the_files_arm_order(self):
        plan = stage_plan.pilot_invocations(self.analysis, stage_stubs.task_file("Devbrand", held=False))
        self.assertEqual(len(plan), 12)
        self.assertEqual([inv.arm for inv in plan], ["shipped"] * 2 + ["open everything (product)"] * 2
                         + ["the block (rules)"] * 2 + ["the block (model)"] * 6)
        self.assertEqual([inv.questions for inv in plan if inv.arm == "the block (model)"],
                         [(q,) for q in stage_plan.PILOT_PLAN["box-model"]])
        with self.assertRaisesRegex(ValueError, "the pilot asks tee-promo-check, which the task file lacks"):
            stage_plan.pilot_invocations(self.analysis, {"tasks": [{"id": "tee-xs-price"}]})

    def test_kinds_and_templates(self):
        self.assertEqual(stage_plan.kind_of("tee-xs-price"), "bound")
        self.assertEqual(stage_plan.kind_of("decline-returns"), "decline")
        with self.assertRaisesRegex(ValueError, "no kind is fixed for the template 'water-target-price'"):
            stage_plan.kind_of("water-target-price")
        self.assertEqual(stage_plan.template_of(self.claim, "rw3-01"), "tee-xs-price")
        self.assertEqual(stage_plan.template_of(self.claim, "tee-top-3"), "tee-top-3")
        self.assertEqual(stage_plan.keyless_of(self.claim), set(stage_stubs.DECLINES) | {"rw-27", "rw3-03"})


class TheCostTable(unittest.TestCase):
    """The 23 October pilot's stored batch prices stage 1 at list price, scaled."""

    @classmethod
    def setUpClass(cls):
        cls.measured = stage_plan.measured_block_costs()
        cls.pilot = json.loads((paths.RESULTS / stage_plan.PILOT_23_OCT / "suite.json").read_text())

    def test_the_measured_costs_are_the_stored_rows(self):
        rows = {row["task"]: row["cost_usd"] for row in self.pilot["rows"]}
        self.assertEqual(self.measured, rows)
        self.assertEqual(self.pilot["arm"], "box-model")

    def test_estimates_by_hand(self):
        with tempfile.TemporaryDirectory() as folder:
            fixture = pathlib.Path(folder) / "f.json"
            fixture.write_text(json.dumps(stage_stubs.fixture("Wexcombe", 45)))
            costs = stage_plan.costs_for(fixture)
            self.assertAlmostEqual(costs.scale, 45 / 21)
            f, s = stage_plan.PILOT_PRICE_FACTOR, 45 / 21
            # A bound question grows; xs-price stands in as target-price; a lookup and a
            # decline do not grow; open everything is 1.3 x the dearer of the question and the
            # count; shipped is flat.
            self.assertAlmostEqual(costs.estimate("box-model", "tee-xs-price"), self.measured["tee-target-price"] / f * s)
            self.assertAlmostEqual(costs.estimate("box", "tee-promo-check"), self.measured["tee-headline"] / f)
            self.assertAlmostEqual(costs.estimate("box-model", "decline-scarcity"), self.measured["decline-delivery"] / f)
            self.assertAlmostEqual(costs.estimate("exhaustive-product", "tee-top-3"),
                                   1.3 * self.measured["tee-count-buyable"] / f * s)
            self.assertAlmostEqual(costs.estimate("none", "tee-count-buyable"), stage_plan.SHIPPED_PILOT_PRICE / f)
            steeper = stage_plan.costs_for(fixture, growth=2)
            self.assertAlmostEqual(steeper.estimate("box-model", "tee-count-buyable"),
                                   self.measured["tee-count-buyable"] / f * s * s)
            with self.assertRaisesRegex(ValueError, "no estimate rule for the arm 'targeting'"):
                costs.estimate("targeting", "tee-top-3")

    def test_the_probes_price_the_text_only_extras(self):
        extras = stage_plan.probe_estimates(10, 10)
        deepseek = stage_plan.probe_charge_per_call(paths.RESULTS / stage_plan.DEEPSEEK_PROBE)
        haiku = stage_plan.probe_charge_per_call(paths.RESULTS / stage_plan.HAIKU_PROBE)
        self.assertAlmostEqual(extras["routing gate"], 30 * deepseek)
        self.assertAlmostEqual(extras["reading tests, DeepSeek"], 10 * deepseek)
        self.assertAlmostEqual(extras["reading tests, Haiku"], 10 * haiku)
        self.assertGreater(haiku, deepseek)
        self.assertIsNone(stage_plan.probe_charge_per_call(paths.RESULTS / "no-such-file.json"))


class Tree(unittest.TestCase):
    """A stub tree per test."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = pathlib.Path(folder.name)

    def build(self, scenario=None, usage=10.0, **flags) -> None:
        stage_stubs.build(self.root, scenario, usage)
        self.flags = flags

    def run_stage(self, stage: str, timeout: int = 180):
        text = stage_stubs.generate(self.root, stage, **self.flags)
        done = stage_stubs.run_chain(self.root, text, timeout)
        tag = "pilot-test" if stage == "pilot" else "stage1-test"
        return done.returncode, stage_stubs.manifest(self.root, tag), text


class TheEmittedText(Tree):
    def test_the_guard_reads_the_estimate_and_caffeinate_and_the_chain_names_its_parts(self):
        self.build()
        text = stage_stubs.generate(self.root, "1")
        head = text.splitlines()[0]
        # The agent's sampling is its code's default: the chain unsets every key the agent or the
        # runner would read first, and stops if .env would refill one.
        self.assertTrue(head.startswith("caffeinate -i env -u BROWSER_WORKER_TEMPERATURE -u BROWSER_WORKER_TOP_P "
                                        "-u BROWSER_MODEL_TEMPERATURE -u BROWSER_MODEL_TOP_P -u MODEL_TEMPERATURE "
                                        "-u MODEL_TOP_P IGR_ESTIMATE_USD="), head)
        self.assertIn("grep -oE '^(BROWSER_WORKER_TEMPERATURE|BROWSER_WORKER_TOP_P|BROWSER_MODEL_TEMPERATURE|"
                      "BROWSER_MODEL_TOP_P|MODEL_TEMPERATURE|MODEL_TOP_P)=' .env", text)
        self.assertIn("exit 10", text)
        self.assertIn(" IGR_PROVIDER_ROUTING='", head)

        self.assertTrue(head.endswith(" bash <<'CHAIN'"))
        self.assertEqual(text.rstrip().splitlines()[-1], "CHAIN")
        self.assertEqual(len(re.findall(r"^FLAGS='.*'; run '", text, re.M)), 79)
        self.assertIn("python3 experiments/analysis/claim.py --protocol \"$F\" --preflight \"$arm\" --flags \"$FLAGS\"", text)
        self.assertIn("MODEL_NAME=$MODEL python3 experiments/runners/suite.py --tasks \"$T\" --repeats 1 --repeat-start \"$round\"", text)
        self.assertIn("exit 7", text)
        self.assertIn("every 1 s, stops any suite.py once spent reaches the cap less $0.30", text)
        for n in (3, 4, 5, 6, 8):
            self.assertIn(f"exit {n}", text)
        # The reading tests: DeepSeek routed, then Haiku with the routing unset, each file once,
        # with the market's templates as the filter.
        tests = [l for l in text.splitlines() if "parse_probe.py --questions experiments/tasks/paraphrases_v" in l
                 and "paraphrases_v1.json" not in l]
        self.assertEqual(len([l for l in text.splitlines() if "--questions experiments/tasks/paraphrases_v1.json" in l]), 1,
                         "the routing gate's probe")
        self.assertEqual(len(tests), 4)
        self.assertTrue(all("--only-templates tee-headline tee-target-price" in l and "decline-scarcity --spec-from" in l
                            for l in tests))
        self.assertEqual([l.startswith("rt=$(env -u IGR_PROVIDER_ROUTING python3") for l in tests], [False, False, True, True])
        self.assertEqual([("anthropic/claude-haiku-4.5" in l) for l in tests], [False, False, True, True])

    def test_the_routing_is_held_to_the_analysis_files_for_the_model(self):
        # Another object for DeepSeek, and none at all, are refused: the file routes it.
        self.build()
        other = json.dumps({DEEPSEEK: {"order": ["deepinfra"], "allow_fallbacks": False}})
        for routing in (other, "none"):
            with self.subTest(routing=routing), self.assertRaises(subprocess.CalledProcessError) as raised:
                stage_stubs.generate(self.root, "1", routing=routing)
            self.assertIn(f"--routing gives {DEEPSEEK}", raised.exception.stderr)
        # The file's own object, with another model's routing beside it, passes.
        both = json.dumps({**stage_stubs.ROUTING, "anthropic/claude-haiku-4.5": {"order": ["amazon-bedrock"]}})
        self.assertIn("IGR_PROVIDER_ROUTING=", stage_stubs.generate(self.root, "1", routing=both))

    def test_the_pilot_text_has_twelve_runs_and_the_check_and_no_voids_loop(self):
        self.build()
        text = stage_stubs.generate(self.root, "pilot")
        self.assertEqual(len(re.findall(r"^FLAGS='.*'; run '", text, re.M)), 12)
        self.assertIn("python3 experiments/analysis/pilot_check.py --manifest \"$MANIFEST\" --protocol \"$F\" --pilot-tasks \"$T\" "
                      "--stage1-tasks experiments/tasks/tasks_claim.json --stage1-cap 69.00", text)
        self.assertIn("exit 9", text)
        self.assertNotIn("voids.py", text)
        self.assertNotIn("parse_probe.py --questions experiments/tasks/paraphrases_v2", text)
        self.assertEqual(len(re.findall(r"^FLAGS='--max-steps 300 --clock 1800'; run 'shipped'", text, re.M)), 2)

    def test_the_estimate_is_the_sum_of_the_plan_and_the_extras(self):
        self.build()
        text = stage_stubs.generate(self.root, "1")
        declared = float(re.search(r"IGR_ESTIMATE_USD=([0-9.]+)", text).group(1))
        highs = [float(m) for m in re.findall(r"; run '.*?' ([0-9.]+) \d --only", text)]
        extras = stage_plan.probe_estimates(7, 7)   # v2's 3, 5, 27 and v3's 4 entries under the filter
        # Each high is printed to the cent, so 79 of them can drift by up to $0.40 from the total.
        self.assertAlmostEqual(declared, sum(highs) / stage_plan.HIGH + sum(extras.values()), delta=0.4)
        self.assertEqual(len(highs), 79)

    def test_out_never_writes_over_a_file(self):
        self.build()
        out = self.root / "chain.txt"
        out.write_text("kept")
        with self.assertRaises(Exception):
            stage_stubs.generate(self.root, "1", out=str(out))
        self.assertEqual(out.read_text(), "kept")


class ThePilotChain(Tree):
    def test_the_whole_pilot_passes_its_check(self):
        self.build()
        code, manifest, _ = self.run_stage("pilot")
        self.assertEqual(code, 0, manifest)
        lines = manifest.splitlines()
        self.assertTrue(lines[0].startswith("start ") and " usage 10.0000 cap 6.00" in lines[0])
        self.assertTrue(lines[1].startswith("conditions commit"))
        self.assertTrue(lines[2].startswith("probe|") and lines[2].endswith(f"|model={DEEPSEEK} routing check"))
        self.assertEqual(lines[3], "routing-check|ok")
        batches = [l for l in lines if l.startswith("batch|")]
        self.assertEqual(len(batches), 12)
        self.assertTrue(all(pathlib.Path(l.split("|")[1]).is_dir() for l in batches))
        # The batch line carries the arm's flags as the analysis file writes them, not a literal:
        # the literal pinned v6's `--rate-plan every` and broke when v7 dropped it (24 October 2026).
        model_flags = stage_stubs.analysis_file()["arms"]["the block (model)"]["flags"]
        self.assertIn(f" arm=the block (model) round=1 --repeats 1 --repeat-start 1 {model_flags} --only decline-fit",
                      batches[-1])
        self.assertTrue(lines[-2].startswith("end "))
        self.assertEqual(lines[-1], "pilot-check|PASS|experiments/results/pilot-test.summary")
        # Every line the chain wrote is one claim.py's manifest parser accepts (the analysis coder's
        # CHAIN_LINES against the runner coder's chain, checked on a real emitted manifest).
        self.assertEqual(claim.parse_manifest(manifest).problems, [])
        summary = (self.root / "experiments/results/pilot-test.summary").read_text()
        self.assertIn("verdict: PASS", summary)
        self.assertIn("projected stage 1: $", summary)
        # Every preflight ran under the chain's model, and every suite call carried the routing.
        preflights = stage_stubs.calls(self.root, ".preflights")
        self.assertEqual(len(preflights), 12)
        self.assertEqual({p["model"] for p in preflights}, {DEEPSEEK})
        suites = stage_stubs.calls(self.root, ".suite_calls")
        self.assertEqual({json.dumps(json.loads(s["routing"]), sort_keys=True) for s in suites},
                         {json.dumps(stage_stubs.ROUTING, sort_keys=True)})
        self.assertTrue((self.root / "experiments/results/pilot-test.done").exists())

    def test_a_void_in_the_pilot_fails_the_check_and_exits_9(self):
        self.build({"void": ["tee-count-buyable"], "void_arms": ["exhaustive-product"]})
        code, manifest, _ = self.run_stage("pilot")
        self.assertEqual(code, 9)
        self.assertTrue(manifest.rstrip().endswith("pilot-check|FAIL|experiments/results/pilot-test.summary"))
        summary = (self.root / "experiments/results/pilot-test.summary").read_text()
        self.assertIn("1 FAIL no harness error and no void: 12 runs, 1 void", summary)

    def test_exit_4_when_the_account_cannot_be_read(self):
        self.build({"usage_unreadable": True})
        code, manifest, _ = self.run_stage("pilot")
        self.assertEqual(code, 4)
        self.assertIn("STOP the account could not be read at the start", manifest)
        self.assertEqual(stage_stubs.calls(self.root, ".suite_calls"), [])

    def test_exit_5_when_the_live_check_fails(self):
        self.build({"livecheck_exit": 1})
        code, manifest, _ = self.run_stage("pilot")
        self.assertEqual(code, 5)
        self.assertIn("STOP the live check failed", manifest)
        self.assertIn("live check of", (self.root / "experiments/results/pilot-test.livecheck").read_text())
        self.assertEqual(stage_stubs.calls(self.root, ".suite_calls"), [])

    def test_exit_10_when_env_sets_a_sampling_key_and_quiet_on_another_key(self):
        # Fires: .env sets a key the agent reads before MODEL_*, which the runner would refill
        # after the chain unset it. The manifest names the key and never its value.
        self.build({"env_keys": ["BROWSER_WORKER_TEMPERATURE", "OPENROUTER_API_KEY"]})
        code, manifest, text = self.run_stage("pilot")
        self.assertEqual(code, 10)
        self.assertIn("STOP .env sets the sampling key(s) BROWSER_WORKER_TEMPERATURE , which the runner would refill",
                      manifest)
        self.assertNotIn("0.73", manifest + text)
        self.assertNotIn("OPENROUTER", manifest)
        self.assertEqual(stage_stubs.calls(self.root, ".suite_calls"), [])
        # Two keys set: both named, once each.
        self.build({"env_keys": ["MODEL_TOP_P", "MODEL_TEMPERATURE", "MODEL_TOP_P"]})
        code, manifest, _ = self.run_stage("pilot")
        self.assertEqual(code, 10)
        self.assertIn("MODEL_TEMPERATURE MODEL_TOP_P ,", manifest)
        # Quiet: a .env that sets no sampling key, and the whole pilot runs.
        self.build({"env_keys": ["OPENROUTER_API_KEY"]})
        code, manifest, _ = self.run_stage("pilot")
        self.assertEqual(code, 0, manifest)
        # The stub root keeps one manifest, so the two STOP lines are the runs above and no more.
        self.assertEqual(manifest.count("STOP"), 2)

    def test_exit_7_when_a_call_was_served_outside_the_routing(self):
        self.build({"provider": "Relace"})
        code, manifest, _ = self.run_stage("pilot")
        self.assertEqual(code, 7)
        self.assertIn("routing-check|fail relace", manifest)
        self.assertIn("STOP the routing check failed: fail relace", manifest)
        self.assertEqual(stage_stubs.calls(self.root, ".suite_calls"), [])

    def test_exit_6_when_the_preflight_refuses_an_arm(self):
        self.build({"preflight_refuse": ["the block (rules)"]})
        code, manifest, _ = self.run_stage("pilot")
        self.assertEqual(code, 6)
        self.assertIn("STOP preflight refused the block (rules)", manifest)
        # Shipped and open everything ran before it; nothing after.
        self.assertEqual(len([l for l in manifest.splitlines() if l.startswith("batch|")]), 4)
        self.assertIn("REFUSED: planted for the block (rules)", (self.root / "experiments/results/pilot-test.preflight").read_text())

    def test_exit_3_when_spent_plus_the_high_would_reach_the_cap(self):
        # The first run costs $5.80 of the $6 cap: the second's $0.31 high no longer fits.
        self.build({"default_cost": 5.8})
        code, manifest, _ = self.run_stage("pilot")
        self.assertEqual(code, 3)
        self.assertEqual(len([l for l in manifest.splitlines() if l.startswith("batch|")]), 1)
        self.assertIn("STOP spent + high $0.31 would reach $6.00", manifest)
        self.assertIn("shipped round 1 --only tee-promo-check", manifest)

    def test_the_watchdog_stops_a_run_once_spent_reaches_the_cap_less_30_cents(self):
        # The run's charges land first ($5.75 of the $6 cap, over the cap less $0.30), then it
        # sleeps: the watchdog, every second here, must stop it before it finishes.
        self.build({"spend_first": 5.75, "sleep": 15, "default_cost": 0.01})
        code, manifest, _ = self.run_stage("pilot", timeout=60)
        self.assertEqual(code, 3, manifest)
        self.assertRegex(manifest, r"WATCHDOG \S+ spent 5\.7\d*: stopped pid \d+")
        self.assertIn("batch||model=", manifest, "the stopped run wrote no batch")
        self.assertNotIn("pilot-check|", manifest)

    def test_a_watchdog_below_the_cap_stays_quiet(self):
        self.build({"spend_first": 0.2, "sleep": 2, "default_cost": 0.01})
        code, manifest, _ = self.run_stage("pilot", timeout=120)
        self.assertEqual(code, 0, manifest)
        self.assertNotIn("WATCHDOG", manifest)


class TheStageChain(Tree):
    """Stage 1 on a smaller design: one round, so the chain runs in seconds."""

    def small(self, scenario=None):
        self.build(scenario)
        analysis = stage_stubs.analysis_file()
        for arm in analysis["design"][DEEPSEEK]["asks"].values():
            for name in arm:
                arm[name] = [1]
        stage_stubs.write(self.root / "experiments/tasks/claim2_analysis.json", analysis)

    def test_the_whole_stage_with_a_void_re_run_and_the_four_reading_tests(self):
        self.small({"void": ["tee-xs-price"], "void_arms": ["box-model"], "default_cost": 0.05})
        code, manifest, text = self.run_stage("1")
        self.assertEqual(code, 0, manifest)
        lines = manifest.splitlines()
        batches = [l for l in lines if l.startswith("batch|")]
        # One round: shipped 13, open everything 8, each block arm 8 + 5 templates and 8 + 4 held-out.
        self.assertEqual(len(batches), 13 + 8 + 2 * 4)
        reruns = [l for l in lines if l.startswith("rerun|")]
        self.assertEqual(len(reruns), 1)
        self.assertTrue(reruns[0].endswith(" --only tee-xs-price --repeat-start 1"), reruns[0])
        self.assertTrue(pathlib.Path(reruns[0].split("|")[1]).is_dir())
        tests = [l for l in lines if l.startswith("reading-test|")]
        self.assertEqual([l.split("|")[2].split()[0] for l in tests],
                         [f"model={DEEPSEEK}"] * 2 + ["model=anthropic/claude-haiku-4.5"] * 2)
        first_block = next(l for l in batches if "arm=the block" in l).split("|")[1]
        self.assertTrue(all(l.endswith(f" page-from {first_block}") for l in tests))
        self.assertTrue(lines[-1].startswith("end "))
        # The re-run and reading-test lines too are ones claim.py's manifest parser accepts.
        self.assertEqual(claim.parse_manifest(manifest).problems, [])
        # Each reading test's result: the filter, the market's task file, Haiku with no routing.
        results = [json.loads(pathlib.Path(l.split("|")[1]).read_text()) for l in tests]
        self.assertEqual([r["env_routing"] is None for r in results], [False, False, True, True])
        self.assertTrue(all(r["spec_from"] == "experiments/tasks/tasks_claim.json" for r in results))
        self.assertEqual([len(r["rows"]) for r in results], [3, 4, 3, 4])
        # The re-run carried the batch's flags and the routing, under the chain's model, and its
        # preflight ran first, under the arm the batch line names (the audit at cd49128).
        suites = stage_stubs.calls(self.root, ".suite_calls")
        rerun = suites[-5]
        self.assertIn("--parser", rerun["argv"])
        self.assertEqual((rerun["model"], json.loads(rerun["routing"])), (DEEPSEEK, stage_stubs.ROUTING))
        preflights = stage_stubs.calls(self.root, ".preflights")
        for_rerun = [p for p in preflights if "--only tee-xs-price --repeat-start 1" in p["flags"]]
        self.assertEqual([(p["arm"], p["model"]) for p in for_rerun], [("the block (model)", DEEPSEEK)])
        self.assertEqual(len(preflights), len(batches) + 1)
        # The brand's search terms before and after every invocation, the re-run's too, as lines
        # the manifest parser knows.
        terms = [l for l in lines if l.startswith("search-terms|")]
        self.assertEqual(len(terms), 2 * (len(batches) + 1))
        self.assertTrue(all(l.split("|")[2] == "Wexcombe" and "wexcombe tee,45,3," in l for l in terms))
        self.assertEqual([l.split("|")[1] for l in terms[:2]], ["before", "after"])
        self.assertTrue(any(l.endswith("|re-run the block (model) --only tee-xs-price --repeat-start 1") for l in terms))
        self.assertEqual(claim.parse_manifest(manifest).extras["search-terms"], terms)

    def test_exit_8_with_no_block_batch_for_the_reading_test(self):
        self.small({"no_batch_for": ["box", "box-model"]})
        code, manifest, _ = self.run_stage("1")
        self.assertEqual(code, 8)
        self.assertIn("STOP no block batch for the reading test", manifest)
        self.assertNotIn("reading-test|", manifest)

    def test_exit_3_before_a_void_re_run_or_a_reading_test_when_the_cap_is_near(self):
        # A re-run needs $2.50 of room under the $69 cap: the last block batch spends to about
        # $67, under the watchdog's line ($68.70) and over the re-run's.
        self.small({"void": ["tee-xs-price"], "void_arms": ["box-model"], "default_cost": 0.05,
                    "cost": {"box-model": {"rw3-05": 63.5}}})
        code, manifest, _ = self.run_stage("1")
        self.assertEqual(code, 3, manifest)
        self.assertIn("STOP before a void re-run", manifest)
        self.assertNotIn("rerun|", manifest)


if __name__ == "__main__":
    unittest.main()
