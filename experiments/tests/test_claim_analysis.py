"""The claim run's analysis, `experiments/analysis/claim.py`, written on 20 October 2026
before the claim run.

The statistics are checked on examples small enough to work out by hand, or against a
published worked example; the analysis on synthetic arms whose every figure is computed in
the comments here; and, where the raw logs are on this machine, on the Thornwood development
batches against cells 1 and 5, where it must reproduce the verifier's in-sample figures.

Every rule has a case where it must fire and one where it must stay quiet, and the faults
the tests are said to catch were planted and seen to fail them (LESSONS 24 and 31). Nothing
here reaches a model.
"""
import contextlib
import dataclasses
import datetime as dt
import hashlib
import io
import itertools
import json
import pathlib
import random
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import claim  # noqa: E402
import compare_cells  # noqa: E402
import suite  # noqa: E402
import verify_cells  # noqa: E402

TASKS_FILE = "tasks_claim_apparel.json"
SPEC = json.loads((paths.TASKS / TASKS_FILE).read_text())
DRAW = suite.draw_id(SPEC)
MARKET = verify_cells.market_urls(SPEC)
HAIKU = "anthropic/claude-haiku-4.5"
DEEPSEEK = "deepseek/deepseek-v4-flash"
TP, CB, AS, CS = claim.TARGET_PRICE, claim.COUNT_BUYABLE, claim.ALL_STOCKED, claim.COUNT_STOCKED

# Answers the claim market's keys judge as the comment says (price 23.43, count-buyable 7,
# count-stocked 10 under the menu key and 7 under the buyable key, all-stocked no).
RIGHT = {TP: "The lowest price for size M is $23.43.", CB: "7 listings have size M in stock.",
         AS: "No. Fairhaven Textiles has no size M.", CS: "10 listings offer size M."}
WRONG = {TP: "Size M starts at $18.11.", CB: "5 listings have size M in stock.",
         AS: "Yes, every listing offers it.", CS: "7 listings offer size M."}


# ---------------------------------------------------------------------------
# 1. The stratified exact rank test

# The verifier's function as its audit wrote it (audit/tools/strat_rank.py, 20 October 2026),
# kept here verbatim so the port can be held to it.
AUDIT_STRAT_RANK = '''
import itertools, collections
def midranks(values):
    order = sorted(values); r = {}
    for v in set(values):
        idx = [i for i, x in enumerate(order) if x == v]; r[v] = sum(idx) / len(idx) + 1
    return [r[v] for v in values]

def stratified_rank_test(a_by_q, b_by_q):
    """a_by_q, b_by_q: {question: [values]}. Statistic: sum over questions of A's mid-rank sum.
    Null: within each question, A's labels are a random subset of the pooled runs. Exact, two-sided."""
    dist = {0.0: 1.0}; observed = 0.0; mean = 0.0
    for q in sorted(set(a_by_q) & set(b_by_q)):
        a, b = a_by_q[q], b_by_q[q]
        ranks = midranks(a + b); na = len(a)
        observed += sum(ranks[:na])
        subsets = list(itertools.combinations(range(len(ranks)), na))
        pmf = collections.Counter(round(sum(ranks[i] for i in s), 6) for s in subsets)
        pmf = {k: v / len(subsets) for k, v in pmf.items()}
        mean += sum(k * p for k, p in pmf.items())
        nxt = collections.defaultdict(float)
        for t, p in dist.items():
            for k, q_ in pmf.items(): nxt[round(t + k, 6)] += p * q_
        dist = nxt
    dev = abs(observed - mean)
    return observed, mean, sum(p for t, p in dist.items() if abs(t - mean) >= dev - 1e-9)
'''


