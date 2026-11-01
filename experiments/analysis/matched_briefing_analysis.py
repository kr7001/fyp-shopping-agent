#!/usr/bin/env python3
"""Separate, offline matched-briefing study reader; never scores by default.

The metadata-only --check-manifest is safe during human reading. --sheet creates
new blind codes exactly once. Only --hand, after validating a complete sheet and
its original questions/keys/answers, calls the frozen scorer and trace readers.
The original claim analysis, scorer, and protocols are not patched or relabelled.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import pathlib
import secrets
import shlex
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import claim  # noqa: E402
import score  # noqa: E402
import trace_stats  # noqa: E402
import verify_cells  # noqa: E402
import voids  # noqa: E402

VERSION = 1
ARMS = {"full-block": "box-model", "matched-briefing": "matched-briefing"}
TASKS = ("tee-cheapest-target", "tee-xs-price", "tee-top-3", "tee-count-buyable")
# Every study this reader may read, by id, with the scope its analysis states. The fresh
# market's (2 November 2026) is the same design on a market drawn after its protocol was
# committed (notes/fresh-market-2-nov/analysis-plan-B.md); the two are never pooled.
STUDIES = {
    "matched-briefing-2026-10-29": "Descriptive mechanism audit on already-observed Quenby; four templates, two repeats; no generalisation or significance claim.",
    "matched-briefing-fresh-2026-11-02": "Descriptive mechanism audit on the fresh held-out market of 2 November 2026; four templates, two repeats; not pooled with Quenby; no generalisation or significance claim.",
}
COLUMNS = claim.SHEET_COLUMNS


class Invalid(ValueError):
    """An incomplete, inconsistent or foreign study artifact."""


def require(test, message):
    if not test:
        raise Invalid(message)


def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def object_digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def number(value, label):
    require(isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0, f"missing/invalid {label}")
    return value


def close(a, b, label):
    require(abs(a - b) <= 0.000002, f"{label} does not match raw provider charges")


def protocol_at(path):
    path = pathlib.Path(path).resolve()
    config = json.loads(path.read_text())
    require(config.get("study_id") in STUDIES, "wrong study_id")
    require(set(config.get("tasks", [])) == set(TASKS) and len(config["tasks"]) == 4,
            "protocol must hold exactly the four predeclared tasks")
    require(config.get("repeats") == [1, 2], "protocol repeats must be [1, 2]")
    require({a: v.get("payload_arm") for a, v in config.get("arms", {}).items()} == ARMS,
            "protocol arm identities differ from this study")
    require(config.get("model") and config.get("tasks_file"), "missing model/tasks_file")
    wanted = {(a, t, r) for a in ARMS for t in TASKS for r in (1, 2)}
    schedule = config.get("schedule", [])
    require(len(schedule) == 16 and [s.get("slot") for s in schedule] == list(range(1, 17)),
            "schedule must number 16 slots exactly once in execution order")
    require({(s.get("arm"), s.get("task"), s.get("repeat")) for s in schedule} == wanted,
            "schedule has a duplicate or missing arm/task/repeat")
    return config


def task_path(config):
    path = pathlib.Path(config["tasks_file"])
    return path if path.is_absolute() else paths.TASKS / path.name


def check_briefing(briefing, label):
    require(isinstance(briefing, dict), f"{label}: missing briefing metadata")
    for field in ("query", "preamble", "page"):
        require(field in briefing and field + "_sha256" in briefing,
                f"{label}: missing briefing {field} identity")
    for field in ("pre_read_elapsed_s", "query_build_elapsed_s"):
        number(briefing.get(field), f"{label}: briefing {field}")
    require(isinstance(briefing.get("pre_read_cached"), bool), f"{label}: missing cache identity")
    require(briefing.get("original_query_sha256"), f"{label}: missing original question identity")
    for field in ("query", "preamble", "original_query"):
        value = briefing.get(field)
        expected = hashlib.sha256(value.encode()).hexdigest() if isinstance(value, str) else None
        require(briefing.get(field + "_sha256") == expected, f"{label}: briefing {field} digest differs")
    page_digest = hashlib.sha256(json.dumps(briefing["page"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(briefing["page_sha256"] == page_digest, f"{label}: briefing page digest differs")
    page = briefing["page"]
    require(page.get("reader") == "rendered" and page.get("next_page") is False
            and bool(page.get("listings")) and page.get("total") == len(page["listings"])
            and page.get("count") == len(page["listings"])
            and page.get("scope") is None and page.get("of") is None,
            f"{label}: briefing is not a complete, unfiltered rendered page")


def charges(row, record, log, condition, no_executor):
    """Provider charges stay separate; unknown costs never become zero."""
    total = number(row.get("cost_usd"), "suite row cost_usd")
    parser = number(row.get("parse_cost_usd"), "parse_cost_usd")
    parsed = row.get("parse_tokens")
    require(isinstance(parsed, dict), "missing parser token metrics")
    for field in ("prompt", "completion", "total", "calls"):
        number(parsed.get(field), "parse_tokens " + field)
    require(parsed["calls"] == 0 or row.get("parse_provider"), "missing parser provider")
    if condition == "matched-briefing":
        require(parser == 0 and all(parsed[k] == 0 for k in ("prompt", "completion", "total", "calls")),
                "matched briefing has parser charges or calls")
        require(not row.get("box"), "matched briefing contains a box plan")
    if no_executor:
        require(condition == "full-block", "baseline cannot close a slot through the box")
        close(total, parser, "nonexecuted-slot total")
        return {"cost_usd": total, "agent_cost_usd": 0, "parse_cost_usd": parser}
    require(record is not None, "missing run record: charge/trace completeness cannot be verified")
    require(record.get("parse_tokens") == parsed, "row/record parser tokens differ")
    require(record.get("parse_provider") == row.get("parse_provider"), "row/record parser provider differs")
    close(number(record.get("cost_usd"), "record cost_usd"), total, "suite/record total")
    agent = number(record.get("agent_cost_usd", record.get("cost_usd")), "agent_cost_usd")
    close(number(record.get("parse_cost_usd"), "record parse_cost_usd"), parser, "parser cost")
    close(total, agent + parser, "agent plus parser total")
    require(log is not None, "missing trace: provider charges cannot be verified")
    raw = trace_stats.cost_reported(log)
    number(raw, "provider charges in trace")
    require(len(trace_stats.COST_FIELD.findall(log)) == len(trace_stats.USAGE.findall(log)),
            "provider charge count differs from completion count")
    close(agent, raw, "agent charge")
    number(record.get("elapsed_s"), "elapsed_s")
    require(isinstance(record.get("trace"), dict), "missing trace metrics")
    for field in ("tool_calls_total", "actions"):
        number(record["trace"].get(field), "trace " + field)
    tokens = claim.stated_tokens(record)
    require(isinstance(tokens, dict), "missing token metrics")
    # Frozen suite.run_tokens combines parser+agent totals without a `calls` field.
    for field in ("prompt", "completion", "total"):
        number(tokens.get(field), "tokens " + field)
    number((record["trace"].get("tokens") or {}).get("calls"), "agent completion count")
    return {"cost_usd": total, "agent_cost_usd": agent, "parse_cost_usd": parser}


def without_study_header(manifest, config):
    """The launcher writes one dated `study <id> ...` header, which is not a claim-chain line.
    Require exactly one, for this study, and give the frozen reader every other line unchanged."""
    lines = manifest.read_text().splitlines()
    header = [i for i, line in enumerate(lines) if line.startswith("study ")]
    require(len(header) == 1 and lines[header[0]].startswith(f"study {config['study_id']} "),
            "manifest needs exactly one study header for this study")
    return "\n".join(line for i, line in enumerate(lines) if i != header[0]) + "\n"


def load_study(protocol, manifest, allow_incomplete=False):
    """Validate only identity, operational exclusions and money; never call a scorer."""
    protocol, manifest = pathlib.Path(protocol).resolve(), pathlib.Path(manifest).resolve()
    config = protocol_at(protocol)
    parsed = claim.parse_manifest(without_study_header(manifest, config))
    require(not parsed.problems, "; ".join(parsed.problems))
    require(len(parsed.starts) == 1 and len(parsed.ends) <= 1, "manifest start/end markers invalid")
    require(allow_incomplete or len(parsed.ends) == 1, "completed manifest needs one end marker")
    require(all(line.kind == "batch" for line in parsed.lines),
            "replays require separate approval/design; this reader accepts the original schedule only")
    require(len(parsed.lines) <= 16, "manifest has more than 16 original slots")
    require(allow_incomplete or len(parsed.lines) == 16, "manifest does not hold all 16 scheduled slots")
    tasks_file = task_path(config)
    spec = json.loads(tasks_file.read_text())
    tasks = {task["id"]: task for task in spec["tasks"]}
    require(set(TASKS) <= tasks.keys(), "task file is missing a study task")
    if config.get("tasks_sha256"):
        require(digest(tasks_file) == config["tasks_sha256"], "task file digest changed")
    for relative, sha in config.get("input_sha256", {}).items():
        require(digest(paths.REPO / relative) == sha, f"frozen input digest changed: {relative}")
    runs, seen = [], set()
    for line, scheduled in zip(parsed.lines, config["schedule"]):
        folder = line.folder
        require(folder is not None and folder.is_dir(), "missing batch folder")
        folder = folder.resolve()
        require(folder not in seen, "duplicate batch folder")
        seen.add(folder)
        payload = json.loads((folder / "suite.json").read_text())
        arm, task, repeat, slot = (scheduled[k] for k in ("arm", "task", "repeat", "slot"))
        label = f"slot {slot}"
        flags = claim.flags(shlex.split(line.args))
        for field, value in (("condition", arm), ("slot-id", str(slot)), ("only", task),
                             ("repeat-start", str(repeat))):
            require(flags.get(field) == [value], f"{label}: manifest --{field} differs from schedule")
        require(flags.get("repeats", ["1"]) == ["1"], f"{label}: invocation repeats not one")
        require(payload.get("arm") == ARMS[arm], f"{label}: wrong payload arm")
        require(claim.flagged_arm(payload) == ("box-model" if arm == "full-block" else "none"),
                f"{label}: payload flags do not match arm")
        require(payload.get("tasks_file") == tasks_file.name, f"{label}: wrong task file")
        require(payload.get("model") == config["model"], f"{label}: wrong model")
        routing = (config.get("provider_routing") or {}).get(config["model"])
        require((payload.get("provider_routing") or {}).get("agent") == routing,
                f"{label}: agent routing differs from protocol")
        require((payload.get("provider_routing") or {}).get("parser") == (routing if arm == "full-block" else None),
                f"{label}: parser routing differs from protocol")
        require(payload.get("repeats") == 1 and payload.get("repeat_start") == repeat,
                f"{label}: payload repeat range differs from schedule")
        rows = payload.get("rows", [])
        require(len(rows) == 1, f"{label}: expected exactly one suite row")
        row = rows[0]
        require((row.get("task"), row.get("repeat")) == (task, repeat), f"{label}: wrong task/repeat")
        record_path = folder / f"{task}-{repeat}.json"
        log_path = record_path.with_suffix(".log")
        require({p.name for p in folder.glob("*.json")} <= {"suite.json", record_path.name},
                f"{label}: unexpected/duplicate run records")
        require({p.name for p in folder.glob("*.log")} <= {log_path.name},
                f"{label}: unexpected/duplicate run logs")
        record = json.loads(record_path.read_text()) if record_path.exists() else None
        log = log_path.read_text(errors="replace") if log_path.exists() else None
        expected = {"study_id": config["study_id"], "protocol_sha256": digest(protocol),
                    "wrapper_id": "matched-briefing-v1", "condition": arm, "slot_id": slot, "arm": ARMS[arm]}
        for source, item in (("payload", payload), ("row", row), ("record", record)):
            if item is None:
                continue
            require(all(item.get(k) == v for k, v in expected.items()), f"{label}: {source} study identity mismatch")
        conditions = claim.conditions_of(payload, record or {},
                                         tuple(set(config.get("require", {})) |
                                               set(config.get("arm_require", {}).get(arm, {}))))
        required = {**config.get("require", {}), **config.get("arm_require", {}).get(arm, {})}
        conditions["model"] = config["model"]
        require(not claim.mismatches(conditions, required), f"{label}: frozen condition mismatch: "
                + "; ".join(claim.mismatches(conditions, required)))
        if record:
            require(record.get("model") == config["model"], f"{label}: run model differs")
            require(record.get("provider_routing") == (payload.get("provider_routing") or {}).get("agent"),
                    f"{label}: record/batch provider routing differs")
        # Exact frozen asked_row branch: no record, no log and a zero executor clock.
        # A closed-looking row whose executor left a log or clock keeps unknown charges.
        closed = (record is None and log is None and row.get("log") is None
                  and row.get("elapsed_s") == 0 and row.get("verdict") in ("asked", "refused"))
        if closed:
            outcome, reason = voids.CLOSED, "closed by the box"
        else:
            outcome, reason, _ = voids.classify(record, log, row=row)
        # Exact frozen suite branch: routed parser failure skips run_once entirely.
        # This is evidence of no executor, unlike a runner that lost its record.
        parser_only = (arm == "full-block" and record is None and log is None
                       and row.get("verdict") == "void" and row.get("log") is None
                       and row.get("elapsed_s") == 0
                       and bool((payload.get("provider_routing") or {}).get("parser")))
        parser_only = parser_only and str(((row.get("box") or {}).get("parse") or {}).get(
            "fallback_reason") or "").startswith("the model call failed")
        briefing = row.get("briefing")
        check_briefing(briefing, label)
        question = tasks[task]["query"].format(base=spec["base_url"])
        require(briefing.get("original_query") == question, f"{label}: original question differs from task file")
        require(payload.get("briefing_page_reader") == "rendered", f"{label}: briefing reader is not rendered")
        if record:
            require(record.get("briefing") == briefing, f"{label}: row/record briefing differs")
            require(record.get("query") == briefing["query"], f"{label}: executed query differs from briefing")
        try:
            costs = charges(row, record, log, arm, closed or parser_only)
        except Invalid as error:
            if outcome == voids.VOID:
                raise Invalid(f"{label}: technical void ({reason}); {error}") from error
            raise
        # No final answer, answer-grade, abstention text or box decision is returned by check_summary.
        runs.append({"slot": slot, "arm": arm, "task": task, "repeat": repeat,
                     "folder": folder, "batch": folder.name, "payload": payload, "row": row,
                     "record": record, "outcome": outcome, "technical_reason": reason if outcome == voids.VOID else None,
                     "record_sha256": digest(record_path) if record else None,
                     "log_sha256": digest(log_path) if log_path.exists() else None, **costs})
    for run in runs:
        pair = [r for r in runs if (r["task"], r["repeat"]) == (run["task"], run["repeat"])]
        if len(pair) == 2:
            require(all(pair[0]["row"]["briefing"][field] == pair[1]["row"]["briefing"][field]
                        for field in ("preamble", "page", "original_query")),
                    f"paired briefing facts differ for {run['task']} repeat {run['repeat']}")
    return {"config": config, "protocol": protocol, "manifest": manifest, "ended": len(parsed.ends) == 1,
            "stops": parsed.stops,
            "protocol_sha256": digest(protocol), "manifest_sha256": digest(manifest),
            "tasks_sha256": digest(tasks_file), "spec": spec, "tasks": tasks, "runs": runs}


def check_summary(study):
    runs = study["runs"]
    return {"study_id": study["config"]["study_id"], "analysis_version": VERSION,
            "scheduled_slots": 16, "recorded_slots": len(runs),
            "complete": len(runs) == 16 and study["ended"], "errors": [], "stops": study["stops"],
            "technical_voids": [{"slot": r["slot"], "reason": r["technical_reason"]}
                                for r in runs if r["outcome"] == voids.VOID],
            "charges_all_attempts": {key: round(sum(r[key] for r in runs), 6)
                                     for key in ("cost_usd", "agent_cost_usd", "parse_cost_usd")}}


def review_rows(study):
    keys = score.keys_for(task_path(study["config"]))
    rows = []
    for run in study["runs"]:
        if run["outcome"] in (voids.VOID, voids.CLOSED):
            continue
        task = study["tasks"][run["task"]]
        reading = verify_cells.run_reading(run["row"], run["payload"])
        key = score.run_key(task, reading, keys)
        rows.append((run, {"question": task["query"].format(base=study["spec"]["base_url"]),
                           "key": json.dumps(key, sort_keys=True),
                           "answer": str((run["record"].get("result") or {}).get("final") or "")}))
    return rows


def key_path(sheet):
    return sheet.with_name(sheet.stem + ".key.json")


def write_sheet(study, sheet):
    sheet = pathlib.Path(sheet)
    mapping_path = key_path(sheet)
    require(not sheet.exists() and not mapping_path.exists(), "refusing to regenerate existing blind codes or key")
    rows, mapping = [], {}
    for run, fields in review_rows(study):
        code = secrets.token_hex(4)
        while code in mapping:
            code = secrets.token_hex(4)
        rows.append({"code": code, **fields, "hand_verdict": "", "note": ""})
        mapping[code] = {k: run[k] for k in ("slot", "arm", "task", "repeat", "batch", "record_sha256", "log_sha256")}
        mapping[code]["fields_sha256"] = object_digest(fields)
    key = {"study_id": study["config"]["study_id"], "analysis_version": VERSION,
           **{k: study[k] for k in ("protocol_sha256", "manifest_sha256", "tasks_sha256")},
           "codes": mapping,
           "left_off": {outcome: sum(r["outcome"] == outcome for r in study["runs"])
                        for outcome in (voids.VOID, voids.CLOSED)}}
    sheet.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation and read-only mapping prevent accidental regeneration/overwrite.
    with mapping_path.open("x") as handle:
        json.dump(key, handle, indent=2)
        handle.write("\n")
    mapping_path.chmod(0o444)
    with sheet.open("x", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r["code"]))
    return len(rows)


def completed_sheet(sheet):
    """Check completeness before opening any identity key or raw run."""
    with pathlib.Path(sheet).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == list(COLUMNS), "review must retain the original six columns")
        rows = list(reader)
    require(rows, "empty review sheet")
    found = {}
    for row in rows:
        code = row["code"]
        require(code and code not in found, "missing/duplicate blind code")
        require(row["hand_verdict"] in claim.HAND_VERDICTS, "review is incomplete or contains invalid verdicts")
        found[code] = row
    return found


def bind_review(study, sheet, rows):
    key = json.loads(key_path(pathlib.Path(sheet)).read_text())
    require(key.get("study_id") == study["config"]["study_id"], "review belongs to another study")
    for field in ("protocol_sha256", "manifest_sha256", "tasks_sha256"):
        require(key.get(field) == study[field], f"review {field} identity changed")
    require(set(key["codes"]) == set(rows), "review has missing or foreign codes")
    expected = {run["slot"]: (run, fields) for run, fields in review_rows(study)}
    by_slot = {}
    for code, mapped in key["codes"].items():
        slot = mapped.get("slot")
        require(slot in expected and slot not in by_slot, "key has a missing/duplicate/foreign run identity")
        run, fields = expected[slot]
        require(all(mapped.get(k) == run[k] for k in ("arm", "task", "repeat", "batch", "record_sha256", "log_sha256")),
                "review run identity or raw source changed")
        actual = {k: rows[code][k] for k in ("question", "key", "answer")}
        require(actual == fields and object_digest(actual) == mapped.get("fields_sha256"),
                "review question, key or original full answer changed")
        by_slot[slot] = {"code": code, "hand_verdict": rows[code]["hand_verdict"], "note": rows[code]["note"]}
    require(set(by_slot) == set(expected), "a run has no hand review")
    return by_slot


def analyse(study, hand):
    """Descriptive per-task paired observations only. No significance tests or intervals."""
    spec = study["spec"]
    truth = verify_cells.ground_truth(verify_cells.fixture_for(spec))
    market = verify_cells.market_urls(spec)
    keys = score.keys_for(task_path(study["config"]))
    results, disagreements = [], []
    for run in study["runs"]:
        item = {k: run[k] for k in ("slot", "arm", "task", "repeat", "batch", "cost_usd", "agent_cost_usd", "parse_cost_usd")}
        item.update({"outcome": run["outcome"], "technical_reason": run["technical_reason"]})
        if run["outcome"] == voids.VOID:
            results.append(item)
            continue
        if run["outcome"] == voids.CLOSED:
            item.update({"hand_verdict": None, "automatic_verdict": "closed by the box", "opened": 0,
                         "elapsed_s": 0, "plan_compliance": None})
        else:
            task = study["tasks"][run["task"]]
            measured = verify_cells.verify_run(run["folder"] / f"{run['task']}-{run['repeat']}.json",
                                              task, truth, run["row"], run["payload"], keys, market)
            require(measured["opened"] is not None and measured["elapsed_s"] is not None,
                    "missing derived trace metrics")
            require(measured["answer_matches_suite"], "suite answer differs from original final")
            reading = verify_cells.run_reading(run["row"], run["payload"])
            verdict = score.score_run(task, reading, keys, measured["answer"], measured["ok"])["verdict"]
            item.update(hand[run["slot"]])
            item.update({"automatic_verdict": verdict, "stored_automatic_verdict": run["row"].get("verdict"),
                         "opened": measured["opened"], "skus": measured["skus"],
                         "elapsed_s": measured["elapsed_s"], "selections": measured["selections"],
                         "tokens": claim.stated_tokens(run["record"]), "providers": claim.agent_providers(
                             run["row"], run["folder"] / f"{run['task']}-{run['repeat']}.log"),
                         "plan_compliance": claim.answer_check({run["arm"]: [{
                             "folder": str(run["folder"]), "batch": run["batch"], "task": run["task"],
                             "repeat": run["repeat"], "planned": bool((run["row"].get("box") or {}).get("query"))
                         }]}, order=[run["arm"]])[run["arm"]] if run["arm"] == "full-block" else None})
            lean = claim.lean_of(verdict, claim.HAND_VERDICTS[item["hand_verdict"]])
            if lean:
                disagreements.append({"slot": run["slot"], "code": item["code"], "arm": run["arm"],
                                      "hand": item["hand_verdict"], "automatic": verdict, "difference": lean})
        briefing = run["row"]["briefing"]
        item["pre_read_elapsed_s"] = briefing["pre_read_elapsed_s"]
        item["query_build_elapsed_s"] = briefing["query_build_elapsed_s"]
        item["total_measured_elapsed_s"] = item["elapsed_s"] + briefing["pre_read_elapsed_s"] + briefing["query_build_elapsed_s"]
        results.append(item)
    paired = []
    for task in study["config"]["tasks"]:
        for repeat in (1, 2):
            pair = {r["arm"]: r for r in results if (r["task"], r["repeat"]) == (task, repeat)}
            a, b = pair["full-block"], pair["matched-briefing"]
            usable = all(r["outcome"] != voids.VOID for r in pair.values())
            paired.append({"task": task, "repeat": repeat, "arms": pair,
                           "paired_differences_full_block_minus_matched": {
                               field: a[field] - b[field] if usable else None
                               for field in ("opened", "cost_usd", "elapsed_s", "total_measured_elapsed_s")}})
    counts = {}
    for task in study["config"]["tasks"]:
        counts[task] = {}
        for arm in ARMS:
            group = [r for r in results if r["task"] == task and r["arm"] == arm]
            counts[task][arm] = {
                "scheduled": len(group), "technical_voids": sum(r["outcome"] == voids.VOID for r in group),
                "closed": sum(r["outcome"] == voids.CLOSED for r in group),
                "human_correct": sum(r.get("hand_verdict") == "correct" for r in group),
                "human_unscorable": sum(r.get("hand_verdict") == "unscorable" for r in group),
                "human_assessable": sum(r.get("hand_verdict") in ("correct", "not correct") for r in group),
                "automatic_correct": sum(r.get("automatic_verdict") == "correct" for r in group)}
    return {**check_summary(study), "scorer_version": score.VERSION, "per_task_counts": counts,
            "scope": STUDIES[study["config"]["study_id"]],
            "paired_by_task_repeat": paired, "human_automatic_disagreements": disagreements,
            "technical_rule": "Original voids.classify; voids excluded, charges retained; no automatic replay."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=pathlib.Path)
    parser.add_argument("--protocol", required=True, type=pathlib.Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--check-manifest", action="store_true")
    modes.add_argument("--sheet", type=pathlib.Path)
    modes.add_argument("--hand", type=pathlib.Path)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--json", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        require(not args.allow_incomplete or args.check_manifest, "partial manifests allowed only for operational checking")
        require(not args.json or args.hand, "--json is only available after completed human review")
        rows = completed_sheet(args.hand) if args.hand else None
        study = load_study(args.protocol, args.manifest, args.allow_incomplete)
        if args.check_manifest:
            print(json.dumps(check_summary(study), indent=2))
        elif args.sheet:
            count = write_sheet(study, args.sheet)
            print(f"Created {count} blind rows; original code mapping saved separately. No grades displayed.")
        else:
            hand = bind_review(study, args.hand, rows)
            result = analyse(study, hand)
            text = json.dumps(result, indent=2) + "\n"
            if args.json:
                require(not args.json.exists(), "refusing to overwrite an existing analysis")
                args.json.write_text(text)
            print(text, end="")
    except (Invalid, OSError, ValueError, KeyError) as error:
        print(f"refused: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
