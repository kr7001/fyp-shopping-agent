#!/usr/bin/env python3
"""Study A's pre-registered analysis, offline, once its blind review is complete and validated.

It refuses to run until browser_use_fresh_review.py has validated a complete review of every
row on the sheet (32 of 32 when every slot ran) and written its receipt, and only then opens
the private key. It computes what notes/fresh-market-2-nov/analysis-plan-A.md pre-registers:

- each of the 32 slots' disposition: answered, failed, timeout, closed by the block, technical
  void or not started, the voids by the launcher's frozen classification
  (`browser_use_transfer.validate_pilot_record`) or the guard's stop;
- the one primary test, `compare_cells.stratified_exact` with one stratum per question type, on
  every slot the agent ran, a slot counting 1 only when the student graded its committed answer
  correct, voids and slots not started left out and listed; and the declared sensitivity, the
  same test with unscorable answers left out;
- the descriptive results, per slot, per question pair, per arm and per repeat: the human
  verdict, the frozen v10 score (secondary) and every disagreement, the provider's charge with
  the parser's share, listings opened by navigation (the cohort's validated counter), product
  pages fetched by script (browser_use_fetches.py), steps and elapsed time.

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
import browser_use_transfer as transfer  # noqa: E402  (the launcher's frozen classification)

require, Refused = blind.require, blind.Refused
CLOSED, VOID, NOT_STARTED = blind.CLOSED, "technical void", "not started"
IN_TEST = ("answered", "failed", "timeout", CLOSED)  # "every slot in which the agent ran"
ALPHA = 0.05
# The frozen code the analysis runs, pinned at b1c67c8 (2 November 2026): the v10 scorer's
# file, as browser_use_analysis.SCORING_INPUTS pins it, and the source text of the test and the
# classification, read with ast as guarded_browser_use.agent_facing_digests reads its own.
SCORE_SHA256 = "8f9df93d3827245686b488111a284f9059d6f86cf71c102dbdd36165b719fc00"
FUNCTIONS = {("experiments/analysis/compare_cells.py", "stratified_exact"):
             "81508a0f0c88525cf134942d6855eedea86cd714b6a7405317501a9aedf41d55",
             ("experiments/runners/browser_use_transfer.py", "validate_pilot_record"):
             "c3b5b6b55ebec86f055ad90a65aae6ad8332bb98a87114b96580412a7ec35a7c"}
# The adapter, listener, runner and import paths whose records and URL identity this reads,
# held to the hashes the batch's own configuration bound when it ran.
RAN_WITH = ("experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py",
            "experiments/runners/browser_use_transfer.py", "experiments/paths.py")
SCRIPT_KINDS = ("fetch", "xhr", "subframe-document")  # browser_use_fetches.ScriptFetches.observe
MEASURES = ("charge_usd", "parser_charge_usd", "openings", "script_fetches", "steps", "elapsed_with_parser_s")


def function_digest(path, name):
    source = Path(path).read_text()
    found = [node for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef) and node.name == name]
    require(len(found) == 1, f"{name} is not defined once in {Path(path).name}.")
    return hashlib.sha256(ast.get_source_segment(source, found[0]).encode()).hexdigest()


def frozen_code(config):
    """Check the code before any of it is used, then import the scorer and the test."""
    require(blind.digest(ROOT / "experiments/analysis/score.py") == SCORE_SHA256, "The v10 scorer changed.")
    for (name, function), wanted in FUNCTIONS.items():
        require(function_digest(ROOT / name, function) == wanted, f"{function} in {name} changed.")
    for name in RAN_WITH:
        require(blind.digest(ROOT / name) == config["hashes"].get(name),
                f"{name} differs from the file the batch ran with.")
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
    charge leaves its total unknown, never zero."""
    require(all(call.get("role") in ("parser", "executor") for call in calls), "A call has an unknown role.")
    costs = [number(call.get("cost_usd")) for call in calls]
    parser = [c for call, c in zip(calls, costs) if call["role"] == "parser"]
    executor = [c for call, c in zip(calls, costs) if call["role"] == "executor"]
    return {"charge_usd": total(costs), "parser_charge_usd": total(parser), "executor_charge_usd": total(executor),
            "charge_known_part_usd": total([c for c in costs if c is not None]),
            "unknown_charge_calls": sum(c is None for c in costs), "provider_calls": len(calls),
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
    # null executor sum for a trial that made no executor call, so a null is not compared.
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
            "agent_error_count": sum(bool(error) for error in record.get("agent_errors") or [])}