def ordinal_ranks(values):
    """A planted fault: ranks with ties broken by position instead of shared."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    for place, i in enumerate(order):
        ranks[i] = place + 1.0
    return ranks


class RankTest(unittest.TestCase):
    # Question 1: A [1, 2] against B [3, 4], A's ranks 1 and 2, a sum of 3. Its six splits
    # give sums 3, 4, 5, 5, 6, 7, mean 5. Question 2: A [5] against B [5, 6], mid-ranks 1.5,
    # 1.5, 3, A's sum 1.5; its three splits give 1.5, 1.5, 3, mean 2. Observed 4.5 against
    # a mean of 7. The eighteen joint splits give sums 4.5 (twice), 6, 5.5 (twice), 7,
    # 6.5 (four times), 8 (twice), 7.5 (twice), 9, 8.5 (twice) and 10: those at least 2.5
    # from 7 are 4.5 twice and 10 once, so p = 3/18 = 1/6.
    A = {"q1": [1.0, 2.0], "q2": [5.0]}
    B = {"q1": [3.0, 4.0], "q2": [5.0, 6.0]}

    def by_enumeration(self, a, b):
        """Every joint assignment of the labels within each question, counted directly."""
        observed_ranks = {}
        splits = []
        for q in sorted(a):
            pooled = a[q] + b[q]
            ranks = claim.midranks(pooled)
            observed_ranks[q] = sum(ranks[:len(a[q])])
            splits.append([sum(ranks[i] for i in s)
                           for s in itertools.combinations(range(len(pooled)), len(a[q]))])
        totals = [sum(parts) for parts in itertools.product(*splits)]
        centre = sum(totals) / len(totals)
        observed = sum(observed_ranks.values())
        return sum(abs(t - centre) >= abs(observed - centre) - 1e-9 for t in totals) / len(totals)

    def test_a_two_question_example_worked_out_by_enumeration(self):
        observed, centre, p = claim.stratified_rank_test(self.A, self.B)
        self.assertEqual((observed, centre), (4.5, 7.0))
        self.assertAlmostEqual(p, 1 / 6, places=12)
        self.assertAlmostEqual(self.by_enumeration(self.A, self.B), 1 / 6, places=12)

    def test_the_port_is_the_audits_logic(self):
        audit = {}
        exec(AUDIT_STRAT_RANK, audit)
        rng = random.Random(20261020)
        for _ in range(200):
            questions = [f"q{n}" for n in range(rng.randint(1, 4))]
            a = {q: [rng.choice([1, 2, 3, 4, 15]) * 1.0 for _ in range(rng.randint(1, 4))] for q in questions}
            b = {q: [rng.choice([1, 2, 3, 15]) * 1.0 for _ in range(rng.randint(1, 4))] for q in questions}
            with self.subTest(a=a, b=b):
                self.assertEqual(claim.stratified_rank_test(a, b), audit["stratified_rank_test"](a, b))
                self.assertAlmostEqual(claim.stratified_rank_test(a, b)[2], self.by_enumeration(a, b), places=9)

    def test_fires_on_a_clear_difference_and_stays_quiet_on_none(self):
        # Three against three in two questions, A lowest in both: only the two extreme
        # joint splits are as far from the mean, 2 x (1/20)^2 = 0.005.
        apart = claim.stratified_rank_test({"q1": [1, 2, 3], "q2": [1, 2, 3]}, {"q1": [7, 8, 9], "q2": [7, 8, 9]})
        self.assertAlmostEqual(apart[2], 0.005, places=12)
        same = claim.stratified_rank_test({"q1": [1, 2, 3], "q2": [4, 4, 4]}, {"q1": [1, 2, 3], "q2": [4, 4, 4]})
        self.assertAlmostEqual(same[2], 1.0, places=12)
        # Only the questions both arms asked count: a question one arm alone has is no stratum.
        observed, centre, _ = claim.stratified_rank_test({"q1": [1, 2, 3], "only A": [9]}, {"q1": [7, 8, 9]})
        self.assertEqual(observed, 6.0)
        self.assertAlmostEqual(centre, 10.5, places=9)

    def test_a_planted_tie_fault_is_caught(self):
        # Ranks that break ties by position give another p on the example, so the example's
        # 1/6 is a test of the mid-ranks.
        with mock.patch.object(claim, "midranks", ordinal_ranks):
            planted = claim.stratified_rank_test(self.A, self.B)[2]
        self.assertNotAlmostEqual(planted, 1 / 6, places=6)


# ---------------------------------------------------------------------------
# 2. Holm's correction

class Holm(unittest.TestCase):
    def test_the_step_down_ordering(self):
        # Sorted: H2 0.01 x 3 = 0.03, H3 0.03 x 2 = 0.06, H1 0.04 x 1 = 0.04, raised to the
        # 0.06 before it. So H1 is not rejected at 0.05 though 0.04 is below it: the steps
        # stop at H3.
        adjusted = claim.holm({"H1": 0.04, "H2": 0.01, "H3": 0.03})
        self.assertEqual({k: round(v, 12) for k, v in adjusted.items()}, {"H1": 0.06, "H2": 0.03, "H3": 0.06})
        self.assertEqual(sorted(k for k, v in adjusted.items() if v <= 0.05), ["H2"])

    def test_quiet_when_every_step_passes(self):
        # 0.01 x 3, 0.02 x 2, 0.03 x 1 raised to 0.04: all three rejected at 0.05.
        adjusted = claim.holm({"H1": 0.03, "H2": 0.01, "H3": 0.02})
        self.assertEqual({k: round(v, 12) for k, v in adjusted.items()}, {"H1": 0.04, "H2": 0.03, "H3": 0.04})
        self.assertEqual(claim.holm({"H1": 0.5, "H2": 0.6, "H3": 0.9}), {"H1": 1.0, "H2": 1.0, "H3": 1.0})

    def test_a_test_not_computed_counts_as_one_and_keeps_m(self):
        adjusted = claim.holm({"H1": None, "H2": 0.01, "H3": 0.02})
        self.assertEqual({k: round(v, 12) for k, v in adjusted.items()}, {"H1": 1.0, "H2": 0.03, "H3": 0.04})


# ---------------------------------------------------------------------------
# 3. Newcombe's interval

class Newcombe(unittest.TestCase):
    """Newcombe RG (1998), "Interval estimation for the difference between independent
    proportions: comparison of eleven methods", Statistics in Medicine 17:873-890, Table II,
    method 10 (the hybrid score interval, no continuity correction), examples (a), (b) and
    (h); and Fagerland, Lydersen and Laake (2015), "Recommended confidence intervals for two
    independent binomial proportions", Statistical Methods in Medical Research 24:224-254,
    whose 7/34 against 1/34 statsmodels' own tests quote as 0.019 to 0.34."""
    PUBLISHED = [((56, 70, 48, 80), (0.0524, 0.3339)), ((9, 10, 3, 10), (0.1705, 0.8090)),
                 ((10, 10, 0, 10), (0.6075, 1.0000))]

    def test_the_published_worked_examples(self):
        for counts, (lower, upper) in self.PUBLISHED:
            with self.subTest(counts=counts):
                got = claim.newcombe(*counts)
                self.assertEqual((round(got[0], 4), round(got[1], 4)), (lower, upper))
        got = claim.newcombe(7, 34, 1, 34)
        self.assertEqual((round(got[0], 3), round(got[1], 2)), (0.019, 0.34))

    def test_a_planted_fault_misses_them(self):
        # The difference's limits built from the wrong arm's Wilson limits, and a plain Wald
        # interval: each misses example (a), so the test above can see either.
        def swapped(x1, n1, x2, n2, z=claim.Z95):
            p1, p2 = x1 / n1, x2 / n2
            l1, u1 = claim.wilson(x1, n1, z)
            l2, u2 = claim.wilson(x2, n2, z)
            return (p1 - p2 - ((p1 - l1) ** 2 + (p2 - l2) ** 2) ** 0.5,
                    p1 - p2 + ((u1 - p1) ** 2 + (u2 - p2) ** 2) ** 0.5)

        def wald(x1, n1, x2, n2, z=claim.Z95):
            p1, p2 = x1 / n1, x2 / n2
            half = z * (p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2) ** 0.5
            return p1 - p2 - half, p1 - p2 + half

        for planted in (swapped, wald):
            got = planted(56, 70, 48, 80)
            self.assertNotEqual((round(got[0], 4), round(got[1], 4)), (0.0524, 0.3339))

    def test_it_agrees_with_statsmodels_on_every_count_up_to_fifteen(self):
        try:
            from statsmodels.stats.proportion import confint_proportions_2indep
        except ImportError:
            self.skipTest("statsmodels is not installed")
        for n1, n2 in ((3, 3), (12, 12), (15, 15), (15, 12)):
            for x1 in range(n1 + 1):
                for x2 in range(n2 + 1):
                    ours = claim.newcombe(x1, n1, x2, n2)
                    theirs = confint_proportions_2indep(x1, n1, x2, n2, method="newcomb", compare="diff")
                    self.assertAlmostEqual(ours[0], theirs[0], places=9)
                    self.assertAlmostEqual(ours[1], theirs[1], places=9)

    def test_no_interval_without_runs(self):
        self.assertIsNone(claim.newcombe(0, 0, 2, 3))


# ---------------------------------------------------------------------------
# 4. The manifest

def manifest_text(root: pathlib.Path) -> str:
    """Lines as the claim command's `echo`s write them, folders absolute as suite.py prints them."""
    return "\n".join([
        "start 2026-10-20T21:05:00 usage 41.2345 cap 30",
        f"batch|{root}/20261020T210501|--repeat-start 1 --only apparel-headline apparel-target-price",
        f"batch|{root}/20261020T211502|--repeat-start 1 --exhaustive --only apparel-target-price",
        f"batch|{root}/20261020T212003|--repeat-start 1 --box --reading menu --only apparel-all-stocked",
        "batch||--repeat-start 2 --box-exhaust --reading menu --only apparel-target-price",
        f"rerun|{root}/20261020T230000|{root}/20261020T210501 --only apparel-target-price --repeat-start 1",
        "STOP cap of $30 reached 2026-10-20T23:05:00",
        "end 2026-10-20T23:10:00 usage None",
    ]) + "\n"


