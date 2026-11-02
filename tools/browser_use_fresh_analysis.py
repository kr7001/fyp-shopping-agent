#!/usr/bin/env python3
"""Study A's pre-registered analysis, offline, once its blind review is complete and validated.

It refuses to run until browser_use_fresh_review.py has validated a complete review of every
row on the sheet and written its receipt, and only then opens the private key. It computes what
notes/fresh-market-2-nov/analysis-plan-A.md pre-registers, with amendments 1 to 4 applied:

- each of the 32 slots' disposition, from whichever stage ran it (attempts 1 to 4): answered,
  failed, timeout, closed by the block, technical void or not started. Attempt 1's voids are the
  launcher's frozen classification (`browser_use_transfer.validate_pilot_record`) or the guard's
  stop; the later stages also end a clock timeout, or a void after a settled request, by the
  runner's own rule (`continuation_disposition`, amendment 3);
- the one primary test, `compare_cells.stratified_exact` with one stratum per question type, on
  every slot the agent ran, a slot counting 1 only when it answered and the student graded it
  correct (a timeout scores 0), voids and slots not started left out and listed;
- beside it, every sensitivity the plan and the amendments declare, none a second primary: the
  unscorable one (plan, amendment 2), timed-out slots left out (sensitivity 1) and each
  replaced by its rerun's outcome (sensitivity 2, amendment 4), voids after a settled request
  counted not correct and slots with a settled request left out (amendment 3), and slots whose
  conversation holds "Full path:" left out (amendment 1); timeouts per arm;
- the descriptive results, per slot, per question pair, per arm and per repeat: the human
  verdict, the frozen v10 score (secondary) and every disagreement, the provider's charge with
  the parser's share and any request settled at its bound, listings opened by navigation (the
  cohort's validated counter), product pages fetched by script (browser_use_fetches.py), steps
  and elapsed time; and every rerun on its own, never pooled into a primary figure.

Every input is bound by SHA-256: the files the review bound at preparation, re-read and
re-checked here, and the frozen code the analysis runs. A measurement that is missing or
invalid stays unknown (null), never zero. No model, provider, account or shop is contacted.

Written 2 November 2026 on the pattern of browser_use_repeat_analysis.py, which is bound to
Quenby's repeats 2 and 3 and runs no test.

    python3 tools/browser_use_fresh_analysis.py --bundle notes/fresh-market-2-nov/study-a-review \\
        --output notes/fresh-market-2-nov/study-a-analysis.json \\
        --table notes/fresh-market-2-nov/study-a-analysis.tsv
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402,F401  (puts runners/ and analysis/ on the import path)
import browser_use_fresh_review as blind  # noqa: E402
import browser_use_fetches as fetches  # noqa: E402  (the script-fetch listener's definition)
import browser_use_runner as runner  # noqa: E402  (the counters' own URL identity; imports no Browser Use)
import browser_use_transfer as transfer  # noqa: E402  (the launcher's frozen classification and stage rule)

require, Refused = blind.require, blind.Refused
CLOSED, VOID, NOT_STARTED, TIMEOUT = blind.CLOSED, "technical void", "not started", "timeout"
IN_TEST = ("answered", "failed", TIMEOUT, CLOSED)  # "every slot in which the agent ran"
# Why a void is one, for amendment 3's sensitivity, which counts only the second kind.
VOID_FROZEN, VOID_SETTLED, VOID_GUARD = "the frozen classification", "after a settled request", "the guard stopped it"
ALPHA = 0.05
# The frozen code the analysis runs, pinned at b1c67c8 (2 November 2026): the v10 scorer's
# file, as browser_use_analysis.SCORING_INPUTS pins it, and the source text of the test and the
# classification, read with ast as guarded_browser_use.agent_facing_digests reads its own. The
# runner's stage rule is pinned as attempt 2 ran it at 7148e83, unchanged at e747460.
SCORE_SHA256 = "8f9df93d3827245686b488111a284f9059d6f86cf71c102dbdd36165b719fc00"
FUNCTIONS = {("experiments/analysis/compare_cells.py", "stratified_exact"):
             "81508a0f0c88525cf134942d6855eedea86cd714b6a7405317501a9aedf41d55",
             ("experiments/runners/browser_use_transfer.py", "validate_pilot_record"):
             "c3b5b6b55ebec86f055ad90a65aae6ad8332bb98a87114b96580412a7ec35a7c",
             ("experiments/runners/browser_use_transfer.py", "continuation_disposition"):
             "93d2f79a452559537c883c2f7a3530450d501f61864291f5212abeaefab2c59d"}
# The adapter, listener and import paths whose records and URL identity this reads, held to the
# hashes every stage's configuration bound when it ran. The runner's own file moved between the
# stages (guarded_browser_use.FRESH_RENEWED), so its two rules are held by their pins above.
RAN_WITH = ("experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py",
            "experiments/paths.py")
SCRIPT_KINDS = ("fetch", "xhr", "subframe-document")  # browser_use_fetches.ScriptFetches.observe
MEASURES = ("charge_usd", "parser_charge_usd", "openings", "script_fetches", "steps", "elapsed_with_parser_s")
# How a request was settled at its bound: by the trial clock, after the provider gave no response
# (amendment 3), or, in attempt 4 and the reruns, after an error reply without usage (amendment 6
# point 2). The runner counts every kind but the clock's in `no_response_settlements`, and the error
# replies again in `error_reply_settlements`, which the review holds to the calls.
CLOCK_KIND, NO_RESPONSE_KIND, ERROR_REPLY_KIND = "trial clock", "no response", blind.ERROR_REPLY_KIND


def function_digest(path, name):
    source = Path(path).read_text()
    found = [node for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef) and node.name == name]
    require(len(found) == 1, f"{name} is not defined once in {Path(path).name}.")
    return hashlib.sha256(ast.get_source_segment(source, found[0]).encode()).hexdigest()


def frozen_code(configs):
    """Check the code before any of it is used, then import the scorer and the test."""
    require(blind.digest(ROOT / "experiments/analysis/score.py") == SCORE_SHA256, "The v10 scorer changed.")
    for (name, function), wanted in FUNCTIONS.items():
        require(function_digest(ROOT / name, function) == wanted, f"{function} in {name} changed.")
    for config in configs:
        for name in RAN_WITH:
            require(blind.digest(ROOT / name) == config["hashes"].get(name),
                    f"{name} differs from the file a stage ran with.")
    import compare_cells
    import score
    require(score.VERSION == 10 and Path(score.__file__).resolve() == ROOT / "experiments/analysis/score.py"
            and Path(compare_cells.__file__).resolve() == ROOT / "experiments/analysis/compare_cells.py"
            and Path(transfer.__file__).resolve() == ROOT / "experiments/runners/browser_use_transfer.py",
            "The scorer, test or classification was imported from another file.")
    return compare_cells, score


def completed_review(study, bundle):
    """The validated review and its receipt, checked before the private key is opened."""
    bundle = Path(bundle)
    manifest = blind.read_json(bundle / "manifest.json")
    reviewed = bundle / "validated/reviewed.csv"
    require(reviewed.exists(), "No validated review: validate the student's completed CSV with --save first.")
    total = manifest.get("rows")
    require(blind.validate(study, bundle, reviewed) == (total, total), f"Complete all {total} human verdicts first.")
    receipt = blind.read_json(bundle / "validated/validation.json")
    require(receipt.get("study_id") == study.study_id and receipt.get("rows") == total
            and receipt.get("complete") is True and receipt.get("arm_key_read") is False
            and receipt.get("scored") is False, "Missing the pre-unblinding validation receipt.")
    require(receipt.get("reviewed_sha256") == blind.digest(reviewed)
            and receipt.get("original_sheet_sha256") == manifest["original_sheet_sha256"],
            "The validated review changed after its receipt.")
    return blind.review.read_sheet(reviewed), manifest


def number(value):
    """A finite, non-negative number, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return value


