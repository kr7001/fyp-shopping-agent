"""The second claim run's analysis, fixed before any of its data (22 October 2026): claim.py
under experiments/tasks/claim2_analysis.json, on synthetic runs fabricated here in a
temporary folder and never written to experiments/results.

The claim market does not exist yet, so the task file is the development market's,
Larchmere, written by env/generate_aplus_tasks.py --rewordings into the same temporary
folder: its fifteen questions and the thirty held-out rewordings of
experiments/tasks/paraphrases_v2.json that keep their template's meaning. The rewordings are
handled by id and template only: no test here shows their texts, one reads them only to
check that none reaches the report, and no rule or model is put to them (the held-out file's
own _about). The template questions are decided by the real box, both parsers, the model's
reply a stub, so the answer check has plans to replay; a rewording's box record has no plan.

Every arm, two models, three rounds. The synthetic answers are built from each question's
own key: the block under the model is right everywhere, under the rules right on the
templates and on half the rewordings, open everything right on the gated questions, shipped
right on the control alone. Each figure the tests hold is worked out in its comment.
Run2Faults plants one fault at a time in such batches, one model's, and watches the
analysis's own checks fire on it.
"""
import contextlib
import dataclasses
import datetime as dt
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import box  # noqa: E402
import claim  # noqa: E402
import form  # noqa: E402
import page as page_module  # noqa: E402
import score  # noqa: E402
import suite  # noqa: E402

PROTOCOL = paths.TASKS / "claim2_analysis.json"
FIXTURE = paths.FIXTURES / "aplus_dev.json"
HELD_OUT = paths.TASKS / "paraphrases_v2.json"
DEEPSEEK, HAIKU = "deepseek/deepseek-v4-flash", "anthropic/claude-haiku-4.5"
TASKS_FILE = "tasks_claim2dev.json"
READINGS_FILE = "readings_claim2dev.json"
RIGHT_ON = {"shipped": {"tee-headline"}}       # besides the arms below


def build_task_files(folder: pathlib.Path) -> None:
    """The claim task file and its sidecar for the development market, with the rewordings,
    as the one command writes them; the other task files beside them, linked, since the
    analysis tools read some of them by name."""
    for path in paths.TASKS.iterdir():
        if path.suffix == ".json":
            (folder / path.name).symlink_to(path)
    subprocess.run([sys.executable, "env/generate_aplus_tasks.py", "--fixture", str(FIXTURE.relative_to(paths.REPO)),
                    "--out", str(folder / TASKS_FILE), "--readings-out", str(folder / READINGS_FILE),
                    "--rewordings", str(HELD_OUT.relative_to(paths.REPO))],
                   cwd=paths.REPO, check=True, capture_output=True)


def larchmere_page(spec: dict) -> page_module.Page:
    """The development market's results pages as the box would read them, from its fixture:
    each listing's seller, title and advertised price, on two pages."""
    fixture = json.loads(FIXTURE.read_text())
    base = spec["base_url"]
    listings = [page_module.Listing(seller=f["seller"], title=f["name"], url=f"{base}/{f['parent_sku'].lower()}.html",
                                    advertised=min(v["price"] for v in f["variants"] if v["qty"] > 0))
                for f in fixture["families"]]
    first = f"{base}/catalogsearch/result/?q={spec['brand']}"
    return page_module.Page(url=first, listings=listings, total=len(listings), next_page=False,
                            pages=(first, f"{base}/catalogsearch/result/index/?p=2&q={spec['brand']}"),
                            reader="rendered")


def right(expect: dict) -> str:
    """An answer its key judges correct."""
    kind = expect["kind"]
    if kind == "contains":
        return f"{expect['any'][0]}" + (f" at ${expect['price']:.2f}." if "price" in expect else ".")
    if kind == "price":
        return f"The lowest is ${expect['value']:.2f}."
    if kind == "boolean":
        return f"Yes. {expect['any'][0]}." if expect["value"] and expect.get("any") else (
            "Yes." if expect["value"] else "No. Some listings lack it.")
    if kind == "count":
        return f"{expect['value']} listings."
    if kind == "ranked":
        return "; ".join(f"{item['any'][0]} ${item['price']:.2f}" for item in expect["items"]) + "."
    return "I would not know."


def wrong(expect: dict) -> str:
    """An answer its key judges wrong."""
    kind = expect["kind"]
    if kind == "contains":
        return f"{expect['not_any'][0]} at $1.00." if expect.get("not_any") else "Nobody at $1.00."
    if kind == "price":
        return "The lowest is $1.00."
    if kind == "boolean":
        return "No." if expect["value"] else "Yes, every one."
    if kind == "count":
        return f"{expect['value'] + 3} listings."
    if kind == "ranked":
        return "; ".join(f"{item['any'][0]} $1.00" for item in reversed(expect["items"])) + "."
    return "I would not know."


@dataclasses.dataclass
class Plan:
    """One arm as the synthetic runs make it."""
    name: str
    recorded: str
    reading: str | None
    opens: int                  # how many of the question's product listings a run opens
    cost: float
    tokens: int

    def is_right(self, task: dict) -> bool:
        if self.name == "the block (model)":
            return True
        if self.name == "the block (rules)":
            return "template" not in task or task["rewording"] % 2 == 1
        if self.name == "open everything (product)":
            return task["gated"]
        return task["id"] in RIGHT_ON["shipped"]


ARMS = [Plan("shipped", "none", None, 4, 0.10, 100_000),
        Plan("open everything (product)", "exhaustive-product", None, 21, 0.60, 900_000),
        Plan("the block (rules)", "box", "menu", 9, 0.35, 400_000),
        Plan("the block (model)", "box-model", "menu", 8, 0.30, 380_000)]


def model_reply(question: str, page: page_module.Page) -> str:
    """The stub the model parser is given: the rules' own form of the question."""
    record = form.from_rules(question, page).record()
    reply = {k: record[k] for k in ("quantifier", "objective", "population", "k", "negated", "reading",
                                    "unknowns", "ambiguities", "filters")}
    reply["evidence"] = {}
    return json.dumps(reply)