class ManifestLines(unittest.TestCase):
    def test_every_line_the_command_writes(self):
        root = pathlib.Path("/nowhere/experiments/results")
        found = claim.parse_manifest(manifest_text(root))
        self.assertEqual(found.problems, [])
        self.assertEqual(found.starts, [{"at": "2026-10-20T21:05:00", "usage": 41.2345, "cap": 30.0}])
        self.assertEqual(found.ends, [{"at": "2026-10-20T23:10:00", "usage": None}])
        self.assertEqual(found.stops, ["STOP cap of $30 reached 2026-10-20T23:05:00"])
        self.assertEqual([(line.kind, line.folder.name if line.folder else None) for line in found.lines],
                         [("batch", "20261020T210501"), ("batch", "20261020T211502"),
                          ("batch", "20261020T212003"), ("batch", None), ("rerun", "20261020T230000")])
        rerun = found.lines[-1]
        self.assertEqual((rerun.original.name, rerun.task, rerun.repeat),
                         ("20261020T210501", "apparel-target-price", 1))
        self.assertEqual(claim.intended(found.lines[2].args), ("box", "menu", [("apparel-all-stocked", 1)]))
        self.assertEqual(claim.intended(found.lines[3].args), ("box-exhaust", "menu", [("apparel-target-price", 2)]))
        self.assertEqual(claim.intended(found.lines[1].args)[:2], ("exhaustive", None))

    def test_a_line_the_command_never_writes_is_a_problem(self):
        found = claim.parse_manifest("batch|/x|--only a\nsomething else\nrerun|/y|/x --only apparel-a\n")
        self.assertEqual(len(found.problems), 2)
        self.assertIn("line 2 is not one the claim command writes", found.problems[0])
        self.assertIn("line 3: a re-run line without its original folder, task and repeat", found.problems[1])


# ---------------------------------------------------------------------------
# 5. Synthetic arms through the whole analysis

@dataclasses.dataclass
class Fake:
    """One run as a batch folder holds it: the answer, which of the market's listings it
    opened (by number), its charge, how long its log was silent, and so on."""
    answer: str
    opened: tuple = ()
    cost: float = 0.1
    silence: int = 5            # seconds from the log's first line to its last
    record: bool = True         # False: the runner wrote a log and no record
    ok: bool = True
    ended: str | None = None    # the result's error, the runtime's word for how it ended
    model: str | None = None    # the record's model, the batch's when None
    asked: bool = False         # the box asked on this slot before the agent ran
    extra_log: str = ""         # anything else the log should hold
    closed: str | None = None   # "refused" or "asked": the box closed the slot, no agent ran


def write_batch(root: pathlib.Path, name: str, arm: str, runs: dict, reading: str | None = None,
                model: str = HAIKU, box_version: int = 12, draw: str = DRAW) -> pathlib.Path:
    """A batch folder as suite.py writes one: suite.json, and for each run its record and its
    log, on the claim market's task file."""
    folder = root / name
    folder.mkdir()
    boxed = arm in ("box", "box-exhaust")
    readings = json.loads((paths.TASKS / "readings_claim_apparel.json").read_text())["readings"]
    tasks = {t["id"]: t for t in SPEC["tasks"]}
    rows = []
    for (task, repeat), run in runs.items():
        tag = f"{task}-{repeat}"
        if run.closed:
            # suite.asked_row: no record, no log, nothing spent.
            rows.append({"task": task, "family": "apparel", "gated": tasks[task]["gated"], "repeat": repeat,
                         "verdict": run.closed, "answer": run.answer, "cost_usd": 0, "error": None, "log": None,
                         "box": {"asked": run.closed == "asked", "reading": None, "query": None, "page": None,
                                 "refuse": run.answer if run.closed == "refused" else None},
                         "reading": None})
            continue
        start = dt.datetime(2026, 10, 20, 21, 0, 0)
        stamp = lambda t: f"{t:%Y-%m-%d %H:%M:%S} | fake | default_trace_id | INFO | "
        lines = [stamp(start) + "the run starts"]
        lines += [f"Page URL: {MARKET[n - 1]}" for n in run.opened]
        lines += [f"cost={run.cost:.4f}, is_byok=False"]
        lines += [run.extra_log] if run.extra_log else []
        lines += [stamp(start + dt.timedelta(seconds=run.silence)) + "the run ends"]
        (folder / f"{tag}.log").write_text("\n".join(lines) + "\n")
        said = reading if task in readings.get(reading or "", {}) else None
        if run.record:
            tokens = int(hashlib.sha1(f"{name}/{tag}".encode()).hexdigest()[:6], 16)
            (folder / f"{tag}.json").write_text(json.dumps({
                "model": run.model or model, "elapsed_s": 10.0, "cost_usd": run.cost, "error": None,
                "result": {"ok": run.ok, "final": run.answer, "error": run.ended},
                "tokens": {"prompt": tokens, "completion": 10}, "log": f"{tag}.log",
                "shop": "gated", "probe": "viewport", "scaffold": "openjiuwen"}))
        key = tasks[task] if said is None else {**tasks[task], "expect": readings[said][task]}
        verdict = claim.scoring.score(key, run.answer, run.ok)["verdict"] if run.record else "failed"
        row = {"task": task, "family": "apparel", "gated": tasks[task]["gated"], "repeat": repeat,
               "verdict": verdict, "answer": run.answer[:300], "cost_usd": run.cost,
               "error": None if run.record else "runner wrote no record", "log": f"{tag}.log"}
        if boxed:
            row.update({"box": {"asked": run.asked, "reading": said, "query": None, "page": None},
                        "reading": said})
        rows.append(row)
    payload = {"ran_at": "2026-10-20T21:10:00", "repeats": 1,
               "repeat_start": min(r for _, r in runs), "policy": "off", "confidence": "off",
               "exhaustive": arm == "exhaustive", "targeting": False, "box": arm == "box",
               "box_exhaust": arm == "box-exhaust", "arm": arm,
               "targeting_version": 7 if boxed else None, "planner_version": 2 if boxed else None,
               "box_version": box_version if boxed else None, "form_version": 9 if boxed else None,
               "primitives_version": 8 if boxed else None, "reading": reading,
               "browser_tool": "0.0.83", "browser_origins": "http://localhost:7770",
               "browser_flags": "--block-service-workers --isolated", "scorer_version": 3,
               "rules_version": None, "model": model, "scaffold": "openjiuwen",
               "agent_core_commit": "a" * 40, "agent_core_patch": "b" * 40,
               "tasks_file": TASKS_FILE, "draw": draw, "instance": SPEC["_instance"],
               "summary": {}, "rows": rows}
    (folder / "suite.json").write_text(json.dumps(payload))
    return folder


def run_main(*argv: str) -> tuple[int, str]:
    with contextlib.redirect_stdout(io.StringIO()) as out:
        code = claim.main(list(argv))
    return code, out.getvalue()