def close(a, b, label):
    require(a is not None and b is not None and abs(Decimal(str(a)) - Decimal(str(b))) <= Decimal("1e-9"),
            f"Accounting mismatch: {label}.")


def total(values):
    """The sum, or None when any value is unknown. Counts stay whole; charges are summed in
    decimal, so no float noise enters a figure."""
    if any(v is None for v in values):
        return None
    if all(type(v) is int for v in values):
        return sum(values)
    return float(sum((Decimal(str(v)) for v in values), Decimal(0)))


def minus(a, b):
    """a - b, or None when either is unknown, in decimal for the same reason."""
    if a is None or b is None:
        return None
    if type(a) is int and type(b) is int:
        return a - b
    return float(Decimal(str(a)) - Decimal(str(b)))


def charges(calls):
    """The provider's charge for every call, the parser's included. A call without a known
    charge leaves its total unknown, never zero; a request settled at its bound (amendment 3) has
    no provider charge, and its bound is reported beside the charges, never added to them."""
    require(all(call.get("role") in ("parser", "executor") for call in calls), "A call has an unknown role.")
    costs = [number(call.get("cost_usd")) for call in calls]
    parser = [c for call, c in zip(calls, costs) if call["role"] == "parser"]
    executor = [c for call, c in zip(calls, costs) if call["role"] == "executor"]
    settled = [call for call in calls if "settled_usd" in call]
    return {"charge_usd": total(costs), "parser_charge_usd": total(parser), "executor_charge_usd": total(executor),
            "charge_known_part_usd": total([c for c in costs if c is not None]),
            "unknown_charge_calls": sum(c is None for c in costs), "provider_calls": len(calls),
            "settled_calls": len(settled), "settled_bound_usd": total([number(c["settled_usd"]) for c in settled]),
            "providers": dict(Counter(call.get("provider") for call in calls))}


def identity(url):
    """A URL as both counters key it (browser_use_runner.normalized_url)."""
    try:
        return runner.normalized_url(url)
    except (ValueError, TypeError):
        raise Refused("A recorded URL is not one the counters could have keyed.") from None


def navigated_openings(record):
    """Listings opened by navigation: the cohort's validated counter, unique candidate URLs
    reached as main-frame product documents, held to its own events (LESSONS 1, 2 and 33)."""
    if record["outcome"] == CLOSED:
        return 0, "closed by the block: no browser ran"
    trace = record.get("trace") or {}
    if trace.get("measurement_valid") is not True or trace.get("observation_errors"):
        return None, "navigation evidence invalid or missing: unknown, not zero"
    candidates = {identity(item["url"]) for item in record["page"]["listings"]}
    urls = [identity(url) for url in trace["opened_urls"]]
    require(len(set(urls)) == len(urls) == trace["opened"] and set(urls) <= candidates,
            "The opened count or its candidates disagree with the navigation record.")
    observed = set()
    for event in trace["navigation_events"]:
        candidate = identity(event["url"]) in candidates
        product = (event.get("main_document") is True and 200 <= event["status"] < 300
                   and event.get("product_document") is True)
        require(event.get("candidate") == candidate and event.get("counted") == (candidate and product),
                "A navigation event disagrees with its recorded membership or success.")
        if candidate and product:
            observed.add(identity(event["url"]))
    require(observed == set(urls), "The opened URLs disagree with the navigation events.")
    return len(urls), "unique candidate URLs reached as main-frame product documents"