def reached_clock(record):
    elapsed, clock = number(record.get("elapsed_s")), number((record.get("settings") or {}).get("clock_s"))
    return elapsed is not None and clock is not None and elapsed >= clock


def disposition(record, status):
    """A slot's disposition under analysis-plan-A.md, and why when it is not the record's own
    outcome. A technical void is a record the launcher's frozen classification stops on, or a
    slot the guard stopped while it ran."""
    if record is None:
        if status["status"] == blind.NOT_STARTED:
            return NOT_STARTED, "not started: " + str(status.get("reason") or "the batch ended before it")
        return VOID, f"the guard stopped the slot while it ran ({status['status']}): {status.get('reason')}"
    try:
        transfer.validate_pilot_record(record, "transfer")
        return record["outcome"], None
    except transfer.Stop as stop:
        reason = str(stop)
    # The adapter never sets `timeout_kind`, so the frozen classification stops on every
    # timeout as "unclassified". The plan's "timeout (the 2700 s trial clock)" is a timeout
    # whose own elapsed time reached its trial clock, with nothing else the classification
    # stops on (2 November 2026, before any Study A trial ran).
    if record["outcome"] == "timeout" and reached_clock(record):
        try:
            transfer.validate_pilot_record({**record, "timeout_kind": "trial_clock"}, "transfer")
            return "timeout", (f"the trial clock: {record['elapsed_s']:.0f} s against "
                               f"{record['settings']['clock_s']} s; the frozen classification stops on any "
                               f"timeout, as it cannot tell a trial-clock one ({reason})")
        except transfer.Stop as stop:
            reason = str(stop)
    return VOID, "the frozen classification: " + reason


def counted(row):
    """1 only when the student graded the slot correct and the agent committed a final answer:
    failed (no final answer), timeout and closure count 0 whatever their row was graded."""
    return int(row["disposition"] == "answered" and row["human_verdict"] == "correct")