class HandComputedArms(unittest.TestCase):
    """Three arms on two questions, three rounds each, where every figure is worked out in
    the comments. The block opens 6 listings on target-price and 15 on count-buyable, shipped
    4 and 4, open everything 15 and 15. Correct: the block 3 of 3 and 2 of 3, shipped 0 of 3
    and 1 of 3, open everything 3 of 3 and 2 of 3."""

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.owner.name)
        six, every, four = (1, 3, 4, 10, 11, 15), tuple(range(1, 16)), (1, 2, 3, 4)
        block = {(TP, r): Fake(RIGHT[TP], six, cost=0.30 + 0.01 * (r - 1)) for r in (1, 2, 3)}
        block.update({(CB, r): Fake(RIGHT[CB] if r < 3 else WRONG[CB], every, cost=0.50 + 0.01 * (r - 1))
                      for r in (1, 2, 3)})
        shipped = {(TP, r): Fake(WRONG[TP], four, cost=0.10) for r in (1, 2, 3)}
        shipped.update({(CB, r): Fake(RIGHT[CB] if r == 1 else WRONG[CB], four, cost=0.10) for r in (1, 2, 3)})
        opened = {(TP, r): Fake(RIGHT[TP], every, cost=0.70 + 0.01 * (r - 1)) for r in (1, 2, 3)}
        opened.update({(CB, r): Fake(RIGHT[CB] if r < 3 else WRONG[CB], every, cost=0.60 + 0.01 * (r - 1))
                       for r in (1, 2, 3)})
        # Folders named so that their order says nothing about their arms.
        folders = [write_batch(root, "20261020T230000", "box", block, reading="menu"),
                   write_batch(root, "20261020T210000", "none", shipped),
                   write_batch(root, "20261020T220000", "exhaustive", opened)]
        manifest = root / "claim-test.manifest"
        manifest.write_text("start 2026-10-20T21:00:00 usage 10.0 cap 30\n"
                            + "".join(f"batch|{f}|\n" for f in folders)
                            + "end 2026-10-20T23:30:00 usage 15.0\n")
        cls.code, cls.out = run_main(str(manifest))
        cls.result = json.loads((root / "claim-test.analysis.json").read_text())
        cls.m = cls.result["models"][HAIKU]

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def test_the_arms_come_from_the_payloads(self):
        self.assertEqual(self.code, 0)
        self.assertEqual({arm: a["batches"] for arm, a in self.m["arms"].items()},
                         {claim.SHIPPED: ["20261020T210000"], claim.OPEN: ["20261020T220000"],
                          claim.BLOCK: ["20261020T230000"]})
        self.assertEqual({arm: a["runs"] for arm, a in self.m["arms"].items()},
                         {claim.SHIPPED: 6, claim.OPEN: 6, claim.BLOCK: 6})

    def test_h1_by_hand(self):
        # Strata (3 of 3, 0 of 3) and (2 of 3, 1 of 3). Each has 3 successes in 6 runs, so the
        # block's share is hypergeometric 1, 9, 9, 1 in 20; their sum is 1, 18, 99, 164, 99,
        # 18, 1 in 400. Observed 3 + 2 = 5, probability 18/400; as or less likely: 0, 1, 5
        # and 6, so p = 38/400 = 0.095.
        h1 = self.m["primary"]["H1"]
        self.assertEqual([(r["task"], r["a"], r["b"]) for r in h1["per_question"]],
                         [(TP, [3, 3], [0, 3]), (CB, [2, 3], [1, 3])])
        self.assertEqual((h1["pooled"]["a"], h1["pooled"]["b"]), ([5, 6], [1, 6]))
        self.assertAlmostEqual(h1["p"], 38 / 400, places=12)

    def test_h2_and_h3_by_hand(self):
        # Opened: target-price 6, 6, 6 against 15, 15, 15, mid-ranks 2, 2, 2, 5, 5, 5, the
        # block's sum 6 against a null of 6, 9, 12, 15 with weights 1, 9, 9, 1 in 20 (mean
        # 10.5); count-buyable all 15, every rank 3.5, the block's sum 10.5 whatever the split.
        # Observed 16.5 against 21: only 16.5 and 25.5 are 4.5 away, p = 2/20 = 0.1.
        h2 = self.m["primary"]["H2"]
        self.assertEqual(h2["observed"], 16.5)
        self.assertAlmostEqual(h2["expected"], 21.0, places=9)
        self.assertAlmostEqual(h2["p"], 0.1, places=12)
        # Cost: the block cheapest in both questions, ranks 1, 2, 3 for a sum of 6 in each, a
        # null mean of 10.5 each. Only a total of 12 or 30, each 1/20 x 1/20, is 9 from 21,
        # so p = 2/400 = 0.005.
        h3 = self.m["primary"]["H3"]
        self.assertEqual(h3["observed"], 12.0)
        self.assertAlmostEqual(h3["expected"], 21.0, places=9)
        self.assertAlmostEqual(h3["p"], 0.005, places=12)

    def test_holm_by_hand(self):
        # H3 0.005 x 3 = 0.015; H1 0.095 x 2 = 0.19; H2 0.1 x 1 = 0.1, raised to 0.19.
        holm = {name: round(t["p_holm"], 12) for name, t in self.m["primary"].items()}
        self.assertEqual(holm, {"H1": 0.19, "H2": 0.19, "H3": 0.015})
        self.assertEqual([name for name, t in self.m["primary"].items() if t["rejected"]], ["H3"])

    def test_against_open_everything_is_counts_and_an_interval(self):
        # Target-price 3/3 against 3/3, count-buyable 2/3 against 2/3, pooled 5/6 against 5/6.
        o = self.m["against_open_everything"]
        self.assertEqual([(r["task"], r["a"], r["b"]) for r in o["per_question"]],
                         [(TP, [3, 3], [3, 3]), (CB, [2, 3], [2, 3])])
        self.assertEqual(o["pooled"]["interval"], list(claim.newcombe(5, 6, 5, 6)))
        self.assertNotIn("p", o["pooled"])

    def test_the_tables(self):
        block = self.m["tables"][claim.BLOCK]
        self.assertEqual((block[TP]["correct"], block[TP]["opened_median"], round(block[TP]["cost_mean"], 6)),
                         (3, 6, 0.31))
        self.assertEqual((block[CB]["correct"], block[CB]["opened"], block[CB]["covered"]), (2, [15, 15, 15], 3))
        # Target-price needs the six listings advertised at or below $23.43; the block opened
        # exactly those, shipped opened four and missed igr-clm-10, -11 and -15 every time.
        self.assertEqual(block[TP]["covered"], 3)
        shipped = self.m["tables"][claim.SHIPPED]
        self.assertEqual(shipped[TP]["missed"], {"igr-clm-10": 3, "igr-clm-11": 3, "igr-clm-15": 3})
        self.assertEqual(shipped["pooled, gated"]["correct"], 1)
        self.assertEqual(self.result["source"]["account_moved"], 5.0)
        self.assertAlmostEqual(self.result["source"]["charges"], 0.93 + 1.53 + 0.6 + 2.13 + 1.83, places=9)

    def test_the_report_says_what_the_json_says(self):
        self.assertIn("p = 0.09500, Holm p = 0.19000", self.out)
        self.assertIn("p = 0.10000, Holm p = 0.19000", self.out)
        self.assertIn("rank sum 12.0 against 21.0 expected, p = 0.00500, Holm p = 0.01500", self.out)