def script_fetched(record):
    """Product pages fetched by script, the new passive measure, never added to openings."""
    if record["outcome"] == CLOSED:
        return 0, "closed by the block: no browser ran"
    seen = record.get("script_fetches")
    if seen is None:
        return None, "not recorded: unknown, not zero"
    require(seen.get("definition") == fetches.DEFINITION, "The script-fetch record has another definition.")
    if seen.get("complete") is not True or seen.get("script_errors"):
        return None, "the listener lost a reading: unknown, not zero"
    candidates = {identity(item["url"]) for item in record["page"]["listings"]}
    fetched = set()
    for event in seen["script_events"]:
        require(event.get("kind") in SCRIPT_KINDS and identity(event["url"]) in candidates
                and (event.get("product_document") is not True or 200 <= event["status"] < 300),
                "A script-fetch event is not one the listener records.")
        if event.get("product_document") is True:
            fetched.add(identity(event["url"]))
    require(seen.get("script_fetched_urls") == sorted(fetched) and seen.get("script_fetched") == len(fetched),
            "The script-fetch count disagrees with its own events.")
    return len(fetched), "unique candidate URLs whose 2xx response by fetch, XMLHttpRequest or a subframe was a product page"


def measure(record):
    """One saved record's measurements, each with its basis; unknown is None, never zero."""
    calls = charges(record["calls"])
    # The record's own sums, written from the same calls, must agree. The adapter writes a
    # null executor sum for a trial that made no executor call, and a sum is null where a
    # request was settled, so a null is not compared.
    for field, wanted in (("total_cost_usd", calls["charge_usd"]), ("parse_cost_usd", calls["parser_charge_usd"]),
                          ("cost_usd", calls["executor_charge_usd"])):
        if wanted is not None and record.get(field) is not None:
            close(number(record[field]), wanted, field)
    openings, openings_basis = navigated_openings(record)
    fetched, fetched_basis = script_fetched(record)
    if record["outcome"] == CLOSED:
        steps, steps_basis = 0, "closed by the block: no agent ran"
    elif type(record.get("steps")) is int and record["steps"] >= 0:
        steps, steps_basis = record["steps"], "the agent's history"
    else:
        steps, steps_basis = None, "not recorded (the trial did not finish): unknown"
    share = (calls["parser_charge_usd"] / calls["charge_usd"]
             if calls["charge_usd"] and calls["parser_charge_usd"] is not None else None)
    return {**calls, "parser_share": share, "openings": openings, "openings_basis": openings_basis,
            "script_fetches": fetched, "script_fetches_basis": fetched_basis, "steps": steps,
            "steps_basis": steps_basis, "elapsed_with_parser_s": number(record.get("elapsed_with_parser_s")),
            "agent_error_count": sum(bool(error) for error in record.get("agent_errors") or []),
            "no_response_settlements": record.get("no_response_settlements", 0),
            "clock_settlements": record.get("clock_settlements", 0),
            # Amendment 6's error replies without usage, apart from the provider's no-responses.
            "error_reply_settlements": sum("settled_usd" in call and call.get("settlement_kind") == ERROR_REPLY_KIND
                                           for call in record["calls"])}


def reached_clock(record):
    elapsed, clock = number(record.get("elapsed_s")), number((record.get("settings") or {}).get("clock_s"))
    return elapsed is not None and clock is not None and elapsed >= clock


def disposition(spec, record, status):
    """A slot's disposition under analysis-plan-A.md and amendments 2 and 3, why when it is not
    the record's own outcome, and for a void which kind. Returns (disposition, reason, void kind)."""
    if record is None:
        if status["status"] == blind.NOT_STARTED:
            return NOT_STARTED, "not started: " + str(status.get("reason") or "the batch ended before it"), None
        return VOID, f"the guard stopped the slot while it ran ({status['status']}): {status.get('reason')}", VOID_GUARD
    if spec.stage in blind.SETTLING:
        # The stage's own rule, as its runner applied it; the review checked the record agrees.
        state, reason = transfer.continuation_disposition(record)
        if state == TIMEOUT:
            return TIMEOUT, reason, None
        if state == VOID:
            return VOID, reason, VOID_SETTLED
    try:
        transfer.validate_pilot_record(record, "transfer")
        return record["outcome"], None, None
    except transfer.Stop as stop:
        reason = str(stop)
    # Attempt 1's launcher never sets `timeout_kind`, so the frozen classification stops on every
    # timeout as "unclassified". The plan's "timeout (the 2700 s trial clock)" is a timeout
    # whose own elapsed time reached its trial clock, with nothing else the classification
    # stops on (amendment 2, 2 November 2026, before any Study A trial ran). The later stages
    # applied the same rule themselves, above.
    if spec.stage not in blind.SETTLING and record["outcome"] == TIMEOUT and reached_clock(record):
        try:
            transfer.validate_pilot_record({**record, "timeout_kind": "trial_clock"}, "transfer")
            return TIMEOUT, (f"the trial clock: {record['elapsed_s']:.0f} s against "
                             f"{record['settings']['clock_s']} s; the frozen classification stops on any "
                             f"timeout, as it cannot tell a trial-clock one ({reason})"), None
        except transfer.Stop as stop:
            reason = str(stop)
    return VOID, "the frozen classification: " + reason, VOID_FROZEN


def counted(row):
    """1 only when the student graded the slot correct and the agent committed a final answer:
    failed (no final answer), timeout and closure count 0 whatever their row was graded."""
    return int(row["disposition"] == "answered" and row["human_verdict"] == "correct")


def decide(p, block, baseline):
    if p < ALPHA and block[0] != baseline[0]:
        return (f"difference claimed: the {'block' if block[0] > baseline[0] else 'baseline'} arm "
                f"answered correctly more often (p < {ALPHA})")
    if p < ALPHA:
        return f"p < {ALPHA} but the arms' total correct counts are equal: no direction, so no claim"
    return f"no difference claimed (p >= {ALPHA}); this is not evidence that the arms are equivalent"


