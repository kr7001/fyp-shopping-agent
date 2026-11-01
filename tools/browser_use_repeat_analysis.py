#!/usr/bin/env python3
"""Offline descriptive analysis of validated repeats 2 and 3; no pooled old trials.

The student's verdicts remain unchanged. Frozen v10 scores are secondary.
Generation identifiers, both attempt ledgers and bound source evidence reconcile
before any output is written. No model calls, shop requests or significance tests.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
from decimal import Decimal
import json
from pathlib import Path
import statistics
import sys

import browser_use_analysis as original
import browser_use_repeat_review as blind

ROOT = original.ROOT
require, digest, read_json = blind.require, blind.digest, blind.read_json
amount, close = original.amount, original.close


def completed_review(bundle):
    bundle = Path(bundle)
    reviewed = bundle / "validated/reviewed.csv"
    require(blind.validate(bundle, reviewed) == (32, 32), "Complete all 32 human verdicts first.")
    receipt = read_json(bundle / "validated/validation.json")
    manifest = read_json(bundle / "manifest.json")
    require(receipt.get("study_id") == blind.STUDY and receipt.get("batch_id") == blind.BATCH
            and receipt.get("complete") is True and receipt.get("rows") == 32
            and receipt.get("arm_key_read") is False and receipt.get("scored") is False,
            "Missing pre-unblinding validation receipt.")
    require(receipt.get("reviewed_sha256") == digest(reviewed)
            and receipt.get("original_sheet_sha256") == manifest["original_sheet_sha256"],
            "Validated review changed after the receipt.")
    return blind.review.read_sheet(reviewed)


def measure_record(record):
    # Costs must remain reconciled even when navigation evidence is unavailable.
    calls = record["calls"]
    require(isinstance(calls, list) and calls, "Missing provider calls.")
    require(all(c.get("role") in ("parser", "executor") for c in calls), "Unknown call role.")
    total = sum((amount(c.get("cost_usd"), "call charge") for c in calls), Decimal(0))
    parser = sum((amount(c["cost_usd"], "parser charge") for c in calls if c["role"] == "parser"), Decimal(0))
    for observed, field in ((total, "total_cost_usd"), (parser, "parse_cost_usd"), (total-parser, "cost_usd")):
        close(observed, amount(record.get(field), field), field)
    trace = record.get("trace") or {}
    valid = trace.get("measurement_valid") is True and not trace.get("observation_errors")
    if valid:
        measured = original.measure_record(record)  # Includes membership/event/duplicate checks.
    else:
        steps = record.get("steps")
        require(steps is None or (type(steps) is int and steps >= 0), "Invalid steps.")
        elapsed = record.get("elapsed_with_parser_s")
        measured = {"openings": None, "total_cost_usd": float(total), "parser_cost_usd": float(parser),
                    "executor_cost_usd": float(total-parser), "steps": steps,
                    "elapsed_s": None if elapsed is None else float(amount(elapsed, "elapsed time")),
                    "error_count": sum(bool(e) for e in record.get("agent_errors", [])),
                    "provider_calls": len(calls), "providers": dict(Counter(c.get("provider") for c in calls))}
    return {**measured, "navigation_measurement_valid": bool(valid),
            "navigation_measurement_note": None if valid else "Unavailable or invalid navigation evidence; not zero openings."}


def sum_values(rows, field):
    values = [r[field] for r in rows if r[field] is not None]
    return {"observed": len(values), "missing": len(rows)-len(values),
            "known_sum": float(sum((Decimal(str(v)) for v in values), Decimal(0))),
            "total": None if len(values) != len(rows) else float(sum((Decimal(str(v)) for v in values), Decimal(0))),
            "median": statistics.median(values) if values else None}


def arm_summary(rows):
    human = Counter(r["human_verdict"] for r in rows)
    assessable = len(rows)-human["unscorable"]
    return {"scheduled": len(rows), "human": dict(human), "human_correct": human["correct"],
            "human_assessable": assessable, "human_correct_out_of_scheduled": human["correct"]/len(rows),
            "human_correct_among_assessable": human["correct"]/assessable if assessable else None,
            "automatic": dict(Counter(r["automatic_verdict"] for r in rows)),
            "outcomes": dict(Counter(r["outcome"] for r in rows)),
            "resources": {field: sum_values(rows, field) for field in
                          ("total_cost_usd", "executor_cost_usd", "parser_cost_usd", "openings", "steps", "elapsed_s", "error_count")},
            "providers": dict(sum((Counter(r["providers"]) for r in rows), Counter()))}


def difference(a, b):
    return None if a is None or b is None else a-b


def mean_complete(values):
    return statistics.mean(values) if values and all(v is not None for v in values) else None


def pair_counts(pairs):
    result = dict(Counter(p["human_pair"] for p in pairs))
    for field, label in (("cost_difference_block_minus_baseline_usd", "cost"),
                         ("opening_difference_block_minus_baseline", "openings")):
        values = [p[field] for p in pairs if p[field] is not None]
        result[label] = {"valid_pairs": len(values), "missing_pairs": len(pairs)-len(values),
                         "block_lower": sum(v < 0 for v in values), "equal": sum(v == 0 for v in values),
                         "block_higher": sum(v > 0 for v in values)}
    return result


def summarize(rows):
    expected = {(task, arm, repeat) for task in blind.TASK_IDS for arm in ("baseline", "block") for repeat in (2, 3)}
    require(len(rows) == 32 and {(r["task"], r["condition"], r["repeat"]) for r in rows} == expected,
            "Analysis requires exactly the 32 scheduled repeat slots.")
    paired = []
    for task in blind.TASK_IDS:
        for repeat in (2, 3):
            pair = {r["condition"]: r for r in rows if r["task"] == task and r["repeat"] == repeat}
            baseline, block = pair["baseline"], pair["block"]
            if "unscorable" in (baseline["human_verdict"], block["human_verdict"]):
                category = "unscorable_pair"
            elif baseline["human_verdict"] == block["human_verdict"] == "correct":
                category = "both_correct"
            elif block["human_verdict"] == "correct":
                category = "block_only_correct"
            elif baseline["human_verdict"] == "correct":
                category = "baseline_only_correct"
            else:
                category = "neither_correct"
            paired.append({"task": task, "repeat": repeat, "human_pair": category,
                           "baseline": baseline, "block": block,
                           "cost_difference_block_minus_baseline_usd": difference(block["total_cost_usd"], baseline["total_cost_usd"]),
                           "opening_difference_block_minus_baseline": difference(block["openings"], baseline["openings"])})
    questions = []
    for task in blind.TASK_IDS:
        subset = [r for r in rows if r["task"] == task]
        arms = {arm: arm_summary([r for r in subset if r["condition"] == arm]) for arm in ("baseline", "block")}
        pairs = [p for p in paired if p["task"] == task]
        questions.append({"task": task, "arms": arms,
                          "correct_scheduled_difference_block_minus_baseline": arms["block"]["human_correct_out_of_scheduled"]-arms["baseline"]["human_correct_out_of_scheduled"],
                          "correct_assessable_difference_block_minus_baseline": difference(arms["block"]["human_correct_among_assessable"], arms["baseline"]["human_correct_among_assessable"]),
                          "mean_cost_difference_block_minus_baseline_usd": mean_complete([p["cost_difference_block_minus_baseline_usd"] for p in pairs]),
                          "mean_opening_difference_block_minus_baseline": mean_complete([p["opening_difference_block_minus_baseline"] for p in pairs])})
    equal_weight = {}
    for field in ("correct_scheduled_difference_block_minus_baseline", "correct_assessable_difference_block_minus_baseline",
                  "mean_cost_difference_block_minus_baseline_usd", "mean_opening_difference_block_minus_baseline"):
        values = [q[field] for q in questions if q[field] is not None]
        equal_weight[field] = {"question_strata": len(values), "missing_strata": 8-len(values),
                               "mean": statistics.mean(values) if values else None}
    return {"arms": {a: arm_summary([r for r in rows if r["condition"] == a]) for a in ("baseline", "block")},
            "paired": paired, "pair_counts": pair_counts(paired), "questions": questions,
            "equal_weight_question_summary": equal_weight,
            "by_repeat": {str(repeat): {"arms": {a: arm_summary([r for r in rows if r["repeat"] == repeat and r["condition"] == a]) for a in ("baseline", "block")},
                                         "pair_counts": pair_counts([p for p in paired if p["repeat"] == repeat])} for repeat in (2, 3)},
            "disagreements": [r for r in rows if r["human_verdict"] != "unscorable"
                              and ((r["human_verdict"] == "correct") != (r["automatic_verdict"] == "correct"))],
            "human_unscorable_audit": [r for r in rows if r["human_verdict"] == "unscorable"]}


def reconcile_calls(records, ledger, status, expected_attempt):
    require(ledger.get("study_budget_id") == blind.BATCH and ledger.get("attempt") == expected_attempt
            and not ledger.get("inflight") and not ledger.get("blocked_reason"), "Unsettled or foreign ledger.")
    calls = [c for record in records for c in record["calls"]]
    def index(values):
        result = {}
        for call in values:
            identifier = call.get("generation_id")
            require(isinstance(identifier, str) and identifier and identifier not in result,
                    "Missing or duplicate provider generation ID.")
            amount(call.get("cost_usd"), "provider charge")
            result[identifier] = call
        return result
    trial_calls, ledger_calls = index(calls), index(ledger["calls"])
    require(set(trial_calls) == set(ledger_calls), "Trial calls do not cover their attempt ledger exactly.")
    for identifier, call in trial_calls.items():
        other = ledger_calls[identifier]
        require(call == other, "Saved trial call differs from its operational ledger.")
    total = sum((amount(c["cost_usd"], "charge") for c in calls), Decimal(0))
    close(total, amount(ledger.get("charged_usd"), "ledger total"), "attempt ledger")
    if "charged_usd" in status:
        close(total, amount(status["charged_usd"], "status total"), "attempt status")
    return {"charge_usd": float(total), "provider_calls": len(calls), "generation_ids": set(trial_calls)}


def analyse(bundle):
    bundle = Path(bundle)
    human_rows = completed_review(bundle)  # Before opening private mapping or scorer.
    manifest = read_json(bundle / "manifest.json")
    mapping_path = bundle / "private-arm-key.json"
    require(digest(mapping_path) == manifest["private_arm_key_sha256"], "Private mapping changed.")
    mapping = read_json(mapping_path)
    require(mapping.get("study_id") == blind.STUDY and mapping.get("batch_id") == blind.BATCH
            and set(mapping["codes"]) == {r["code"] for r in human_rows}, "Review mapping coverage changed.")
    for path, wanted in mapping["inputs"].items():
        require(digest(path) == wanted, "Bound review input changed.")
    configs, backups = [], []
    for attempt, wanted in enumerate(blind.CONFIG_SHAS, 1):
        paths = [Path(p) for p in mapping["inputs"] if Path(p).name == f"attempt{attempt}-command.json"]
        require(len(paths) == 1 and digest(paths[0]) == wanted, "Wrong repeat configuration.")
        configs.append(read_json(paths[0])); backups.append(paths[0].parent)
    checksum_paths = [Path(p) for p in mapping["inputs"] if Path(p).name == "attempt2-backup-sha256.json"]
    require(len(checksum_paths) == 1 and digest(checksum_paths[0]) == blind.CHECKSUMS_SHA256, "Wrong completion checksum manifest.")
    checksums = read_json(checksum_paths[0])
    sources = dict(mapping["inputs"])
    def bound(path, attempt):
        relative = ("prior/" if attempt == 1 else "") + str(path.relative_to(backups[attempt-1]))
        require(checksums.get(relative) == digest(path), "Completion backup checksum mismatch.")
        sources[str(path.resolve())] = digest(path)
        return read_json(path)
    full = blind.expected_schedule(configs[0]["questions"])
    require(configs[1]["questions"] == configs[0]["questions"] and tuple(q["id"] for q in configs[0]["questions"]) == blind.TASK_IDS,
            "Question set differs across attempts.")
    statuses, records_by_attempt, ledgers = [], [[], []], []
    for attempt, (backup, config) in enumerate(zip(backups, configs), 1):
        require(config.get("stage") == ("plain-repeat-transfer", "plain-repeat-recovery")[attempt-1]
                and config.get("attempt") == attempt and config.get("repeats") == [2, 3]
                and "observation_contract" not in config, "Wrong repeated condition.")
        status = bound(backup / f"attempt{attempt}.status.json", attempt)
        require(status.get("config_sha256") == blind.CONFIG_SHAS[attempt-1]
                and status.get("status") == ("stopped", "complete")[attempt-1], "Wrong terminal status.")
        statuses.append(status)
        schedule = bound(backup / f"attempt{attempt}.results/schedule.json", attempt)
        require(schedule["slots"] == (full if attempt == 1 else full[6:]), "Wrong continuation coverage.")
        completed = bound(backup / f"attempt{attempt}.results/completed.json", attempt)
        require(completed["completed"] == [s["id"] for s in (full[:6] if attempt == 1 else full[6:])], "Wrong retained completion prefix.")
        ledgers.append(bound(backup / f"attempt{attempt}.ledger.json", attempt))
        analysis_plan = backup / "analysis-plan.md"
        require(digest(analysis_plan) == config["hashes"][config["analysis_plan_file"]], "Frozen analysis plan changed.")
        sources[str(analysis_plan.resolve())] = digest(analysis_plan)
    for path, wanted in original.SCORING_INPUTS.items():
        require(digest(ROOT / path) == wanted, "Frozen scoring input changed.")
    sys.path.insert(0, str(ROOT / "experiments"))
    import paths  # noqa: F401
    import score
    require(score.VERSION == 10, "Expected frozen v10 scorer.")
    task_path = ROOT / "experiments/tasks/tasks_tee_replication_28_oct.json"
    task_spec = read_json(task_path); tasks = {t["id"]: t for t in task_spec["tasks"]}; keys = score.keys_for(task_path)
    rows, seen_slots = [], set()
    for human in human_rows:
        mapped = mapping["codes"][human["code"]]
        attempt = mapped["attempt"]
        require(attempt in (1, 2), "Foreign attempt in mapping.")
        config = configs[attempt-1]
        eligible = full[:6] if attempt == 1 else full[6:]
        slots = {s["id"]: s for s in eligible}
        require(mapped["slot"] in slots and mapped["slot"] not in seen_slots, "Duplicate, foreign or replayed slot.")
        slot = slots[mapped["slot"]]; seen_slots.add(slot["id"])
        record_path = Path(mapped["record"])
        require(record_path.resolve() == (backups[attempt-1] / f"attempt{attempt}.results" / (slot["id"]+".json")).resolve()
                and digest(record_path) == mapped["record_sha256"], "Mapped trial path or checksum changed.")
        record = bound(record_path, attempt)
        expected = {"study_id": blind.STUDY, "batch_id": blind.BATCH, "stage": config["stage"], "phase": "transfer",
                    "task": slot["question"]["id"], "condition": slot["condition"], "repeat": slot["repeat"], "slot": slot["id"],
                    "scaffold": "browser-use", "browser_use_version": "0.13.14", "model": config["model"],
                    "provider_routing": config["provider"], "outcome": mapped["outcome"],
                    "dropdown_semantics": "native-disabled-state-v1", "evaluate_semantics": "fresh-local-script-scope-v1"}
        require(all(record.get(k) == v for k, v in expected.items()), "Trial differs from its scheduled condition.")
        require(all(mapped[k] == record[k] for k in ("task", "condition", "repeat")), "Private mapping identity differs.")
        task = tasks[record["task"]]; answer = record.get("answer") or ""
        require(answer == human["answer"] and record["question"] == human["question"] == task["query"].format(base=task_spec["base_url"])
                and json.loads(human["key"]) == task["expect"], "Reviewed evidence differs from original trial/key.")
        for setting in ("temperature", "frequency_penalty", "top_p", "max_steps", "max_failures", "max_input_bytes", "max_output_tokens", "clock_s"):
            require(record["settings"].get(setting) == config.get(setting) == configs[0].get(setting), "Execution setting changed.")
        reading = (record.get("box") or {}).get("reading")
        require(score.run_key(task, reading, keys) == task["expect"], "Unexpected reading-specific key.")
        auto = score.score_run(task, reading, keys, answer, record["outcome"] == "answered")
        records_by_attempt[attempt-1].append(record)
        rows.append({"code": human["code"], "task": record["task"], "condition": record["condition"], "repeat": record["repeat"],
                     "attempt": attempt, "slot": record["slot"], "record": str(record_path), "record_sha256": mapped["record_sha256"],
                     "human_verdict": human["hand_verdict"], "human_note": human["note"], "automatic_verdict": auto["verdict"],
                     "automatic_reason": auto["why"], "outcome": record["outcome"], **measure_record(record)})
    reconciled = [reconcile_calls(records, ledger, status, attempt) for attempt, (records, ledger, status)
                  in enumerate(zip(records_by_attempt, ledgers, statuses), 1)]
    require(not (reconciled[0]["generation_ids"] & reconciled[1]["generation_ids"]), "Provider generation reused across attempts.")
    total = sum((amount(x["charge_usd"], "attempt charge") for x in reconciled), Decimal(0))
    close(amount(statuses[1]["carryover_usd"], "carryover"), amount(reconciled[0]["charge_usd"], "first attempt"), "carryover")
    close(total, amount(statuses[1]["shared_cost_upper_usd"], "shared total"), "shared total")
    rows.sort(key=lambda r: (blind.TASK_IDS.index(r["task"]), r["repeat"], r["condition"]))
    return {"study_id": blind.STUDY, "batch_id": blind.BATCH, "cohort": "additional repeats 2 and 3 only",
            "unit": "eight fixed question types, two executions per condition per question",
            "human_scoring": "Validated blind student verdicts, preserved without adjudication",
            "automatic_scoring": {"version": 10, "role": "secondary", "input_sha256": original.SCORING_INPUTS},
            "reviewed_sha256": digest(bundle / "validated/reviewed.csv"), "validation_sha256": digest(bundle / "validated/validation.json"),
            "mapping_sha256": digest(mapping_path), "analysis_script_sha256": digest(Path(__file__)),
            "helper_sha256": {name: digest(ROOT / name) for name in ("tools/browser_use_analysis.py",
                "tools/browser_use_repeat_review.py", "tools/browser_use_review.py", "tools/hand_review.py")},
            "source_sha256": sources,
            "rows": rows, **summarize(rows),
            "operational_accounting": {"scheduled": 32, "attempts": [{k: v for k, v in x.items() if k != "generation_ids"} for x in reconciled],
                                       "total_charge_usd": float(total), "shared_cap_usd": 2,
                                       "failed_slot_charge_usd": sum(r["total_cost_usd"] for r in rows if r["outcome"] == "failed")},
            "limits": ["Additional repeats were planned after seeing repeat 1; no pooling with the original 16 here.",
                       "Eight question types, not 32 independent shopping problems; descriptive comparisons only.",
                       "Human unscorable marks remain unscorable; no AI-generated replacement grades.",
                       "Resource totals include the failed slot and must be read alongside correctness and completion.",
                       "elapsed_s is saved elapsed_with_parser_s and starts after the rendered pre-read; summed trial times are not batch wall-clock runtime.",
                       "Human final-commitment correctness does not establish sufficient evidence or page-state accuracy."]}


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
        fields = ["task", "repeat", "condition", "outcome", "human_verdict", "automatic_verdict", "openings", "navigation_measurement_valid",
                  "total_cost_usd", "executor_cost_usd", "parser_cost_usd", "steps", "elapsed_s", "error_count", "human_note", "automatic_reason"]
        with args.table.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", extrasaction="ignore")
            writer.writeheader(); writer.writerows(result["rows"])
        print(json.dumps({"rows": len(result["rows"]), "disagreements": len(result["disagreements"]),
                          "human_unscorable": len(result["human_unscorable_audit"]), "operational_accounting": result["operational_accounting"]}, indent=2))
    except (ValueError, OSError, KeyError, TypeError):
        parser.exit(1, "Analysis refused; no output conclusions should be used. Inspect synthetic validation first.\n")


if __name__ == "__main__":
    main()