class VoidsReplaced(unittest.TestCase):
    """A void is replaced by its re-run, matched on arm, task and repeat; a second void, a
    void never re-run and a void whose only re-run is of another arm are missing; a re-run
    of a run that was not void is left out."""

    @classmethod
    def setUpClass(cls):
        cls.owner = tempfile.TemporaryDirectory()
        root = cls.root = pathlib.Path(cls.owner.name)
        f = {
            # shipped, round 1: count-buyable-1 slept through 900 seconds
            "s1": write_batch(root, "20261020T210000", "none", {
                (TP, 1): Fake(WRONG[TP]), (CB, 1): Fake(RIGHT[CB], silence=900)}),
            # the block, round 1, all well
            "b1": write_batch(root, "20261020T210500", "box", {
                (TP, 1): Fake(RIGHT[TP]), (CB, 1): Fake(RIGHT[CB])}, reading="menu"),
            # shipped, round 2: target-price-2's runner wrote no record
            "s2": write_batch(root, "20261020T211000", "none", {
                (TP, 2): Fake("", record=False)}),
            # the block, round 2: count-buyable-2 slept, and is never re-run as the block
            "b2": write_batch(root, "20261020T211500", "box", {
                (CB, 2): Fake(RIGHT[CB], silence=600)}, reading="menu"),
            # re-runs: shipped count-buyable-1, answered wrong this time
            "r1": write_batch(root, "20261020T230000", "none", {(CB, 1): Fake(WRONG[CB])}),
            # shipped target-price-2, void again
            "r2": write_batch(root, "20261020T230500", "none", {(TP, 2): Fake(RIGHT[TP], silence=700)}),
            # the block's target-price-1, which was never void
            "r3": write_batch(root, "20261020T231000", "box", {(TP, 1): Fake(RIGHT[TP])}, reading="menu"),
            # the block's count-buyable-2, re-run under the wrong arm
            "r4": write_batch(root, "20261020T231500", "none", {(CB, 2): Fake(RIGHT[CB])}),
        }
        lines = ["start 2026-10-20T21:00:00 usage 1.0 cap 30"]
        lines += [f"batch|{f[k]}|" for k in ("s1", "b1", "s2", "b2")]
        lines += [f"rerun|{f['r1']}|{f['s1']} --only {CB} --repeat-start 1",
                  f"rerun|{f['r2']}|{f['s2']} --only {TP} --repeat-start 2",
                  f"rerun|{f['r3']}|{f['b1']} --only {TP} --repeat-start 1",
                  f"rerun|{f['r4']}|{f['b2']} --only {CB} --repeat-start 2",
                  "end 2026-10-20T23:30:00 usage 2.0"]
        (root / "v.manifest").write_text("\n".join(lines) + "\n")
        manifest = claim.parse_manifest((root / "v.manifest").read_text())
        cls.result = claim.analyse(manifest.lines, manifest)
        cls.m = cls.result["models"][HAIKU]

    @classmethod
    def tearDownClass(cls):
        cls.owner.cleanup()

    def counted(self) -> set:
        return {(r["arm"], r["batch"], r["task"], r["repeat"]) for r in self.m["runs"]}

    def test_the_runs_that_count(self):
        self.assertEqual(self.counted(), {
            (claim.SHIPPED, "20261020T210000", TP, 1), (claim.SHIPPED, "20261020T230000", CB, 1),
            (claim.BLOCK, "20261020T210500", TP, 1), (claim.BLOCK, "20261020T210500", CB, 1)})
        # The re-run's own answer counts, wrong as it was, never the void's right one.
        self.assertEqual(next(r["own"] for r in self.m["runs"] if r["batch"] == "20261020T230000"), "wrong")

    def test_replaced_missing_and_left_out(self):
        e = self.m["exclusions"]
        self.assertEqual([(r["batch"], r["task"], r["by"]) for r in e["replaced"]],
                         [("20261020T210000", CB, "20261020T230000")])
        missing = {(x["batch"], x["task"], x["repeat"]): x["why"] for x in e["missing"]}
        self.assertEqual(sorted(missing), [("20261020T211000", TP, 2), ("20261020T211500", CB, 2)])
        self.assertIn("void again on its re-run in 20261020T230500", missing[("20261020T211000", TP, 2)])
        self.assertEqual(missing[("20261020T211500", CB, 2)], "void, and no re-run of its arm, task and repeat")
        self.assertEqual(sorted((v["batch"], v["reason"]) for v in e["voids"]),
                         [("20261020T210000", "suspended"), ("20261020T211000", "no record"),
                          ("20261020T211500", "suspended"), ("20261020T230500", "suspended")])
        left_out = [p for p in self.result["problems"] if "replaced no void" in p]
        self.assertEqual(sorted(left_out), [
            f"20261020T231000/{TP}-1: a re-run that replaced no void of its arm, left out",
            f"20261020T231500/{CB}-2: a re-run that replaced no void of its arm, left out"])

    def test_with_the_voids_included(self):
        # The voids with a record join the counted runs: shipped count-buyable-1 (right) and
        # the re-run target-price-2 (right), and the block's count-buyable-2 (right).
        h1 = self.m["sensitivity"]["with the voids included"]["H1"]
        self.assertEqual([(r["task"], r["a"], r["b"]) for r in h1["per_question"]],
                         [(TP, [1, 1], [1, 2]), (CB, [2, 2], [1, 2])])
        primary = self.m["primary"]["H1"]
        self.assertEqual([(r["task"], r["a"], r["b"]) for r in primary["per_question"]],
                         [(TP, [1, 1], [0, 1]), (CB, [1, 1], [0, 1])])

    def test_a_list_of_folders_counts_every_run_that_is_not_void(self):
        lines = [claim.Line("folder", self.root / name) for name in
                 ("20261020T210000", "20261020T230000", "20261020T231000")]
        result = claim.analyse(lines)
        runs = {(r["batch"], r["task"], r["repeat"]) for r in result["models"][HAIKU]["runs"]}
        self.assertEqual(runs, {("20261020T210000", TP, 1), ("20261020T230000", CB, 1),
                                ("20261020T231000", TP, 1)})
        self.assertEqual(result["problems"], [])


class ModelsApart(unittest.TestCase):
    """Two models are never pooled, and one arm under two conditions stops the analysis."""

    def test_each_model_is_its_own_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            lines = [claim.Line("folder", write_batch(root, name, arm, {(TP, 1): Fake(answer)},
                                                      reading="menu" if arm == "box" else None,
                                                      model=model))
                     for name, arm, answer, model in (
                         ("20261020T210000", "none", WRONG[TP], HAIKU),
                         ("20261020T210100", "box", RIGHT[TP], HAIKU),
                         ("20261020T210200", "none", RIGHT[TP], DEEPSEEK),
                         ("20261020T210300", "box", WRONG[TP], DEEPSEEK))]
            result = claim.analyse(lines)
        self.assertEqual(sorted(result["models"]), sorted([HAIKU, DEEPSEEK]))
        h1 = {model: [(r["a"], r["b"]) for r in m["primary"]["H1"]["per_question"]]
              for model, m in result["models"].items()}
        # Pooled, each would read 1 of 2 against 1 of 2.
        self.assertEqual(h1, {HAIKU: [([1, 1], [0, 1])], DEEPSEEK: [([0, 1], [1, 1])]})
        self.assertEqual({model: sorted(b for a in m["arms"].values() for b in a["batches"])
                          for model, m in result["models"].items()},
                         {HAIKU: ["20261020T210000", "20261020T210100"],
                          DEEPSEEK: ["20261020T210200", "20261020T210300"]})

    def test_one_arm_under_two_box_versions_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            lines = [claim.Line("folder", write_batch(root, "20261020T210000", "box", {(TP, 1): Fake(RIGHT[TP])},
                                                      reading="menu", box_version=12)),
                     claim.Line("folder", write_batch(root, "20261020T210100", "box", {(TP, 2): Fake(RIGHT[TP])},
                                                      reading="menu", box_version=11))]
            with self.assertRaises(SystemExit) as refused:
                claim.analyse(lines)
            self.assertIn("box_version", str(refused.exception))
            self.assertIn("never pooled", str(refused.exception))
            # The same two batches under one version are one arm.
            (root / "20261020T210100" / "suite.json").write_text(
                (root / "20261020T210100" / "suite.json").read_text().replace('"box_version": 11', '"box_version": 12'))
            result = claim.analyse(lines)
            self.assertEqual(result["models"][HAIKU]["arms"][claim.BLOCK]["runs"], 2)

    def test_arms_on_two_markets_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            lines = [claim.Line("folder", write_batch(root, "20261020T210000", "none", {(TP, 1): Fake(RIGHT[TP])})),
                     claim.Line("folder", write_batch(root, "20261020T210100", "box", {(TP, 1): Fake(RIGHT[TP])},
                                                      reading="menu", draw="Ashcombe:0000000000"))]
            with self.assertRaises(SystemExit) as refused:
                claim.analyse(lines)
            self.assertIn("more than one market draw", str(refused.exception))