def stratified(compare_cells, rows, task_ids, keep=None, score=None, why_out=None):
    """The plan's test on the slots `keep` admits, each counting `score` (default: in the test,
    counted as the primary counts it), with every slot left out listed and why."""
    keep = keep or (lambda r: r["in_test"])
    score = score or (lambda r: r["counted"])
    why_out = why_out or (lambda r: r["disposition_reason"])
    used = [r for r in rows if keep(r)]
    strata, shown = [], []
    for task in task_ids:
        block = [r for r in used if r["task"] == task and r["condition"] == "block"]
        baseline = [r for r in used if r["task"] == task and r["condition"] == "baseline"]
        stratum = (sum(score(r) for r in block), len(block), sum(score(r) for r in baseline), len(baseline))
        strata.append(stratum)
        correct, trials = stratum[0] + stratum[2], stratum[1] + stratum[3]
        shown.append({"task": task, "block_correct": stratum[0], "block_trials": stratum[1],
                      "baseline_correct": stratum[2], "baseline_trials": stratum[3],
                      "informative": bool(stratum[1] and stratum[3] and 0 < correct < trials)})
    p = compare_cells.stratified_exact(strata)
    block = [sum(s[0] for s in strata), sum(s[1] for s in strata)]
    baseline = [sum(s[2] for s in strata), sum(s[3] for s in strata)]
    kept = {r["slot"] for r in used}
    left = [{"slot": r["slot"], "condition": r["condition"], "disposition": r["disposition"], "reason": why_out(r)}
            for r in rows if r["slot"] not in kept]
    return {"test": "compare_cells.stratified_exact, one stratum per question type, two-sided",
            "strata": shown, "block_correct_of_trials": block, "baseline_correct_of_trials": baseline,
            "p": p, "alpha": ALPHA, "decision": decide(p, block, baseline), "slots_in_test": len(used),
            "planned_slots": len(rows), "complete_against_plan": not left, "left_out": left}


def exact_test(compare_cells, rows, task_ids, leave_out_unscorable):
    """The plan's primary test, or with `leave_out_unscorable` its declared sensitivity."""
    if not leave_out_unscorable:
        return stratified(compare_cells, rows, task_ids)
    return stratified(compare_cells, rows, task_ids, keep=lambda r: r["in_test"] and not r["unscorable_answer"],
                      why_out=lambda r: "unscorable answer" if r["in_test"] else r["disposition_reason"])


def sensitivities(compare_cells, rows, task_ids):
    """Every sensitivity the amendments declare, each the plan's test on another view of the same
    slots, none a second primary. A slot's own count is the primary's unless a view says otherwise."""
    timed_out = lambda r: r["disposition"] == TIMEOUT  # noqa: E731
    settled = lambda r: bool(r["no_response_settlements"] or r["clock_settlements"]  # noqa: E731
                             or r["error_reply_settlements"])

    def with_rerun(r):
        """Sensitivity 2: a timed-out slot counts its rerun's outcome, when its rerun is a trial the
        agent ran; otherwise it keeps the primary's 0."""
        rerun = r["rerun"]
        if timed_out(r) and rerun and rerun["in_test"]:
            return rerun["counted"]
        return r["counted"]

    def label(r):
        """What sensitivity 2 used for a timed-out slot, and why when it kept the primary's 0: no
        rerun, or a rerun that was a void or never started, as one the deadline left no time for."""
        rerun = r["rerun"]
        if rerun and rerun["in_test"]:
            return f"rerun with its clock doubled to {rerun['clock_s']} s"
        why = (f"its rerun is a {rerun['disposition']}: {rerun['disposition_reason']}" if rerun
               else "it was not rerun")
        return f"no rerun outcome, since {why}. The primary timeout is kept, counted 0"

    substituted = [{"slot": r["slot"], "condition": r["condition"], "primary": TIMEOUT,
                    "rerun_disposition": (r["rerun"] or {}).get("disposition"),
                    "used": with_rerun(r) if r["rerun"] and r["rerun"]["in_test"] else None,
                    "label": label(r)} for r in rows if timed_out(r)]
    return {
        "unscorable_left_out": {**exact_test(compare_cells, rows, task_ids, leave_out_unscorable=True),
                                "role": "declared sensitivity (plan, amendment 2): answered slots graded unscorable left out"},
        "timeouts_left_out": {**stratified(compare_cells, rows, task_ids, keep=lambda r: r["in_test"] and not timed_out(r),
                                           why_out=lambda r: "timeout" if timed_out(r) else r["disposition_reason"]),
                              "role": "sensitivity 1 (amendment 4): timed-out slots left out"},
        "timeouts_replaced_by_rerun": {**stratified(compare_cells, rows, task_ids, score=with_rerun),
                                       "substituted": substituted,
                                       "role": "sensitivity 2 (amendment 4), secondary: each timed-out slot counts "
                                               "its rerun, run once with its clock doubled. A second sample for "
                                               "those slots only"},
        "voids_after_settlement_not_correct": {
            **stratified(compare_cells, rows, task_ids, keep=lambda r: r["in_test"] or r["void_kind"] == VOID_SETTLED,
                         score=lambda r: r["counted"] if r["in_test"] else 0),
            "counted_not_correct": [r["slot"] for r in rows if r["void_kind"] == VOID_SETTLED],
            "role": "amendment 3: each slot that ended without an answer after a settled request counted not "
                    "correct instead of left out"},
        "settled_request_slots_left_out": {
            **stratified(compare_cells, rows, task_ids, keep=lambda r: r["in_test"] and not settled(r),
                         why_out=lambda r: "a request settled at its bound" if r["in_test"] else r["disposition_reason"]),
            "role": "amendment 3 as written: every slot with a request settled at its bound, by the provider's "
                    "no-response, by the trial clock or, from attempt 4, after an error reply without usage "
                    "(amendment 6), left out"},
        "no_response_slots_left_out": {
            **stratified(compare_cells, rows, task_ids,
                         keep=lambda r: r["in_test"] and not (r["no_response_settlements"] or r["error_reply_settlements"]),
                         why_out=lambda r: ("a request settled with no usable reply" if r["in_test"]
                                            else r["disposition_reason"])),
            "role": "amendment 3, narrower reading: only slots where a request was settled with no usable reply, "
                    "after which the agent saw an error and went on, left out. That is the provider's no-response "
                    "and, from attempt 4, an error reply without usage, which amendment 6 settles the same way and "
                    "this view treats the same way"},
        "full_path_slots_left_out": {
            **stratified(compare_cells, rows, task_ids, keep=lambda r: r["in_test"] and not r["full_path"],
                         why_out=lambda r: "conversation holds Full path:" if r["in_test"] else r["disposition_reason"]),
            "role": "amendment 1: slots whose conversation holds Full path: left out"},
    }


