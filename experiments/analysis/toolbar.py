#!/usr/bin/env python3
"""The results pages a run asked the shop for, read from its log: which page of the results,
the sort order, the page size and the view (23 October 2026).

Magento's results page takes all of them from its address: `p` the page, `product_list_order`
the sort (relevance by default on a search, or name, or price), `product_list_dir` its
direction, `product_list_limit` how many listings a page holds, and `product_list_mode` grid or
list, list having page sizes of its own. However a run sets one, by navigating to an address
that holds it, by choosing from the toolbar's sorter or limiter (`browser_select_option` on
`#sorter` or `#limiter`, which navigates), inside a `browser_batch_interact`, by a script, or by
the second agent's `goto`, the shop answers with a page whose address holds it. Of the 24 tools
in openJiuwen's schema (the `tools` of each llm_call_end event, read on 23 October 2026), those
that can move the browser are navigate, navigate_back, click, select_option, press_key, type,
fill_form, evaluate, tabs, batch_interact and custom_action, and each reply says what page the
browser is on after it, in one of three ways: "Page URL: <address>" (the Playwright tools),
"data={'ok': True, 'url': '<address>'" (the probes), "'page_state': {... 'url': '<address>'"
(a batch). The second agent prints "Page URL: <address>" after each step. So a run's pages are
read from two things only: the addresses its navigations asked for, and the addresses its
replies reported. Never from a page's links, which hold a pager's "p=2" on every first page and
repeat the current address's parameters, nor from the text of a page (LESSONS 2, 3).

Found by the verifier's audit of 23 October 2026: four stored runs of the second agent sorted the
Calderwood results by name, one of them by price as well (20260918T054737 and 20260918T060028,
scaled-all-stocked and scaled-cheapest-target), and two openJiuwen runs set the page size, to 24
(20260910T000915 scaled-best-per-litre-1) and to 60 (20261020T221540 apparel-target-price-3, a
run of the first claim). At 60 a page the A+ market's 42 listings render on one page, which
voids its page rules, and they hold for the relevance order only (docs/content/claim2-protocol.md,
"Limits stated in advance").

Not read: a sort the session remembers across pages without the address saying so, which
Magento does only with `catalog/frontend/remember_pagination` set (not checked on the live shop).

    python3 experiments/analysis/toolbar.py experiments/results/<batch> [...]
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401  (puts box/ and analysis/ on the path)
import sufficiency  # noqa: E402  (PAGE_MARKER, the one reading of a reply's page line)
import trace_stats  # noqa: E402

# How an openJiuwen reply states the page the browser is on after the call, besides the
# Playwright tools' "Page URL:" line (`sufficiency.PAGE_MARKER`): a probe's leading url, and a
# batch's page_state.
PROBE_PAGE = re.compile(r"data=\{'ok': (?:True|False), 'url': '([^']*)'")
BATCH_PAGE = re.compile(r"'page_state': \{[^{}]*?'url': '([^']*)'")
# The toolbar's parameters, and the sort a search has when none is asked for.
ORDER, DIRECTION, LIMIT, MODE, PAGE = ("product_list_order", "product_list_dir", "product_list_limit",
                                       "product_list_mode", "p")
DEFAULT_ORDER = "relevance"


def clean(address: str) -> str:
    """An address as a log line holds it, cut at the first character no address holds: the
    reply's text is JSON inside a log line, so an address can run on into an escaped newline."""
    return re.split(r"[\\\s\"'<>]", address.strip())[0]


def openjiuwen_addresses(log_path: pathlib.Path) -> list[str]:
    """The addresses an openJiuwen run's navigations asked for and its replies reported, in call
    order, from every tool call that has a reply (`trace_stats.tool_replies`)."""
    found = []
    for name, text, arguments in trace_stats.tool_replies(log_path).values():
        if name == "browser_navigate" and isinstance(arguments, dict) and arguments.get("url"):
            found.append(str(arguments["url"]))
        if name == "browser_batch_interact":
            found += [op["target"] for op in trace_stats.batch_ops(arguments)
                      if op["op"] in ("navigate", "goto") and op["target"].startswith(("http", "/"))]
        for marker in (sufficiency.PAGE_MARKER, PROBE_PAGE, BATCH_PAGE):
            found += [match.group(1) for match in marker.finditer(text or "")]
    return [clean(address) for address in found if clean(address)]


def naive_addresses(log_path: pathlib.Path) -> list[str]:
    """The same for the second agent, whose log is the steps it printed: each `goto`'s address
    and each "Page URL:" line it printed after a step."""
    found = []
    for line in log_path.read_text(errors="replace").splitlines():
        step = trace_stats.NAIVE_STEP.match(line)
        if step and step.group(1) == "goto":
            try:
                address = (json.loads(step.group(2)) or {}).get("url")
            except json.JSONDecodeError:
                address = None
            if address:
                found.append(str(address))
        elif line.startswith("Page URL:"):
            found.append(line[len("Page URL:"):])
    return [clean(address) for address in found if clean(address)]


def addresses(log_path: pathlib.Path) -> list[str]:
    """Every address a run asked for or was reported on, from either agent's log: openJiuwen's
    tool calls and replies, and where the log holds none, the second agent's printed steps.
    Neither reader finds anything in the other's log: openJiuwen's lines start with a time,
    where the second agent's steps and page lines start the line."""
    return openjiuwen_addresses(log_path) or naive_addresses(log_path)


def read(log_path: pathlib.Path) -> dict:
    """What a run asked of the results pages: every value each toolbar parameter took, the
    results pages it saw by number and the page sizes it asked of them, whether it sorted
    (any order but relevance, or any direction) and whether it changed the page size (any
    limit, or the list view, whose page sizes are its own)."""
    seen = {key: [] for key in (ORDER, DIRECTION, LIMIT, MODE)}
    pages, limits = set(), set()
    for address in addresses(log_path):
        parts = urllib.parse.urlsplit(address)
        query = urllib.parse.parse_qs(parts.query)
        for key in seen:
            for value in query.get(key, []):
                if value not in seen[key]:
                    seen[key].append(value)
        if "catalogsearch" in parts.path:
            pages |= {int(value) for value in query.get(PAGE, []) if value.isdigit()}
            limits |= {int(value) for value in query.get(LIMIT, []) if value.isdigit()}
    return {"order": seen[ORDER], "direction": seen[DIRECTION], "limit": seen[LIMIT], "mode": seen[MODE],
            "results_pages": sorted(pages), "results_limits": sorted(limits),
            "sorted": any(value != DEFAULT_ORDER for value in seen[ORDER]) or bool(seen[DIRECTION]),
            "resized": bool(seen[LIMIT]) or "list" in seen[MODE]}


def past_page_one(reading: dict, page_size: int) -> bool:
    """Whether a run, as `read` reads it, saw past the first results page at the shop's
    `page_size`: a results page numbered 2 or more, or one whose limit holds more than a page."""
    return (any(page >= 2 for page in reading["results_pages"])
            or any(limit > page_size for limit in reading["results_limits"]))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batches", nargs="+", type=pathlib.Path)
    args = parser.parse_args(argv)
    for batch in args.batches:
        for log in sorted(batch.glob("*.log")):
            got = read(log)
            if got["sorted"] or got["resized"]:
                print(f"{batch.name}/{log.stem}: sorted {got['order'] + got['direction'] or '-'}, "
                      f"page size {got['limit'] + got['mode'] or '-'}, results pages {got['results_pages']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