class ArmsFromPayloads(unittest.TestCase):
    def test_the_payload_wins_over_the_manifests_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            folder = write_batch(root, "20261020T210000", "exhaustive", {(TP, 1): Fake(RIGHT[TP])})
            text = (f"start 2026-10-20T21:00:00 usage 1.0 cap 30\n"
                    f"batch|{folder}|--repeat-start 1 --box --reading menu --only {TP}\n"
                    f"end 2026-10-20T21:30:00 usage 1.5\n")
            manifest = claim.parse_manifest(text)
            result = claim.analyse(manifest.lines, manifest)
        self.assertEqual(list(result["models"][HAIKU]["arms"]), [claim.OPEN])
        self.assertTrue(any("ask for arm box, reading menu; its payload says exhaustive" in p
                            for p in result["problems"]))

    def test_the_protocols_five_names_and_anything_else(self):
        base = {"scaffold": "openjiuwen", "policy": "off", "confidence": "off"}
        run = {"shop": "gated", "probe": "viewport"}
        cases = [({"arm": "none"}, claim.SHIPPED), ({"exhaustive": True}, claim.OPEN),
                 ({"arm": "box", "box": True, "reading": "menu"}, claim.BLOCK),
                 ({"box": True, "reading": "buyable"}, claim.BUYABLE),
                 ({"arm": "box-exhaust", "box_exhaust": True, "reading": "menu"}, claim.NO_STOP)]
        for payload, name in cases:
            with self.subTest(payload=payload):
                self.assertEqual(claim.arm_of({**base, **payload}, run), name)
        # A setting the protocol does not hold is not one of its arms.
        for payload, extra in (({"arm": "none"}, {"probe": "whole-page"}), ({"arm": "none", "scaffold": "naive"}, {}),
                               ({"arm": "box", "box": True, "reading": None}, {}),
                               ({"arm": "box", "box": True, "reading": "menu", "policy": "gate"}, {})):
            with self.subTest(payload=payload, extra=extra):
                self.assertTrue(claim.arm_of({**base, **payload}, {**run, **extra}).startswith("other: "))


# ---------------------------------------------------------------------------
# 6. Calls by page, asks and leaks

def event_line(calls: list[tuple[str, dict, str]]) -> str:
    """One openJiuwen trace event holding these calls and their replies."""
    messages = [{"role": "user", "content": "the task"},
                {"role": "assistant", "content": "", "tool_calls": [
                    {"id": f"c{n}", "function": {"name": name, "arguments": json.dumps(args)}}
                    for n, (name, args, _) in enumerate(calls)]}]
    messages += [{"role": "tool", "tool_call_id": f"c{n}", "content": reply}
                 for n, (_, _, reply) in enumerate(calls)]
    return "2026-10-20 21:00:00 | x | y | INFO | " + json.dumps({"event_id": "e1", "messages": messages})


def event_log(folder: pathlib.Path, calls: list[tuple[str, dict, str]]) -> pathlib.Path:
    """An openJiuwen log whose one event holds these calls and their replies."""
    path = folder / "run.log"
    path.write_text(event_line(calls) + "\n")
    return path


class PageTypes(unittest.TestCase):
    RESULTS = "http://localhost:7770/catalogsearch/result/?q=Ashcombe"
    THORNWOOD = "http://localhost:7770/igr-app-03.html"
    CATEGORY = "http://localhost:7770/electronics.html"

    def calls(self, folder):
        nav = "mcp_playwright-official_browser_navigate"
        return event_log(folder, [
            (nav, {"url": self.RESULTS}, f"### Page\n- Page URL: {self.RESULTS}\n"),
            ("browser_probe_cards", {}, "cards: 15"),
            (nav, {"url": MARKET[0]}, f"- Page URL: {MARKET[0]}"),
            ("mcp_playwright-official_browser_find", {"query": "Size"}, "combobox \"Size\""),
            (nav, {"url": self.THORNWOOD}, f"- Page URL: {self.THORNWOOD}"),
            (nav, {"url": self.CATEGORY}, f"- Page URL: {self.CATEGORY}"),
            ("ask_user", {"question": "which reading?"}, "menu")])

    def test_a_call_is_placed_by_the_page_it_left_the_browser_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = self.calls(pathlib.Path(tmp))
            calls, actions, names = claim.page_calls(log, MARKET)
            # On the claim market a Thornwood listing is not one of its listings (LESSONS 33).
            self.assertEqual(dict(calls), {"results": 2, "listing": 2, "other": 3})
            self.assertEqual(dict(actions), {"results": 1, "listing": 1, "other": 2})
            self.assertEqual(sum(1 for name in names if "ask" in name), 1)
            # Without a market the counter's own rule takes any generated listing for one.
            calls, _, _ = claim.page_calls(log, None)
            self.assertEqual(dict(calls), {"results": 2, "listing": 3, "other": 2})

    def test_a_planted_shape_rule_would_be_seen(self):
        # The fault LESSONS 33 names: a listing recognised by the shape of its address, the
        # market ignored. The test above would see it.
        original = claim.page_kind
        with tempfile.TemporaryDirectory() as tmp:
            log = self.calls(pathlib.Path(tmp))
            with mock.patch.object(claim, "page_kind", lambda url, own: original(url, None)):
                calls, _, _ = claim.page_calls(log, MARKET)
        self.assertNotEqual(dict(calls), {"results": 2, "listing": 2, "other": 3})

    def test_an_ask_the_agent_makes_itself_is_counted_in_its_run(self):
        # openJiuwen's schema has no ask tool today; were one called, the run's asks say so.
        nav = "mcp_playwright-official_browser_navigate"
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            asking = event_line([(nav, {"url": self.RESULTS}, f"- Page URL: {self.RESULTS}"),
                                 ("ask_user", {"question": "which size?"}, "M")])
            quiet = event_line([(nav, {"url": self.RESULTS}, f"- Page URL: {self.RESULTS}")])
            lines = [claim.Line("folder", write_batch(root, "20261020T210000", "none", {
                (TP, 1): Fake(RIGHT[TP], extra_log=asking), (TP, 2): Fake(RIGHT[TP], extra_log=quiet)}))]
            m = claim.analyse(lines)["models"][HAIKU]
        self.assertEqual((m["tables"][claim.SHIPPED][TP]["asks"], m["tables"][claim.SHIPPED][TP]["agent_asks"]), (1, 1))
        self.assertEqual(m["secondary"]["asks"][claim.SHIPPED]["clear"], {"runs": 2, "asks": 0, "agent_asks": 1})
        self.assertEqual(m["tables"][claim.SHIPPED][TP]["calls_results"], 1.5)

    def test_asks_on_the_clear_and_the_ambiguous_questions(self):
        runs = [{"ambiguous": True, "asked": True, "agent_asks": 0},
                {"ambiguous": True, "asked": True, "agent_asks": 0},
                {"ambiguous": False, "asked": False, "agent_asks": 1},
                {"ambiguous": False, "asked": False, "agent_asks": 0}]
        self.assertEqual(claim.asks({claim.BLOCK: runs})[claim.BLOCK],
                         {"clear": {"runs": 2, "asks": 0, "agent_asks": 1},
                          "ambiguous": {"runs": 2, "asks": 2, "agent_asks": 0}})