def summary(values):
    known = [v for v in values if v is not None]
    return {"slots": len(values), "known": len(known), "unknown": len(values) - len(known),
            "total": total(values), "median": statistics.median(values) if values and len(known) == len(values) else None,
            "known_total": total(known), "known_median": statistics.median(known) if known else None}


def arm_summary(rows):
    """One arm's slots: both denominators, the sensitivity's, and the measures beside them."""
    in_test = [r for r in rows if r["in_test"]]
    sensitivity = [r for r in in_test if not r["unscorable_answer"]]
    correct = sum(r["counted"] for r in in_test)
    charge, parser = total([r["charge_usd"] for r in in_test]), total([r["parser_charge_usd"] for r in in_test])
    return {"scheduled": len(rows), "in_test": len(in_test),
            "dispositions": dict(Counter(r["disposition"] for r in rows)),
            "timeouts": sum(r["disposition"] == TIMEOUT for r in rows),
            "human_verdicts": dict(Counter(r["human_verdict"] for r in rows if r["human_verdict"])),
            "automatic_verdicts": dict(Counter(r["automatic_verdict"] for r in rows if r["automatic_verdict"])),
            "correct_of_scheduled": [correct, len(rows)], "correct_of_in_test": [correct, len(in_test)],
            "correct_of_sensitivity": [sum(r["counted"] for r in sensitivity), len(sensitivity)],
            "measures_in_test": {field: summary([r[field] for r in in_test]) for field in MEASURES},
            "parser_share_of_charge": parser / charge if charge and parser is not None else None,
            "providers": dict(sum((Counter(r["providers"]) for r in in_test), Counter()))}


def pair_rows(rows, task_ids, repeats):
    """Each question and repeat's two slots, block minus baseline."""
    pairs = []
    for repeat in repeats:
        for task in task_ids:
            pair = {r["condition"]: r for r in rows if r["task"] == task and r["repeat"] == repeat}
            block, baseline = pair["block"], pair["baseline"]
            complete = block["in_test"] and baseline["in_test"]
            if not complete:
                correctness = "incomplete pair"
            else:
                correctness = {(1, 1): "both correct", (1, 0): "block only correct",
                               (0, 1): "baseline only correct", (0, 0): "neither correct"}[(block["counted"], baseline["counted"])]
            differences = {field: minus(block[field], baseline[field]) if complete else None for field in MEASURES}
            pairs.append({"task": task, "repeat": repeat, "block_slot": block["slot"], "baseline_slot": baseline["slot"],
                          "block_disposition": block["disposition"], "baseline_disposition": baseline["disposition"],
                          "block_human": block["human_verdict"], "baseline_human": baseline["human_verdict"],
                          "block_automatic": block["automatic_verdict"], "baseline_automatic": baseline["automatic_verdict"],
                          "block_counted": block["counted"], "baseline_counted": baseline["counted"],
                          "correctness": correctness, "block_minus_baseline": differences})
    return pairs


def pair_counts(pairs):
    counts = {"correctness": dict(Counter(p["correctness"] for p in pairs))}
    for field, words in (("charge_usd", ("block cost less", "same", "block cost more")),
                         ("openings", ("block opened fewer", "same", "block opened more")),
                         ("script_fetches", ("block fetched fewer", "same", "block fetched more")),
                         ("steps", ("block took fewer", "same", "block took more"))):
        values = [p["block_minus_baseline"][field] for p in pairs]
        known = [v for v in values if v is not None]
        counts[field] = {words[0]: sum(v < 0 for v in known), words[1]: sum(v == 0 for v in known),
                         words[2]: sum(v > 0 for v in known), "unknown or incomplete": len(values) - len(known)}
    return counts


