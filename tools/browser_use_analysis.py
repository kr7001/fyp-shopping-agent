#!/usr/bin/env python3
"""Explicit, offline unblinding of the validated 1 November Browser Use review.

Human verdicts remain unchanged. The frozen v10 scorer is a separate secondary
measurement. This command never calls a model and never rewrites raw records.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from decimal import Decimal
import json
import math
from pathlib import Path
import statistics
import sys
from urllib.parse import urlsplit

import browser_use_review as blind

ROOT = Path(__file__).resolve().parents[1]
APPROVED_COMMIT = "4bdfe0fe286dfc9a976a12a4c32879366b698db9"
# Independently compared with git show APPROVED_COMMIT:<path> before unblinding.
SCORING_INPUTS = {
    "experiments/analysis/score.py": "8f9df93d3827245686b488111a284f9059d6f86cf71c102dbdd36165b719fc00",
    "experiments/tasks/tasks_tee_replication_28_oct.json": blind.TASKS_SHA256,
    "experiments/tasks/readings_tee_replication_28_oct.json": "2a6d2dcb0929aa1c015d209fc0c01ff01a4942ad3051a60fa4bcbbaab2c369ab",
    "env/fixtures/tee_replication_28_oct.json": "fddbfeb7d81d5aefc26cc631f15e90f943c17a5dd130cea4c1d696f55c6e8c49",
    "experiments/paths.py": "e4e0d303c120b4de4d0220fa9d73b1589c9d47d086c371225173188f08fff2fb",
}
require, digest, read_json = blind.require, blind.digest, blind.read_json


def completed_review(bundle):
    """Check completion and its receipt before any mapping/raw-record read."""
    bundle = Path(bundle)
    reviewed = bundle / "validated/reviewed.csv"
    require(blind.validate(bundle, reviewed) == (16, 16), "Complete all 16 human verdicts first.")
    receipt = read_json(bundle / "validated/validation.json")
    manifest = read_json(bundle / "manifest.json")
    require(receipt.get("study_id") == blind.STUDY and receipt.get("complete") is True
            and receipt.get("rows") == 16 and receipt.get("arm_key_read") is False
            and receipt.get("scored") is False, "Missing pre-unblinding validation receipt.")
    require(receipt.get("reviewed_sha256") == digest(reviewed)
            and receipt.get("original_sheet_sha256") == manifest["original_sheet_sha256"],
            "Validated review changed after the receipt.")
    return blind.review.read_sheet(reviewed)


def amount(value, label):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0, f"Invalid or missing {label}.")
    return Decimal(str(value))


def close(a, b, label):
    require(abs(a - b) <= Decimal("0.000000001"), f"Accounting mismatch: {label}.")


def url_identity(url):
    parsed = urlsplit(url)
    require(parsed.scheme in ("http", "https") and parsed.hostname
            and not parsed.username and not parsed.password, "Invalid observed URL.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return (f"{parsed.scheme}://{parsed.hostname.lower()}:{port}" + (parsed.path or "/")
            + ("?" + parsed.query if parsed.query else ""))


def measure_record(record):
    """Reconcile saved measurement evidence without relying on answer claims."""
    calls = record["calls"]
    require(isinstance(calls, list) and calls, "Missing provider call records.")
    require(all(c.get("role") in ("executor", "parser") for c in calls), "Unknown call role.")
    charges = [amount(c.get("cost_usd"), "call charge") for c in calls]
    total = sum(charges, Decimal(0))
    parser = sum((v for c, v in zip(calls, charges) if c["role"] == "parser"), Decimal(0))
    executor = total - parser
    close(total, amount(record.get("total_cost_usd"), "trial charge"), "all calls")
    close(parser, amount(record.get("parse_cost_usd"), "parser charge"), "parser calls")
    close(executor, amount(record.get("cost_usd"), "executor charge"), "executor calls")
    trace = record["trace"]
    require(trace.get("measurement_valid") is True and not trace.get("observation_errors"),
            "Invalid navigation measurements.")
    candidates = {url_identity(item["url"]) for item in record["page"]["listings"]}
    urls = [url_identity(url) for url in trace["opened_urls"]]
    require(len(set(urls)) == len(urls) == trace["opened"] and set(urls) <= candidates,
            "Opened count or candidate membership mismatch.")
    observed = set()
    for event in trace["navigation_events"]:
        candidate = url_identity(event["url"]) in candidates
        product = (event.get("main_document") is True and 200 <= event["status"] < 300
                   and event.get("product_document") is True)
        counted = candidate and product
        require(event.get("candidate") == candidate and event.get("counted") == counted,
                "Navigation evidence disagrees with recorded membership/success.")
        if counted:
            observed.add(url_identity(event["url"]))
    require(observed == set(urls), "Opened URLs disagree with navigation events.")
    require(type(record.get("steps")) is int and record["steps"] >= 0, "Invalid step count.")
    elapsed = amount(record.get("elapsed_with_parser_s"), "elapsed time")
    return {"openings": len(urls), "total_cost_usd": float(total),
            "executor_cost_usd": float(executor), "parser_cost_usd": float(parser),
            "steps": record["steps"], "elapsed_s": float(elapsed),
            "error_count": sum(bool(error) for error in record.get("agent_errors", [])),
            "provider_calls": len(calls), "providers": dict(Counter(c.get("provider") for c in calls))}


def summarize(rows):
    expected = {(task, arm) for task in blind.TASK_IDS for arm in ("baseline", "block")}
    require(len(rows) == 16 and {(r["task"], r["condition"]) for r in rows} == expected,
            "Analysis must contain exactly the sixteen formal slots.")
    arms = {}
    for arm in ("baseline", "block"):
        selected = [r for r in rows if r["condition"] == arm]
        human = Counter(r["human_verdict"] for r in selected)
        auto = Counter(r["automatic_verdict"] for r in selected)
        arms[arm] = {"scheduled": 8, "human": dict(human), "automatic": dict(auto),
                     "human_assessable": 8 - human["unscorable"],
                     "human_correct": human["correct"],
                     "total_cost_usd": float(sum((Decimal(str(r["total_cost_usd"])) for r in selected), Decimal(0))),
                     "executor_cost_usd": float(sum((Decimal(str(r["executor_cost_usd"])) for r in selected), Decimal(0))),
                     "parser_cost_usd": float(sum((Decimal(str(r["parser_cost_usd"])) for r in selected), Decimal(0))),
                     "total_openings": sum(r["openings"] for r in selected),
                     "median_openings": statistics.median(r["openings"] for r in selected),
                     "median_cost_usd": statistics.median(r["total_cost_usd"] for r in selected),
                     "total_steps": sum(r["steps"] for r in selected),
                     "total_elapsed_s": sum(r["elapsed_s"] for r in selected),
                     "total_error_events": sum(r["error_count"] for r in selected)}
    paired = []
    for task in blind.TASK_IDS:
        pair = {r["condition"]: r for r in rows if r["task"] == task}
        baseline, block = pair["baseline"], pair["block"]
        paired.append({"task": task,
                       "human_baseline": baseline["human_verdict"], "human_block": block["human_verdict"],
                       "automatic_baseline": baseline["automatic_verdict"], "automatic_block": block["automatic_verdict"],
                       "openings_baseline": baseline["openings"], "openings_block": block["openings"],
                       "cost_baseline_usd": baseline["total_cost_usd"], "cost_block_usd": block["total_cost_usd"],
                       "opening_difference_block_minus_baseline": block["openings"] - baseline["openings"],
                       "cost_difference_block_minus_baseline_usd": block["total_cost_usd"] - baseline["total_cost_usd"]})
    discrepancies = [r for r in rows if (r["human_verdict"] == "correct") != (r["automatic_verdict"] == "correct")
                     or r["human_verdict"] == "unscorable"]
    return {"arms": arms, "paired": paired, "disagreements": discrepancies,
            "block_cheaper_pairs": sum(p["cost_difference_block_minus_baseline_usd"] < 0 for p in paired),
            "block_fewer_openings_pairs": sum(p["opening_difference_block_minus_baseline"] < 0 for p in paired),
            "equal_openings_pairs": sum(p["opening_difference_block_minus_baseline"] == 0 for p in paired),
            "block_cost_reduction_fraction": 1 - arms["block"]["total_cost_usd"] / arms["baseline"]["total_cost_usd"]}


def analyse(bundle):
    bundle = Path(bundle)
    human_rows = completed_review(bundle)  # Must run before opening mapping/scorer.
    manifest = read_json(bundle / "manifest.json")
    key_path = bundle / "private-arm-key.json"
    require(digest(key_path) == manifest["private_arm_key_sha256"], "Private mapping changed.")
    mapping = read_json(key_path)
    require(mapping.get("study_id") == blind.STUDY and set(mapping["codes"]) == {r["code"] for r in human_rows},
            "Review mapping has missing or foreign codes.")
    for path, wanted in mapping["inputs"].items():
        require(digest(path) == wanted, "A bound original input changed.")
    for path, wanted in SCORING_INPUTS.items():
        require(digest(ROOT / path) == wanted, "A frozen scoring input changed.")
    sys.path.insert(0, str(ROOT / "experiments"))
    import paths  # noqa: F401
    import score
    require(score.VERSION == 10, "Expected frozen scorer v10.")
    task_path = ROOT / "experiments/tasks/tasks_tee_replication_28_oct.json"
    task_spec = read_json(task_path)
    tasks = {t["id"]: t for t in task_spec["tasks"]}
    keys = score.keys_for(task_path)
    configs = [Path(p) for p in mapping["inputs"] if Path(p).name == "monitored-command-1-nov.json"]
    require(len(configs) == 1 and digest(configs[0]) == blind.CONFIG_SHA256, "Wrong execution configuration.")
    config = read_json(configs[0])
    rows, seen, generation_ids = [], set(), set()
    for human in human_rows:
        mapped = mapping["codes"][human["code"]]
        record_path = Path(mapped["record"])
        require(digest(record_path) == mapped["record_sha256"], "Trial record checksum changed.")
        record = read_json(record_path)
        task = tasks[mapped["task"]]
        identity = (mapped["task"], mapped["condition"], mapped["repeat"])
        require(identity not in seen and identity[0] in blind.TASK_IDS and identity[1] in ("baseline", "block")
                and identity[2] == 1, "Duplicate or foreign trial identity.")
        seen.add(identity)
        require(all(record.get(k) == v for k, v in {
            "study_id": blind.STUDY, "stage": "monitored-transfer", "phase": "transfer",
            "task": mapped["task"], "condition": mapped["condition"], "repeat": 1, "slot": mapped["slot"],
            "scaffold": "browser-use", "browser_use_version": "0.13.14", "model": config["model"],
            "provider_routing": config["provider"], "outcome": "answered",
            "dropdown_semantics": "native-disabled-state-v1", "evaluate_semantics": "fresh-local-script-scope-v1",
        }.items()), "Trial condition does not match the frozen monitored design.")
        require(record["answer"] == human["answer"] and record["question"] == human["question"]
                == task["query"].format(base=task_spec["base_url"])
                and json.loads(human["key"]) == task["expect"], "Reviewed evidence differs from its original trial/key.")
        for setting in ("temperature", "frequency_penalty", "top_p", "max_steps", "max_failures",
                        "max_input_bytes", "max_output_tokens", "clock_s"):
            require(record["settings"].get(setting) == config.get(setting), "Execution settings differ across slots.")
        for call in record["calls"]:
            identifier = call.get("generation_id")
            require(identifier and identifier not in generation_ids, "Missing/duplicate provider generation ID.")
            generation_ids.add(identifier)
        reading = (record.get("box") or {}).get("reading")
        require(score.run_key(task, reading, keys) == task["expect"], "Unexpected reading-specific answer key.")
        auto = score.score_run(task, reading, keys, record["answer"], record["outcome"] == "answered")
        rows.append({"code": human["code"], "task": mapped["task"], "condition": mapped["condition"],
                     "repeat": 1, "human_verdict": human["hand_verdict"], "human_note": human["note"],
                     "automatic_verdict": auto["verdict"], "automatic_reason": auto["why"],
                     "outcome": record["outcome"], **measure_record(record)})
    rows.sort(key=lambda r: (blind.TASK_IDS.index(r["task"]), r["condition"]))
    summary = summarize(rows)
    # The status total includes diagnostics; do not mislabel it as formal spend.
    status_path = configs[0].with_name("monitored-1-nov.status.json")
    status = read_json(status_path)
    formal_charge = sum((Decimal(str(r["total_cost_usd"])) for r in rows), Decimal(0))
    diagnostic_charge = Decimal(0)
    diagnostic_count = 0
    results = configs[0].parent / "monitored-1-nov.results"
    schedule = read_json(results / "schedule.json")
    for slot in schedule["slots"]:
        if slot.get("phase") == "pilot":
            # Read accounting fields only; diagnostic answers are never scored here.
            record = read_json(results / (slot["id"] + ".json"))
            charged = sum((amount(c.get("cost_usd"), "diagnostic charge") for c in record["calls"]), Decimal(0))
            close(charged, amount(record.get("total_cost_usd"), "diagnostic total"), "diagnostic calls")
            diagnostic_charge += charged
            diagnostic_count += 1
    close(formal_charge + diagnostic_charge, amount(status["charged_usd"], "monitored status total"), "monitored total")
    return {"study_id": blind.STUDY, "condition": "monitored-1-nov", "approved_commit": APPROVED_COMMIT,
            "unit": "eight fixed Quenby questions, one trial per condition per question",
            "human_scoring": "student blind review, completed and validated before unblinding",
            "automatic_scoring": {"version": score.VERSION, "role": "secondary, retained separately",
                                  "input_sha256": SCORING_INPUTS},
            "reviewed_sha256": digest(bundle / "validated/reviewed.csv"),
            "validation_sha256": digest(bundle / "validated/validation.json"),
            "mapping_sha256": digest(key_path), "analysis_script_sha256": digest(Path(__file__)),
            "source_sha256": mapping["inputs"], "rows": rows, **summary,
            "operational_accounting": {"formal_trials": 16, "formal_charge_usd": float(formal_charge),
                 "diagnostic_trials": diagnostic_count, "diagnostic_charge_usd": float(diagnostic_charge),
                 "new_monitored_charge_usd": status["charged_usd"], "conservative_prior_carryover_usd": status["carryover_usd"],
                 "conservative_all_attempts_upper_usd": status["shared_cost_upper_usd"]},
            "limits": ["Descriptive exploratory fixed-market transfer; no significance test or post-hoc repeat selection.",
                       "Human final-commitment correctness does not certify observation sufficiency.",
                       "Unique successful product navigations do not count every DOM read, same-origin fetch or hidden-data access.",
                       "One framework/model/market and one trial per pair; no pooling with prior studies."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--table", type=Path, required=True)
    args = parser.parse_args()
    try:
        require(not args.output.exists() and not args.table.exists(), "Refusing to overwrite analysis outputs.")
        result = analyse(args.bundle)
        blind.write_json(args.output, result)
        fields = ["task", "condition", "human_verdict", "automatic_verdict", "openings", "total_cost_usd",
                  "executor_cost_usd", "parser_cost_usd", "steps", "elapsed_s", "error_count", "human_note", "automatic_reason"]
        with args.table.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(result["rows"])
        print(json.dumps({k: result[k] for k in ("arms", "operational_accounting")}, indent=2))
        print(f"Human/automatic disagreements: {len(result['disagreements'])}")
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.exit(1, f"Analysis refused: {error}\n")


if __name__ == "__main__":
    main()
