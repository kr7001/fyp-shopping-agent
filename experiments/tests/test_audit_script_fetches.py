"""Free checks for tools/audit_script_fetches.py, the audit of product pages fetched by page
script in the primary studies.

Written 4 November 2026 with the audit. Each rule has a test where it must fire on a planted
fault and one where it must stay quiet, on small logs written in openJiuwen's format. The last
class reads stored run logs whose fault is known from earlier audits, and is skipped where
those logs are not on the machine.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "tools/audit_script_fetches.py"
spec = importlib.util.spec_from_file_location("audit_script_fetches", MODULE)
audit = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = audit  # its dataclasses look their module up by name
spec.loader.exec_module(audit)

BASE = "http://localhost:7770"
KEYS = [f"igr-tst-{n:02d}" for n in range(1, 13)]
MARKET = [f"{BASE}/{key}.html" for key in KEYS]
EVALUATE = "mcp_playwright-official_browser_evaluate"


def result(text='"ok"'):
    return "{'result': " + repr("### Result\n" + text) + "}"


def evaluate(code, reply=None, tool=EVALUATE):
    return tool, {"function": code}, result() if reply is None else reply


def navigate(url):
    reply = (f"### Ran Playwright code\n```js\nawait page.goto('{url}');\n```\n"
             f"### Page\n- Page URL: {url}\n- Page Title: A tee")
    return "mcp_playwright-official_browser_navigate", {"url": url}, "{'result': " + repr(reply) + "}"


def log(*steps):
    """A log as openJiuwen writes one: an event line per model call, each carrying the whole
    conversation so far, every reply a Python repr inside JSON."""
    messages, lines = [], []
    for i, (tool, arguments, reply) in enumerate(steps):
        messages.append({"role": "assistant", "content": "", "tool_calls": [{
            "id": f"call_{i}", "type": "function",
            "function": {"name": tool, "arguments": json.dumps(arguments)}}]})
        if reply is not None:
            messages.append({"role": "tool", "tool_call_id": f"call_{i}", "content": reply})
        lines.append("2026-11-04 12:00:00 INFO llm_call_end "
                     + json.dumps({"event_id": f"e{i}", "messages": list(messages)}))
    return "\n".join(lines) + "\n"


def counts(*steps, market=MARKET):
    found = audit.audit_text(log(*steps), market)
    found.pop("_findings")
    return found


class Fires(unittest.TestCase):
    """A product document a script that ran named and requested is counted."""

    def test_a_listing_fetched_by_its_url(self):
        found = counts(evaluate(f"async () => (await fetch('{BASE}/igr-tst-03.html')).status"))
        self.assertEqual(found["fetched"], ["igr-tst-03"])
        self.assertEqual((found["navigated"], found["combined"]), (0, 1))

    def test_keys_mapped_to_urls_and_fetched_in_a_loop(self):
        code = ("async () => { const keys = " + json.dumps(KEYS) + ";\n"
                "  for (const k of keys) { const r = await fetch('http://localhost:7770/' + k + '.html'); }\n"
                "  return keys.length; }")
        self.assertEqual(counts(evaluate(code))["fetched"], KEYS)

    def test_a_prefix_and_numbers_listed_as_strings(self):
        # 20261102T061732/tee-count-buyable-2: the keys are never written whole.
        code = ("async () => { const ids = ['01','02','07'];\n"
                "  for (const id of ids) { const url = 'http://localhost:7770/igr-tst-' + id + '.html';\n"
                "    await fetch(url); } }")
        self.assertEqual(counts(evaluate(code))["fetched"], ["igr-tst-01", "igr-tst-02", "igr-tst-07"])

    def test_a_prefix_in_a_template_literal(self):
        code = ("async () => { const nums = ['04','05'];\n"
                "  for (const n of nums) { await fetch(`http://localhost:7770/igr-tst-${n}.html`); } }")
        self.assertEqual(counts(evaluate(code))["fetched"], ["igr-tst-04", "igr-tst-05"])

    def test_every_request_form(self):
        forms = {
            "XMLHttpRequest": "() => { const x = new XMLHttpRequest(); x.open('GET', '/igr-tst-06.html', false); x.send(); }",
            "jQuery": "() => $.get('/igr-tst-06.html')",
            "iframe": "() => { const f = document.createElement('iframe'); f.src = '/igr-tst-06.html'; }",
            "window.open": "() => window.open('http://localhost:7770/igr-tst-06.html')",
            "location": "() => { window.location.href = 'http://localhost:7770/igr-tst-06.html'; }",
        }
        for how, code in forms.items():
            with self.subTest(how=how):
                self.assertEqual(counts(evaluate(code))["fetched"], ["igr-tst-06"])

    def test_combined_adds_only_what_the_counter_missed(self):
        code = ("async () => { const keys = " + json.dumps(KEYS) + ";\n"
                "  for (const k of keys) await fetch('http://localhost:7770/' + k + '.html'); }")
        found = counts(navigate(MARKET[0]), navigate(MARKET[1]), evaluate(code))
        self.assertEqual((found["navigated"], found["fetched_by_script"]), (2, 12))
        self.assertEqual((found["fetched_only_by_script"], found["combined"]), (10, 12))

    def test_reply_listings_are_reported_apart(self):
        code = ("async () => { const html = await (await fetch('/catalogsearch/result/?q=Tst')).text();\n"
                "  const urls = [...html.matchAll(/href=\"([^\"]+\\.html)\"/g)].map(m => m[1]);\n"
                "  const out = []; for (const u of urls) { const r = await fetch(u); out.push(u); }\n"
                "  return out; }")
        reply = result(json.dumps(MARKET[:5]))
        found = counts(navigate(MARKET[0]), evaluate(code, reply))
        self.assertEqual((found["fetched_by_script"], found["combined"]), (0, 1))
        self.assertEqual((found["named_in_reply_only"], found["combined_with_reply"]), (4, 5))
        self.assertEqual(found["unresolved_calls"], 0)

    def test_a_loop_that_builds_the_keys_is_unresolved_not_counted(self):
        # 20261024T232020/decline-delivery-1 counted from 1 to 45 to build its keys.
        code = ("() => { const pages = []; for (let i = 1; i <= 12; i++) pages.push(('0' + i).slice(-2));\n"
                "  return Promise.all(pages.map(n => fetch('http://localhost:7770/igr-tst-' + n + '.html'))); }")
        found = counts(evaluate(code, result('"01|Abbey Tees\\n02|Brook Tees"')))
        self.assertEqual((found["fetched_by_script"], found["unresolved_calls"]), (0, 1))


class Quiet(unittest.TestCase):
    """Nothing is counted that is not another product document fetched by a script that ran."""

    def test_the_current_pages_store_is_not_a_fetch(self):
        code = "() => JSON.parse(atob(document.getElementById('igr-variant-store').getAttribute('data-igr')))"
        found = counts(navigate(MARKET[2]), evaluate(code, result('{"107": {"finalPrice": {"amount": 9.5}}}')))
        self.assertEqual((found["fetched_by_script"], found["combined"]), (0, 1))
        self.assertEqual(found["embedded_reads"], {"current_page": 1, "fetched_documents": 0})

    def test_a_refetch_of_the_current_page(self):
        code = "async () => (await (await fetch(window.location.href)).text()).length"
        found = counts(navigate(MARKET[2]), evaluate(code, result(f'"{MARKET[2]} 9000"')))
        self.assertEqual((found["fetched_by_script"], found["named_in_reply_only"]), (0, 0))
        self.assertEqual(found["requests_in_scripts_that_ran"], {"current page": 1})

    def test_results_pages_whose_reply_lists_every_listing(self):
        # 20261028T013644/tee-xs-price-1 read 45 URLs off the results pages it fetched.
        code = ("async () => { const urls = []; for (const p of [1, 2]) {\n"
                "  const h = await (await fetch(base + '/catalogsearch/result/index/?p=' + p + '&q=Tst')).text();\n"
                "  urls.push(...h.match(/igr-tst-\\d+\\.html/g)); } return urls; }")
        found = counts(evaluate(code, result(json.dumps(MARKET))))
        self.assertEqual((found["fetched_by_script"], found["named_in_reply_only"]), (0, 0))
        self.assertEqual(found["unresolved_calls"], 0)

    def test_api_requests_naming_a_sku_or_a_key(self):
        code = ("async () => { const a = await fetch('/rest/V1/products/IGR-TST-03');\n"
                "  const b = await fetch('/graphql', {method: 'POST', body: JSON.stringify({query:\n"
                "    'products(filter: {url_key: {eq: \"igr-tst-03\"}}) { items { sku } }'})});\n"
                "  const c = await fetch('/inventory_catalog/product/getQty/?sku=IGR-TST-03-M'); }")
        found = counts(evaluate(code))
        self.assertEqual(found["fetched_by_script"], 0)
        self.assertEqual(found["requests_in_scripts_that_ran"], {"API": 3})

    def test_a_post_to_a_listing_reads_nothing(self):
        code = f"async () => fetch('{BASE}/igr-tst-03.html', {{method: 'POST', body: new FormData()}})"
        found = counts(evaluate(code))
        self.assertEqual(found["fetched_by_script"], 0)
        self.assertEqual(found["requests_in_scripts_that_ran"], {"not a read": 1})

    def test_a_tool_the_runtime_did_not_know(self):
        tool = "mcp_playwright-official-browser_evaluate"
        code = f"async () => fetch('{BASE}/igr-tst-03.html')"
        found = counts(evaluate(code, f"Ability not found in resource_mgr: {tool}", tool=tool))
        self.assertEqual(found["fetched_by_script"], 0)
        self.assertEqual(found["script_calls"], {"did not run": 1})

    def test_a_script_that_threw_is_listed_not_counted(self):
        code = f"async () => {{ await fetch('{BASE}/igr-tst-03.html'); null.x; }}"
        reply = "{'result': " + repr("### Error\nTypeError: Cannot read properties of null") + "}"
        found = counts(evaluate(code, reply))
        self.assertEqual((found["fetched_by_script"], found["threw_after_requesting_listings"]), (0, 1))

    def test_a_navigation_tool_is_not_a_script(self):
        found = counts(navigate(MARKET[4]))
        self.assertEqual((found["navigated"], found["fetched_by_script"], found["script_calls"]), (1, 0, {}))

    def test_a_key_is_matched_whole_and_in_lower_case(self):
        market = [f"{BASE}/igr-tst-2.html", f"{BASE}/igr-tst-22.html"]
        for code, fetched in (("async () => fetch('/igr-tst-22.html')", ["igr-tst-22"]),
                              ("async () => { const s = 'IGR-TST-2'; return fetch(u + s); }", []),
                              ("async () => { const k = 'igr-tst-2-m'; return fetch(u + k); }", [])):
            with self.subTest(code=code):
                self.assertEqual(counts(evaluate(code), market=market)["fetched"], fetched)

    def test_a_product_page_outside_the_market(self):
        code = f"async () => fetch('{BASE}/cinch-mens-jersey-tee.html')"
        found = counts(evaluate(code))
        self.assertEqual(found["fetched_by_script"], 0)
        self.assertEqual(found["requests_in_scripts_that_ran"], {"product page outside the market": 1})

    def test_a_number_inside_a_regular_expression_names_nothing(self):
        # 20261024T232020/decline-delivery-1: "17", a size's option id, inside a regex literal.
        code = ("() => Promise.all(pages.map(n => fetch('http://localhost:7770/igr-tst-' + n + '.html')\n"
                "  .then(r => r.text()).then(h => /.\"07\".*\\[/.test(h))))")
        self.assertEqual(counts(evaluate(code))["fetched_by_script"], 0)


class Arguments(unittest.TestCase):
    def test_strings_and_brackets_are_skipped_whole(self):
        code = "fetch(base + ('/x,' + y), {method: 'POST', note: ')'}); next()"
        start = code.index("(") + 1
        self.assertEqual(audit.arguments_at(code, start), ["base + ('/x,' + y)", "{method: 'POST', note: ')'}"])

    def test_a_call_whose_end_is_not_found_is_cut(self):
        code = "fetch(" + "a" * 1000
        self.assertEqual(len(audit.arguments_at(code, 6, limit=50)[0]), 50)


def record(block, other, h1=0.1, h3=0.2):
    """A minimal analysis record: H2 over two questions, its stored values the frozen test's."""
    runs = [{"batch": f"b-{arm}-{q}-{r}", "task": q, "repeat": r, "arm": arm, "opened": value}
            for arm, by_q in (("block", block), ("open", other))
            for q, values in by_q.items() for r, value in enumerate(values, 1)]
    questions = sorted(block)
    test = audit.claim.compare_ranks([r for r in runs if r["arm"] == "block"],
                                     [r for r in runs if r["arm"] == "open"], questions, "opened")
    holm = audit.claim.holm({"H1": h1, "H2": test["p"], "H3": h3})
    tests = {"H1": {"p": h1, "p_holm": holm["H1"]},
             "H2": {"a": "block", "b": "open", "questions": questions, "p": test["p"], "p_holm": holm["H2"]},
             "H3": {"p": h3, "p_holm": holm["H3"]}}
    return {"runs": runs, "primary": tests}