def reconcile(batch, rows):
    """One stage: every saved record's calls, in schedule order, are its ledger's first entries,
    unchanged; the calls after them belong to the slot the stage stopped in. Unknown charges and
    unsettled requests keep the total unknown; requests settled at their bound are counted apart."""
    spec, ledger, slots = batch["spec"], batch["ledger"], batch["slots"]
    out = {"stage": spec.name, "batch_status": batch["status"]["status"], "batch_stop_reason": batch["status"].get("reason"),
           "cap_usd": batch["config"]["cap_usd"], "estimate_usd": batch["config"]["estimate_usd"],
           # The stage's share of Study A's total cap: USD 3 to attempt 2, 10 to attempt 3 and 15
           # to the reruns (amendment 4 points 5 and 6), as its own configuration bound it.
           "shared_cap_usd": batch["config"].get("shared_cap_usd", batch["config"]["cap_usd"]),
           "carryover_usd": batch["config"].get("carryover_usd", 0)}
    if ledger is None:
        return {**out, "ledger_calls": 0, "known_charge_usd": 0, "unknown_charge_calls": 0, "settled_calls": 0,
                "settled_bound_usd": 0, "unsettled_requests": 0, "total_charge_usd": 0,
                "note": "stopped before its first trial: no ledger, no call"}
    calls = ledger["calls"]
    saved = [call for slot in slots for call in (batch["records"].get(slot["id"]) or {}).get("calls", [])]
    reservations = [call.get("reservation") for call in calls]
    require(all(isinstance(r, str) for r in reservations) and len(set(reservations)) == len(reservations),
            f"{spec.name}: the ledger's reservations are missing or repeated.")
    require(calls[:len(saved)] == saved, f"{spec.name}: a saved trial's calls are not the ledger's own, in order.")
    leftover = calls[len(saved):]
    stopped = slots[batch["ran"]]["id"] if batch["ran"] < len(slots) else None
    require(not leftover or (stopped and batch["statuses"][stopped]["status"] in blind.GUARD_STOPPED),
            f"{spec.name}: the ledger holds calls no slot can account for.")
    known = total([number(c.get("cost_usd")) for c in calls if number(c.get("cost_usd")) is not None])
    close(known, number(ledger.get("charged_usd")), f"{spec.name}: the ledger's charged total")
    if batch["status"]["status"] == "complete" and "charged_usd" in batch["status"]:
        close(known, number(batch["status"].get("charged_usd")), f"{spec.name}: the launcher's completed status")
    settled = [c for c in calls if "settled_usd" in c]
    unknown = [c for c in calls if number(c.get("cost_usd")) is None and "settled_usd" not in c]
    unsettled = list((ledger.get("inflight") or {}).values())
    if leftover:
        rows[stopped].update(charges(leftover), charges_basis="the ledger's calls after the last saved record")
    return {**out, "ledger_calls": len(calls), "calls_in_saved_records": len(saved),
            "calls_after_last_saved_record": len(leftover), "their_slot": stopped if leftover else None,
            "known_charge_usd": known, "unknown_charge_calls": len(unknown), "unsettled_requests": len(unsettled),
            "settled_calls": len(settled), "settled_bound_usd": total([number(c["settled_usd"]) for c in settled]),
            "total_charge_usd": known if not unknown and not unsettled and not settled else None,
            "reserved_bound_of_unknown_usd": total([number(c.get("reserved_usd")) for c in unknown + unsettled]),
            "blocked_reason": ledger.get("blocked_reason"),
            "account_usage_change_usd": minus(number(ledger.get("highwater_usage")), number(ledger.get("start_usage"))),
            "account_note": "the account lags the provider; a check on the summed charges, not the measure (LESSONS 6)"}


def slim(row):
    return {k: row.get(k) for k in ("slot", "code", "task", "condition", "repeat", "stage", "rerun", "disposition",
                                     "human_verdict", "human_note", "automatic_verdict", "automatic_reason")}


def trial_row(study, batch, key, human, score, keys, slot, entry, index):
    """One trial's row, primary or rerun: its disposition, its human and automatic verdicts and
    its measurements, each checked against what the review bound."""
    spec, record, status = entry["spec"], entry["record"], entry["status"]
    question = slot["question"]
    state, reason, void_kind = disposition(spec, record, status)
    row = {"index": index, "slot": slot["id"], "task": question["id"], "condition": slot["condition"],
           "repeat": slot["repeat"], "stage": spec.name, "attempt": spec.attempt, "rerun": not spec.primary,
           "clock_s": slot["clock_s"], "status": status["status"], "outcome": record and record["outcome"],
           "disposition": state, "disposition_reason": reason, "void_kind": void_kind, "code": None,
           "human_verdict": None, "human_note": None, "answer_names_an_arm": None, "full_path": None,
           "conversation_files": None, "reading": None, "automatic_verdict": None, "automatic_reason": None,
           **{field: None for field in MEASURES}, "charge_known_part_usd": None, "executor_charge_usd": None,
           "unknown_charge_calls": None, "settled_calls": 0, "settled_bound_usd": 0, "provider_calls": 0,
           "providers": {}, "no_response_settlements": 0, "clock_settlements": 0, "error_reply_settlements": 0,
           "record_sha256": None}
    if record is not None:
        path = str((entry["batch"]["results"] / (slot["id"] + ".json")).resolve())
        row["record_sha256"] = batch["inputs"][path]
        mapped = key["by_record"].get(path)
        require(mapped is not None and mapped["record_sha256"] == row["record_sha256"]
                and (mapped["slot"], mapped["task"], mapped["condition"], mapped["repeat"], mapped["stage"],
                     mapped["rerun"]) == (row["slot"], row["task"], row["condition"], row["repeat"], spec.stage,
                                          row["rerun"]),
                "The private key does not name this trial as the review bound it.")
        seen = blind.conversation(entry["batch"]["results"] / slot["id"])
        require(seen == mapped["conversation"], "A trial's conversation changed after preparation.")
        row.update(full_path=seen["full_path"], conversation_files=seen["files"])
        if mapped.get("code"):
            graded = human[mapped["code"]]
            task = batch["tasks"][question["id"]]
            require(graded["question"] == question["query"] and graded["answer"] == (record.get("answer") or "")
                    and json.loads(graded["key"]) == task["expect"],
                    "Reviewed evidence differs from its trial or its key.")
            row.update(code=mapped["code"], human_verdict=graded["hand_verdict"], human_note=graded["note"],
                       answer_names_an_arm=mapped["answer_names_an_arm"])
        row["reading"] = (record.get("box") or {}).get("reading")
        automatic = score.score_run(batch["tasks"][question["id"]], row["reading"], keys,
                                    record.get("answer") or "", record["outcome"] == "answered")
        row.update(automatic_verdict=automatic["verdict"], automatic_reason=automatic["why"], **measure(record))
    row["in_test"] = state in IN_TEST
    row["counted"] = counted(row) if row["in_test"] else None
    row["unscorable_answer"] = row["in_test"] and state == "answered" and row["human_verdict"] == "unscorable"
    return row