def exact_test(compare_cells, rows, task_ids, leave_out_unscorable):
    """The plan's primary test, or with `leave_out_unscorable` its declared sensitivity."""
    used = [r for r in rows if r["in_test"] and not (leave_out_unscorable and r["unscorable_answer"])]
    strata, shown = [], []
    for task in task_ids:
        block = [r for r in used if r["task"] == task and r["condition"] == "block"]
        baseline = [r for r in used if r["task"] == task and r["condition"] == "baseline"]
        stratum = (sum(r["counted"] for r in block), len(block), sum(r["counted"] for r in baseline), len(baseline))
        strata.append(stratum)
        correct, trials = stratum[0] + stratum[2], stratum[1] + stratum[3]
        shown.append({"task": task, "block_correct": stratum[0], "block_trials": stratum[1],
                      "baseline_correct": stratum[2], "baseline_trials": stratum[3],
                      "informative": bool(stratum[1] and stratum[3] and 0 < correct < trials)})
    p = compare_cells.stratified_exact(strata)
    block = [sum(s[0] for s in strata), sum(s[1] for s in strata)]
    baseline = [sum(s[2] for s in strata), sum(s[3] for s in strata)]
    if p < ALPHA and block[0] != baseline[0]:
        decision = (f"difference claimed: the {'block' if block[0] > baseline[0] else 'baseline'} arm "
                    f"answered correctly more often (p < {ALPHA})")
    elif p < ALPHA:
        decision = f"p < {ALPHA} but the arms' total correct counts are equal: no direction, so no claim"
    else:
        decision = f"no difference claimed (p >= {ALPHA}); this is not evidence that the arms are equivalent"
    kept = {r["slot"] for r in used}
    left = [{"slot": r["slot"], "disposition": r["disposition"],
             "reason": "unscorable answer" if r["in_test"] else r["disposition_reason"]}
            for r in rows if r["slot"] not in kept]
    return {"test": "compare_cells.stratified_exact, one stratum per question type, two-sided",
            "strata": shown, "block_correct_of_trials": block, "baseline_correct_of_trials": baseline,
            "p": p, "alpha": ALPHA, "decision": decision, "slots_in_test": len(used),
            "planned_slots": len(rows), "complete_against_plan": not left, "left_out": left}


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
    """Every saved record's calls, in schedule order, are the ledger's first entries, unchanged;
    the calls after them belong to the slot the batch stopped in. Unknown charges and unsettled
    requests keep the batch total unknown."""
    ledger, slots = batch["ledger"], batch["slots"]
    calls = ledger["calls"]
    saved = [call for slot in slots for call in (batch["records"].get(slot["id"]) or {}).get("calls", [])]
    reservations = [call.get("reservation") for call in calls]
    require(all(isinstance(r, str) for r in reservations) and len(set(reservations)) == len(reservations),
            "The ledger's reservations are missing or repeated.")
    require(calls[:len(saved)] == saved, "A saved trial's calls are not the ledger's own, in order.")
    leftover = calls[len(saved):]
    ran = len(batch["records"])
    stopped = slots[ran]["id"] if ran < len(slots) else None
    require(not leftover or (stopped and batch["statuses"][stopped]["status"] in blind.GUARD_STOPPED),
            "The ledger holds calls no slot can account for.")
    known = total([number(c.get("cost_usd")) for c in calls if number(c.get("cost_usd")) is not None])
    close(known, number(ledger.get("charged_usd")), "the ledger's charged total")
    if batch["status"]["status"] == "complete":
        close(known, number(batch["status"].get("charged_usd")), "the launcher's completed status")
    unknown = [c for c in calls if number(c.get("cost_usd")) is None]
    unsettled = list((ledger.get("inflight") or {}).values())
    if leftover:
        row = next(r for r in rows if r["slot"] == stopped)
        row.update(charges(leftover), charges_basis="the ledger's calls after the last saved record")
    in_test = [r for r in rows if r["in_test"]]
    return {"ledger_calls": len(calls), "calls_in_saved_records": len(saved),
            "calls_after_last_saved_record": len(leftover), "their_slot": stopped if leftover else None,
            "known_charge_usd": known, "unknown_charge_calls": len(unknown), "unsettled_requests": len(unsettled),
            "total_charge_usd": known if not unknown and not unsettled else None,
            "reserved_bound_of_unknown_usd": total([number(c.get("reserved_usd")) for c in unknown + unsettled]),
            "charge_in_test_usd": {arm: total([r["charge_usd"] for r in in_test if r["condition"] == arm])
                                   for arm in transfer.ARMS},
            "known_charge_outside_test_usd": total([r["charge_usd"] for r in rows
                                                     if not r["in_test"] and r["charge_usd"] is not None]),
            "blocked_reason": ledger.get("blocked_reason"), "batch_status": batch["status"]["status"],
            "batch_stop_reason": batch["status"].get("reason"),
            "account_usage_change_usd": minus(number(ledger.get("highwater_usage")), number(ledger.get("start_usage"))),
            "account_note": "the account lags the provider; a check on the summed charges, not the measure (LESSONS 6)",
            "cap_usd": batch["config"]["cap_usd"], "estimate_usd": batch["config"]["estimate_usd"]}


def slim(row):
    return {k: row[k] for k in ("slot", "code", "task", "condition", "repeat", "disposition", "human_verdict",
                                "human_note", "automatic_verdict", "automatic_reason")}