def write_batch(root: pathlib.Path, name: str, arm: Plan, model: str, spec: dict, readings: dict,
                page: page_module.Page, asked: dict[str, list[str]]) -> pathlib.Path:
    """One arm's batch for one model, every question the protocol's design gives it, three
    rounds, as suite.py writes a batch: suite.json, and for each run its record and its log."""
    folder = root / name
    folder.mkdir()
    tasks = {t["id"]: t for t in spec["tasks"]}
    fixture = json.loads(FIXTURE.read_text())
    product_urls = {p: [f"{spec['base_url']}/{f['parent_sku'].lower()}.html" for f in fixture["families"]
                        if f["product"] == p] for p in ("tee", "water")}
    boxed = arm.recorded.startswith("box")
    rows = []
    for task_id in asked[arm.name]:
        task = tasks[task_id]
        question = task["query"].format(base=spec["base_url"])
        decision = None
        if boxed and "template" not in task:
            parser = "model" if arm.recorded == "box-model" else "rules"
            call = (lambda prompt, q=question: model_reply(q, page)) if parser == "model" else None
            decision = box.decide(question, page, reply=arm.reading, parser=parser, call=call)
        for repeat in (1, 2, 3):
            tag = f"{task_id}-{repeat}"
            refused = (decision is not None and decision.refuse is not None) or (
                boxed and task.get("template") in ("decline-delivery", "decline-taste"))
            if refused:
                record = decision.record() if decision is not None else {
                    "asked": False, "ask": None, "refuse": "The shop does not show it.", "query": None,
                    "page": None, "reading": None, "bypassed": False, "fallback": False}
                # Under the model parser the parse is paid for, as suite.py writes it.
                row = suite.asked_row(task, repeat, record, cost=0.002 if arm.recorded == "box-model" else 0)
                if arm.recorded == "box-model":
                    row["parse_cost_usd"] = 0.002
                rows.append(row)
                continue
            answer = right(task["expect"]) if arm.is_right(task) else wrong(task["expect"])
            urls = product_urls[task["product"]][:arm.opens]
            start = dt.datetime(2026, 11, 1, 10, 0, 0)
            stamp = lambda t: f"{t:%Y-%m-%d %H:%M:%S} | fake | default_trace_id | INFO | "  # noqa: E731
            lines = [stamp(start) + "the run starts"] + [f"Page URL: {url}" for url in urls]
            lines += [f"cost={arm.cost:.4f}, is_byok=False", stamp(start + dt.timedelta(seconds=8)) + "the run ends"]
            (folder / f"{tag}.log").write_text("\n".join(lines) + "\n")
            (folder / f"{tag}.json").write_text(json.dumps({
                "model": model, "elapsed_s": 8.0, "cost_usd": arm.cost, "error": None,
                "result": {"ok": True, "final": answer},
                "trace": {"tokens": {"prompt": arm.tokens - 1000, "completion": 1000}},
                "log": f"{tag}.log", "shop": "gated", "probe": "viewport", "scaffold": "openjiuwen",
                "max_steps": 300, "clock_s": 1800}))
            row = {"task": task_id, "family": task["family"], "gated": task["gated"], "repeat": repeat,
                   "answer": answer[:300], "cost_usd": arm.cost, "error": None, "log": f"{tag}.log"}
            if boxed:
                record = (decision.record() if decision is not None else
                          {"asked": False, "ask": None, "refuse": None, "query": None, "page": None,
                           "reading": None, "bypassed": False, "fallback": False})
                row.update({"box": record, "reading": record.get("reading")})
            reading = (row.get("box") or {}).get("reading")
            row["verdict"] = score.score_under(task, reading, readings, answer, True)["verdict"]
            rows.append(row)
    payload = {"ran_at": "2026-11-01T10:30:00", "repeats": 3, "repeat_start": 1, "policy": "off",
               "confidence": "off", "exhaustive": arm.recorded == "exhaustive-product",
               "exhaustive_wording": "product" if arm.recorded == "exhaustive-product" else None,
               "targeting": False, "box": boxed, "box_exhaust": False, "arm": arm.recorded,
               "targeting_version": 9 if boxed else None, "planner_version": 2 if boxed else None,
               "box_version": box.VERSION if boxed else None, "form_version": 11 if boxed else None,
               "primitives_version": 11 if boxed else None, "page_reader": "rendered" if boxed else None,
               "parser": ("model" if arm.recorded == "box-model" else "rules") if boxed else None,
               "parser_model": model if arm.recorded == "box-model" else None,
               "prompt_version": 2 if arm.recorded == "box-model" else None,
               "normalise_version": 4 if arm.recorded == "box-model" else None,
               "reading": arm.reading, "browser_tool": "0.0.83", "browser_origins": "http://localhost:7770",
               "browser_flags": "--block-service-workers --isolated", "scorer_version": score.VERSION,
               "rules_version": None, "model": model, "scaffold": "openjiuwen",
               "agent_core_commit": "a" * 40, "agent_core_patch": "b" * 40, "max_steps": 300, "clock_s": 1800,
               "tasks_file": TASKS_FILE, "draw": suite.draw_id(spec), "instance": spec["_instance"],
               "summary": {}, "rows": rows}
    (folder / "suite.json").write_text(json.dumps(payload))
    return folder


def build_run2(root: pathlib.Path, models=(DEEPSEEK, HAIKU), plant=None, asks=None) -> pathlib.Path:
    """The task files under root/tasks, every arm's batch for each model, and the claim
    command's manifest naming them, whose path is returned. For a fault, `plant(model, arm,
    folder)` alters a batch once it is written, and `asks(design)` the questions each arm
    is given."""
    tasks_dir = root / "tasks"
    tasks_dir.mkdir()
    build_task_files(tasks_dir)
    spec = json.loads((tasks_dir / TASKS_FILE).read_text())
    readings = json.loads((tasks_dir / READINGS_FILE).read_text())["readings"]
    config = json.loads(PROTOCOL.read_text())
    design = claim.resolve_protocol(PROTOCOL, config, spec).design
    if asks is not None:
        design = asks(design)
    page = larchmere_page(spec)
    lines, n = [], 0
    for model in models:
        for arm in ARMS:
            n += 1
            folder = write_batch(root, f"202611{n:02d}T100000", arm, model, spec, readings, page, design)
            if plant is not None:
                plant(model, arm, folder)
            lines.append(f"batch|{folder}|{config['arms'][arm.name]['flags']}")
    manifest = root / "claim2-test.manifest"
    manifest.write_text("start 2026-11-01T10:00:00 usage 20.0 cap 60\n" + "\n".join(lines)
                        + "\nend 2026-11-01T16:00:00 usage 41.0\n")
    return manifest