def trial(run, value):
    return {"batch": run["batch"], "task": run["task"], "repeat": run["repeat"],
            "navigated": run["opened"], "combined": value, "combined_with_reply": value}


STUDY = audit.Study("Synthetic", "none.json", "model", "primary", None)


class Sensitivity(unittest.TestCase):
    def setUp(self):
        # The block's 10 ranks above open everything's 4 on q1, so moving the 4 moves the test.
        self.record = record({"q1": [1, 10], "q2": [5, 5]}, {"q1": [4, 45], "q2": [45, 45]})

    def test_h2_moves_when_open_everything_fetched_more(self):
        # The Quenby replication's tee-all-stocked-1: 4 navigated, 45 fetched by script.
        trials = [trial(r, 45 if r["opened"] == 4 else r["opened"]) for r in self.record["runs"]]
        out = audit.sensitivity(self.record, STUDY, trials)
        self.assertEqual(out["fetched_by_script"]["per_question"][0]["b"], [45, 45])
        self.assertEqual(out["frozen"]["observed"] - out["fetched_by_script"]["observed"], 1)
        self.assertTrue(out["fetched_by_script"]["p_changed"])
        self.assertTrue(out["fetched_by_script"]["block_fewer"])
        self.assertFalse(out["fetched_by_script"]["medians_changed"])

    def test_h2_unchanged_when_no_count_changes(self):
        trials = [trial(r, r["opened"]) for r in self.record["runs"]]
        out = audit.sensitivity(self.record, STUDY, trials)
        self.assertFalse(out["fetched_by_script"]["p_changed"])
        self.assertEqual(out["fetched_by_script"]["p"], self.record["primary"]["H2"]["p"])

    def test_stops_when_the_frozen_h2_does_not_reproduce(self):
        broken = copy.deepcopy(self.record)
        broken["primary"]["H2"]["p"] = 0.5
        with self.assertRaises(ValueError):
            audit.sensitivity(broken, STUDY, [trial(r, r["opened"]) for r in broken["runs"]])