def analyse(study, bundle):
    bundle = Path(bundle)
    human_rows, manifest = completed_review(study, bundle)  # before the private key is opened
    key_path = bundle / "private-arm-key.json"
    require(blind.digest(key_path) == manifest["private_arm_key_sha256"], "The private key changed.")
    key = blind.read_json(key_path)
    require(key.get("study_id") == study.study_id and key.get("config_sha256") == manifest["config_sha256"]
            and set(key["codes"]) == {r["code"] for r in human_rows}, "The private key does not cover the review.")
    for path, wanted in key["inputs"].items():
        require(blind.digest(path) == wanted, "A file bound at preparation changed.")
    batch = blind.load_batch(study, key["config"], key["config_sha256"])
    require(batch["inputs"] == key["inputs"], "The batch's files are not the set bound at preparation.")
    compare_cells, score = frozen_code(batch["config"])
    task_path = batch["repo"] / study.tasks_file
    keys = score.keys_for(task_path)
    results = Path(batch["config"]["output_dir"]).resolve()
    on_sheet = {mapped["slot"]: (code, mapped) for code, mapped in key["codes"].items()}
    closed = {sid for sid, record in batch["records"].items() if record["outcome"] == CLOSED}
    require(len(on_sheet) == len(key["codes"]) and set(on_sheet) == set(batch["records"]) - closed
            and set(key["off_sheet"]) == closed, "The review does not cover every saved trial exactly once.")
    human = {r["code"]: r for r in human_rows}
    rows = []
    for index, slot in enumerate(batch["slots"]):
        sid, question = slot["id"], slot["question"]
        record, status = batch["records"].get(sid), batch["statuses"][sid]
        state, reason = disposition(record, status)
        row = {"index": index, "slot": sid, "task": question["id"], "condition": slot["condition"],
               "repeat": slot["repeat"], "status": status["status"], "outcome": record and record["outcome"],
               "disposition": state, "disposition_reason": reason, "code": None, "human_verdict": None,
               "human_note": None, "answer_names_an_arm": None, "reading": None, "automatic_verdict": None,
               "automatic_reason": None,
               **{field: None for field in MEASURES}, "charge_known_part_usd": None, "executor_charge_usd": None,
               "unknown_charge_calls": None, "provider_calls": 0, "providers": {}, "record_sha256": None}
        if record is not None:
            path = str((results / (sid + ".json")).resolve())
            row["record_sha256"] = batch["inputs"][path]
            if sid in on_sheet:
                code, mapped = on_sheet[sid]
                graded = human[code]
                task = batch["tasks"][question["id"]]
                require(mapped["record"] == path and mapped["record_sha256"] == row["record_sha256"]
                        and (mapped["task"], mapped["condition"], mapped["repeat"]) == (row["task"], row["condition"], row["repeat"])
                        and graded["question"] == question["query"] and graded["answer"] == (record.get("answer") or "")
                        and json.loads(graded["key"]) == task["expect"],
                        "Reviewed evidence differs from its trial or its key.")
                row.update(code=code, human_verdict=graded["hand_verdict"], human_note=graded["note"],
                           answer_names_an_arm=mapped["answer_names_an_arm"])
            row["reading"] = (record.get("box") or {}).get("reading")
            automatic = score.score_run(batch["tasks"][question["id"]], row["reading"], keys,
                                        record.get("answer") or "", record["outcome"] == "answered")
            row.update(automatic_verdict=automatic["verdict"], automatic_reason=automatic["why"], **measure(record))
        row["in_test"] = state in IN_TEST
        row["counted"] = counted(row) if row["in_test"] else None
        row["unscorable_answer"] = row["in_test"] and state == "answered" and row["human_verdict"] == "unscorable"
        rows.append(row)
    accounting = reconcile(batch, rows)
    arms = {arm: arm_summary([r for r in rows if r["condition"] == arm]) for arm in transfer.ARMS}
    pairs = pair_rows(rows, study.task_ids, study.repeats)
    graded = [r for r in rows if r["human_verdict"]]
    sources = {**key["inputs"], **{str(p.resolve()): blind.digest(p) for p in (
        bundle / "manifest.json", key_path, bundle / "validated/reviewed.csv", bundle / "validated/validation.json")}}
    code = {name: blind.digest(ROOT / name) for name in (
        "tools/browser_use_fresh_analysis.py", "tools/browser_use_fresh_review.py", "tools/hand_review.py",
        "tools/hand_review.html", "experiments/analysis/score.py", "experiments/analysis/compare_cells.py", *RAN_WITH)}
    return {
        "study_id": study.study_id, "stage": study.stage, "config_sha256": key["config_sha256"],
        "head": batch["config"]["expected_head"], "market": study.market,
        "plan": batch["config"]["analysis_plan_file"],
        "unit": "eight question types on one market; per arm, two attempts at each; trials, not a population of questions",
        "human_scoring": "the student's blind verdicts, validated before the private key was opened, kept as written",
        "automatic_scoring": {"version": score.VERSION, "role": "secondary; disagreements listed, never adjudicated here"},
        "primary_test": exact_test(compare_cells, rows, study.task_ids, leave_out_unscorable=False),
        "sensitivity": {**exact_test(compare_cells, rows, study.task_ids, leave_out_unscorable=True),
                        "role": "declared sensitivity, not a second primary: unscorable answers left out instead of counted 0"},
        "arms": arms,
        "by_repeat": {str(repeat): {"arms": {arm: arm_summary([r for r in rows if r["condition"] == arm and r["repeat"] == repeat])
                                             for arm in transfer.ARMS},
                                    "pair_counts": pair_counts([p for p in pairs if p["repeat"] == repeat])}
                      for repeat in study.repeats},
        "pairs": pairs, "pair_counts": pair_counts(pairs),
        "disagreements": [slim(r) for r in graded if r["human_verdict"] != "unscorable"
                          and (r["human_verdict"] == "correct") != (r["automatic_verdict"] == "correct")],
        "human_unscorable": [slim(r) for r in graded if r["human_verdict"] == "unscorable"],
        # Rows whose count the disposition decides, whatever their grade: a failed or timed-out
        # trial graded correct or unscorable still counts 0, and stays in the sensitivity.
        "graded_but_decided_by_disposition": [slim(r) for r in graded if r["in_test"]
                                              and r["disposition"] != "answered" and r["human_verdict"] != "not correct"],
        # Rows the student may have read unblinded: the answer repeats a slot's arm label.
        "answers_naming_an_arm": [slim(r) for r in graded if r["answer_names_an_arm"]],
        "slots": rows, "accounting": accounting,
        "sources_sha256": sources, "code_sha256": code,
        "limits": [
            f"One market ({study.market['brand']}, seed {study.market['seed']}), one model, one agent setup: no "
            "pooling with Quenby or any other study, and no claim about other agents, models, markets or market "
            "generators.",
            "Two attempts per arm at each of eight questions: the evidence concerns these questions on this market "
            "under this configuration. A non-significant result is not evidence that the arms are equivalent.",
            "The arm order is balanced but fixed; the test assumes order has no effect.",
            "Openings, script fetches and charges are descriptive. Browser Use's openings are not compared with "
            "openJiuwen's. Script fetches are never added to openings.",
            "Elapsed time runs from after the results-page read, which the runner does not time, to the record: "
            "the parser and the trial are included, the page read is not.",
            "The student's verdict judges the final commitment, not whether the evidence behind it was sufficient.",
        ]}


TABLE = ("slot", "task", "repeat", "condition", "disposition", "human_verdict", "counted", "automatic_verdict",
         "charge_usd", "parser_charge_usd", "unknown_charge_calls", "openings", "script_fetches", "steps",
         "elapsed_with_parser_s", "disposition_reason", "human_note", "automatic_reason")


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
    primary, sensitivity = result["primary_test"], result["sensitivity"]
    print(json.dumps({
        "primary": {k: primary[k] for k in ("block_correct_of_trials", "baseline_correct_of_trials", "p",
                                            "decision", "slots_in_test", "complete_against_plan")},
        "sensitivity": {k: sensitivity[k] for k in ("block_correct_of_trials", "baseline_correct_of_trials", "p")},
        "arms": {arm: {k: s[k] for k in ("correct_of_scheduled", "correct_of_in_test", "dispositions")}
                 for arm, s in result["arms"].items()},
        "pair_counts": result["pair_counts"], "disagreements": len(result["disagreements"]),
        "accounting": {k: result["accounting"][k] for k in ("total_charge_usd", "known_charge_usd",
                                                             "unknown_charge_calls", "unsettled_requests")}},
        indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
