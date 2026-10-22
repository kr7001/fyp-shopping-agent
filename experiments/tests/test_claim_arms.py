"""The claim run's arms and conditions, from the verifier's logic audit of the claim plan on
20 October 2026: the browser's profile kept in memory, strategy text v8, a strict "under",
the box without its stop rule (`--box-exhaust`), and repeat numbers that say which round a
run belongs to.

Every rule has a case where it must fire and one where it must stay quiet (LESSONS 24 and
31). Nothing here reaches a model: the suite runs in this process with its runner replaced
by one that writes a record and a log and returns.
"""
import base64
import contextlib
import dataclasses
import difflib
import hashlib
import io
import json
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import ambiguity  # noqa: E402
import box  # noqa: E402
import form as form_module  # noqa: E402
import leaks  # noqa: E402
import page as page_module  # noqa: E402
import primitives  # noqa: E402
import replay_box  # noqa: E402
import suite  # noqa: E402
import targeting  # noqa: E402
import verify_cells  # noqa: E402
import voids  # noqa: E402
from form import Filter  # noqa: E402
from test_box import BASE, FIXTURES, RESULTS_URL, clothing_questions, openjiuwen_log, synthetic_page  # noqa: E402

GO = f"Go to {RESULTS_URL} . "
SUITE = paths.EXPERIMENTS / "runners" / "suite.py"


def thornwood_page() -> page_module.Page:
    """The Thornwood results page as the box read it on 14 October 2026, from the committed
    record of that batch, so these tests need neither the shop nor its fixture."""
    payload = json.loads((paths.RESULTS / "20261014T213118" / "suite.json").read_text())
    return page_module.from_record(next(row["box"]["page"] for row in payload["rows"]
                                        if (row.get("box") or {}).get("page")))


def sentences(text: str | None) -> list[str]:
    """The sentences of a text, a step's number left out, in order."""
    found = []
    for line in (text or "").split("\n"):
        for part in re.split(r"(?<=[.?!:])\s+(?=[A-Z0-9\"'])", line.strip()):
            if part and not re.fullmatch(r"\d+\.", part):
                found.append(part)
    return found


@dataclasses.dataclass
class SuiteRun:
    code: int                       # main's return, or the exit code of a refusal
    out: str                        # what it printed, stdout then stderr
    batch: pathlib.Path | None      # the batch folder, None when nothing was written
    calls: int                      # how many runs the runner was started for
    owner: tempfile.TemporaryDirectory


def run_suite(*argv: str, page: page_module.Page | None = None,
              answer: str = "Rookwood Uniforms advertises the lowest price, $11.87.") -> SuiteRun:
    """`suite.main()` in this process with the agent replaced: each run's runner writes the
    record and the log a real one would, and nothing is sent anywhere. The results go to a
    temporary folder, kept alive by the returned `owner`. A refusal by the argument parser
    is returned as its exit code, with its message in `out`."""
    owner = tempfile.TemporaryDirectory()
    results = pathlib.Path(owner.name)
    calls = []

    def runner(command, cwd=None, env=None, stdout=None, stderr=None, check=False):
        calls.append(command)
        record = pathlib.Path(command[command.index("--out") + 1])
        record.write_text(json.dumps({"model": "fake/model", "elapsed_s": 1.0, "cost_usd": 0.0,
                                      "error": None, "result": {"ok": True, "final": answer}}))
        stdout.write("2026-10-20 12:00:00 | fake | default_trace_id | INFO | the run\n")
        return subprocess.CompletedProcess(command, 0)

    identity = {"agent_core_commit": "a" * 40, "agent_core_patch": "b" * 40}
    with mock.patch.object(sys, "argv", ["suite.py", *argv]), \
            mock.patch.object(suite, "RESULTS", results), \
            mock.patch.object(suite.subprocess, "run", runner), \
            mock.patch.object(suite, "agent_code_identity", return_value=identity), \
            mock.patch.object(suite, "results_page", lambda url: page), \
            contextlib.redirect_stdout(io.StringIO()) as out, \
            contextlib.redirect_stderr(io.StringIO()) as err:
        try:
            code = suite.main()
        except SystemExit as refused:
            code = refused.code
    batches = sorted(p for p in results.iterdir() if p.is_dir())
    return SuiteRun(code, out.getvalue() + err.getvalue(), batches[0] if batches else None,
                    len(calls), owner)


def dry_run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SUITE), *argv, "--dry-run"],
                          capture_output=True, text=True)


# ---------------------------------------------------------------------------
# 1. The browser profile in memory

