"""The results pages a run asked for (toolbar.py, 23 October 2026), read from both agents'
logs: the sort, the page size, the view and the page numbers.

Each reading has a case where it must fire and one where it must stay quiet (LESSONS 1, 24),
in openJiuwen's log and the second agent's (LESSONS 2), through every way a reply reports the
page it left the browser on (LESSONS 3). A page's own links, a pager's "p=2" on every first
page, must never count. The stored batches where the fault is known, four runs sorted and two
resized, are read when their logs are on this machine.
"""
import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import toolbar  # noqa: E402

BASE = "http://localhost:7770"
SEARCH = f"{BASE}/catalogsearch/result/index/?q=Larchmere"


def call(call_id: str, name: str, arguments: dict) -> dict:
    return {"id": call_id, "type": "function",
            "function": {"name": f"mcp_playwright-official_{name}" if name.startswith("browser_") and name not in (
                "browser_probe_cards", "browser_batch_interact") else name, "arguments": json.dumps(arguments)}}


def openjiuwen_log(folder: pathlib.Path, steps: list[tuple[str, dict, str]]) -> pathlib.Path:
    """A log as openJiuwen writes it, one event holding the conversation: each step a tool
    call and its reply."""
    messages = [{"role": "user", "content": "the question"}]
    for n, (name, arguments, reply) in enumerate(steps):
        messages.append({"role": "assistant", "content": "", "tool_calls": [call(f"c{n}", name, arguments)]})
        messages.append({"role": "tool", "tool_call_id": f"c{n}", "content": reply})
    path = folder / "tee-target-price-1.log"
    path.write_text("2026-11-01 10:00:00 | trace | INFO | " + json.dumps({"event_id": "e1", "messages": messages}) + "\n")
    return path


def page_reply(url: str, extra: str = "") -> str:
    return f"### Ran Playwright code\n```js\nawait page.click();\n```\n### Page\n- Page URL: {url}\n- Page Title: x\n{extra}"