def analyse(study, bundle):
    bundle = Path(bundle)
    human_rows, manifest = completed_review(study, bundle)  # before the private key is opened
    key_path = bundle / "private-arm-key.json"
    require(blind.digest(key_path) == manifest["private_arm_key_sha256"], "The private key changed.")
    key = blind.read_json(key_path)
    require(key.get("study_id") == study.study_id
            and {name: sha for name, (_, sha) in key["stages"].items()} == manifest["stages_sha256"]
            and set(key["codes"]) == {r["code"] for r in human_rows}, "The private key does not cover the review.")
    for path, wanted in key["inputs"].items():
        require(blind.digest(path) == wanted, "A file bound at preparation changed.")
    batch = blind.load_study(study, {name: (Path(path), sha) for name, (path, sha) in key["stages"].items()})
    require(batch["inputs"] == key["inputs"], "The batch's files are not the set bound at preparation.")
    compare_cells, score = frozen_code([stage["config"] for stage in batch["stages"]])
    keys = score.keys_for(batch["repo"] / study.tasks_file)
    by_record = {mapped["record"]: {**mapped, "code": code} for code, mapped in key["codes"].items()}
    for mapped in key["off_sheet"]:
        require(mapped["outcome"] == CLOSED and mapped["record"] not in by_record, "An off-sheet trial is not a closure.")
        by_record[mapped["record"]] = {**mapped, "code": None, "answer_names_an_arm": None}
    saved = {str((entry["batch"]["results"] / (sid + ".json")).resolve())
             for kind in ("held", "reruns") for sid, entry in batch[kind].items() if entry["record"] is not None}
    require(len(by_record) == len(key["codes"]) + len(key["off_sheet"]) and set(by_record) == saved,
            "The review does not cover every saved trial exactly once.")
    key = {**key, "by_record": by_record}
    human = {r["code"]: r for r in human_rows}
    reruns = {}
    for index, slot in enumerate(batch["slots"]):
        entry = batch["reruns"].get(slot["id"])
        if entry:
            rerun_slot = next(s for s in entry["batch"]["slots"] if s["id"] == slot["id"])
            reruns[slot["id"]] = trial_row(study, batch, key, human, score, keys, rerun_slot, entry, index)
    rows = []
    for index, slot in enumerate(batch["slots"]):
        row = trial_row(study, batch, key, human, score, keys, slot, batch["held"][slot["id"]], index)
        row["rerun"] = reruns.get(slot["id"])
        rows.append(row)
    by_slot = {r["slot"]: r for r in rows}
    accounting = [reconcile(stage, by_slot if stage["spec"].primary else reruns) for stage in batch["stages"]]
    arms = {arm: arm_summary([r for r in rows if r["condition"] == arm]) for arm in transfer.ARMS}
    pairs = pair_rows(rows, study.task_ids, study.repeats)
    every = rows + list(reruns.values())
    graded = [r for r in every if r["human_verdict"]]
    sources = {**key["inputs"], **{str(p.resolve()): blind.digest(p) for p in (
        bundle / "manifest.json", key_path, bundle / "validated/reviewed.csv", bundle / "validated/validation.json")}}
    code = {name: blind.digest(ROOT / name) for name in (
        "tools/browser_use_fresh_analysis.py", "tools/browser_use_fresh_review.py", "tools/hand_review.py",
        "tools/hand_review.html", "experiments/analysis/score.py", "experiments/analysis/compare_cells.py",
        "experiments/runners/browser_use_transfer.py", *RAN_WITH)}
    stage_count = Counter(r["stage"] for r in rows if r["status"] != blind.NOT_STARTED)
    return {
        "study_id": study.study_id, "market": study.market,
        "stages": {stage["spec"].name: {"stage": stage["spec"].stage, "config_sha256": stage["config_sha256"],
                                        "head": stage["config"]["expected_head"], "status": stage["status"]["status"],
                                        "slots_given": len(stage["slots"]), "slots_run": stage["ran"]}
                   for stage in batch["stages"]},
        "plan": batch["config"]["analysis_plan_file"],
        "unit": "eight question types on one market; per arm, two attempts at each; trials, not a population of questions",
        "human_scoring": "the student's blind verdicts, validated before the private key was opened, kept as written",
        "automatic_scoring": {"version": score.VERSION, "role": "secondary; disagreements listed, never adjudicated here"},
        "primary_test": exact_test(compare_cells, rows, study.task_ids, leave_out_unscorable=False),
        "sensitivity": {**exact_test(compare_cells, rows, study.task_ids, leave_out_unscorable=True),
                        "role": "declared sensitivity, not a second primary: unscorable answers left out instead of counted 0"},
        "sensitivities": sensitivities(compare_cells, rows, study.task_ids),
        "timeouts_per_arm": {arm: {"timeouts": arms[arm]["timeouts"],
                                   "slots": [r["slot"] for r in rows if r["condition"] == arm and r["disposition"] == TIMEOUT]}
                             for arm in transfer.ARMS},
        "slots_run_by_stage": dict(stage_count),
        "settled_request_slots": [{**slim(r), "no_response_settlements": r["no_response_settlements"],
                                   "clock_settlements": r["clock_settlements"],
                                   "error_reply_settlements": r["error_reply_settlements"],
                                   "settled_bound_usd": r["settled_bound_usd"]}
                                  for r in every if r["no_response_settlements"] or r["clock_settlements"]
                                  or r["error_reply_settlements"]],
        "full_path_slots": {"count_primary": sum(bool(r["full_path"]) for r in rows),
                            "by_arm_primary": {arm: sum(bool(r["full_path"]) for r in rows if r["condition"] == arm)
                                               for arm in transfer.ARMS},
                            "slots": [slim(r) for r in every if r["full_path"]]},
        "arms": arms,
        "by_repeat": {str(repeat): {"arms": {arm: arm_summary([r for r in rows if r["condition"] == arm and r["repeat"] == repeat])
                                             for arm in transfer.ARMS},
                                    "pair_counts": pair_counts([p for p in pairs if p["repeat"] == repeat])}
                      for repeat in study.repeats},
        "pairs": pairs, "pair_counts": pair_counts(pairs),
        "reruns": {"role": "each timed-out slot run once more with its clock doubled (amendment 4). Never pooled "
                           "into a primary figure, used only by sensitivity 2",
                   "by_arm": {arm: {"rerun": sum(r["condition"] == arm for r in reruns.values()),
                                    "dispositions": dict(Counter(r["disposition"] for r in reruns.values()
                                                                 if r["condition"] == arm)),
                                    "correct": sum(bool(r["counted"]) for r in reruns.values() if r["condition"] == arm)}
                              for arm in transfer.ARMS},
                   "trials": list(reruns.values())},
        "disagreements": [slim(r) for r in graded if r["human_verdict"] != "unscorable"
                          and (r["human_verdict"] == "correct") != (r["automatic_verdict"] == "correct")],
        "human_unscorable": [slim(r) for r in graded if r["human_verdict"] == "unscorable"],
        # Rows whose count the disposition decides, whatever their grade: a failed or timed-out
        # trial graded correct or unscorable still counts 0, and stays in the sensitivity.
        "graded_but_decided_by_disposition": [slim(r) for r in graded if r["in_test"]
                                              and r["disposition"] != "answered" and r["human_verdict"] != "not correct"],
        # Rows the student may have read unblinded: the answer repeats a slot's arm label.
        "answers_naming_an_arm": [slim(r) for r in graded if r["answer_names_an_arm"]],
        "slots": [{k: v for k, v in r.items() if k != "rerun"} | {"rerun_disposition": (r["rerun"] or {}).get("disposition")}
                  for r in rows],
        "accounting": {"stages": accounting,
                       "known_charge_usd": total([a["known_charge_usd"] for a in accounting]),
                       "settled_bound_usd": total([a["settled_bound_usd"] for a in accounting]),
                       "unknown_charge_calls": sum(a["unknown_charge_calls"] for a in accounting),
                       "unsettled_requests": sum(a["unsettled_requests"] for a in accounting),
                       "total_charge_usd": total([a["total_charge_usd"] for a in accounting]),
                       "charge_in_test_usd": {arm: total([r["charge_usd"] for r in rows if r["in_test"] and r["condition"] == arm])
                                              for arm in transfer.ARMS}},
        "sources_sha256": sources, "code_sha256": code,
        "limits": [
            f"One market ({study.market['brand']}, seed {study.market['seed']}), one model, one agent setup: no "
            "pooling with Quenby or any other study, and no claim about other agents, models, markets or market "
            "generators.",
            "Two attempts per arm at each of eight questions: the evidence concerns these questions on this market "
            "under this configuration. A non-significant result is not evidence that the arms are equivalent.",
            "The arm order is balanced but fixed; the test assumes order has no effect. The slots ran in up to three "
            "attempts on one day, in their scheduled order, under one condition.",
            "Openings, script fetches and charges are descriptive. Browser Use's openings are not compared with "
            "openJiuwen's. Script fetches are never added to openings. A request settled at its bound has no "
            "provider charge, so a slot holding one has an unknown charge.",
            "Elapsed time runs from after the results-page read, which the runner does not time, to the record: "
            "the parser and the trial are included, the page read is not. Time to answer is not an outcome.",
            "The student's verdict judges the final commitment, not whether the evidence behind it was sufficient.",
        ]}