class UnderTheReadingAnswered(unittest.TestCase):
    def test_opened_what_it_needs_and_the_ask(self):
        # "Does every listing offer size M": under the menu reading only a listing without M
        # settles it (igr-clm-01 has none); under buyable a sold-out M does too (igr-clm-02's
        # is sold out). Each run opened one of them and answered No after the box asked.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            lines = [claim.Line("folder", write_batch(root, "20261020T210000", "box", {
                         (AS, 1): Fake(RIGHT[AS], (1,), asked=True), (AS, 2): Fake(RIGHT[AS], (2,), asked=True)},
                         reading="menu")),
                     claim.Line("folder", write_batch(root, "20261020T210100", "box", {
                         (AS, 1): Fake(RIGHT[AS], (1,), asked=True), (AS, 2): Fake(RIGHT[AS], (2,), asked=True)},
                         reading="buyable"))]
            m = claim.analyse(lines)["models"][HAIKU]
        self.assertEqual(m["tables"][claim.BLOCK][AS]["covered"], 1)
        self.assertEqual(m["tables"][claim.BUYABLE][AS]["covered"], 2)
        self.assertEqual(m["tables"][claim.BLOCK][AS]["asks"], 2)
        self.assertEqual(m["secondary"]["asks"][claim.BUYABLE]["ambiguous"], {"runs": 2, "asks": 2, "agent_asks": 0})


class ClosedByTheBox(unittest.TestCase):
    def test_a_slot_the_box_closed_is_a_run_that_answered_nothing(self):
        # Nothing but a void is excluded: a refusal stays in, not correct, nothing opened,
        # nothing spent, and the table says how many such slots there were.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            lines = [claim.Line("folder", write_batch(root, "20261020T210000", "box", {
                (TP, 1): Fake(RIGHT[TP], (1, 3, 4, 10, 11, 15), cost=0.3),
                (TP, 2): Fake("The shop does not show what the question needs.", closed="refused")},
                reading="menu"))]
            result = claim.analyse(lines)
        row = result["models"][HAIKU]["tables"][claim.BLOCK][TP]
        self.assertEqual((row["runs"], row["correct"], row["closed"], row["opened"], row["cost_total"]),
                         (2, 1, 1, [6, 0], 0.3))
        self.assertEqual(result["models"][HAIKU]["exclusions"]["voids"], [])
        self.assertEqual(result["problems"], [])


class LeaksAndDistinct(unittest.TestCase):
    def test_a_run_that_saw_a_hidden_price_is_left_out_of_that_sensitivity_only(self):
        # igr-clm-04's size M is sold out at $17.90, a price no page shows: a run whose log
        # holds it leaked, and only "without the runs that saw a hidden price" drops it.
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            lines = [claim.Line("folder", write_batch(root, "20261020T210000", "none", {
                         (TP, 1): Fake(WRONG[TP], extra_log="As low as $17.90"), (TP, 2): Fake(WRONG[TP])})),
                     claim.Line("folder", write_batch(root, "20261020T210100", "box", {
                         (TP, 1): Fake(RIGHT[TP]), (TP, 2): Fake(RIGHT[TP])}, reading="menu"))]
            m = claim.analyse(lines)["models"][HAIKU]
        self.assertEqual(m["tables"][claim.SHIPPED][TP]["leaks"], 1)
        self.assertEqual(m["primary"]["H1"]["per_question"][0]["b"], [0, 2])
        self.assertEqual(m["sensitivity"]["without the runs that saw a hidden price"]["H1"]["per_question"][0]["b"],
                         [0, 1])
        self.assertEqual(m["tables"][claim.BLOCK][TP]["leaks"], 0)

    def test_repeats_that_are_the_same_run_count_once_when_asked(self):
        runs = [{"task": TP, "tokens": (1, 2), "answer": "a"}, {"task": TP, "tokens": (1, 2), "answer": "a"},
                {"task": TP, "tokens": (1, 3), "answer": "a"}]
        self.assertEqual(len(compare_cells.distinct(runs)), 2)


# ---------------------------------------------------------------------------
# 7. The Thornwood development batches against cells 1 and 5, in-sample

IN_SAMPLE = ["20261007T112057", "20261008T034455", "20261008T143724", "20261008T144558",
             "20261014T213118", "20261014T222007"]
HAVE_LOGS = all(any((paths.RESULTS / name).glob("*.log")) for name in IN_SAMPLE)