def analyse(manifest: pathlib.Path) -> tuple[int, dict, str]:
    """claim.py --protocol on the manifest, as the command line runs it: its exit code, the
    analysis it writes beside the manifest, and what it prints."""
    with mock.patch.object(paths, "TASKS", manifest.parent / "tasks"), \
            contextlib.redirect_stdout(io.StringIO()) as out:
        code = claim.main(["--protocol", str(PROTOCOL), str(manifest)])
    return code, json.loads(manifest.with_suffix(".analysis.json").read_text()), out.getvalue()


class SyntheticRun2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.owner.name)
        manifest = build_run2(root)
        cls.spec = json.loads((root / "tasks" / TASKS_FILE).read_text())
        cls.config = json.loads(PROTOCOL.read_text())
        cls.code, cls.result, cls.out = analyse(manifest)
        cls.protocol = claim.resolve_protocol(PROTOCOL, cls.config, cls.spec)

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def test_it_reads_the_protocol_and_every_arm(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(self.result["problems"], [])
        self.assertEqual(sorted(self.result["models"]), sorted([DEEPSEEK, HAIKU]))
        for model, m in self.result["models"].items():
            with self.subTest(model=model):
                self.assertTrue(m["named"])
                self.assertEqual(list(m["arms"]), list(self.config["arms"]))
                # Shipped asks the 15 templates, open everything the 12 gated, each block the
                # 15 and the 30 rewordings, three rounds each: 45, 36, 135 and 135 runs.
                self.assertEqual({arm: a["runs"] for arm, a in m["arms"].items()},
                                 {"shipped": 45, "open everything (product)": 36,
                                  "the block (rules)": 135, "the block (model)": 135})
                self.assertEqual((m["exclusions"]["design"]["slots"], m["exclusions"]["design"]["filled"]),
                                 (351, 351))
                self.assertEqual((m["conditions"]["held"]["max_steps"], m["conditions"]["held"]["clock_s"]),
                                 (300, 1800))
                self.assertEqual(m["conditions"]["required"], [])

    def test_h1_correct_on_the_reading_independent_questions(self):
        # The block under the model is right on all nine, 27 of 27; shipped right on none of
        # them, 0 of 27. Every stratum is 3 of 3 against 0 of 3, hypergeometric 1/20 each,
        # and the block's 27 is the only total as extreme: p = 2 x (1/20)^9.
        for model, m in self.result["models"].items():
            h1 = m["primary"]["H1"]
            with self.subTest(model=model):
                self.assertEqual((h1["a"], h1["b"], len(h1["per_question"])), ("the block (model)", "shipped", 9))
                self.assertEqual((h1["pooled"]["a"], h1["pooled"]["b"]), ([27, 27], [0, 27]))
                self.assertAlmostEqual(h1["p"], 2 * (1 / 20) ** 9, places=20)

    def test_h2_and_h3_by_hand(self):
        # Opened: the block opens 8, open everything 21, in each of the twelve gated
        # questions; the block's three take ranks 1 to 3, a sum of 6 against a null mean of
        # 10.5 each, so 72 against 126, and only the two most extreme of 20^12 joint splits
        # are as far: p = 2 x (1/20)^12. Cost and tokens the same, the block cheaper in each.
        for model, m in self.result["models"].items():
            h2, h3 = m["primary"]["H2"], m["primary"]["H3"]
            with self.subTest(model=model):
                self.assertEqual((h2["observed"], h2["expected"]), (72.0, 126.0))
                self.assertAlmostEqual(h2["p"], 2 * (1 / 20) ** 12, places=25)
                self.assertEqual((h3["observed"], h3["also"]["observed"], h3["also"]["measure"]),
                                 (72.0, 72.0, "tokens_total"))
                self.assertEqual(h3["also"]["pooled"]["a"][:3], [380_000] * 3)

    def test_h4_on_the_held_out_rewordings_by_template(self):
        # Thirteen keyed templates, two rewordings each, three rounds: six runs a stratum and
        # arm. The model is right on all; the rules on the odd-numbered rewordings. The
        # templates differ in how many odd ids they hold, so the counts are read from the
        # task file, by id only.
        held = {task["id"]: task for task in self.spec["tasks"] if task.get("template")}
        for model, m in self.result["models"].items():
            h4 = m["primary"]["H4"]
            with self.subTest(model=model):
                self.assertEqual((h4["a"], h4["b"], h4["strata"]), ("the block (model)", "the block (rules)", "template"))
                keyed = sorted({t["template"] for t in held.values() if t["expect"]["kind"] != "none"})
                self.assertEqual(sorted(h4["questions"]), keyed)
                for row in h4["per_question"]:
                    ids = [t for t in held.values() if t["template"] == row["task"]]
                    self.assertEqual(row["a"], [6, 6])
                    self.assertEqual(row["b"], [3 * sum(t["rewording"] % 2 for t in ids), 6])
                self.assertEqual(h4["pooled"]["a"], [78, 78])

    def test_the_audits_rules_stay_quiet_on_a_plain_run(self):
        # Protocol analysis v2: no closed slot on a gated question, nothing sorted or resized,
        # so the two sensitivities give the primary's p; and every shipped failure, with no
        # results page in its log, never reached page 2.
        for model, m in self.result["models"].items():
            with self.subTest(model=model):
                self.assertEqual((m["primary"]["H2"]["closed"], m["primary"]["H3"]["closed"]), ([], []))
                self.assertEqual({arm: (row["sorted"], row["resized"]) for arm, row in m["secondary"]["toolbar"].items()},
                                 {arm: (0, 0) for arm in self.config["arms"]})
                for name in ("with the closed slots in H2 and H3", "without the runs that sorted or changed the page size"):
                    self.assertEqual({t: v["p"] for t, v in m["sensitivity"][name].items()},
                                     {t: v["p"] for t, v in m["primary"].items()})
                self.assertEqual(m["secondary"]["failure_breakdown"]["pooled"],
                                 {"page 2 never reached": 36, "a card or sold-out price taken": 0, "other": 0})

    def test_h4_on_each_part_of_each_split(self):
        # The model right on all, the rules on the odd-numbered rewordings: each part's counts
        # follow from its templates, and the two parts of a split are H4's thirteen strata.
        held = [task for task in self.spec["tasks"] if task.get("template")]
        sets = self.config["sets"]
        for model, m in self.result["models"].items():
            splits = m["splits"]["H4"]
            with self.subTest(model=model):
                self.assertEqual([s["split"] for s in splits], list(self.config["splits"]["H4"]))
                for split in splits:
                    for part in split["parts"]:
                        templates = sets[part["set"]]
                        odd = sum(t["rewording"] % 2 for t in held if t["template"] in templates)
                        self.assertEqual(sorted(part["questions"]), sorted(templates))
                        self.assertEqual((part["pooled"]["a"], part["pooled"]["b"]),
                                         ([6 * len(templates)] * 2, [3 * odd, 6 * len(templates)]))
                    self.assertEqual(sorted(q for part in split["parts"] for q in part["questions"]),
                                     sorted(m["primary"]["H4"]["questions"]))
        self.assertIn("H4 on the pre-specified splits, secondary and unadjusted", self.out)

    def test_h4_by_rewording(self):
        # One unit a rewording: the model's share is 1 on every one, the rules' 1 on the odd
        # ones and 0 on the even, 26 units an arm; H1 to H3 are the primary's.
        held = [task for task in self.spec["tasks"] if task.get("template") and task["expect"]["kind"] != "none"]
        for model, m in self.result["models"].items():
            tests = m["sensitivity"]["H4 by rewording, not by run"]
            h4 = tests["H4"]
            with self.subTest(model=model):
                self.assertEqual((h4.get("unit"), len(h4["pooled"]["a"]), len(h4["pooled"]["b"])), ("rewording", 26, 26))
                for row in h4["per_question"]:
                    ids = [t for t in held if t["template"] == row["task"]]
                    self.assertEqual(row["a"], [1.0] * len(ids))
                    self.assertEqual(sorted(row["b"]), sorted(float(t["rewording"] % 2) for t in ids))
                self.assertEqual({t: tests[t]["p"] for t in ("H1", "H2", "H3")},
                                 {t: m["primary"][t]["p"] for t in ("H1", "H2", "H3")})

    def test_a_split_that_does_not_divide_the_strata_is_refused(self):
        for label, change, words in (
                ("a template in neither part", lambda s: s["water_templates"].pop(), "does not divide"),
                ("a template in both", lambda s: s["water_templates"].append("tee-headline"), "overlap")):
            with self.subTest(fault=label):
                broken = json.loads(json.dumps(self.config))
                change(broken["sets"])
                with self.assertRaises(SystemExit) as raised:
                    claim.resolve_protocol(PROTOCOL, broken, self.spec)
                self.assertIn(words, str(raised.exception))

    def test_holm_over_the_four(self):
        for model, m in self.result["models"].items():
            tests = m["primary"]
            with self.subTest(model=model):
                self.assertEqual(list(tests), ["H1", "H2", "H3", "H4"])
                ps = {name: t["p"] for name, t in tests.items()}
                self.assertEqual({name: t["p_holm"] for name, t in tests.items()}, claim.holm(ps))
                # Four tests, so the smallest p is multiplied by four.
                self.assertAlmostEqual(min(t["p_holm"] for t in tests.values()), 4 * min(ps.values()), places=30)
                self.assertEqual([name for name, t in tests.items() if t["rejected"]], ["H1", "H2", "H3", "H4"]
                                 if tests["H4"]["p_holm"] <= claim.ALPHA else ["H1", "H2", "H3"])

    def test_each_model_is_its_own_result(self):
        # The two models' runs are the same here, so their figures are, and neither pools the
        # other: each counts its own 351 runs.
        a, b = (self.result["models"][m] for m in (DEEPSEEK, HAIKU))
        self.assertEqual(len(a["runs"]), 351)
        self.assertEqual(len(b["runs"]), 351)
        self.assertEqual(a["primary"]["H1"]["p"], b["primary"]["H1"]["p"])

    def test_the_tables_and_the_secondary_figures(self):
        m = self.result["models"][HAIKU]
        model, shipped = m["tables"]["the block (model)"], m["tables"]["shipped"]
        self.assertEqual((model["tee-target-price"]["correct"], model["tee-target-price"]["opened"]), (3, [8, 8, 8]))
        self.assertEqual((shipped["tee-headline"]["correct"], shipped["pooled, gated"]["correct"]), (3, 0))
        # The declines: the box refuses both templates and their four rewordings, three rounds.
        self.assertEqual(m["secondary"]["declines"]["the block (model)"]["refused"], 18)
        self.assertEqual(m["secondary"]["declines"]["shipped"]["answered without a plan"], 6)
        # Two readings are the sidecar's `two_readings` (task F, item 1): the three templates
        # and their six rewordings, three rounds, 27 of the block's 135 runs. Under the rule
        # before it every question the sidecar keys, 39 of them, had two: 117.
        row = m["secondary"]["asks"]["the block (model)"]
        self.assertEqual((row["clear"]["runs"], row["ambiguous"]["runs"], row["ambiguous"]["asks"]), (108, 27, 9))
        # The count with two readings, arm by key.
        table = m["secondary"]["count_two_readings"]["table"]
        self.assertEqual(table["the block (model)"]["menu_key"], 3)
        # The answer check replayed the block's template plans: thirteen planned questions,
        # three rounds, every stored text reproduced. The synthetic logs hold no tool reply,
        # so the check sees no observation and refuses every answer, which shows it ran.
        check = m["secondary"]["answer_check"]["the block (model)"]
        self.assertEqual((check["runs"], check["planned"], check["not_reproduced"]), (39, 39, []))
        self.assertEqual(len(check["correct_refused"]), 39)
        self.assertEqual(model["tee-target-price"]["tokens_mean"], 380_000)
        # A slot the box closed costs its parse under the model parser, nothing under the rules.
        rules = m["tables"]["the block (rules)"]
        self.assertEqual((model["decline-taste"]["cost_mean"], rules["decline-taste"]["cost_mean"]), (0.002, 0.0))
        # A question with no key has no count of correct answers to show: "-", never 0.
        self.assertEqual((model["decline-taste"]["keyed"], model["tee-target-price"]["keyed"]), (False, True))
        self.assertRegex(self.out, r"\n    decline-taste +3 +-  ")
        self.assertRegex(self.out, r"\n    tee-target-price +3 +3/3  ")
        self.assertEqual(list(m["sensitivity"]), self.config["sensitivity"])

    def test_the_report_prints_every_section(self):
        for words in ("The claim analysis under", "Problems found: 0", "Model deepseek/deepseek-v4-flash",
                      "Model anthropic/claude-haiku-4.5", "Held constant across the arms:", "max_steps 300",
                      "clock_s 1800", "1. Each arm by question", "2. Primary tests, two-sided, with Holm's "
                      "correction over the 4", "H1 correct, the block (model) against shipped",
                      "H4 correct, the block (model) against the block (rules), on held_out, by template",
                      "stratified exact test by template", "380k",
                      "and on the agent's tokens, outside Holm", "3. Correct, the block (model) against open everything",
                      "4. The held-out rewordings, by template", "5. Secondary and exploratory",
                      "c. The questions the block should not plan", "6. Sensitivity"):
            with self.subTest(words=words):
                self.assertIn(words, self.out)

    def test_no_rewording_text_is_printed_or_stored(self):
        # Checked without showing any: only whether one appears.
        held = json.loads(HELD_OUT.read_text())["paraphrases"]
        limit = self.spec["_instance"]["exists_limit"]
        texts = [entry["text"].format(brand=self.spec["brand"], limit=limit) for entry in held]
        report = self.out + json.dumps(self.result)
        self.assertFalse(any(text in report for text in texts))


def set_conditions(folder: pathlib.Path, **values) -> None:
    """A written batch's conditions changed: in its payload, and in each run record that
    holds them."""
    for path in folder.glob("*.json"):
        data = json.loads(path.read_text())
        data.update({key: value for key, value in values.items() if path.name == "suite.json" or key in data})
        path.write_text(json.dumps(data))


def drop_run(folder: pathlib.Path, task: str, repeat: int) -> None:
    """A run taken out of a written batch, row, record and log, as if never run."""
    payload = json.loads((folder / "suite.json").read_text())
    payload["rows"] = [row for row in payload["rows"] if (row["task"], row["repeat"]) != (task, repeat)]
    (folder / "suite.json").write_text(json.dumps(payload))
    for suffix in (".json", ".log"):
        (folder / f"{task}-{repeat}{suffix}").unlink()


def void_run(folder: pathlib.Path, task: str, repeat: int) -> None:
    """A run of a written batch made void: the provider failed and no answer came back."""
    path = folder / f"{task}-{repeat}.json"
    record = json.loads(path.read_text())
    record.update(result={"ok": False, "final": ""}, error="Error code: 429, rate limited")
    path.write_text(json.dumps(record))
    payload = json.loads((folder / "suite.json").read_text())
    for row in payload["rows"]:
        if (row["task"], row["repeat"]) == (task, repeat):
            row.update(answer="", verdict="failed", error=record["error"])
    (folder / "suite.json").write_text(json.dumps(payload))


def answer_under(folder: pathlib.Path, task_id: str, repeat: int, reading: str, answer: str) -> None:
    """A run of a written batch answered under `reading`, as its box record now says, with
    `answer`, and the verdict the batch would have stored for it."""
    tasks_dir = folder.parent / "tasks"
    task = next(t for t in json.loads((tasks_dir / TASKS_FILE).read_text())["tasks"] if t["id"] == task_id)
    readings = json.loads((tasks_dir / READINGS_FILE).read_text())["readings"]
    path = folder / f"{task_id}-{repeat}.json"
    record = json.loads(path.read_text())
    record["result"]["final"] = answer
    path.write_text(json.dumps(record))
    payload = json.loads((folder / "suite.json").read_text())
    for row in payload["rows"]:
        if (row["task"], row["repeat"]) == (task_id, repeat):
            row["box"]["reading"] = row["reading"] = reading
            row.update(answer=answer[:300], verdict=score.score_under(task, reading, readings, answer, True)["verdict"])
    (folder / "suite.json").write_text(json.dumps(payload))


def task_of(folder: pathlib.Path, task_id: str) -> dict:
    return next(t for t in json.loads((folder.parent / "tasks" / TASKS_FILE).read_text())["tasks"]
                if t["id"] == task_id)


def close_slot(folder: pathlib.Path, task_id: str, repeat: int, cost: float = 0.002) -> None:
    """A run of a written batch turned into a slot the box closed: it asked, no reply came, no
    agent ran, and the model parser's parse was paid for, as suite.py writes such a slot."""
    for suffix in (".json", ".log"):
        (folder / f"{task_id}-{repeat}{suffix}").unlink()
    record = {"asked": True, "ask": "Do you mean listed, or in stock now?", "refuse": None, "query": None,
              "page": None, "reading": None, "bypassed": False, "fallback": False}
    payload = json.loads((folder / "suite.json").read_text())
    payload["rows"] = [suite.asked_row(task_of(folder, task_id), repeat, record, cost=cost) | {"parse_cost_usd": cost}
                       if (row["task"], row["repeat"]) == (task_id, repeat) else row for row in payload["rows"]]
    (folder / "suite.json").write_text(json.dumps(payload))


def add_pages(folder: pathlib.Path, task_id: str, repeat: int, *urls: str) -> None:
    """Pages a run of a written batch was on, as its log reports them, before its last line."""
    path = folder / f"{task_id}-{repeat}.log"
    lines = path.read_text().splitlines()
    path.write_text("\n".join(lines[:-1] + [f"Page URL: {url}" for url in urls] + lines[-1:]) + "\n")


def answer_with(folder: pathlib.Path, task_id: str, repeat: int, answer: str) -> None:
    """A run of a written batch given another answer, and the verdict the batch would have
    stored for it."""
    path = folder / f"{task_id}-{repeat}.json"
    record = json.loads(path.read_text())
    record["result"]["final"] = answer
    path.write_text(json.dumps(record))
    readings = json.loads((folder.parent / "tasks" / READINGS_FILE).read_text())["readings"]
    payload = json.loads((folder / "suite.json").read_text())
    for row in payload["rows"]:
        if (row["task"], row["repeat"]) == (task_id, repeat):
            row.update(answer=answer[:300],
                       verdict=score.score_under(task_of(folder, task_id), None, readings, answer, True)["verdict"])
    (folder / "suite.json").write_text(json.dumps(payload))


def fixture_prices() -> tuple[float, float]:
    """The development market's cheapest tee card and its cheapest size M that is sold out,
    from its fixture: a price a card shows and one a sold-out size shows."""
    tees = [f for f in json.loads(FIXTURE.read_text())["families"] if f["product"] == "tee"]
    card = min(min(v["price"] for v in f["variants"] if v["qty"] > 0) for f in tees)
    sold_out = min(v["price"] for f in tees for v in f["variants"] if v["option"] == "M" and v["qty"] == 0)
    return card, sold_out


SEARCH = "http://localhost:7770/catalogsearch/result/index/?q=Larchmere"


def another_seller(expect: dict) -> str:
    """A tee seller of the development market that a contains key neither wants nor excludes."""
    named = {token.lower() for token in expect["any"] + expect.get("not_any", [])}
    return next(f["seller"] for f in json.loads(FIXTURE.read_text())["families"]
                if f["product"] == "tee" and f["seller"].split()[0].lower() not in named)


def showcase(model: str, arm: Plan, folder: pathlib.Path) -> None:
    """Every fault the verifier's fairness audit of 23 October 2026 named, planted in one run
    of the synthetic batches: the block (model) closes two slots on the gated questions, an
    ask no reply answered; shipped sorts one run and sets 60 a page in another, gives a card
    price, a sold-out price and a plain wrong one after reaching page 2, and a card price
    without reaching it; open everything sorts one run; and the block (rules) names as the
    cheapest a seller its key never excluded, which the batch stored as correct."""
    card, sold_out = fixture_prices()
    if arm.name == "the block (model)":
        close_slot(folder, "tee-count-stocked", 1)
        close_slot(folder, "water-all-stocked", 2)
    if arm.name == "shipped":
        add_pages(folder, "tee-target-price", 1, f"{SEARCH}&p=2")
        answer_with(folder, "tee-target-price", 1, f"The lowest is ${card:.2f}.")
        add_pages(folder, "tee-target-price", 2, f"{SEARCH}&p=2")
        answer_with(folder, "tee-target-price", 2, f"The lowest is ${sold_out:.2f}.")
        add_pages(folder, "tee-target-price", 3, f"{SEARCH}&product_list_limit=60")
        add_pages(folder, "tee-cheapest-target", 1, f"{SEARCH}&product_list_order=price")
        # The first rule that holds decides: a card price, but page 1 alone.
        answer_with(folder, "tee-exists-under", 1, f"Yes, at ${card:.2f}.")
    if arm.name == "open everything (product)":
        add_pages(folder, "tee-count-buyable", 2, f"{SEARCH}&product_list_order=name")
    if arm.name == "the block (rules)":
        expect = task_of(folder, "tee-cheapest-target")["expect"]
        answer_with(folder, "tee-cheapest-target", 1, f"{another_seller(expect)} is the cheapest for size M at "
                                                      f"$1.00. {expect['any'][0]} is next at ${expect['price']:.2f}.")


def drop_key(tasks_dir: pathlib.Path, task_id: str) -> dict:
    """A question's buyable key taken out of the sidecar; the key is returned."""
    path = tasks_dir / READINGS_FILE
    sidecar = json.loads(path.read_text())
    key = sidecar["readings"]["buyable"].pop(task_id)
    path.write_text(json.dumps(sidecar))
    return key


class Run2Faults(unittest.TestCase):
    """The run-2 analysis's own checks, each firing on a fault planted in the synthetic
    batches, and quiet without it. One model's batches, so the other named model has none."""

    def run2(self, plant=None, models=(HAIKU,), asks=None) -> tuple[int, dict, str]:
        with tempfile.TemporaryDirectory() as tmp:
            return analyse(build_run2(pathlib.Path(tmp), models, plant, asks))

    def test_quiet_but_for_the_named_model_with_no_run(self):
        code, result, out = self.run2()
        self.assertEqual(result["problems"], [f"the protocol's model {DEEPSEEK} has no run"])
        self.assertIn("Problems found: 1", out)
        self.assertEqual(list(result["models"]), [HAIKU])

    def test_a_step_budget_the_protocol_does_not_require(self):
        def plant(model, arm, folder):
            if arm.name == "shipped":
                set_conditions(folder, max_steps=150)
        _, result, out = self.run2(plant)
        self.assertIn(f"{HAIKU}: shipped ran with max_steps 150, where the protocol requires 300", result["problems"])
        self.assertTrue(any(p.startswith(f"{HAIKU}: max_steps differs between the arms: shipped 150;")
                            for p in result["problems"]), result["problems"])
        self.assertIn("NOT AS REQUIRED: shipped ran with max_steps 150", out)

    def test_a_condition_that_differs_between_the_arms(self):
        def plant(model, arm, folder):
            if arm.name == "open everything (product)":
                set_conditions(folder, browser_tool="0.0.84")
        _, result, out = self.run2(plant)
        self.assertIn(f"{HAIKU}: browser_tool differs between the arms: shipped 0.0.83; open everything "
                      f"(product) 0.0.84; the block (rules) 0.0.83; the block (model) 0.0.83", result["problems"])
        self.assertIn("DIFFERS between arms, browser_tool", out)

    def test_a_slot_never_run_is_a_problem_and_a_void_is_not(self):
        def plant(model, arm, folder):
            if arm.name == "shipped":
                drop_run(folder, "tee-top-3", 2)
            if arm.name == "the block (rules)":
                void_run(folder, "tee-top-3", 2)
        _, result, _ = self.run2(plant)
        design = result["models"][HAIKU]["exclusions"]["design"]
        self.assertEqual(design["missing"], ["shipped, tee-top-3 repeat 2", "the block (rules), tee-top-3 repeat 2"])
        self.assertEqual(design["never_run"], ["shipped, tee-top-3 repeat 2"])
        self.assertEqual([v["task"] for v in result["models"][HAIKU]["exclusions"]["voids"]], ["tee-top-3"])
        self.assertEqual(result["problems"], [f"{HAIKU}: the design's slot shipped, tee-top-3 repeat 2 has no "
                                              f"run, void or not", f"the protocol's model {DEEPSEEK} has no run"])

    def test_a_run_the_design_does_not_ask_for(self):
        _, result, _ = self.run2(asks=lambda design: {**design, "shipped": design["shipped"] + ("rw-03",)})
        self.assertEqual([p for p in result["problems"] if "does not ask for" in p],
                         [f"{HAIKU}: a run the design does not ask for, shipped, rw-03 repeat {r}" for r in (1, 2, 3)])

    def test_a_model_the_protocol_does_not_name_is_analysed_apart(self):
        other = "x-ai/grok-5-mini"
        _, result, out = self.run2(models=(HAIKU, other))
        self.assertEqual((result["models"][HAIKU]["named"], result["models"][other]["named"]), (True, False))
        self.assertIn(f"Model {other}, which the protocol does not name", out)
        self.assertEqual(result["problems"], [f"the protocol's model {DEEPSEEK} has no run"])
        self.assertEqual(len(result["models"][other]["runs"]), 351)

    def the_run(self, result: dict, arm: str, task: str, repeat: int) -> dict:
        return next(run for run in result["models"][HAIKU]["runs"]
                    if (run["arm"], run["task"], run["repeat"]) == (arm, task, repeat))

    def test_a_run_is_scored_under_the_reading_it_answered(self):
        # The block (model)'s first round of tee-count-stocked answered under the buyable
        # reading, as its box record now says, with the buyable count: correct under that
        # key, wrong under the question's own (score v4), and so correct.
        def plant(model, arm, folder):
            if arm.name == "the block (model)":
                readings = json.loads((folder.parent / "tasks" / READINGS_FILE).read_text())["readings"]
                answer_under(folder, "tee-count-stocked", 1, "buyable", right(readings["buyable"]["tee-count-stocked"]))
        _, result, _ = self.run2(plant)
        run = self.the_run(result, "the block (model)", "tee-count-stocked", 1)
        self.assertEqual((run["answered"], run["own"], run["buyable"], run["verdict"]),
                         ("buyable", "wrong", "correct", "correct"))
        self.assertEqual(result["problems"], [f"the protocol's model {DEEPSEEK} has no run"])

    def test_a_run_with_no_key_for_its_reading_is_in_no_test_of_correct(self):
        # A rewording of tee-count-stocked answered under the buyable reading where the
        # sidecar has no buyable key for it: unscored, so H4's tee-count-stocked stratum
        # holds the block (model)'s other five runs, and the run is listed as a problem.
        found = {}

        def plant(model, arm, folder):
            if arm.name == "the block (model)":
                key = drop_key(folder.parent / "tasks", "rw-09")
                answer_under(folder, "rw-09", 1, "buyable", right(key))
                found["batch"] = folder.name
        _, result, out = self.run2(plant)
        run = self.the_run(result, "the block (model)", "rw-09", 1)
        self.assertEqual((run["answered"], run["verdict"]), ("buyable", "unscored"))
        h4 = result["models"][HAIKU]["primary"]["H4"]
        self.assertEqual(next(row["a"] for row in h4["per_question"] if row["task"] == "tee-count-stocked"), [5, 5])
        self.assertIn(f"{HAIKU}: {found['batch']}/rw-09-1 has no key for the reading it answered, buyable, so it is "
                      f"unscored and in no test of correct", result["problems"])
        self.assertRegex(out, r"\n     tee-count-stocked +5/5  asked")

    def test_a_closed_slot_with_no_charge_is_unknown_not_free(self):
        def plant(model, arm, folder):
            if arm.name == "the block (model)":
                payload = json.loads((folder / "suite.json").read_text())
                for row in payload["rows"]:
                    if (row["task"], row["repeat"]) == ("decline-taste", 1):
                        row["cost_usd"] = row["parse_cost_usd"] = None
                (folder / "suite.json").write_text(json.dumps(payload))
        _, result, _ = self.run2(plant)
        row = result["models"][HAIKU]["tables"]["the block (model)"]["decline-taste"]
        self.assertEqual((row["cost_mean"], row["cost_missing"]), (0.002, 1))
        self.assertIsNone(self.the_run(result, "the block (model)", "decline-taste", 1)["cost"])

    def test_batches_on_two_task_files_are_refused(self):
        def plant(model, arm, folder):
            if arm.name == "shipped":
                set_conditions(folder, tasks_file="tasks_aplus_dev.json")
        with self.assertRaises(SystemExit) as raised:
            self.run2(plant)
        self.assertIn("the batches read 2 task files", str(raised.exception))


class AuditItems(unittest.TestCase):
    """Protocol analysis v2 (23 October 2026): each rule the verifier's fairness audit asked
    for, firing on the synthetic run that carries its fault (`showcase`). The plain run, where
    each must stay quiet, is SyntheticRun2's."""

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        cls.code, cls.result, cls.out = analyse(build_run2(pathlib.Path(cls.owner.name), plant=showcase))
        cls.m = cls.result["models"][HAIKU]

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def row(self, test: dict, task: str) -> dict:
        return next(row for row in test["per_question"] if row["task"] == task)

    def test_h2_and_h3_count_only_the_slots_where_the_agent_ran(self):
        # The block (model) closed tee-count-stocked's first round and water-all-stocked's
        # second: each stratum holds its two runs, 8 opened at $0.30, and the closed slots are
        # listed. Put back, each is 0 listings at the parse's $0.002.
        for name, value, closed_value in (("H2", 8, 0), ("H3", 0.30, 0.002)):
            test = self.m["primary"][name]
            with self.subTest(test=name):
                for task in ("tee-count-stocked", "water-all-stocked"):
                    self.assertEqual(self.row(test, task)["a"], [value, value])
                self.assertEqual(test["closed"], [{"task": "tee-count-stocked", "a": 1, "b": 0},
                                                  {"task": "water-all-stocked", "a": 1, "b": 0}])
                back = self.m["sensitivity"]["with the closed slots in H2 and H3"][name]
                self.assertEqual(sorted(self.row(back, "tee-count-stocked")["a"]), [closed_value, value, value])
        self.assertIn("slots the box closed, no agent run, left out (a the block (model), b open everything "
                      "(product)): tee-count-stocked 1/0, water-all-stocked 1/0", self.out)

    def test_sorting_and_page_size_are_counted_by_arm(self):
        table = self.m["secondary"]["toolbar"]
        got = {arm: (row["sorted"], row["resized"]) for arm, row in table.items()}
        self.assertEqual(got, {"shipped": (1, 1), "open everything (product)": (1, 0),
                               "the block (rules)": (0, 0), "the block (model)": (0, 0)})
        named = {n["run"].split("/")[1]: (n["sorted"], n["page size"]) for n in table["shipped"]["named"]}
        self.assertEqual(named, {"tee-cheapest-target-1": (["price"], []), "tee-target-price-3": ([], ["60"])})
        # Dropped in the sensitivity: shipped's tee-target-price and tee-cheapest-target keep
        # two runs each in H1, open everything's tee-count-buyable two in H2.
        dropped = self.m["sensitivity"]["without the runs that sorted or changed the page size"]
        self.assertEqual(self.row(dropped["H1"], "tee-cheapest-target")["b"], [0, 2])
        self.assertEqual(self.row(dropped["H1"], "tee-target-price")["b"], [0, 2])
        self.assertEqual(len(self.row(dropped["H2"], "tee-count-buyable")["b"]), 2)
        self.assertEqual(self.row(self.m["primary"]["H1"], "tee-target-price")["b"], [0, 3])

    def test_the_shipped_failures_are_coded_by_the_written_rules(self):
        fb = self.m["secondary"]["failure_breakdown"]
        codes = {run["run"].split("/")[1]: run["code"] for run in fb["runs"]}
        self.assertEqual((fb["failures"], fb["of"]), (36, 36))
        card, sold_out = fixture_prices()
        self.assertEqual({tag: codes[tag] for tag in ("tee-target-price-1", "tee-target-price-2", "tee-target-price-3",
                                                      "tee-cheapest-target-1", "tee-exists-under-1")},
                         {"tee-target-price-1": "a card or sold-out price taken",
                          "tee-target-price-2": "a card or sold-out price taken",
                          # 60 a page shows every listing: past page 1, and $1.00 is no price shown.
                          "tee-target-price-3": "other",
                          # Sorted, but never past the first page.
                          "tee-cheapest-target-1": "page 2 never reached",
                          # A card price too, but the rules are tried in order and the first holds.
                          "tee-exists-under-1": "page 2 never reached"})
        evidence = {run["run"].split("/")[1]: run["evidence"] for run in fb["runs"]}
        self.assertEqual(evidence["tee-target-price-1"], f"card ${card:.2f}")
        self.assertEqual(evidence["tee-target-price-2"], f"sold out ${sold_out:.2f}")
        self.assertEqual(fb["pooled"], {"page 2 never reached": 33, "a card or sold-out price taken": 2, "other": 1})
        self.assertIn("f. Why shipped was not correct", self.out)

    def test_a_verdict_the_markets_sellers_move_is_listed(self):
        # The block (rules) named a seller the key never excluded the cheapest: the batch
        # stored it correct, scored without the market's sellers as suite.py scores today;
        # this analysis scores it with them, wrong, and says so rather than applying it unseen.
        run = next(r for r in self.m["runs"] if (r["arm"], r["task"], r["repeat"])
                   == ("the block (rules)", "tee-cheapest-target", 1))
        self.assertEqual(run["verdict"], "wrong")
        # One problem a model's rules batch: "<batch>/tee-cheapest-target-1: stored verdict ...".
        moved = [p for p in self.result["problems"] if "stored verdict correct, re-scored wrong" in p]
        self.assertEqual([p.split(": ")[0].split("/")[1] for p in moved], ["tee-cheapest-target-1"] * 2)
        self.assertEqual(len(self.result["problems"]), 2)

    def test_each_model_has_its_role_and_its_own_holm(self):
        self.assertEqual(list(self.result["models"]), [DEEPSEEK, HAIKU])
        self.assertEqual({m: r["role"] for m, r in self.result["models"].items()},
                         {DEEPSEEK: "primary", HAIKU: "replication"})
        self.assertIn(f"Model {DEEPSEEK}, the primary: its four tests are the claim, Holm over the four.", self.out)
        self.assertIn(f"Model {HAIKU}, a replication of the primary: its own Holm over its four.", self.out)
        for model, m in self.result["models"].items():
            with self.subTest(model=model):
                ps = {name: t["p"] for name, t in m["primary"].items()}
                self.assertEqual({name: t["p_holm"] for name, t in m["primary"].items()}, claim.holm(ps))


class TwoReadings(unittest.TestCase):
    """Which questions have two readings, for claim.py (task F, item 1): the A+ sidecar keys
    every question, so being keyed no longer says a question has two, and its `two_readings`
    names them. The first claim's sidecar has no such field, and keeps the rule it had."""

    def test_the_sidecar_names_them_or_says_nothing(self):
        self.assertEqual(score.two_readings_for(paths.TASKS / "tasks_aplus_dev.json"),
                         ["tee-all-stocked", "tee-count-stocked", "water-all-stocked"])
        self.assertIsNone(score.two_readings_for(paths.TASKS / "tasks_claim_apparel.json"))
        self.assertIsNone(score.two_readings_for(paths.TASKS / "tasks_reviews.json"))    # no sidecar
        # Where it says nothing, every question it keys has two: the first claim's two.
        keyed = score.readings_for(paths.TASKS / "tasks_claim_apparel.json")
        self.assertEqual(sorted({task for keys in keyed.values() for task in keys}),
                         ["apparel-all-stocked", "apparel-count-stocked"])


class ProtocolFile(unittest.TestCase):
    def test_the_file_is_whole(self):
        self.assertEqual(claim.check_protocol(json.loads(PROTOCOL.read_text())), [])

    def test_a_file_that_does_not_hold_together_is_refused_before_any_batch(self):
        config = json.loads(PROTOCOL.read_text())
        for label, change, words in (
                ("an unknown arm in a test", lambda c: c["tests"]["H1"].update(b="the agent"), "compares an arm"),
                ("an unknown measure", lambda c: c["tests"]["H2"].update(measure="speed"), "measures what"),
                ("template strata off the rewordings", lambda c: c["tests"]["H1"].update(strata="template"),
                 "only the held-out rewordings have"),
                ("a set missing", lambda c: c["sets"].pop("two_readings"), "names no two_readings set"),
                ("a sensitivity unknown", lambda c: c["sensitivity"].append("with luck"), "no sensitivity"),
                ("a condition no run records", lambda c: c["require"].update(colour="red"), "no run records"),
                ("two arms alike", lambda c: c["arms"]["shipped"].update(arm="box", reading="menu"),
                 "same instruction and reading"),
                # Protocol analysis v2, 23 October 2026.
                ("two primaries", lambda c: c["roles"].update({HAIKU: "primary"}), "other than one primary"),
                ("a role this analysis has not", lambda c: c["roles"].update({HAIKU: "lead"}), "role is not one of"),
                ("a role for a model not named", lambda c: c["roles"].update({"x-ai/grok-5-mini": "replication"}),
                 "not the protocol's models"),
                ("a split of a test the file has not", lambda c: c["splits"].update({"H9": {}}),
                 "a test the protocol has not"),
                ("a split of one set", lambda c: c["splits"]["H4"].update({"one": ["tee_templates"]}),
                 "is not two sets"),
                ("the failure codes out of order", lambda c: c["failure_breakdown"]["codes"].reverse(),
                 "codes are not this analysis's"),
                ("no page size", lambda c: c["failure_breakdown"].pop("page_size"), "names no page size")):
            with self.subTest(fault=label):
                broken = json.loads(json.dumps(config))
                change(broken)
                self.assertTrue(any(words in problem for problem in claim.check_protocol(broken)),
                                claim.check_protocol(broken))


if __name__ == "__main__":
    unittest.main()
