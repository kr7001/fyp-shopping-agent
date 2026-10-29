#!/usr/bin/env python3
"""Run one scheduled slot of the separate matched-briefing mechanism study.

The frozen suite owns execution, scoring, model parsing, charges and browser resets.
This wrapper replaces only the baseline query and adds study provenance. A dry run
never calls a model. A real invocation requires a frozen protocol; that is not paid
launch approval, which remains the external watchdog/operator's responsibility.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import page as page_module  # noqa: E402
import primitives  # noqa: E402
import suite  # noqa: E402

STUDY_ID = "matched-briefing-2026-10-29"
WRAPPER_ID = "matched-briefing-v1"
ARMS = {"full-block": "box-model", "matched-briefing": "matched-briefing"}

# Fixed environment facts, independent of the task. No question classifier, form,
# product filter, candidate pruning, traversal order or stopping policy is used.
SHOP_FACTS = (
    "Shop facts: The advertised price on a results card is the price of that listing's "
    "cheapest option that can be bought, so it is a lower bound on the prices of its "
    "buyable options. The price a listing shows before a size is chosen is its cheapest "
    "option that can be bought, not necessarily the size asked about. A size's price is "
    "shown after that size is chosen and the page is read again; the reply to choosing "
    "an option does not show the new price. An option can be absent from the menu, "
    "present but unavailable, or available to buy. An unavailable option is disabled "
    "or greyed out and cannot be chosen from the menu, so it has no selectable price."
)


def sha256(value: str | bytes) -> str:
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def page_digest(page: dict) -> str:
    return sha256(json.dumps(page, sort_keys=True, separators=(",", ":")))


def factual_query(question: str, page: page_module.Page) -> str:
    """Only the original question and observed candidate page enter this function."""
    check_page(page)
    return f"{question}\n\n{primitives.preamble(page)}\n\n{SHOP_FACTS}\n{primitives.LABEL_NOTE}"


def check_page(page: page_module.Page) -> None:
    if page.reader != "rendered" or page.next_page or not page.listings:
        raise ValueError("matched briefing requires a complete nonempty rendered search")
    if page.scope is not None or page.of is not None:
        raise ValueError("matched briefing must not prune or scope the candidate page")
    if page.total is None or page.total != len(page.listings):
        raise ValueError("candidate count must equal the observed search total")


class Session:
    """Scoped adapters; all original suite functions are restored even on failure."""

    def __init__(self, metadata: dict):
        self.metadata = metadata
        self.condition = metadata["condition"]
        self.current = None
        self.reads = {}
        self.read_elapsed = 0.0
        self.out_dir = None
        self.before_dirs = set(suite.RESULTS.iterdir()) if suite.RESULTS.exists() else set()
        self.original = {name: getattr(suite, name) for name in
                         ("build_query", "results_page", "run_once", "summarise", "print_summary")}

    def results_page(self, url, reader="rendered"):
        if reader != "rendered":
            raise ValueError("this study uses only the rendered reader")
        cached = url in suite.PAGES
        started = time.perf_counter()
        page = self.original["results_page"](url, reader)
        elapsed = time.perf_counter() - started
        check_page(page)
        if url not in self.reads:
            self.reads[url] = {"pre_read_elapsed_s": elapsed, "pre_read_cached": cached}
            self.read_elapsed += elapsed
        return page

    def build_query(self, task, spec, args, call=None):
        started = time.perf_counter()
        read_before = self.read_elapsed
        # Do not pass keys, fixture names, expected answers or metadata to the
        # counterfactual prompt builder. The suite retains these for scoring only.
        question = task["query"].format(base=spec["base_url"])
        if self.condition == "full-block":
            query, applied = self.original["build_query"](task, spec, args, call=call)
            page = applied["page"]
        else:
            url = suite.box_module.results_url(question)
            page = self.results_page(url)
            query = factual_query(question, page)
            applied = {"strategy": None, "box": None, "page": page, "decision": None}
        if page is None:
            raise ValueError("study questions must name a results page")
        check_page(page)
        preamble = primitives.preamble(page)
        if query is not None and preamble not in query:
            raise ValueError("full block changed the matched candidate preamble")
        self.current = {
            "query": query, "query_sha256": sha256(query) if query is not None else None,
            "original_query": question, "original_query_sha256": sha256(question),
            "preamble": preamble, "preamble_sha256": sha256(preamble),
            "page": page.record(), "page_sha256": page_digest(page.record()),
            **self.reads[page.url],
            "query_build_elapsed_s": time.perf_counter() - started - (self.read_elapsed - read_before),
        }
        return query, applied

    def decorate(self, record):
        record.update(self.metadata)
        record["briefing"] = dict(self.current)
        # Keep the frozen executor elapsed_s. This separate field includes the
        # initial all-page read and actual query construction (including parsing).
        elapsed = record.get("elapsed_s")
        record["elapsed_with_briefing_s"] = (
            None if elapsed is None else elapsed + self.current["pre_read_elapsed_s"]
            + self.current["query_build_elapsed_s"])
        if self.condition == "matched-briefing":
            record.update(parse_cost_usd=0, parse_tokens=suite.parse_tokens([]), parse_provider=None)
        return record

    def run_once(self, task, base_url, out_dir, tag, **kwargs):
        self.out_dir = out_dir
        record = self.original["run_once"](
            {"id": task["id"], "query": task["query"]}, base_url, out_dir, tag, **kwargs)
        self.decorate(record)
        path = out_dir / f"{tag}.json"
        if path.exists():
            path.write_text(json.dumps(record, indent=2, default=str) + "\n")
        return record

    def summarise(self, rows):
        if len(rows) != 1:
            raise ValueError("one scheduled slot is required per invocation")
        self.decorate(rows[0])
        return self.original["summarise"](rows)

    def print_summary(self, summary, rows):
        # suite.json has just been written; finish its metadata before the frozen
        # suite prints the 'full results:' marker consumed by the watchdog.
        if self.out_dir is None:
            candidates = [p for p in set(suite.RESULTS.iterdir()) - self.before_dirs
                          if (p / "suite.json").exists()]
            if len(candidates) != 1:
                raise ValueError("cannot identify this slot's suite output")
            self.out_dir = candidates[0]
        path = self.out_dir / "suite.json"
        payload = json.loads(path.read_text())
        payload.update(self.metadata)
        payload["briefing_page_reader"] = "rendered"
        payload["briefing_version"] = 1
        if self.condition == "matched-briefing":
            payload.update(parse_charged_usd=0, parse_charges_unknown=0,
                           parse_tokens=suite.parse_tokens([]), parse_tokens_unknown=0)
        path.write_text(json.dumps(payload, indent=2, default=str) + "\n")
        self.original["print_summary"](summary, rows)

    @contextlib.contextmanager
    def install(self):
        with contextlib.ExitStack() as stack:
            for name in self.original:
                stack.callback(setattr, suite, name, getattr(suite, name))
                setattr(suite, name, getattr(self, name))
            stack.callback(setattr, suite, "arm_of", suite.arm_of)
            suite.arm_of = lambda args: ARMS[self.condition]
            # Match a fresh suite process even in an in-process synthetic test.
            previous_pages = suite.PAGES
            suite.PAGES = {}
            stack.callback(setattr, suite, "PAGES", previous_pages)
            yield


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--condition", choices=tuple(ARMS), required=True)
    parser.add_argument("--protocol", type=pathlib.Path, required=True)
    parser.add_argument("--slot-id", type=int, required=True)
    parser.add_argument("--tasks", type=pathlib.Path, required=True)
    parser.add_argument("--only", required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--repeat-start", type=int, required=True)
    parser.add_argument("--page-reader", choices=("rendered",), default="rendered")
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--clock", type=int, default=1800)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--parser-replies", type=pathlib.Path)
    args = parser.parse_args(argv)
    protocol = json.loads(args.protocol.read_text())
    if protocol.get("study_id") != STUDY_ID:
        parser.error("wrong study identity")
    if args.repeats != 1:
        parser.error("each invocation must execute exactly one scheduled slot")
    slots = [s for s in protocol["schedule"] if s["slot"] == args.slot_id]
    if len(slots) != 1 or (slots[0]["arm"], slots[0]["task"], slots[0]["repeat"]) != (
            args.condition, args.only, args.repeat_start):
        parser.error("condition/task/repeat do not match the protocol slot")
    if suite.tasks_file_name(args.tasks) != protocol["tasks_file"]:
        parser.error("task file differs from protocol")
    if args.max_steps != 300 or args.clock != 1800:
        parser.error("this study fixes max steps at 300 and clock at 1800 seconds")
    if args.parser_replies and not (args.dry_run and args.condition == "full-block"):
        parser.error("parser replies are allowed only for full-block dry runs")
    if not args.dry_run and protocol.get("status") != "frozen":
        parser.error("real execution requires a frozen protocol and separate paid-launch approval")
    return args, protocol


def suite_argv(args):
    # Consume wrapper flags ourselves. In particular baseline --page-reader must
    # not reach suite's box-only flag validation, and baseline is never --box.
    argv = ["suite.py", "--tasks", str(args.tasks), "--only", args.only,
            "--repeats", "1", "--repeat-start", str(args.repeat_start),
            "--max-steps", str(args.max_steps), "--clock", str(args.clock)]
    if args.condition == "full-block":
        argv += ["--box", "--parser", "model", "--reading", "own",
                 "--page-reader", "rendered"]
    if args.dry_run:
        argv.append("--dry-run")
    if args.parser_replies:
        argv += ["--parser-replies", str(args.parser_replies)]
    return argv


def main(argv=None):
    args, protocol = arguments(argv)
    metadata = {
        "study_id": STUDY_ID, "protocol_id": protocol.get("protocol_id", STUDY_ID),
        "protocol_sha256": sha256(args.protocol.read_bytes()), "wrapper_id": WRAPPER_ID,
        "condition": args.condition, "arm": ARMS[args.condition], "slot_id": args.slot_id,
        # The wrapper exposes no override; record these even when the full block
        # closes a slot without an executor record (ask, decline or parse failure).
        "shop": "gated", "probe": "viewport",
    }
    print("study: " + json.dumps(metadata, sort_keys=True))
    session = Session(metadata)
    previous_argv = sys.argv
    try:
        sys.argv = suite_argv(args)
        with session.install():
            return suite.main()
    finally:
        sys.argv = previous_argv


if __name__ == "__main__":
    raise SystemExit(main())