class OpenJiuwen(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(self.enterContext(tempfile.TemporaryDirectory()))

    def test_every_way_a_reply_reports_its_page(self):
        # Each address is reported one way only, so a reading left out loses its value.
        log = openjiuwen_log(self.tmp, [
            # A navigation that asks for a sort, whose reply reports no page: the asking counts.
            ("browser_navigate", {"url": f"{SEARCH}&product_list_order=price"}, "Error: navigation timed out"),
            # The limiter chosen: the address only the reply's page line reports.
            ("browser_select_option", {"element": "#limiter", "values": ["60"]},
             page_reply(f"{SEARCH}&product_list_limit=60")),
            # A probe's own page, on the second results page.
            ("browser_probe_cards", {}, f"success=True data={{'ok': True, 'url': '{BASE}/catalogsearch/result/"
                                        f"index/?p=2&q=Larchmere', 'title': 'x', 'cards': []}}"),
            # A batch whose step navigates to the descending sort and goes on to a listing.
            ("browser_batch_interact", {"steps": [{"op": "navigate", "url": f"{SEARCH}&product_list_dir=desc"}]},
             f"success=True data={{'ok': True, 'steps': [], 'page_state': {{'page_id': 'p1', 'url': "
             f"'{BASE}/igr-dev-01.html', 'title': 'x'}}}}"),
            # A batch that chooses from the sorter: only its page_state says where it left the page.
            ("browser_batch_interact", {"steps": [{"op": "select_option", "selector": "#sorter", "value": "name"}]},
             f"success=True data={{'ok': True, 'steps': [], 'page_state': {{'page_id': 'p1', 'url': "
             f"'{SEARCH}&product_list_order=name', 'title': 'x'}}}}"),
        ])
        got = toolbar.read(log)
        self.assertEqual((got["order"], got["direction"], got["limit"], got["results_pages"]),
                         (["price", "name"], ["desc"], ["60"], [2]))
        self.assertTrue(got["sorted"] and got["resized"])

    def test_the_list_view_is_a_page_size_of_its_own(self):
        log = openjiuwen_log(self.tmp, [("browser_click", {"element": "List"},
                                         page_reply(f"{SEARCH}&product_list_mode=list"))])
        got = toolbar.read(log)
        self.assertEqual((got["mode"], got["resized"], got["sorted"]), (["list"], True, False))
        # Quiet: the grid view is the shop's own.
        log = openjiuwen_log(self.tmp, [("browser_click", {"element": "Grid"},
                                         page_reply(f"{SEARCH}&product_list_mode=grid"))])
        self.assertFalse(toolbar.read(log)["resized"])

    def test_a_pages_links_are_not_where_the_run_went(self):
        # Quiet: a snapshot of the first page lists the pager's page 2 and a sorted link; the
        # run never went to either, and its pages say so.
        log = openjiuwen_log(self.tmp, [
            ("browser_navigate", {"url": SEARCH}, page_reply(SEARCH)),
            ("browser_snapshot", {}, page_reply(SEARCH, extra=(
                f"- link \"Page 2\" [ref=e9]:\n  - /url: {BASE}/catalogsearch/result/index/?p=2&q=Larchmere\n"
                f"- link \"Name\":\n  - /url: {SEARCH}&product_list_order=name"))),
            ("browser_probe_cards", {}, f"success=True data={{'ok': True, 'url': '{SEARCH}', 'cards': "
                                        f"[{{'url': '{BASE}/catalogsearch/result/index/?p=2&q=Larchmere'}}]}}"),
        ])
        got = toolbar.read(log)
        self.assertEqual((got["order"], got["limit"], got["results_pages"], got["sorted"], got["resized"]),
                         ([], [], [], False, False))

    def test_the_default_order_is_no_sort(self):
        log = openjiuwen_log(self.tmp, [("browser_navigate", {"url": f"{SEARCH}&product_list_order=relevance"},
                                         page_reply(f"{SEARCH}&product_list_order=relevance"))])
        got = toolbar.read(log)
        self.assertEqual((got["order"], got["sorted"]), (["relevance"], False))
        # A direction alone is a sort.
        log = openjiuwen_log(self.tmp, [("browser_navigate", {"url": f"{SEARCH}&product_list_dir=desc"},
                                         page_reply(f"{SEARCH}&product_list_dir=desc"))])
        self.assertTrue(toolbar.read(log)["sorted"])


class SecondAgent(unittest.TestCase):
    def test_its_steps_and_its_page_lines_but_not_its_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = pathlib.Path(tmp) / "scaled-all-stocked-1.log"
            log.write_text(
                # A goto whose page line is the shop's answer, sorted; and one that printed no
                # page line, so only the asking says it asked for 24 a page.
                f"[tool goto] {{\"url\": \"{SEARCH}\"}}\n"
                f"Page URL: {SEARCH}&product_list_order=name\n"
                "Items 1-12 of 15\n"
                f"List -> {SEARCH}&product_list_mode=list\n"
                f"Page 2 -> {BASE}/catalogsearch/result/index/?p=2&q=Larchmere\n"
                f"[tool goto] {{\"url\": \"{SEARCH}&product_list_limit=24\"}}\n"
                "navigation failed\n"
                f"[tool read_page] {{\"url\": \"{BASE}/x.html\"}}\n")
            got = toolbar.read(log)
        self.assertEqual((got["order"], got["limit"], got["mode"], got["results_pages"]), (["name"], ["24"], [], []))
        self.assertEqual((got["sorted"], got["resized"]), (True, True))


class PastPageOne(unittest.TestCase):
    def test_a_second_page_or_a_page_that_holds_more(self):
        reading = {"results_pages": [], "results_limits": []}
        self.assertFalse(toolbar.past_page_one(reading, 36))
        self.assertTrue(toolbar.past_page_one({**reading, "results_pages": [1, 2]}, 36))
        self.assertTrue(toolbar.past_page_one({**reading, "results_limits": [60]}, 36))
        # Quiet: a smaller page holds less than one of the shop's.
        self.assertFalse(toolbar.past_page_one({**reading, "results_pages": [1], "results_limits": [24]}, 36))


# The stored runs where the fault is known (the verifier's audit, 23 October 2026, confirmed by
# reading every stored log that day): four of the second agent's sorted, two of openJiuwen's
# resized. Every other run of their batches did neither.
KNOWN = {"20260918T054737/scaled-all-stocked-1": (["name"], []),
         "20260918T054737/scaled-cheapest-target-1": (["name", "price"], []),
         "20260918T060028/scaled-all-stocked-1": (["name"], []),
         "20260918T060028/scaled-all-stocked-2": (["name"], []),
         "20260910T000915/scaled-best-per-litre-1": ([], ["24"]),
         "20261020T221540/apparel-target-price-3": ([], ["60"])}
BATCHES = sorted({name.split("/")[0] for name in KNOWN})
HAVE_LOGS = all(any((paths.RESULTS / batch).glob("*.log")) for batch in BATCHES)


@unittest.skipUnless(HAVE_LOGS, "the raw logs live on the laptop, not in git")
class StoredRuns(unittest.TestCase):
    def test_the_six_and_no_other(self):
        found = {}
        for batch in BATCHES:
            for log in sorted((paths.RESULTS / batch).glob("*.log")):
                got = toolbar.read(log)
                if got["sorted"] or got["resized"]:
                    found[f"{batch}/{log.stem}"] = (got["order"], got["limit"])
        self.assertEqual(found, KNOWN)


if __name__ == "__main__":
    unittest.main()