QUENBY = "tasks_tee_replication_28_oct.json"   # a public task file whose fixture names the market


class OneStudy(unittest.TestCase):
    """A study folder written here: an analysis file and one batch per run, Quenby's market."""

    def write(self, folder, opened, logged=("block", "open")):
        url = "http://localhost:7770/igr-rp28-{:02d}.html".format
        runs = [{"batch": "B-block", "task": "tee-top-3", "repeat": 1, "arm": "block",
                 "outcome": "answered", "opened": opened["block"]},
                {"batch": "B-open", "task": "tee-top-3", "repeat": 1, "arm": "open",
                 "outcome": "answered", "opened": opened["open"]}]
        for run, pages in zip(runs, ([url(1)], [url(1), url(2)])):
            batch = folder / run["batch"]
            batch.mkdir()
            (batch / "suite.json").write_text(json.dumps({"tasks_file": QUENBY}))
            if run["arm"] in logged:
                (batch / "tee-top-3-1.log").write_text(log(*map(navigate, pages)))
        test = audit.claim.compare_ranks(runs[:1], runs[1:], ["tee-top-3"], "opened")
        primary = {"H2": {"a": "block", "b": "open", "questions": ["tee-top-3"], "p": test["p"],
                          "p_holm": audit.claim.holm({"H2": test["p"]})["H2"]}}
        (folder / "x.analysis.json").write_text(json.dumps({"models": {"m": {
            "runs": runs, "exclusions": {"voids": []}, "primary": primary}}}))
        return audit.Study("Synthetic", "x.analysis.json", "m", "primary", None)

    def test_quiet_when_the_counter_agrees_with_the_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = audit.audit_study(self.write(Path(tmp), {"block": 1, "open": 2}), Path(tmp))
        self.assertEqual((out["scanned"], out["missing_logs"]), (2, []))
        self.assertFalse(out["h2"]["fetched_by_script"]["p_changed"])

    def test_stops_when_the_counter_disagrees_with_the_analysis(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                audit.audit_study(self.write(Path(tmp), {"block": 1, "open": 3}), Path(tmp))

    def test_a_missing_log_is_named_and_h2_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = audit.audit_study(self.write(Path(tmp), {"block": 1, "open": 2}, logged=("block",)), Path(tmp))
        self.assertEqual([gone["arm"] for gone in out["missing_logs"]], ["open"])
        self.assertIsNone(out["h2"])


RESULTS = ROOT / "experiments/results"


def stored(relative):
    path = RESULTS / relative
    if not path.exists():
        raise unittest.SkipTest(f"{relative} is not on this machine")
    found = audit.audit_text(path.read_text(errors="replace"), audit.market_of(path.parent, {}))
    found.pop("_findings")
    return found


class KnownFaults(unittest.TestCase):
    """Stored runs whose script fetches earlier audits found by hand, and runs with none."""

    def test_claim1_deepseek_read_15_while_counted_as_2(self):
        # The report's 27 October draft: "one read 15 listings while being counted as opening 2".
        found = stored("20261021T002924/apparel-count-stocked-3.log")
        self.assertEqual((found["navigated"], found["fetched_by_script"], found["combined"]), (2, 15, 15))

    def test_matched_briefing_slots_7_and_13_fetched_all_45(self):
        # notes/review-integration-1-nov/independent-fetch-caveat-1-nov.json: 7 and 5 navigations.
        for relative, navigated in (("20261029T224819/tee-count-buyable-1.log", 7),
                                    ("20261029T231451/tee-top-3-2.log", 5)):
            with self.subTest(log=relative):
                found = stored(relative)
                self.assertEqual((found["navigated"], found["fetched_by_script"], found["combined"]),
                                 (navigated, 45, 45))

    def test_rookmere_count_trial_built_its_keys_from_parts(self):
        found = stored("20261102T061732/tee-count-buyable-2.log")
        self.assertEqual((found["navigated"], found["combined"]), (2, 45))

    def test_quenby_open_everything_counted_4_fetched_45(self):
        found = stored("20261028T020926/tee-all-stocked-1.log")
        self.assertEqual((found["navigated"], found["fetched_only_by_script"], found["combined"]), (4, 41, 45))

    def test_quiet_on_block_runs(self):
        for relative, navigated in (("20261028T031956/tee-top-3-1.log", 9),
                                    ("20261020T203740/apparel-count-buyable-1.log", 15)):
            with self.subTest(log=relative):
                found = stored(relative)
                self.assertEqual((found["navigated"], found["fetched_by_script"], found["combined_with_reply"]),
                                 (navigated, 0, navigated))


if __name__ == "__main__":
    unittest.main()