@unittest.skipUnless(HAVE_LOGS, "the raw logs live on the laptop, not in git")
class InSampleThornwood(unittest.TestCase):
    """The development batches as the block (20261014T213118 under the menu reading,
    20261014T222007 under buyable), cell 1 as shipped and cell 5 as open everything
    (compare_cells.CELLS). In-sample, no claim (LESSONS 19): this checks the analysis, not
    the box. The verifier's audit found the block against cell 5 at p = 0.00025 on listings
    opened and p < 1e-5 on cost."""

    @classmethod
    def setUpClass(cls):
        cls.result = claim.analyse([claim.Line("folder", paths.RESULTS / name) for name in IN_SAMPLE])
        cls.m = cls.result["models"][HAIKU]

    def test_the_arms_are_the_cells(self):
        self.assertEqual({arm: a["batches"] for arm, a in self.m["arms"].items()}, {
            claim.SHIPPED: compare_cells.CELLS["1 openJiuwen, limit on"],
            claim.OPEN: compare_cells.CELLS["5 openJiuwen, open everything"],
            claim.BLOCK: ["20261014T213118"], claim.BUYABLE: ["20261014T222007"]})
        # The runs compare_cells counts for each cell: every gated run in its batches but the
        # ones silent for over 60 seconds, which test_claim_arms finds are exactly these three.
        suspended = {("20261008T034455", "apparel-count-buyable", 2), ("20261008T034455", "apparel-target-price", 1),
                     ("20261008T034455", "apparel-target-price", 2)}
        for arm in (claim.SHIPPED, claim.OPEN):
            with self.subTest(arm=arm):
                ours = {(r["batch"], r["task"], r["repeat"]) for r in self.m["runs"]
                        if r["arm"] == arm and r["task"] != claim.CONTROL}
                theirs = {(batch, *record.stem.rsplit("-", 1)) for batch in self.m["arms"][arm]["batches"]
                          for record in (paths.RESULTS / batch).glob("apparel-*.json")
                          if not record.stem.startswith(claim.CONTROL)}
                theirs = {(batch, task, int(repeat)) for batch, task, repeat in theirs} - suspended
                self.assertEqual(ours, theirs)
                self.assertEqual(len(ours), 15)

    def test_cell_5s_three_suspended_runs_are_left_out(self):
        self.assertEqual(sorted(f"{v['task']}-{v['repeat']}" for v in self.m["exclusions"]["voids"]),
                         ["apparel-count-buyable-2", "apparel-target-price-1", "apparel-target-price-2"])
        self.assertEqual([f"{x['task']}-{x['repeat']}" for x in self.m["exclusions"]["not_correct"]],
                         ["apparel-count-buyable-3"])
        # Cell 5's re-runs were numbered from 1 before --repeat-start, so count-buyable-2's
        # re-run sits beside the first batch's count-buyable-1: listed, both counted, as
        # compare_cells counts them, and repeat 2 shows as empty in the design.
        self.assertEqual(self.result["problems"], [
            "2 runs counted for open everything, anthropic/claude-haiku-4.5, apparel-count-buyable "
            "repeat 1: 20261008T034455, 20261008T144558"])
        self.assertIn("open everything, count-buyable repeat 2", self.m["exclusions"]["design"]["missing"])

    def test_the_audits_figures(self):
        primary = self.m["primary"]
        self.assertEqual(round(primary["H2"]["p"], 5), 0.00025)
        self.assertLess(primary["H3"]["p"], 1e-5)
        self.assertEqual(round(primary["H1"]["p"], 5), 0.022)
        self.assertEqual(primary["H1"]["pooled"], {"a": [10, 12], "b": [4, 12]})

    def test_the_figures_compare_cells_and_cell_facts_print(self):
        # cell_facts' development section: 13 of 15 correct, 14 covered, median 8 opened;
        # its "menu correct box vs 1, by question" over the five questions is p = 0.00155.
        pooled = self.m["tables"][claim.BLOCK]["pooled, gated"]
        self.assertEqual((pooled["correct"], pooled["covered"], pooled["opened_median"]), (13, 14, 8))
        self.assertEqual(round(self.m["sensitivity"]["count-stocked under the menu key"]["H1"]["p"], 5), 0.00155)
        shipped = self.m["tables"][claim.SHIPPED]["pooled, gated"]
        self.assertEqual((shipped["correct"], shipped["correct_buyable"], shipped["covered"]), (4, 5, 3))

    def test_count_stocked_by_arm_and_key_and_the_asks(self):
        # Cell 1 counted 2, 2 and 5; cell 5 counted 5 three times; the block counted 10 under
        # the menu reading and 5 under buyable, each after one user turn.
        table = self.m["secondary"]["count_stocked"]["table"]
        self.assertEqual({arm: (row["menu_key"], row["buyable_key"], row["user_turns"]) for arm, row in table.items()},
                         {claim.SHIPPED: (0, 1, 0), claim.OPEN: (0, 3, 0), claim.BLOCK: (3, 0, 3),
                          claim.BUYABLE: (0, 3, 3)})
        self.assertEqual(len(self.m["secondary"]["count_stocked"]["sheet"]), 12)
        asks = self.m["secondary"]["asks"]
        self.assertEqual({arm: (a["clear"]["asks"], a["clear"]["runs"], a["ambiguous"]["asks"], a["ambiguous"]["runs"])
                          for arm, a in asks.items()},
                         {claim.SHIPPED: (0, 12, 0, 6), claim.OPEN: (0, 9, 0, 6), claim.BLOCK: (0, 12, 6, 6),
                          claim.BUYABLE: (0, 0, 6, 6)})

    def test_the_answer_check_replayed(self):
        check = self.m["secondary"]["answer_check"]
        self.assertIsNone(check[claim.SHIPPED])
        self.assertEqual((check[claim.BLOCK]["wrong"], check[claim.BLOCK]["wrong_refused"]), (2, []))
        self.assertEqual(check[claim.BUYABLE]["correct_refused"],
                         ["20261014T222007/apparel-all-stocked-1: counterexample_not_opened"])


class QuestionSets(unittest.TestCase):
    """The question sets a protocol names (22 October 2026): the first claim's by default,
    and a file's under `--sets`, so the second claim's tee-* and water-* ids are named
    without a code change."""
    NAMES = ("CONTROL", "GATED", "QUESTIONS", "INVARIANT", "OFFER", "STOP_RULE", "COUNT_STOCKED", "DESIGN")
    SECOND = {"control": ["tee-headline"],
              "gated": ["tee-target-price", "tee-cheapest-target", "tee-all-stocked", "tee-count-stocked",
                        "water-target-price", "water-all-stocked", "water-best-per-litre"],
              "invariant": ["tee-target-price", "tee-cheapest-target", "water-target-price",
                            "water-best-per-litre"],
              "offer": ["tee-all-stocked", "tee-count-stocked", "water-all-stocked"],
              "stop_rule": ["tee-target-price", "water-target-price"],
              "count_stocked": "tee-count-stocked",
              "design": {claim.SHIPPED: ["tee-headline", "tee-target-price"], claim.BLOCK: ["water-target-price"]}}

    def setUp(self):
        saved = {name: getattr(claim, name) for name in self.NAMES}
        self.addCleanup(lambda: [setattr(claim, name, value) for name, value in saved.items()])

    def test_a_protocols_sets_are_the_ones_analysed(self):
        # Planted: `primary` reading its questions when the module was loaded, H1 kept the
        # first claim's four.
        claim.apply_sets(self.SECOND)
        self.assertEqual((claim.CONTROL, claim.QUESTIONS[:2], claim.OFFER, claim.COUNT_STOCKED),
                         ("tee-headline", ("tee-headline", "tee-target-price"),
                          ("tee-all-stocked", "tee-count-stocked", "water-all-stocked"), "tee-count-stocked"))
        tests = claim.primary({})
        self.assertEqual(tests["H1"]["questions"], self.SECOND["invariant"])
        self.assertEqual(tests["H2"]["questions"], self.SECOND["gated"])
        self.assertEqual(claim.DESIGN, {claim.SHIPPED: ("tee-headline", "tee-target-price"),
                                        claim.BLOCK: ("water-target-price",)})

    def test_the_first_claims_sets_as_a_file_change_nothing(self):
        first = {"control": [claim.CONTROL], "gated": list(claim.GATED), "invariant": list(claim.INVARIANT),
                 "offer": list(claim.OFFER), "stop_rule": list(claim.STOP_RULE),
                 "count_stocked": claim.COUNT_STOCKED,
                 "design": {arm: list(questions) for arm, questions in claim.DESIGN.items()}}
        before = {name: getattr(claim, name) for name in self.NAMES}
        claim.apply_sets(json.loads(json.dumps(first)))
        self.assertEqual({name: getattr(claim, name) for name in self.NAMES}, before)

    def test_sets_that_do_not_hold_together_are_refused_before_anything_is_read(self):
        for label, change, words in (
                ("a key missing", {"design": None}, "name no design"),
                ("an invariant question not gated", {"invariant": ["tee-headline"]}, "not gated"),
                ("count-stocked outside the offer set", {"count_stocked": "tee-target-price"}, "not in the offer set"),
                ("an arm the analysis has not", {"design": {"the block (model)": ["tee-headline"]}},
                 "an arm the analysis has not"),
                ("two controls", {"control": ["tee-headline", "water-target-price"]}, "2 control questions")):
            with self.subTest(fault=label):
                sets = {key: value for key, value in {**self.SECOND, **change}.items() if value is not None}
                with self.assertRaisesRegex(SystemExit, words):
                    claim.apply_sets(sets)
                self.assertEqual(claim.CONTROL, "apparel-headline")     # nothing was applied

    def test_a_task_file_may_hold_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "tasks_x.json"
            path.write_text(json.dumps({"tasks": [], "claim_sets": self.SECOND}))
            self.assertEqual(claim.read_sets(path), self.SECOND)
            path.write_text(json.dumps(self.SECOND))
            self.assertEqual(claim.read_sets(path), self.SECOND)


if __name__ == "__main__":
    unittest.main()
