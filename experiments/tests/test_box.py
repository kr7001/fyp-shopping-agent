"""The box's front half: the question classifier and the planner.

The box may use only what the agent could see, the question and the pages. These tests pin
how every clothing question is classified, controls included (LESSONS 18), check that the
code which runs before the agent never reads an answer key, and keep the two answer checks
that do read one, today, from being taken for part of the box.
"""
import ast
import contextlib
import io
import json
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import planner  # noqa: E402
import targeting  # noqa: E402

BASE = "http://localhost:7770"


class Classifier(unittest.TestCase):
    EXPECTED = {
        "apparel-headline": "results_page",          # the control: answered on the results page
        "apparel-target-price": "availability_bound",
        "apparel-cheapest-target": "availability_bound",
        "apparel-all-stocked": "refutation",
        "apparel-count-stocked": "survey",
        "apparel-count-buyable": "survey",
    }

    def test_every_clothing_question(self):
        spec = json.loads((paths.TASKS / "tasks_apparel.json").read_text())
        self.assertEqual({t["id"] for t in spec["tasks"]}, set(self.EXPECTED))
        for task in spec["tasks"]:
            with self.subTest(task=task["id"]):
                self.assertEqual(targeting.classify(task["query"].format(base=BASE)),
                                 self.EXPECTED[task["id"]])


class Planner(unittest.TestCase):
    def test_regression_passes(self):
        # Every question in every task file: the plan renders the same text the strategy
        # table does, and every plan passes its own soundness check.
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(planner.regression(), 0)

    def test_an_unsound_plan_is_caught(self):
        plan = planner.plan("Across the Thornwood listings, which seller is cheapest for size M?")
        self.assertEqual(planner.verify(plan), [])
        # Each break is a failure already paid for: pruning a market never listed, and a
        # bound's arithmetic reported as a price.
        for label, broken in (("not enumerated", {**plan, "enumerate_first": False}),
                              ("bound reportable", {**plan, "forbidden_claims": []})):
            with self.subTest(broken=label):
                self.assertNotEqual(planner.verify(broken), [])


# What a piece of code can read an answer through: the keys of a task's answer and of a
# market's instance, and the fixture files themselves.
ANSWER_KEYS = {"_instance", "expect", "oracle_min_opens"}
BEFORE_THE_AGENT = ("targeting.py", "planner.py")


def code_values(source: str) -> tuple[list[str], list[float], set[str]]:
    """The strings, decimal numbers and names a piece of code uses, leaving out comments and
    docstrings, which may quote a past failure without reading anything."""
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    strings = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
               and isinstance(n.value, str) and id(n) not in docstrings]
    floats = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
              and isinstance(n.value, float)]
    names = ({n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
             | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)})
    return strings, floats, names


def answer_reads(source: str) -> list[str]:
    strings, _, names = code_values(source)
    found = [s for s in strings if s in ANSWER_KEYS or "fixtures" in s.lower()]
    return found + sorted(n for n in names if n == "FIXTURES")


def market_facts() -> tuple[set[str], set[str]]:
    """Every seller and every price in every market this project has generated."""
    sellers, prices = set(), set()
    for fixture in paths.FIXTURES.glob("*.json"):
        for family in json.loads(fixture.read_text())["families"]:
            if family.get("seller"):
                sellers.add(family["seller"])
            prices.update(f"{v['price']:.2f}" for v in family["variants"])
    return sellers, prices


def copied_facts(source: str) -> list[str]:
    sellers, prices = market_facts()
    strings, floats, _ = code_values(source)
    text = "\n".join(strings)
    found = sorted(s for s in sellers if s in text)
    found += sorted(p for p in prices if re.search(rf"(?<![\d.]){re.escape(p)}(?!\d)", text))
    found += sorted(f"{x:.2f}" for x in floats if f"{x:.2f}" in prices)
    return found


class NoAnswerKey(unittest.TestCase):
    """The parts of the box that run before the agent decide from the question alone.

    Checked by what the code uses rather than by how one file happens to be spelled: the
    keys an answer is read through, the fixture files, and any seller or price copied in.
    """

    def source(self, name: str) -> str:
        return (paths.EXPERIMENTS / "box" / name).read_text()

    def test_reads_no_answer_key_or_fixture(self):
        for name in BEFORE_THE_AGENT:
            with self.subTest(file=name):
                self.assertEqual(answer_reads(self.source(name)), [])

    def test_copies_no_seller_or_price(self):
        for name in BEFORE_THE_AGENT:
            with self.subTest(file=name):
                self.assertEqual(copied_facts(self.source(name)), [])

    def test_the_checks_catch_a_planted_read(self):
        seller = sorted(market_facts()[0])[0]
        planted = {
            'x = spec["_instance"]["winner"]': answer_reads,
            "x = task['expect']": answer_reads,
            'x = task.get("expect")': answer_reads,
            'x = paths.FIXTURES / "scaled_apparel.json"': answer_reads,
            f'x = "{seller}"': copied_facts,
            "x = 25.77": copied_facts,
        }
        for code, check in planted.items():
            with self.subTest(planted=code):
                self.assertNotEqual(check(code), [])

    def test_only_the_answer_checks_read_the_answer_key(self):
        # sufficiency.py and policy.py judge a finished answer, and today they read the
        # answer key's market size and floor. Until box v1 takes both from the page they are
        # evaluation tools, not part of the box, and no other file here may join them.
        readers = sorted(p.name for p in (paths.EXPERIMENTS / "box").glob("*.py")
                         if answer_reads(p.read_text()))
        self.assertEqual(readers, ["policy.py", "sufficiency.py"])


if __name__ == "__main__":
    unittest.main()