TABLE = ("slot", "task", "repeat", "condition", "stage", "disposition", "human_verdict", "counted", "automatic_verdict",
         "charge_usd", "parser_charge_usd", "unknown_charge_calls", "settled_calls", "openings", "script_fetches",
         "steps", "elapsed_with_parser_s", "full_path", "rerun_disposition", "disposition_reason", "human_note",
         "automatic_reason")


def main(study=blind.STUDY_A):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--table", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists() and not args.table.exists(), "Refusing to overwrite analysis outputs.")
        result = analyse(study, args.bundle)
        blind.write_json(args.output, result)
        with args.table.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=TABLE, delimiter="\t", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(result["slots"])
    except Refused as error:
        parser.exit(1, f"Analysis refused: {error}\n")
    except (ValueError, OSError, KeyError, TypeError, csv.Error) as error:
        parser.exit(1, f"Analysis refused ({type(error).__name__}); no conclusion should be drawn.\n")
    primary = result["primary_test"]
    print(json.dumps({
        "primary": {k: primary[k] for k in ("block_correct_of_trials", "baseline_correct_of_trials", "p",
                                            "decision", "slots_in_test", "complete_against_plan")},
        "sensitivities": {name: {k: view[k] for k in ("block_correct_of_trials", "baseline_correct_of_trials", "p")}
                          for name, view in result["sensitivities"].items()},
        "timeouts_per_arm": {arm: view["timeouts"] for arm, view in result["timeouts_per_arm"].items()},
        "arms": {arm: {k: s[k] for k in ("correct_of_scheduled", "correct_of_in_test", "dispositions")}
                 for arm, s in result["arms"].items()},
        "full_path_slots": result["full_path_slots"]["by_arm_primary"],
        "settled_request_slots": len(result["settled_request_slots"]),
        "pair_counts": result["pair_counts"], "disagreements": len(result["disagreements"]),
        "accounting": {k: result["accounting"][k] for k in ("total_charge_usd", "known_charge_usd", "settled_bound_usd",
                                                             "unknown_charge_calls", "unsettled_requests")}},
        indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