class IsolatedProfile(unittest.TestCase):
    """Every openJiuwen run since 8 September 2026 shared one Playwright MCP profile on disk,
    PHPSESSID and history included, so a state one run left was there for the next. Since
    20 October the gated shop's browser keeps its profile in memory (`--isolated`)."""

    def test_the_gated_env_carries_the_three_flags(self):
        words = shlex.split(suite.browser_env("gated")["PLAYWRIGHT_MCP_ARGS"])
        for flag in ("--allowed-origins", "--block-service-workers", "--isolated"):
            with self.subTest(flag=flag):
                self.assertEqual(words.count(flag), 1)
        self.assertEqual(words[words.index("--allowed-origins") + 1], suite.ALLOWED_ORIGINS)
        flags = suite.browser_conditions("openjiuwen", "gated")["browser_flags"]
        self.assertEqual(flags.split(), ["--block-service-workers", "--isolated"])

    def test_the_default_shop_and_the_naive_scaffold_are_unchanged(self):
        self.assertNotIn("PLAYWRIGHT_MCP_ARGS", suite.browser_env("default"))
        for scaffold, shop in (("openjiuwen", "default"), ("naive", "gated"), ("naive", "default")):
            with self.subTest(scaffold=scaffold, shop=shop):
                self.assertEqual(suite.browser_conditions(scaffold, shop),
                                 {"browser_tool": None, "browser_origins": None, "browser_flags": None})
        # The second agent's command is what it was: its own browser, the user agent and
        # nothing of the MCP's.
        commands = []

        def runner(command, **kwargs):
            commands.append(command)
            return subprocess.CompletedProcess(command, 0)

        task = {"id": "t", "query": "q"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(suite.subprocess, "run", runner):
            suite.run_once(task, BASE, pathlib.Path(tmp), "t-1", query="q", scaffold="naive")
        self.assertEqual(commands[0][-2:], ["--user-agent", page_module.GATED_UA])
        self.assertFalse(any("--isolated" in word for word in commands[0]))

    def test_the_dry_run_header_says_so(self):
        run = dry_run("--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
                      "--only", "apparel-headline")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("browser: browser_tool=0.0.83 browser_origins=http://localhost:7770 "
                      "browser_flags=--block-service-workers --isolated\n", run.stdout)
        naive = dry_run("--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
                        "--only", "apparel-headline", "--scaffold", "naive")
        self.assertIn("browser: browser_tool=None browser_origins=None browser_flags=None\n",
                      naive.stdout)

    def test_the_payload_records_it(self):
        run = run_suite("--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
                        "--only", "apparel-headline")
        self.addCleanup(run.owner.cleanup)
        payload = json.loads((run.batch / "suite.json").read_text())
        self.assertEqual((run.code, payload["browser_flags"]), (0, "--block-service-workers --isolated"))


# ---------------------------------------------------------------------------
# 2. Strategy texts v8 and v9

# The rewordings are listed once, in `box.REWORDED`, which `replay_box` reads too. Five of
# them are in the six clothing texts v1 rendered: four from the audit (v8) and the fifth from
# what the leak counter found (v9).
IN_THE_V1_TEXTS = 5
# The sha1 of the 18 queries in fixtures/v1_clothing_queries.json as frozen at 34c0356 from
# the v1 code, json.dumps(queries, sort_keys=True), read before the amendment.
V1_QUERIES_SHA1 = "d539dc80468c3331d63f68d308799125eb498b19"


def every_text() -> list[str]:
    """Every text the box sends, from both clothing task files under each reading and under
    each arm, on the Thornwood page, the frozen strategy table the targeting arm sends, and
    the dearest's text, which no task file asks for."""
    page = thornwood_page()
    texts = list(targeting.STRATEGIES.values())
    for name in ("tasks_apparel.json", "tasks_apparel_v2.json"):
        spec = json.loads((paths.TASKS / name).read_text())
        for task in spec["tasks"]:
            query = task["query"].format(base=spec["base_url"])
            for reading in (None, "menu", "buyable"):
                for exhaust in (False, True):
                    decision = box.decide(query, page if box.results_url(query, required=False) else None,
                                          reply=reading, exhaust=exhaust)
                    texts.append(decision.query or decision.refuse or decision.ask.text)
    texts.append(primitives.argmax_text(form_module.from_rules(GO + "Which seller is the most expensive "
                                                                    "for size M?"), synthetic_page([12.0])))
    return texts


class StrategyTextV8(unittest.TestCase):
    """The five sentences v8 and v9 reword were false of the gated shop: igr-app-07
    advertises $18.33 with M sold out at $15.04, Thornwood's cheapest M, igr-app-14 at
    $25.77, is that listing's own card price, and a script can force a sold-out size the
    menu refuses (20261007T115021/apparel-target-price-1)."""

    def test_the_versions(self):
        # Box 13, form 10 and primitives 9 since 22 October 2026, the model's front door
        # (test_model_parser.py). The strategy texts are v9 still, and every rules-path text
        # with them.
        self.assertEqual((targeting.VERSION, box.VERSION, form_module.VERSION, primitives.VERSION),
                         (9, 13, 10, 9))

    def test_no_text_the_box_sends_holds_an_old_wording(self):
        texts = every_text()
        self.assertEqual(len(box.REWORDED), 8)
        for since, old, new in box.REWORDED:
            with self.subTest(sentence=old[:50]):
                self.assertFalse(any(old in text for text in texts))
                self.assertTrue(any(new in text for text in texts))

    def test_the_quarantine_and_the_stop_sentences_read_v8(self):
        self.assertIn(box.REWORDED[2][2], targeting.QUARANTINE)
        self.assertIn(box.REWORDED[3][2], targeting.BODIES["refutation"])
        exists = primitives.witness_text(form_module.from_rules(GO + "Is there any seller under $20 for size M?"))
        self.assertIn("Stopping after one opening, when that listing meets the condition, is the "
                      "correct outcome here", exists)

    def test_a_text_is_put_back_in_the_words_of_the_version_that_sent_it(self):
        text = targeting.BODIES["availability_bound"]
        v6, v10 = box.as_sent_by(text, 6), box.as_sent_by(text, 10)
        self.assertIn(box.REWORDED[0][1], v6)
        self.assertNotIn(box.REWORDED[0][2], v6)
        # A box v10 run already had v10's words, and only v11's are put back.
        self.assertIn(box.REWORDED[0][2], v10)
        self.assertIn("cannot be chosen, so it has no price", v10)
        self.assertEqual(box.as_sent_by(text, box.VERSION), text)
        self.assertIsNone(box.as_sent_by(None, 6))


class V1Amendment(unittest.TestCase):
    """The fixture `test_box.V1Bytes` pins was amended on 20 October 2026 for v8 and v9, and
    in five sentences only: putting them back in v1's words gives back the queries v1
    rendered, to the byte, by the same list `replay_box` reads (`box.REWORDED`)."""

    def setUp(self):
        self.frozen = json.loads((FIXTURES / "v1_clothing_queries.json").read_text())

    def test_the_v1_words_give_the_v1_queries(self):
        undone = [{**row, "query": box.as_sent_by(row["query"], 1)} for row in self.frozen["queries"]]
        digest = hashlib.sha1(json.dumps(undone, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, V1_QUERIES_SHA1)
        # The amended fixture is not the v1 one, so the check above is not vacuous.
        self.assertNotEqual(hashlib.sha1(json.dumps(self.frozen["queries"], sort_keys=True).encode())
                            .hexdigest(), V1_QUERIES_SHA1)

    def test_each_rewording_of_the_v1_texts_is_in_the_fixture_and_dated(self):
        queries = [row["query"] or "" for row in self.frozen["queries"]]
        found = [new for _, old, new in box.REWORDED if any(new in q for q in queries)]
        self.assertEqual(len(found), IN_THE_V1_TEXTS)
        for since, old, new in box.REWORDED:
            with self.subTest(sentence=old[:50]):
                self.assertFalse(any(old in q for q in queries))
        about = " ".join(self.frozen["_about"])
        self.assertIn("box.VERSION 1", about)          # the v1 provenance is kept
        self.assertIn("Amended on 20 October 2026 for strategy texts v8 and v9", about)


def replayed(folder: str, task_id: str, record: dict, tasks_file: str = "tasks_apparel_v2.json",
             reading: str | None = None) -> dict:
    """One stored run, its record as the suite writes it, replayed by `replay_box` from a
    batch folder of its own."""
    batch = pathlib.Path(folder) / f"20261020T1200{len(list(pathlib.Path(folder).iterdir())):02d}"
    batch.mkdir()
    tag = f"{task_id}-1"
    (batch / f"{tag}.json").write_text(json.dumps({"result": {"final": "No.", "ok": True}}))
    openjiuwen_log(str(batch), tag, [])
    row = {"task": task_id, "repeat": 1, "verdict": "correct", "log": f"{tag}.log", "box": record,
           "reading": reading}
    (batch / "suite.json").write_text(json.dumps({"tasks_file": tasks_file, "reading": reading,
                                                  "rows": [row]}))
    return replay_box.replay(batch)[0]


class ReplayUnderTheVersionThatRan(unittest.TestCase):
    """`replay_box` recomposes a stored plan from its form with today's code and compares it
    in the words of the box version that ran, with the run's own box-exhaust flag; today's
    decision is the same, an expected difference for a named deliberate change shown to be
    the whole difference, or unexpected (20 October 2026)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.page = thornwood_page()
        self.v2 = json.loads((paths.TASKS / "tasks_apparel_v2.json").read_text())
        self.tasks = {t["id"]: t for t in self.v2["tasks"]}

    def exhaust_record(self, task_id: str) -> dict:
        """The record a dry run of --box-exhaust --reading menu writes for one task."""
        args = mock.Mock(box=False, box_exhaust=True, reading="menu", targeting=False, exhaustive=False,
                         confidence="off")
        with mock.patch.object(suite, "results_page", lambda url: self.page):
            query, applied = suite.build_query(self.tasks[task_id], self.v2, args)
        self.assertIn(primitives.OPEN_EVERY, query)
        return applied["box"]

    def test_a_box_exhaust_run_replays_with_its_flag(self):
        record = self.exhaust_record("apparel-cheapest-target")
        row = replayed(self.tmp.name, "apparel-cheapest-target", record, reading="menu")
        self.assertEqual((row["text_reproduced"], row["today"]), (True, "same"))
        # Without the flag the plan is the box's, with its stop rule, so it is not the text
        # the run was sent, and today's decision differs unexpectedly.
        flagless = {**record, "exhaust": False, "plan": {**record["plan"], "exhaust": False}}
        row = replayed(self.tmp.name, "apparel-cheapest-target", flagless, reading="menu")
        self.assertFalse(row["text_reproduced"])
        self.assertIn("Skip every unopened listing", row["differs"])
        self.assertEqual(row["today"], "unexpected")

    def v6_record(self, task_id: str) -> dict:
        """A record as box v6 wrote it on 14 October 2026: its form read "under" as "<=", and
        its text was that form's plan in the words box v6 sent."""
        question = self.tasks[task_id]["query"].format(base=self.v2["base_url"])
        record = box.decide(question, self.page).record()
        old = form_module.from_record(record["form"], "rules")
        old = dataclasses.replace(old, filters=tuple(
            dataclasses.replace(f, op="<=") if f.attribute == "price" else f for f in old.filters))
        plan = primitives.compose(old, self.page)
        return {**record, "box_version": 6, "form": old.record(),
                "query": box.as_sent_by(f"{question}\n\n{plan.text}", 6)}

    def test_a_strict_limit_is_the_expected_difference_and_the_whole_of_it(self):
        record = self.v6_record("apparel-exists-under-27")
        self.assertIn("at or below $27.00", record["query"])
        self.assertIn(box.REWORDED[2][1], record["query"])          # v6's quarantine wording
        row = replayed(self.tmp.name, "apparel-exists-under-27", record)
        self.assertEqual((row["text_reproduced"], row["today"], row["change"]),
                         (True, "expected", "the limit is strict since form v9 (price < 27)"))
        # A sentence of the stored text changed besides the operator: neither reproduced nor
        # expected, and the line where it first differs is named.
        tampered = {**record, "query": record["query"].replace("Do not open any others to confirm.",
                                                               "Open one more to confirm.")}
        row = replayed(self.tmp.name, "apparel-exists-under-27", tampered)
        self.assertFalse(row["text_reproduced"])
        self.assertIn("Open one more to confirm.", row["differs"])
        self.assertEqual(row["today"], "unexpected")

    def test_a_question_refused_today_is_an_expected_difference(self):
        question = self.tasks["apparel-softest"]["query"].format(base=self.v2["base_url"])
        today = box.decide(question, self.page)
        self.assertTrue(today.refuse)
        status, change = replay_box.compared_today(today, {"query": "the fallback's plan", "refuse": None,
                                                           "box_version": 6})
        self.assertEqual(status, "expected")
        self.assertIn("refused today: The shop does not show what 'softest' ranks by", change)

    def test_the_first_difference(self):
        self.assertEqual(replay_box.first_difference("a\nb\nc", "a\nB\nc"), "line 2: stored 'b', today 'B'")
        self.assertEqual(replay_box.first_difference("a", "a\nb"), "stored 1 lines, today 2")


# ---------------------------------------------------------------------------
# 3. A strict "under"

class StrictUnder(unittest.TestCase):
    """"under $27" is below $27, as verify_cells' floor and the generator's witnesses read
    it; "at most $27" includes $27. Every reader of the operator agrees: the form, the
    witness text and stop rule, the witness check's floor, the filter's sentence and check,
    `box.stated_figures` and the threshold ask's example."""

    STRICT = ("under $27", "below $27", "less than $27", "cheaper than $27")
    INCLUSIVE = ("at most $27", "no more than $27", "not more than $27", "up to $27", "within $27",
                 "$27 or less", "$27 or under", "$27 or below", "$27 or cheaper")

    def limit(self, words: str) -> Filter:
        return form_module.from_rules(GO + f"Is there any seller with size M {words}?").filter("price")

    def test_the_form_reads_each_word(self):
        for words in self.STRICT:
            with self.subTest(words=words):
                self.assertEqual(self.limit(words), Filter("price", "<", 27.0))
        for words in self.INCLUSIVE:
            with self.subTest(words=words):
                self.assertEqual(self.limit(words), Filter("price", "<=", 27.0))

    def test_the_witness_text_and_stop_rule_follow_the_operator(self):
        page = synthetic_page([10.15, 27.00, 30.00])
        strict = primitives.compose(form_module.from_rules(GO + "Is there any seller under $27 for size M?"), page)
        inclusive = primitives.compose(form_module.from_rules(GO + "Is there any seller at most $27 for size M?"), page)
        for needle in ("the price you read is below $27.00", "advertised price is at or above $27.00",
                       "every listing advertised below $27.00"):
            with self.subTest(needle=needle):
                self.assertIn(needle, strict.instruction)
                self.assertNotIn(needle, inclusive.instruction)
        for needle in ("the price you read is at or below $27.00", "advertised price is above $27.00",
                       "every listing advertised at or below $27.00"):
            with self.subTest(needle=needle):
                self.assertIn(needle, inclusive.instruction)
                self.assertNotIn(needle, strict.instruction)
        self.assertIn("available below the limit", strict.stop_rule)
        # A limit that includes its figure renders the words the stop rule always held.
        self.assertEqual(inclusive.stop_rule,
                         "at the first listing whose option is available at or below the limit, "
                         "or when every listing advertised at or below the limit has been opened")
        self.assertNotIn("{within}", strict.stop_rule + inclusive.stop_rule)

    def test_the_witness_floor_at_the_limit(self):
        # A listing advertised at exactly $27.00 cannot sell below it, so under "under $27"
        # a No owes Seller A only; under "at most $27" it owes Seller B too.
        page = synthetic_page([10.15, 27.00, 30.00])
        only_a = f"Page URL: {page.listings[0].url}\nPrice: $28.00"
        no = "No. None of the sellers has size M within the limit."
        strict = primitives.check(form_module.from_rules(GO + "Is there any seller under $27 for size M?", page),
                                  page, no, only_a)
        inclusive = primitives.check(form_module.from_rules(GO + "Is there any seller at most $27 for size M?", page),
                                     page, no, only_a)
        self.assertEqual((strict["ok"], inclusive["ok"]), (True, False))
        self.assertEqual(inclusive["flag"], "existence_denied_without_coverage")
        self.assertIn("of the 2 listings", inclusive["why"])

    def test_the_filter_check_at_the_limit(self):
        page = synthetic_page([10.15, 27.00, 30.00])
        opened = f"Page URL: {page.listings[1].url}\nPrice: $27.00"
        yes = "Yes. Seller B has size M at $27.00."
        strict = primitives.check(form_module.from_rules(GO + "Is there any seller under $27 for size M?", page),
                                  page, yes, opened)
        inclusive = primitives.check(form_module.from_rules(GO + "Is there any seller at most $27 for size M?", page),
                                     page, yes, opened)
        self.assertEqual((strict["ok"], strict["flag"]), (False, "answer_above_limit"))
        self.assertIn("allows less than $27.00", strict["why"])
        self.assertTrue(inclusive["ok"])
        # One cent under the limit meets the strict one.
        self.assertTrue(primitives.check(form_module.from_rules(GO + "Is there any seller under $27 for size M?", page),
                                         page, "Yes. Seller B has size M at $26.99.", opened)["ok"])

    def test_the_figure_is_the_questions_own_either_way(self):
        page = synthetic_page([10.15, 27.00, 30.00])
        for words in ("under $27", "at most $27"):
            with self.subTest(words=words):
                decision = box.decide(GO + f"Is there any seller {words} for size M?", page)
                self.assertEqual(box.stated_figures(decision), {2700})

    def test_the_threshold_ask_says_below(self):
        asked = ambiguity.threshold_ask("cheap")
        self.assertIn("such as under $20, and only listings below it will count", asked.text)
        self.assertNotIn("at or below", asked.text)

    # The seven task files of the audit, 58 questions, and the claim market's, written after
    # it by a generator that already read "under" strictly (335dda6).
    AUDITED = ("tasks.json", "tasks_apparel.json", "tasks_apparel_v2.json", "tasks_heldout.json",
               "tasks_heldout_gated.json", "tasks_reviews.json", "tasks_scaled.json")

    def strict_questions(self, name: str) -> tuple[int, list[str]]:
        """How many questions a task file holds, and those whose limit is strict. Beside
        it, form v8's pattern: the same figure is read from the same words everywhere."""
        v8 = re.compile(r"\b(?:under|below|less than|at most|no more than|not more than|cheaper "
                        r"than|up to|within)\s*\$?\s*(?P<a>\d+(?:\.\d{1,2})?)\b"
                        r"|\$?(?P<b>\d+(?:\.\d{1,2})?)\s+or\s+(?:less|under|below|cheaper)\b",
                        re.IGNORECASE)
        spec = json.loads((paths.TASKS / name).read_text())
        strict = []
        for task in spec["tasks"]:
            query = task["query"].format(base=spec.get("base_url", BASE))
            old, new = v8.search(query), form_module.CEILING.search(query)
            self.assertEqual(bool(old), bool(new), task["id"])
            if new:
                self.assertEqual(old.span(), new.span(), task["id"])
            limit = form_module.from_rules(query).filter("price")
            if limit is not None and limit.op == "<":
                strict.append(task["id"])
        return len(spec["tasks"]), strict

    def test_only_the_two_under_questions_change_their_form(self):
        # The operator changes only where the words are strict: of the audit's 58 forms,
        # the two "under $" questions on Thornwood.
        counted = [self.strict_questions(name) for name in self.AUDITED]
        self.assertEqual(sum(n for n, _ in counted), 58)
        self.assertEqual(sorted(task for _, strict in counted for task in strict),
                         ["apparel-exists-under-25", "apparel-exists-under-27"])
        # On the claim market the two existence questions, whose keys its generator
        # computed with a strict limit, read the same way.
        self.assertEqual(sorted(self.strict_questions("tasks_claim_apparel.json")[1]),
                         ["apparel-exists-under-23", "apparel-exists-under-24"])
        self.assertEqual(sorted(p.name for p in paths.TASKS.glob("tasks*.json")),
                         sorted(self.AUDITED + ("tasks_claim_apparel.json",)))


# ---------------------------------------------------------------------------
# 4. The box without its stop rule

# The quarantine's first sentence, which says what the bound decides, and the one the box
# without its stop rule sends in its place (20 October 2026).
QUARANTINE_LEAD = "Important: the figure this bound produces is a limit used only to decide what to skip."
EXHAUST_LEAD = ("Important: the advertised price is the price of the cheapest option that can be bought, "
                "which need not be the option asked about.")
# Every sentence --box-exhaust may take out of the --box text, and every one it may put in,
# by kind, on the questions of both clothing task files under each reading. Any other
# difference fails `test_only_the_stop_sentences_differ`. The count questions, the
# results-page control, the asks, the refusals and the bypasses differ in nothing.
EXHAUST_DIFFERENCES = {
    "availability_bound": (
        {"Skip every unopened listing whose advertised price is at or above your best available total.",
         "Such a listing cannot win whatever its stock.",
         "Stop when no unopened listing has an advertised price below your best available total.",
         "Say how many listings you opened, how many you skipped, and how many you rejected for being "
         "unavailable.",
         QUARANTINE_LEAD},
        {"Open every listing on the page before answering.",
         "Say how many listings you opened, and how many you rejected for being unavailable.",
         EXHAUST_LEAD}),
    "refutation": (
        {"Nothing more.", "So hunt for a counterexample rather than surveying:",
         "Open a listing and check for the option asked about.",
         "If it lacks the option, you are finished.",
         "Answer No, name that listing as your evidence, and stop immediately.",
         "Do not open any others to confirm, and do not continue in order to be thorough.",
         "Opening more cannot change the answer.",
         "Stopping after one or two openings, once a counterexample is found, is the correct outcome here, "
         "not a sign that you did too little.",
         "Note that the previous version of this instruction was followed to the letter and not to its point: "
         "the agent enumerated and then opened ten listings when the first counterexample had already settled "
         "the question."},
        {"Open every listing on the page before answering, and check each for the option asked about.",
         "If one lacks the option, answer No and name that listing as your evidence."}),
    "exists_price": (
        {"Name it and stop.", "Nothing is gained by finding a second.",
         "If the option is available and the price you read is below {limit}, you are finished.",
         "Answer yes, name that listing and the price you read, and stop immediately.",
         "Do not open any others to confirm.",
         "Skip every unopened listing whose advertised price is at or above {limit}.",
         "Nothing it can sell costs less than its advertised price, so it cannot meet the condition.",
         "Stopping after one opening, when that listing meets the condition, is the correct outcome here, "
         "not a sign that you did too little.",
         QUARANTINE_LEAD},
        {"If the option is available and the price you read is below {limit}, answer yes and name that "
         "listing and the price you read.",
         "Open every listing on the page before answering.",
         EXHAUST_LEAD}),
    "topk_price": (
        {"Once you hold 3, skip every unopened listing whose advertised price is at or above the dearest of "
         "those 3 totals.",
         "Such a listing cannot enter the 3 whatever its stock.",
         "Stop when you hold 3 and no unopened listing has an advertised price below the dearest of them.",
         "If fewer than 3 listings have the option available, you must open every listing, and then say so "
         "and name those that do.",
         "In your answer, list the 3 sellers in order with the price of each, say explicitly that you checked "
         "each option was available rather than only listed, and say how many listings you opened, how many "
         "you skipped, and why skipping them was safe.",
         QUARANTINE_LEAD},
        {"Open every listing on the page before answering.",
         "If fewer than 3 listings have the option available, say so and name those that do.",
         "In your answer, list the 3 sellers in order with the price of each, say explicitly that you checked "
         "each option was available rather than only listed, and say how many listings you opened.",
         EXHAUST_LEAD}),
    "named_lookup": (
        {"Open each of them and nothing else:",
         "Do not skip any of them: the question is about exactly these, so each has to be read, and opening "
         "others cannot change the answer."},
        {"Open every listing on the page before answering, these among them:",
         "Do not skip any of them: the question is about exactly these, so each has to be read."}),
}
# The questions whose plan already opens every listing, so both arms send the same bytes.
ALREADY_EXHAUST = ("apparel-count-stocked", "apparel-count-buyable")


def both_arms():
    """(task id, reading, the --box decision, the --box-exhaust decision) for every question
    of both clothing task files under each reading, on the Thornwood page."""
    page = thornwood_page()
    for name in ("tasks_apparel.json", "tasks_apparel_v2.json"):
        spec = json.loads((paths.TASKS / name).read_text())
        for task in spec["tasks"]:
            query = task["query"].format(base=spec["base_url"])
            seen = page if box.results_url(query, required=False) else None
            for reading in (None, "menu", "buyable"):
                yield (task["id"], reading, box.decide(query, seen, reply=reading),
                       box.decide(query, seen, reply=reading, exhaust=True))


class BoxExhaust(unittest.TestCase):

    def test_only_the_stop_sentences_differ(self):
        kinds = set()
        for task_id, reading, plain, exhaust in both_arms():
            with self.subTest(task=task_id, reading=reading):
                record, other = plain.record(), exhaust.record()
                self.assertEqual((record["exhaust"], other["exhaust"]), (False, True))
                self.assertEqual({k: v for k, v in record.items() if k not in ("exhaust", "query", "plan")},
                                 {k: v for k, v in other.items() if k not in ("exhaust", "query", "plan")})
                if plain.kind not in EXHAUST_DIFFERENCES:
                    self.assertEqual(exhaust.query, plain.query)
                    continue
                kinds.add(plain.kind)
                diff = list(difflib.ndiff(sentences(plain.query), sentences(exhaust.query)))
                removed = {d[2:] for d in diff if d.startswith("- ")}
                added = {d[2:] for d in diff if d.startswith("+ ")}
                limit = primitives.limit_of(plain.form)
                fill = {"limit": f"${limit.value:.2f}" if limit else ""}
                want_removed, want_added = EXHAUST_DIFFERENCES[plain.kind]
                self.assertEqual(removed, {s.format(**fill) for s in want_removed})
                self.assertEqual(added, {s.format(**fill) for s in want_added})
                self.assertEqual((exhaust.plan.stop_rule, exhaust.plan.exhaust),
                                 (primitives.EXHAUST_STOP, True))
        self.assertEqual(kinds, set(EXHAUST_DIFFERENCES))

    def test_the_count_questions_are_byte_identical(self):
        for task_id, reading, plain, exhaust in both_arms():
            if task_id in ALREADY_EXHAUST and plain.query is not None:
                with self.subTest(task=task_id, reading=reading):
                    self.assertEqual(plain.kind, "survey")
                    self.assertEqual(exhaust.query, plain.query)
                    self.assertEqual(exhaust.plan.stop_rule, plain.plan.stop_rule)

    def test_no_stop_sentence_survives_and_every_gated_plan_opens_everything(self):
        stops = ("skip every", "Stop when", "stop immediately", "Name it and stop", "nothing else",
                 "Stopping after", "cannot change the answer", "Do not open any others",
                 "rather than surveying", "decide what to skip")
        for task_id, reading, plain, exhaust in both_arms():
            if plain.plan is None or plain.kind == "results_page":
                continue
            with self.subTest(task=task_id, reading=reading):
                self.assertIn("pen every listing", exhaust.plan.instruction)
                for stop in stops:
                    self.assertNotIn(stop.lower(), exhaust.plan.instruction.lower())

    def test_a_stop_sentence_not_found_is_refused(self):
        with self.assertRaises(ValueError) as refused:
            primitives.without_stop_rule("Read the page.", [("Stop when done.", "")])
        self.assertIn("0 times, not once", str(refused.exception))
        self.assertEqual(primitives.without_stop_rule("Read. Stop when done.", [(" Stop when done.", "")]),
                         "Read.")

    def test_a_review_question_has_no_listing_stop_rule_to_replace(self):
        reviews = form_module.from_rules(f"Go to {BASE}/review/product/list/id/230/ . Do any buyers report "
                                         "that this product leaks? Answer yes or no.")
        page = synthetic_page([12.0])
        self.assertEqual(primitives.compose(reviews, page).primitive, "depth")
        with self.assertRaises(ValueError):
            primitives.compose(reviews, page, exhaust=True)

    def test_the_check_is_the_boxs_in_both_arms(self):
        page = thornwood_page()
        question = clothing_questions()["apparel-cheapest-target"]
        answer = "Alderney Clothing Co is cheapest for size M at $25.77."
        with tempfile.TemporaryDirectory() as tmp:
            log = openjiuwen_log(tmp, "run", [item.url for item in page.by_price()[:8]], "Price: $25.77")
            plain = box.check(box.decide(question, page), answer, log)
            exhaust = box.check(box.decide(question, page, exhaust=True), answer, log)
        self.assertEqual(plain, exhaust)

    def test_the_flags_it_excludes(self):
        tasks = ("--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
                 "--only", "apparel-headline")
        for other in (("--box",), ("--exhaustive",), ("--targeting",)):
            with self.subTest(other=other):
                run = dry_run(*tasks, "--box-exhaust", *other)
                self.assertEqual(run.returncode, 2)
                self.assertIn("--box-exhaust cannot be combined with --box, --targeting or --exhaustive",
                              run.stderr)
        naive = dry_run(*tasks, "--box-exhaust", "--scaffold", "naive")
        self.assertEqual(naive.returncode, 2)
        self.assertIn("the second agent's browser is not confined", naive.stderr)
        retry = dry_run(*tasks, "--box-exhaust", "--policy", "retry")
        self.assertEqual(retry.returncode, 2)
        alone = dry_run(*tasks, "--reading", "menu")
        self.assertEqual(alone.returncode, 2)
        self.assertIn("needs --box or --box-exhaust", alone.stderr)

    def test_the_payload_and_the_rows_record_the_arm(self):
        page = thornwood_page()
        tasks = ("--tasks", str(paths.TASKS / "tasks_apparel.json"), "--repeats", "1",
                 "--only", "apparel-cheapest-target", "apparel-headline")
        run = run_suite(*tasks, "--box-exhaust", page=page)
        self.addCleanup(run.owner.cleanup)
        self.assertEqual(run.code, 0)
        payload = json.loads((run.batch / "suite.json").read_text())
        self.assertEqual((payload["arm"], payload["box_exhaust"], payload["box"]), ("box-exhaust", True, False))
        self.assertEqual((payload["box_version"], payload["form_version"], payload["primitives_version"],
                          payload["targeting_version"]),
                         (box.VERSION, form_module.VERSION, primitives.VERSION, targeting.VERSION))
        rows = {row["task"]: row for row in payload["rows"]}
        gated = rows["apparel-cheapest-target"]["box"]
        self.assertEqual((gated["exhaust"], gated["plan"]["exhaust"], gated["plan"]["stop_rule"]),
                         (True, True, primitives.EXHAUST_STOP))
        self.assertIn(primitives.OPEN_EVERY, gated["query"])
        self.assertTrue(rows["apparel-headline"]["box"]["exhaust"])
        self.assertIn("arm: box-exhaust\n", run.out)
        # The box itself, and no box at all, record their own arms.
        run = run_suite(*tasks, "--box", page=page)
        self.addCleanup(run.owner.cleanup)
        payload = json.loads((run.batch / "suite.json").read_text())
        self.assertEqual((payload["arm"], payload["box_exhaust"], payload["box"]), ("box", False, True))
        self.assertFalse(payload["rows"][0]["box"]["exhaust"])
        run = run_suite(*tasks)
        self.addCleanup(run.owner.cleanup)
        payload = json.loads((run.batch / "suite.json").read_text())
        self.assertEqual((payload["arm"], payload["box_version"]), ("none", None))
        self.assertEqual(suite.arm_of(mock.Mock(box=False, box_exhaust=False, targeting=True, exhaustive=True)),
                         "targeting+exhaustive")


# ---------------------------------------------------------------------------
# 5. Repeat numbers that start where the round does

class RepeatStart(unittest.TestCase):
    TASKS = ("--tasks", str(paths.TASKS / "tasks_apparel.json"), "--only", "apparel-headline")

    def runs(self, batch: pathlib.Path) -> list[str]:
        return sorted(p.stem for p in batch.glob("apparel-headline-*.json"))

    def test_the_records_and_rows_carry_the_given_repeats(self):
        run = run_suite(*self.TASKS, "--repeats", "2", "--repeat-start", "3")
        self.addCleanup(run.owner.cleanup)
        batch = run.batch
        self.assertEqual((run.code, run.calls), (0, 2))
        self.assertEqual(self.runs(batch), ["apparel-headline-3", "apparel-headline-4"])
        payload = json.loads((batch / "suite.json").read_text())
        self.assertEqual([row["repeat"] for row in payload["rows"]], [3, 4])
        self.assertEqual([row["log"] for row in payload["rows"]],
                         ["apparel-headline-3.log", "apparel-headline-4.log"])
        self.assertEqual((payload["repeats"], payload["repeat_start"]), (2, 3))
        for repeat in (3, 4):
            record = json.loads((batch / f"apparel-headline-{repeat}.json").read_text())
            self.assertEqual(record["log"], f"apparel-headline-{repeat}.log")
            self.assertTrue((batch / f"apparel-headline-{repeat}.log").exists())
        self.assertIn("1 tasks x 2 repeats = 2 runs, repeats 3 to 4 -> ", run.out)

    def test_the_default_is_unchanged(self):
        run = run_suite(*self.TASKS, "--repeats", "2")
        self.addCleanup(run.owner.cleanup)
        self.assertEqual(self.runs(run.batch), ["apparel-headline-1", "apparel-headline-2"])
        payload = json.loads((run.batch / "suite.json").read_text())
        self.assertEqual([row["repeat"] for row in payload["rows"]], [1, 2])
        self.assertEqual(payload["repeat_start"], 1)
        self.assertIn("1 tasks x 2 repeats = 2 runs -> ", run.out)
        self.assertNotIn("repeats 1 to", run.out)

    def test_a_round_of_one_with_the_box(self):
        # The claim's rounds: --repeats 1 per arm, the round's number as the repeat, and an
        # ask closed by the box carries it too.
        page = thornwood_page()
        run = run_suite("--tasks", str(paths.TASKS / "tasks_apparel.json"),
                        "--only", "apparel-headline", "apparel-all-stocked",
                        "--repeats", "1", "--repeat-start", "2", "--box", page=page)
        self.addCleanup(run.owner.cleanup)
        payload = json.loads((run.batch / "suite.json").read_text())
        self.assertEqual({(row["task"], row["repeat"], row["verdict"] == "asked") for row in payload["rows"]},
                         {("apparel-headline", 2, False), ("apparel-all-stocked", 2, True)})

    def test_a_start_below_one_is_refused(self):
        run = dry_run(*self.TASKS, "--repeats", "1", "--repeat-start", "0")
        self.assertEqual(run.returncode, 2)
        self.assertIn("--repeat-start numbers the first repeat", run.stderr)


# ---------------------------------------------------------------------------
# 6. A key for every reading a run is scored under, found before anything runs

class ScoringKeyPreflight(unittest.TestCase):
    """Since 335dda6 `score.under_reading` raises for a question with two readings answered
    under one its sidecar has no key for, and the suite scores each run right after it. So
    every task is resolved under the reading its runs would be scored under before the
    first run, and in the dry run, and a missing key refuses the batch with nothing spent."""

    BEST_PRICE = {"id": "apparel-best-price", "family": "apparel", "gated": True,
                  "query": "Go to {base}/catalogsearch/result/?q=Thornwood . Which Thornwood seller has "
                           "the best price for size M?",
                  "expect": {"kind": "contains", "any": ["Alderney"], "not_any": [], "price": 25.77}}

    def task_file(self, folder: str, extra: tuple = (), buyable: dict | None = None) -> pathlib.Path:
        """A copy of two Thornwood questions, the control and the ambiguous "every listing
        offer size M", with any extra tasks, and a readings sidecar only when `buyable`."""
        spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        spec["tasks"] = [t for t in spec["tasks"] if t["id"] in ("apparel-headline", "apparel-all-stocked")]
        spec["tasks"] += list(extra)
        path = pathlib.Path(folder) / "tasks_preflight.json"
        path.write_text(json.dumps(spec))
        if buyable is not None:
            (pathlib.Path(folder) / "readings_preflight.json").write_text(
                json.dumps({"readings": {"buyable": buyable}}))
        return path

    def batch(self, tasks: pathlib.Path, *flags: str) -> SuiteRun:
        run = run_suite("--tasks", str(tasks), "--repeats", "1", *flags, page=thornwood_page())
        self.addCleanup(run.owner.cleanup)
        return run

    def test_a_missing_buyable_key_is_refused_before_anything_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            tasks = self.task_file(folder)
            for dry in ((), ("--dry-run",)):
                with self.subTest(dry=bool(dry)):
                    run = self.batch(tasks, "--box", "--reading", "buyable", *dry)
                    self.assertEqual((run.code, run.calls, run.batch), (2, 0, None))
                    self.assertIn("tasks_preflight.json has no answer key for the reading", run.out)
                    self.assertIn("apparel-all-stocked under the buyable reading", run.out)
                    self.assertNotIn("apparel-headline under", run.out)

    def test_the_same_file_passes_under_the_menu_reading_and_with_its_key(self):
        with tempfile.TemporaryDirectory() as folder:
            tasks = self.task_file(folder)
            menu = self.batch(tasks, "--box", "--reading", "menu")
            self.assertEqual((menu.code, menu.calls), (0, 2))
            self.assertEqual(self.batch(tasks, "--box", "--reading", "menu", "--dry-run").code, 0)
            # Without the box no reading is a condition, and every run takes its own key.
            self.assertEqual(self.batch(tasks).calls, 2)
        with tempfile.TemporaryDirectory() as folder:
            tasks = self.task_file(folder, buyable={"apparel-all-stocked": {"kind": "boolean", "value": False}})
            buyable = self.batch(tasks, "--box", "--reading", "buyable")
            self.assertEqual((buyable.code, buyable.calls), (0, 2))

    def test_the_reading_the_box_takes_itself_needs_its_key_too(self):
        # "has the best price for size M" has a price only for a size that can be sold, so
        # the box reads it as buyable without asking: it is scored under the buyable key
        # with or without --reading.
        with tempfile.TemporaryDirectory() as folder:
            tasks = self.task_file(folder, extra=(self.BEST_PRICE,))
            refused = self.batch(tasks, "--box", "--only", "apparel-best-price")
            self.assertEqual((refused.code, refused.calls), (2, 0))
            self.assertIn("apparel-best-price under the buyable reading", refused.out)
            # The box without its stop rule decides the reading the same way.
            self.assertEqual(self.batch(tasks, "--box-exhaust", "--only", "apparel-best-price").code, 2)
        with tempfile.TemporaryDirectory() as folder:
            tasks = self.task_file(folder, extra=(self.BEST_PRICE,),
                                   buyable={"apparel-best-price": {"kind": "contains", "any": ["Alderney"],
                                                                   "not_any": [], "price": 25.77},
                                            "apparel-all-stocked": {"kind": "boolean", "value": False}})
            run = self.batch(tasks, "--box", "--only", "apparel-best-price")
            self.assertEqual((run.code, run.calls), (0, 1))

    def test_an_asked_question_with_no_reply_runs_nothing_and_needs_no_key(self):
        with tempfile.TemporaryDirectory() as folder:
            run = self.batch(self.task_file(folder), "--box")
            self.assertEqual((run.code, run.calls), (0, 1))       # the control ran, the ask did not


# ---------------------------------------------------------------------------
# 7. Void runs, and runs reported without a correct answer

def stamped(*seconds: int) -> str:
    """A log whose timestamped lines fall at these offsets from 12:00:00, in openJiuwen's
    line format, which `verify_cells.longest_silence` reads."""
    return "".join(f"2026-10-20 12:{s // 60:02d}:{s % 60:02d} | common | default_trace_id | INFO | line\n"
                   for s in seconds)


def record_of(final: str = "Alderney Clothing Co at $25.77.", ok: bool = True, error: str | None = None,
              ended: str | None = None, **extra) -> dict:
    return {"model": "fake/model", "error": error,
            "result": {"ok": ok, "final": final, "error": ended}, **extra}


class VoidClassifier(unittest.TestCase):
    """Each rule of `voids.classify` on the fault it exists for, real where the project has
    one (a 429 from the provider, an empty worker output, the step budget, the clock) and
    planted where it has none, and on the case beside it where it must stay quiet."""

    RUNS = paths.EXPERIMENTS / "runs"

    def stored(self, path: pathlib.Path) -> dict:
        return json.loads(path.read_text())

    def test_the_suspended_rule_is_verify_cells_own(self):
        self.assertIs(voids.verify_cells, verify_cells)
        limit = verify_cells.SUSPENDED_AFTER_S
        self.assertEqual(voids.classify(record_of(), stamped(0, limit + 1))[:2], (voids.VOID, "suspended"))
        self.assertEqual(voids.classify(record_of(), stamped(0, limit))[0], voids.ANSWERED)
        # It is decided before the answer: a right one in a suspended run is still void.
        self.assertEqual(voids.classify(record_of("Yes."), stamped(0, 3018))[0], voids.VOID)

    def test_a_provider_error_with_no_final_is_void(self):
        rate_limited = self.stored(self.RUNS / "20260908T215305-deepseek_deepseek-chat.json")
        outcome, reason, why = voids.classify(rate_limited, None)
        self.assertEqual((outcome, reason), (voids.VOID, "provider error"))
        self.assertIn("Error code: 429", why)
        # The same run had it reached an answer is not void: the error did not end it.
        recovered = {**rate_limited, "result": {**rate_limited["result"], "final": "Seller A, $9.89.", "ok": True}}
        self.assertEqual(voids.classify(recovered, None)[0], voids.ANSWERED)
        # An LLM call error in the log voids a run with no final whatever it ended on, and
        # leaves one that answered alone.
        log = stamped(0, 10) + '{"event_type": "llm_call_error"}\n'
        self.assertEqual(voids.classify(record_of("", ok=False, ended="task_timeout: exceeded 600s"), log)[:2],
                         (voids.VOID, "provider error"))
        self.assertEqual(voids.classify(record_of(), log)[0], voids.ANSWERED)
        # The second agent records a reply that was not a 200 as its status and body.
        naive = {"scaffold": "naive", "error": '429 {"error": "rate limited"}',
                 "result": {"final": "", "ok": False}, "tokens": {"calls": 3}}
        self.assertEqual(voids.classify(naive, None)[:2], (voids.VOID, "provider error"))

    def test_a_runner_failure_or_no_record_is_void(self):
        empty_worker = self.stored(self.RUNS / "20260908T221542-google_gemini-2.5-flash-lite.json")
        self.assertEqual(voids.classify(empty_worker, None)[:2], (voids.VOID, "runner error"))
        crashed = {"model": "fake/model", "error": "RuntimeError: the browser closed", "result": None}
        self.assertEqual(voids.classify(crashed, stamped(0, 5))[:2], (voids.VOID, "runner error"))
        self.assertEqual(voids.classify(None, None, row={"error": "runner wrote no record"})[:2],
                         (voids.VOID, "no record"))
        # An agent that reports a tool's failure in words has a final, so it reported.
        worded = self.stored(self.RUNS / "20260908T214912-deepseek_deepseek-chat.json")
        self.assertEqual(voids.classify(worded, None)[:2], (voids.NOT_CORRECT, "no answer"))

    def test_the_step_budget_and_the_clock_are_not_correct_and_not_void(self):
        budget = self.stored(paths.RESULTS / "20261007T115021" / "apparel-target-price-1.json")
        self.assertEqual(voids.classify(budget, stamped(0, 20))[:2], (voids.NOT_CORRECT, "step budget"))
        clock = self.stored(paths.RESULTS / "20261008T034455" / "apparel-target-price-1.json")
        self.assertEqual(clock["result"]["error"], "task_timeout: exceeded 600s")
        self.assertEqual(voids.classify(clock, stamped(0, 30))[:2], (voids.NOT_CORRECT, "clock"))
        # That run was in fact silent for 3018 seconds, and the silence comes first.
        self.assertEqual(voids.classify(clock, stamped(0, 3018))[:2], (voids.VOID, "suspended"))
        naive = {"scaffold": "naive", "error": None, "result": {"final": "", "ok": False},
                 "tokens": {"calls": voids.NAIVE_STEP_LIMIT}}
        self.assertEqual(voids.classify(naive, None)[:2], (voids.NOT_CORRECT, "step budget"))
        self.assertEqual(voids.classify({**naive, "tokens": {"calls": 12}}, None)[:2],
                         (voids.NOT_CORRECT, "no answer"))
        # The second agent's budget is the runner's own figure.
        self.assertIn(f"STEP_LIMIT = {voids.NAIVE_STEP_LIMIT}\n",
                      (paths.EXPERIMENTS / "runners" / "naive_agent.py").read_text())

    def test_no_answer_and_an_abstention(self):
        self.assertEqual(voids.classify(record_of(""), stamped(0, 5))[:2], (voids.NOT_CORRECT, "no answer"))
        self.assertEqual(voids.classify(record_of(ok=False), stamped(0, 5))[:2], (voids.NOT_CORRECT, "no answer"))
        self.assertEqual(voids.classify(record_of("I could not determine this reliably."), stamped(0, 5))[:2],
                         (voids.NOT_CORRECT, "abstention"))
        # Under a policy the reported answer is the policy's: the gate's abstention counts.
        self.assertEqual(voids.classify(record_of(), stamped(0, 5),
                                        reported="I could not determine this reliably. The figure...")[:2],
                         (voids.NOT_CORRECT, "abstention"))
        self.assertEqual(voids.classify(record_of(), stamped(0, 5))[:2], (voids.ANSWERED, ""))

    def test_a_batch_prints_its_voids_as_rerun_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            batch = pathlib.Path(tmp) / "20261021T190000"
            batch.mkdir()
            runs = {"apparel-target-price-1": (record_of(), stamped(0, 5)),
                    "apparel-target-price-2": (record_of(), stamped(0, 900)),
                    "apparel-all-stocked-3": (record_of("", ok=False, ended="[181001] model call failed, "
                                                        "reason: Error code: 502"), stamped(0, 5)),
                    "apparel-count-buyable-1": (record_of("Max iterations reached without completion", ok=False,
                                                          ended="max_iterations_reached"), stamped(0, 5))}
            for name, (record, log) in runs.items():
                (batch / f"{name}.json").write_text(json.dumps({**record, "log": f"{name}.log"}))
                (batch / f"{name}.log").write_text(log)
            (batch / "apparel-cheapest-target-2.log").write_text(stamped(0, 5))   # no record
            rows = [{"task": "apparel-headline", "repeat": 1, "verdict": "asked", "answer": "?"}]
            rows += [{"task": n.rsplit("-", 1)[0], "repeat": int(n.rsplit("-", 1)[1]), "verdict": "correct",
                      "answer": "x"} for n in runs]
            (batch / "suite.json").write_text(json.dumps({"tasks_file": "tasks_claim_apparel.json",
                                                          "box": True, "box_exhaust": False, "reading": "menu",
                                                          "policy": "off", "rows": rows}))
            classes = {run.name: (run.outcome, run.reason) for run in voids.batch_runs(batch)}
            self.assertEqual(classes, {
                "apparel-target-price-1": (voids.ANSWERED, ""),
                "apparel-target-price-2": (voids.VOID, "suspended"),
                "apparel-all-stocked-3": (voids.VOID, "provider error"),
                "apparel-count-buyable-1": (voids.NOT_CORRECT, "step budget"),
                "apparel-cheapest-target-2": (voids.VOID, "no record"),
                "apparel-headline-1": (voids.CLOSED, "asked")})
            with mock.patch.object(sys, "argv", ["voids.py", str(batch)]), \
                    contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(voids.main(), 0)
        text = out.getvalue()
        self.assertIn("re-run the 3 void, each with --tasks experiments/tasks/tasks_claim_apparel.json "
                      "--repeats 1 --box --reading menu:", text)
        lines = [line.strip() for line in text.splitlines() if line.strip().startswith("--only")]
        self.assertEqual(sorted(lines), ["--only apparel-all-stocked --repeat-start 3",
                                         "--only apparel-cheapest-target --repeat-start 2",
                                         "--only apparel-target-price --repeat-start 2"])
        self.assertNotIn("apparel-count-buyable --repeat-start", text)   # not correct is not re-run


CELL_5_FIRST = paths.RESULTS / "20261008T034455"


@unittest.skipUnless(any(CELL_5_FIRST.glob("*.log")), "the raw logs live on the laptop, not in git")
class VoidsOnTheStoredBatch(unittest.TestCase):
    """LESSONS 1: the counter is run on the batch where the fault is known to exist. Cell
    5's first batch lost three runs to the laptop sleeping, and the rule must find exactly
    those three, by silence, before any answer is read."""

    def test_cell_5s_three_suspended_runs(self):
        runs = {run.name: run for run in voids.batch_runs(CELL_5_FIRST)}
        void = sorted(name for name, run in runs.items() if run.outcome == voids.VOID)
        self.assertEqual(void, ["apparel-count-buyable-2", "apparel-target-price-1", "apparel-target-price-2"])
        self.assertTrue(all(runs[name].reason == "suspended" for name in void))
        self.assertEqual((runs["apparel-count-buyable-3"].outcome, runs["apparel-count-buyable-3"].reason),
                         (voids.NOT_CORRECT, "step budget"))
        self.assertEqual(sum(run.outcome == voids.ANSWERED for run in runs.values()), 11)


# ---------------------------------------------------------------------------
# 8. Runs that read the prices the gated theme hides

THEME = (paths.REPO / "env" / "gated_theme" / "Magento_ConfigurableProduct" / "templates" / "product"
         / "view" / "type" / "options" / "configurable.phtml")
# A stretch of igr-app-08's blob as one stored run's tool reply held it, cut mid-blob, with
# neither the attribute's name nor its start (20261014T220116/apparel-softest-1).
EXCERPT = ("W91bnQiOjE3LjEyfSwiYmFzZVByaWNlIjp7ImFtb3VudCI6MTcuMTJ9LCJmaW5hbFByaWNlIjp7ImFtb3VudCI6MTcu"
           "MTJ9LCJ0aWVyUHJpY2VzIjpbXSwibXNycFByaWNlIjp7ImFtb3VudCI6MH19LCIxMDYyODciOnsiYmFzZU9sZFByaWNl"
           "Ijp7ImFtb3VudCI6MTguMDh9")


def blob(prices: dict[str, float]) -> str:
    """The attribute the theme writes for these child prices: json_encode, then base64."""
    table = {child: {key: {"amount": price} for key in ("baseOldPrice", "oldPrice", "basePrice", "finalPrice")}
             | {"tierPrices": [], "msrpPrice": {"amount": 0}} for child, price in prices.items()}
    return base64.b64encode(json.dumps(table, separators=(",", ":")).encode()).decode()


def tool_log(folder: str, name: str, replies: list[str], said: str = "") -> pathlib.Path:
    """An openJiuwen log holding these tool replies, and an assistant message saying `said`."""
    messages = [{"role": "user", "content": "the task"},
                {"role": "assistant", "content": said, "tool_calls": [
                    {"id": f"c{n}", "function": {"name": "mcp_playwright-official_browser_evaluate",
                                                 "arguments": "{}"}} for n in range(len(replies))]}]
    messages += [{"role": "tool", "tool_call_id": f"c{n}", "content": text} for n, text in enumerate(replies)]
    path = pathlib.Path(folder) / f"{name}.log"
    path.write_text(json.dumps({"event_id": "e1", "messages": messages}) + "\n")
    return path


class LeakCounter(unittest.TestCase):
    """`leaks.py` on the three signs it reads, each planted and each left out, and on how it
    knows the hidden prices of a batch's market."""

    def setUp(self):
        self.thornwood = leaks.market_of(paths.FIXTURES / "scaled_apparel.json")

    def test_the_theme_encodes_as_the_counter_reads(self):
        template = THEME.read_text()
        self.assertIn("$hidden = base64_encode(json_encode($truePrices));", template)
        self.assertIn('data-igr="<?= $block->escapeHtmlAttr($hidden) ?>"', template)
        self.assertIn('id="igr-variant-store"', template)

    def test_the_blob_is_found_whatever_its_alignment_or_cut(self):
        for children in ({"106279": 16.22, "106280": 15.04}, {"7": 9.5}, {"12345678": 20.0, "9": 1.0},
                         {"1": 3.0, "22": 4.0, "333": 5.0}):
            with self.subTest(children=children):
                encoded = blob(children)
                self.assertTrue(any(sig in encoded for sig in leaks.SIGNATURES))
                self.assertTrue(leaks.leaks_in(f"... {encoded[37:]} ...", "", None))
        self.assertTrue(any(sig in EXCERPT for sig in leaks.SIGNATURES))
        # Quiet on base64 that is not the blob, and on the keys written out as plain JSON.
        for clean in (base64.b64encode(b"an image, or a session token: 0123456789" * 3).decode(),
                      '{"finalPrice":{"amount":18.33}}', "As low as $18.33"):
            with self.subTest(clean=clean[:30]):
                self.assertEqual(leaks.leaks_in(clean, clean, None), [])

    def test_the_store_words_are_found_anywhere_in_the_log(self):
        for word in ("data-igr", "igr-variant-store"):
            with self.subTest(word=word):
                self.assertEqual(len(leaks.leaks_in(f'<div id="x" {word}="...">', "", None)), 1)
        self.assertEqual(leaks.leaks_in("<div hidden>", "", None), [])

    def test_a_hidden_price_counts_in_a_tool_reply_only(self):
        self.assertEqual(sorted(self.thornwood.hidden)[:3], [1504, 1622, 1655])
        self.assertEqual(len(self.thornwood.hidden), 12)
        self.assertEqual(self.thornwood.hidden[1504], ["igr-app-07 M"])
        with tempfile.TemporaryDirectory() as tmp:
            forced = tool_log(tmp, "forced", ['### Result\\n"As low as\\\\n        $15.04"'])
            shown = tool_log(tmp, "shown", ['### Result\\n"As low as\\\\n        $18.33"'])
            said = tool_log(tmp, "said", ["### Result\\nok"], said="M might be $15.04")
            for path, count in ((forced, 1), (shown, 0), (said, 0)):
                with self.subTest(log=path.stem):
                    log = path.read_text()
                    self.assertEqual(len(leaks.leaks_in(log, leaks.tool_text(path, log), self.thornwood)), count)
            # The second agent's log: its observations count, its own calls and answer do not.
            naive = pathlib.Path(tmp) / "naive.log"
            naive.write_text('[tool read_page] {"url": "x"}\nAs low as $15.04\n\n'
                             '[tool finish] {"answer": "M is $16.22 at Fairhaven"}\n')
            text = naive.read_text()
            found = leaks.leaks_in(text, leaks.tool_text(naive, text), self.thornwood)
            self.assertEqual(len(found), 1)
            self.assertIn("$15.04 (igr-app-07 M)", found[0])

    def test_a_sold_out_price_some_listing_shows_does_not_count(self):
        # Seller B's sold-out M costs what Seller A's buyable L does, so $12.00 on a page
        # says nothing; Seller B's sold-out S at $9.99 is shown nowhere and counts.
        fixture = {"families": [
            {"parent_sku": "X-01", "variants": [{"option": "L", "price": 12.00, "qty": 3}]},
            {"parent_sku": "X-02", "variants": [{"option": "M", "price": 12.00, "qty": 0},
                                                {"option": "S", "price": 9.99, "qty": 0},
                                                {"option": "XL", "price": 14.00, "qty": 5}]}]}
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "fixture.json"
            path.write_text(json.dumps(fixture))
            market = leaks.market_of(path)
        self.assertEqual((market.hidden, market.shown_too), ({999: ["x-02 S"]}, ["x-02 M"]))
        self.assertEqual(leaks.leaks_in("", "As low as $12.00", market), [])
        self.assertEqual(len(leaks.leaks_in("", "As low as $9.99", market)), 1)

    def test_the_hidden_prices_are_only_looked_for_on_the_batchs_own_market(self):
        market, why = leaks.batch_market({"tasks_file": "tasks_apparel.json", "draw": "Thornwood:f9faf835ea"})
        self.assertEqual((market.name, why), ("scaled_apparel.json", ""))
        claim, _ = leaks.batch_market({"tasks_file": "tasks_claim_apparel.json",
                                       "draw": suite.draw_id(json.loads((paths.TASKS / "tasks_claim_apparel.json")
                                                                         .read_text()))})
        self.assertEqual(claim.name, "claim_apparel.json")
        for payload, reason in (({"tasks_file": "tasks_apparel.json", "draw": "Thornwood:e923925b0b"}, "draw"),
                                ({"tasks_file": "tasks_scaled.json", "draw": "Rivenhall:2cf12d1df7"}, "no brand"),
                                ({"tasks_file": "tasks_heldout.json", "draw": "x"}, "fixture"),
                                ({}, "no task file")):
            with self.subTest(payload=payload):
                market, why = leaks.batch_market(payload)
                self.assertIsNone(market)
                self.assertIn(reason, why)


LEAK_BATCHES = [paths.RESULTS / name for name in ("20261007T115021", "20261014T220116", "20261007T112057")]


@unittest.skipUnless(all(any(b.glob("*.log")) for b in LEAK_BATCHES), "the raw logs live on the laptop, not in git")
class LeaksOnTheStoredBatches(unittest.TestCase):
    """The counter on the stored runs where it found something, and on a batch it clears."""

    def found(self, batch: pathlib.Path) -> dict[str, list[str]]:
        runs, _ = leaks.batch_leaks(batch)
        return {run.run: run.found for run in runs if run.found}

    def test_the_three_runs(self):
        cell_2 = self.found(LEAK_BATCHES[0])
        self.assertEqual(sorted(cell_2), ["apparel-target-price-1"])
        self.assertEqual(sorted(re.findall(r"\(igr-app-\d\d M\)", " ".join(cell_2["apparel-target-price-1"]))),
                         ["(igr-app-05 M)", "(igr-app-07 M)", "(igr-app-08 M)", "(igr-app-09 M)", "(igr-app-10 M)"])
        development = self.found(LEAK_BATCHES[1])
        self.assertEqual(sorted(development), ["apparel-softest-1", "apparel-top-3-1"])
        self.assertTrue(all(f.startswith("the blob") for f in development["apparel-softest-1"]))
        self.assertTrue(all("(igr-app-10 M)" in f for f in development["apparel-top-3-1"]))
        self.assertEqual(self.found(LEAK_BATCHES[2]), {})


if __name__ == "__main__":
    unittest.main()
