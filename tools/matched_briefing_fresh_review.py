#!/usr/bin/env python3
"""Blind review and analysis of Study B, the matched briefing on the fresh market, offline.

Study B (notes/fresh-market-2-nov/analysis-plan-B.md) runs 16 openJiuwen trials on Rookmere: the
full block against a matched factual briefing, four tasks, two repeats. Under amendment 4
(2 November 2026) it may have up to three stages, each with its own manifest beside the others:
the primary run (`batch|` lines, slots 1 to 15, then a budget stop during slot 16), a
continuation that runs slot 16 only on the student's ruling, and one timeout rerun of each slot
whose primary record reached its 1800 s clock, with the clock doubled (`rerun|` lines).

    prepare   checks every stage against its configuration and status, reads every run through
              the frozen reader (matched_briefing_analysis.load_study, unchanged), checks that
              every slot carries one `preamble_sha256` (reporting rule 5) and records the
              result, then writes one blank sheet holding every answer, primary and rerun,
              under random codes, with no arm, repeat, stage, rerun flag, cost, time or
              automatic verdict; the private key holds those. Voids and slots the block closed
              are kept off the sheet, as the frozen reader keeps them.
    validate  reads only the public manifest, the blank sheet and the student's CSV; with
              --save writes the completed-review receipt (browser_use_fresh_review.validate).
    analysis  only after that receipt: the descriptive results analysis-plan-B.md declares,
              with amendment 4's timeouts per arm and its two sensitivities. No significance
              test.

The frozen reader and the reader page are hash-bound by Study B's launch configurations, so
neither is edited: this tool calls them. Written 2 November 2026.

    python3 tools/matched_briefing_fresh_review.py prepare --bundle notes/fresh-market-2-nov/study-b-review \\
        [--continuation <its configuration> <its SHA-256>] [--rerun <its configuration> <its SHA-256>]
    python3 tools/matched_briefing_fresh_review.py validate --bundle notes/fresh-market-2-nov/study-b-review \\
        --reviewed <the student's CSV> --save
    python3 tools/matched_briefing_fresh_review.py analysis --bundle notes/fresh-market-2-nov/study-b-review \\
        --output notes/fresh-market-2-nov/study-b-analysis.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import csv
import dataclasses
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "experiments/analysis"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402,F401  (puts analysis/ and runners/ on the import path)
import browser_use_fresh_review as blind  # noqa: E402  (the bundle, reader page and validation, shared)
import guarded_matched_briefing as guard  # noqa: E402  (the stages' names, paths and timeout rule)
import matched_briefing_analysis as frozen  # noqa: E402  (the frozen reader, called, never edited)

require, Refused = blind.require, blind.Refused
claim, score, verify_cells, voids = frozen.claim, frozen.score, frozen.verify_cells, frozen.voids
PRIMARY, CONTINUATION, RERUN = "primary", guard.CONTINUATION, guard.RERUN
NOT_STARTED = "not started"
TIMEOUT = (voids.NOT_CORRECT, "clock")  # the frozen void rules' class and reason for a clock limit
# The code this review runs, each file held to the hash Study B's primary command bound, so the
# reader, void rules, scorer, trace readers, reader page and reading rules are the ones the study
# was launched under (as Study A's analysis holds its own, 2 November 2026).
FROZEN_CODE = ("experiments/analysis/matched_briefing_analysis.py", "experiments/analysis/claim.py",
               "experiments/analysis/score.py", "experiments/analysis/voids.py",
               "experiments/analysis/verify_cells.py", "experiments/analysis/trace_stats.py",
               "experiments/paths.py", "tools/hand_review.py", "tools/hand_review.html",
               "docs/content/claim2-reading-rules.md")
DIFFERENCES = ("opened", "cost_usd", "elapsed_s", "total_measured_elapsed_s")

NOTE = """Matched-briefing fresh-market review (Rookmere), 2 November 2026

One row for each openJiuwen trial of this study that left an answer to judge, in random order,
with the final text that trial recorded. A row is empty when the trial recorded none. Judge only
the final commitment, against the expected answer and the frozen rules below. Do not grade the
amount of browsing, evidence sufficiency, presentation quality or cost. No verdict has been
supplied by AI. This page adds no arm label, repeat label, stage, rerun label, execution
outcome, cost, time or automatic verdict. An answer itself may still suggest its condition:
judge that row by the same rules. Rows from earlier studies are not part of this review, and the
references below to other studies or a second reader add no rows to it.

"""


@dataclasses.dataclass(frozen=True)
class Study:
    """Everything Study B's review is bound to. STUDY_B is the fresh market's; the tests build
    their own in a temporary repository."""
    study_id: str
    root: Path            # the repository whose stages are read
    protocol: str         # the analysis file, a repository path
    primary_config: str   # the primary run's command, a repository path
    primary_sha256: str   # its SHA-256, as every later stage binds it
    sheet: str            # the blank sheet's file name, and the reader's download name
    note: str = NOTE


STUDY_B = Study(study_id=guard.FRESH, root=ROOT, protocol="experiments/tasks/matched_briefing_2_nov.json",
                primary_config=guard.FRESH_PRIMARY_CONFIG, primary_sha256=guard.FRESH_PRIMARY_SHA256,
                sheet="study-b-fresh-2-nov.sheet.csv")


@contextlib.contextmanager
def frozen_reading(schedule, clock_s):
    """matched_briefing_analysis.load_study, unchanged, reading lines whose slots are `schedule`
    and whose trial clock is `clock_s`: its protocol reader returns the frozen protocol, every
    check of it still made, with only those two fields replaced. The frozen reader zips a
    manifest's lines with the whole 16-slot schedule from slot 1 and requires the 1800 s clock,
    so it reads neither a continuation's slot 16 nor a rerun's doubled clock as they are."""
    original = frozen.protocol_at

    def protocol_at(path):
        config = original(path)
        return {**config, "schedule": schedule, "require": {**config["require"], "clock_s": clock_s}}
    frozen.protocol_at = protocol_at
    try:
        yield
    finally:
        frozen.protocol_at = original


def frozen_runs(study, protocol, lines, clock_s):
    """The runs of `lines`, (scheduled slot, folder, arguments) each, as the frozen reader checks
    and returns them, through one manifest written for it alone and then discarded."""
    if not lines:
        return []
    with tempfile.TemporaryDirectory() as folder:
        manifest = Path(folder) / "lines.manifest"
        manifest.write_text("\n".join(
            ["start 2026-11-02T00:00:00 usage 0 cap 0", f"study {study.study_id} lines read by the fresh review"]
            + [f"batch|{path}|{args}" for _, path, args in lines]) + "\n")
        with frozen_reading([slot for slot, _, _ in lines], clock_s):
            try:
                return frozen.load_study(protocol, manifest, allow_incomplete=True)["runs"]
            except frozen.Invalid as error:
                raise Refused(f"The frozen reader refused a run: {error}") from None


def slot_of(args):
    found = re.search(r"--slot-id (\d+)\b", args)
    require(found, "A manifest line names no slot.")
    return int(found.group(1))


def manifest_lines(path, kind):
    """A manifest's `kind` lines, each (folder, arguments); `rerun|` lines also give the primary
    folder they name. Any other line is the launcher's own (start, header, end, STOP)."""
    out = []
    for line in Path(path).read_text().splitlines():
        if not line.startswith(kind + "|"):
            continue
        if kind == "batch":
            _, folder, args = line.split("|", 2)
            out.append({"folder": folder, "args": args})
        else:
            parts = line.split("|", 4)
            require(len(parts) == 5 and parts[2] == f"stage {RERUN}" and parts[3].startswith("primary "),
                    "A rerun line is not the shape the launcher writes.")
            out.append({"folder": parts[1], "args": parts[4], "primary": parts[3][len("primary "):]})
    return out


def stage_config(study, stage, given, statuses):
    """A later stage's configuration and its status, checked against the SHA-256 named for it, its
    verifier's receipt and its fixed paths. A stage not named must have left no file."""
    root = study.root
    if given is None:
        require(not guard.launched(root, stage), f"The {stage} stage was launched: name its configuration.")
        return None
    path, sha = Path(given[0]).resolve(), given[1]
    require(blind.digest(path) == sha, f"{stage}: the configuration file is not the one named by its SHA-256.")
    config = blind.read_json(path)
    require(config.get("study_id") == study.study_id and config.get("stage") == stage
            and all(config.get(k) == v for k, v in guard.LATER[stage].items())
            and config["hashes"].get(study.primary_config) == study.primary_sha256,
            f"{stage}: the configuration is not this study's stage.")
    receipt = blind.read_json(root / config["verification_receipt"])
    require(receipt.get("status") == "PASS" and receipt.get("config_sha256") == sha
            and receipt.get("head") == config["expected_head"],
            f"{stage}: the configuration lacks the verifier's pass.")
    status = blind.read_json(root / config["status"])
    require(status.get("status") in ("complete", "stopped") and status.get("config_sha256") == sha
            and status.get("stage") == stage, f"{stage}: the stage has not ended under this configuration.")
    statuses[stage] = status
    return {"path": str(path), "sha256": sha, "config": config, "status": status}


def load_study(study, continuation=None, rerun=None):
    """Every stage of Study B, its runs read by the frozen reader, and slot 16's state.
    `continuation` and `rerun` are (configuration, SHA-256) when those stages were launched."""
    root = study.root
    protocol_path = root / study.protocol
    protocol = frozen.protocol_at(protocol_path)
    require(protocol["study_id"] == study.study_id, "The analysis file is not this study's.")
    schedule = {slot["slot"]: slot for slot in protocol["schedule"]}
    primary_path = root / study.primary_config
    require(blind.digest(primary_path) == study.primary_sha256, "The primary run's configuration is not the one it ran.")
    primary = blind.read_json(primary_path)
    for name in FROZEN_CODE:
        require(primary["hashes"].get(name) == blind.digest(ROOT / name),
                f"{name} is not the file Study B's primary run bound.")
    status = blind.read_json(root / primary["status"])
    require(status.get("status") in ("complete", "stopped") and status.get("config_sha256") == study.primary_sha256,
            "The primary run has not ended under its configuration.")
    statuses = {PRIMARY: status}
    later = {CONTINUATION: stage_config(study, CONTINUATION, continuation, statuses),
             RERUN: stage_config(study, RERUN, rerun, statuses)}
    files = [study.protocol, study.primary_config, primary["status"], primary["manifest"]]
    lines = manifest_lines(root / primary["manifest"], "batch")
    slots = [slot_of(line["args"]) for line in lines]
    require(slots == list(range(1, len(slots) + 1)), "The primary manifest's slots are not the schedule's first ones.")
    entries = [(schedule[s], line["folder"], line["args"], PRIMARY) for s, line in zip(slots, lines)]
    # Slot 16 (amendment 4, correction of 12:30): the primary run started it, and its budget stop
    # ended it with no record. It is a technical void unless the student ruled it be run again,
    # which the continuation's configuration carries.
    try:
        # Since f4035ed it also reads the charges the started run's own logs show, and refuses a
        # completion logged without its charge.
        partial = guard.partial_run(root, primary, status)
    except guard.original.Stop as stop:
        raise Refused(f"The primary run's started slot cannot be accounted: {stop}") from None
    cont = later[CONTINUATION]
    if cont:
        config = cont["config"]
        files += [config["status"], config["manifest"]]
        added = manifest_lines(root / config["manifest"], "batch")
        steps = [step["study_slot"]["slot"] for step in config["steps"] if step["kind"] == "paid"]
        added_slots = [slot_of(line["args"]) for line in added]
        require(added_slots == steps[:len(added_slots)] and not set(added_slots) & set(slots),
                "The continuation's lines are not its own steps, or replay a primary slot.")
        require(config.get("partial_run") == partial
                and (partial is None or (isinstance(config.get("partial_run_ruling"), str)
                                         and config["partial_run_ruling"].strip())),
                "A started slot was run again without the student's ruling recorded in its configuration.")
        entries += [(schedule[s], line["folder"], line["args"], CONTINUATION) for s, line in zip(added_slots, added)]
        slots += added_slots
    runs = frozen_runs(study, protocol_path, [(slot, folder, args) for slot, folder, args, _ in entries], 1800)
    for run, entry in zip(runs, entries):
        run["stage"] = entry[3]
    require(len({run["folder"] for run in runs}) == len(runs), "Two slots name one results folder.")
    # A slot no stage ran: the one the primary run had started when it stopped is a technical
    # void, its charges in its own run log (`partial_run`) but in no record. Any other was never
    # started.
    started = next_step_slot(primary, status) if partial else None
    left = {}
    for number in schedule:
        if number in slots:
            continue
        ended = cont["status"] if cont else status
        left[number] = {"slot": number, **{k: schedule[number][k] for k in ("arm", "task", "repeat")},
                        "outcome": NOT_STARTED, "partial_run": None,
                        "reason": "not started: " + str(ended.get("reason") or "its stage ended before it")}
        if number == started:
            left[number].update(outcome=voids.VOID, partial_run=partial,
                                reason="the primary run started it and its budget stop ended it before its runner "
                                       "wrote a record. It was not run again")
    ruling = cont["config"]["partial_run_ruling"] if cont and started in slots else None
    # The timeout reruns: every slot whose primary record reached its clock, once, in slot order,
    # as the launcher's own rule finds them (guarded_matched_briefing.primary_timeouts).
    reruns = []
    rer = later[RERUN]
    if rer:
        config = rer["config"]
        files += [config["status"], config["manifest"]]
        manifests = [primary["manifest"]] + ([cont["config"]["manifest"]] if cont else [])
        timeouts = guard.primary_timeouts(root, manifests)
        paid = [step for step in config["steps"] if step["kind"] == "paid"]
        rows = [step.get("rerun_of") for step in paid]
        require(rows == timeouts, "The reruns are not every primary timeout, each once, in slot order.")
        # Each rerun ran the frozen code through the reviewed wrapper, which hands suite.py the
        # doubled clock and nothing else (amendment 4 point 6), bound by the stage at its pin.
        require(config["hashes"].get(guard.RERUN_RUNNER) == guard.RERUN_RUNNER_SHA256
                and all(step["argv"][1] == guard.RERUN_RUNNER and "--clock" in step["argv"]
                        and step["argv"][step["argv"].index("--clock") + 1] == str(guard.RERUN_CLOCK_S)
                        for step in paid),
                "The reruns did not run through the reviewed wrapper at the doubled clock.")
        added = manifest_lines(root / config["manifest"], "rerun")
        by_slot = {run["slot"]: run for run in runs}
        rerun_slots = [slot_of(line["args"]) for line in added]
        require(rerun_slots == [row["slot"] for row in timeouts][:len(added)]
                and all(Path(line["primary"]).resolve() == by_slot[s]["folder"] for s, line in zip(rerun_slots, added))
                and all("--clock 3600" in line["args"] for line in added),
                "A rerun line does not name its timed-out primary run, or its doubled clock.")
        reruns = frozen_runs(study, protocol_path, [(schedule[s], line["folder"], line["args"])
                                                    for s, line in zip(rerun_slots, added)], 3600)
        for run, row in zip(reruns, timeouts):
            run.update(stage=RERUN, rerun_of=row)
        require(not {run["folder"] for run in reruns} & {run["folder"] for run in runs},
                "A rerun reused a primary results folder.")
        reruns_left = [row["slot"] for row in timeouts][len(added):]
    else:
        reruns_left = []
    inputs = {str((root / name).resolve()): blind.digest(root / name) for name in files}
    if partial:
        for name in (partial["log"], *partial["run_logs"]):
            inputs[str((root / name).resolve())] = blind.digest(root / name)
    for later_stage in (cont, rer):
        if later_stage:
            inputs[later_stage["path"]] = later_stage["sha256"]
    for run in runs + reruns:
        for name in ("suite.json", f"{run['task']}-{run['repeat']}.json", f"{run['task']}-{run['repeat']}.log"):
            if (run["folder"] / name).exists():
                inputs[str((run["folder"] / name).resolve())] = blind.digest(run["folder"] / name)
    return {"protocol": protocol, "protocol_path": protocol_path, "primary": primary, "statuses": statuses,
            "later": later, "runs": runs, "left": left, "reruns": reruns, "reruns_not_run": reruns_left,
            "partial_run": partial, "ruling": ruling, "inputs": inputs,
            "spec": json.loads(frozen.task_path(protocol).read_text()),
            "stage_args": {PRIMARY: [str(primary_path.resolve()), study.primary_sha256],
                           **{name: [stage["path"], stage["sha256"]] for name, stage in later.items() if stage}}}


def next_step_slot(primary, status):
    """The slot of the step the primary run had reached when it stopped, if it stopped mid-schedule."""
    done = len(status["completed_steps"])
    steps = primary["steps"]
    return steps[done]["study_slot"]["slot"] if done < len(steps) and steps[done]["kind"] == "paid" else None


def frozen_study(loaded, runs):
    """The frozen reader's own study value, for its sheet fields and measurements."""
    spec = loaded["spec"]
    return {"config": loaded["protocol"], "runs": runs, "spec": spec,
            "tasks": {task["id"]: task for task in spec["tasks"]}}


def classified(run):
    """The frozen void rules' class and reason for a run (voids.classify, as the reader calls it)."""
    if run["outcome"] in (voids.VOID, voids.CLOSED):
        return run["outcome"], run["technical_reason"] or "closed by the box"
    log_path = run["folder"] / f"{run['task']}-{run['repeat']}.log"
    log = log_path.read_text(errors="replace") if log_path.exists() else None
    outcome, reason, _ = voids.classify(run["record"], log, row=run["row"])
    return outcome, reason


def timed_out(run):
    """A run its own clock stopped: the frozen rules' clock limit, its elapsed time at or past its
    clock (guarded_matched_briefing.primary_timeouts)."""
    record = run["record"] or {}
    clock, elapsed = record.get("clock_s"), record.get("elapsed_s")
    return (classified(run) == TIMEOUT and isinstance(elapsed, (int, float)) and type(clock) is int
            and elapsed >= clock)


def preamble_check(loaded):
    """Reporting rule 5: every slot that ran carries one `preamble_sha256`, the same briefing of
    the same listings. Recorded at preparation, before the student opens the sheet."""
    seen = [(run["slot"], run["stage"], run["row"]["briefing"]["preamble_sha256"],
             len(run["row"]["briefing"]["page"]["listings"])) for run in loaded["runs"] + loaded["reruns"]]
    hashes = sorted({s[2] for s in seen})
    return {"rule": "reporting rule 5: all slots carry one preamble_sha256, the same briefing",
            "slots_checked": sorted({s[0] for s in seen if s[1] != RERUN}),
            "reruns_checked": sorted(s[0] for s in seen if s[1] == RERUN),
            "slots_not_run": sorted(loaded["left"]), "preamble_sha256": hashes,
            "listings_in_briefing": sorted({s[3] for s in seen}), "one_preamble": len(hashes) == 1}


def prepare(study, bundle, continuation=None, rerun=None):
    bundle = Path(bundle)
    require(not bundle.exists(), "The bundle already exists; its random codes are kept, never made again.")
    loaded = load_study(study, continuation, rerun)
    rows, codes, off_sheet = [], {}, []
    for runs in (loaded["runs"], loaded["reruns"]):
        on_sheet = {run["slot"]: fields for run, fields in frozen.review_rows(frozen_study(loaded, runs))}
        for run in runs:
            mapped = {"slot": run["slot"], "arm": run["arm"], "task": run["task"], "repeat": run["repeat"],
                      "stage": run["stage"], "rerun": run["stage"] == RERUN, "batch": run["batch"],
                      "folder": str(run["folder"]), "record_sha256": run["record_sha256"],
                      "log_sha256": run["log_sha256"], "outcome": run["outcome"]}
            if run["slot"] not in on_sheet:
                off_sheet.append({**mapped, "reason": run["technical_reason"] or "closed by the box: counted not correct"})
                continue
            fields = on_sheet[run["slot"]]
            code = blind.new_code(codes)
            rows.append({"code": code, **fields, "hand_verdict": "", "note": ""})
            codes[code] = {**mapped, "fields_sha256": frozen.object_digest(fields)}
    integrity = preamble_check(loaded)
    blind.write_bundle(study, bundle, rows, {
        "study_id": study.study_id, "stages": loaded["stage_args"], "codes": codes, "off_sheet": off_sheet,
        "inputs": loaded["inputs"]}, {
        "trials_scheduled": 16 + len(loaded["reruns"]) + len(loaded["reruns_not_run"]),
        "stages_sha256": {name: sha for name, (_, sha) in loaded["stage_args"].items()},
        "generator_sha256": blind.digest(Path(__file__)), "reader_sha256": blind.digest(Path(frozen.__file__)),
        "preamble_check": integrity})
    return len(rows), integrity


def completed_review(study, bundle):
    """The validated review and its receipt, checked before the private key is opened."""
    manifest = blind.read_json(bundle / "manifest.json")
    reviewed = bundle / "validated/reviewed.csv"
    require(reviewed.exists(), "No validated review: validate the student's completed CSV with --save first.")
    total = manifest.get("rows")
    require(blind.validate(study, bundle, reviewed) == (total, total), f"Complete all {total} human verdicts first.")
    receipt = blind.read_json(bundle / "validated/validation.json")
    require(receipt.get("study_id") == study.study_id and receipt.get("rows") == total
            and receipt.get("complete") is True and receipt.get("arm_key_read") is False
            and receipt.get("scored") is False
            and receipt.get("reviewed_sha256") == blind.digest(reviewed)
            and receipt.get("original_sheet_sha256") == manifest["original_sheet_sha256"],
            "Missing or changed pre-unblinding validation receipt.")
    return {row["code"]: row for row in blind.review.read_sheet(reviewed)}, manifest


def measured(loaded, run, hand, keys, truth, market):
    """One run's measurements, as matched_briefing_analysis.analyse measures each of its runs."""
    item = {k: run[k] for k in ("slot", "arm", "task", "repeat", "batch", "cost_usd", "agent_cost_usd", "parse_cost_usd")}
    item.update({"outcome": run["outcome"], "technical_reason": run["technical_reason"]})
    if run["outcome"] == voids.VOID:
        return item
    if run["outcome"] == voids.CLOSED:
        item.update({"hand_verdict": None, "automatic_verdict": "closed by the box", "opened": 0,
                     "elapsed_s": 0, "plan_compliance": None})
    else:
        task = {t["id"]: t for t in loaded["spec"]["tasks"]}[run["task"]]
        found = verify_cells.verify_run(run["folder"] / f"{run['task']}-{run['repeat']}.json",
                                        task, truth, run["row"], run["payload"], keys, market)
        require(found["opened"] is not None and found["elapsed_s"] is not None, "missing derived trace metrics")
        require(found["answer_matches_suite"], "suite answer differs from original final")
        reading = verify_cells.run_reading(run["row"], run["payload"])
        verdict = score.score_run(task, reading, keys, found["answer"], found["ok"])["verdict"]
        item.update(hand)
        item.update({"automatic_verdict": verdict, "stored_automatic_verdict": run["row"].get("verdict"),
                     "opened": found["opened"], "skus": found["skus"],
                     "elapsed_s": found["elapsed_s"], "selections": found["selections"],
                     "tokens": claim.stated_tokens(run["record"]), "providers": claim.agent_providers(
                         run["row"], run["folder"] / f"{run['task']}-{run['repeat']}.log"),
                     "plan_compliance": claim.answer_check({run["arm"]: [{
                         "folder": str(run["folder"]), "batch": run["batch"], "task": run["task"],
                         "repeat": run["repeat"], "planned": bool((run["row"].get("box") or {}).get("query"))
                     }]}, order=[run["arm"]])[run["arm"]] if run["arm"] == "full-block" else None})
    briefing = run["row"]["briefing"]
    item["pre_read_elapsed_s"] = briefing["pre_read_elapsed_s"]
    item["query_build_elapsed_s"] = briefing["query_build_elapsed_s"]
    item["total_measured_elapsed_s"] = item["elapsed_s"] + briefing["pre_read_elapsed_s"] + briefing["query_build_elapsed_s"]
    return item


def counted(item):
    """1 only when the student graded the answer correct, and the run neither timed out (amendment
    4: a timeout scores 0) nor was closed by the block (reporting rule 1)."""
    return int(item.get("hand_verdict") == "correct" and not item["timeout"] and item["outcome"] != voids.CLOSED)


def table(slots, use):
    """Per task and arm, and per arm over the tasks: the slots in the table, those that count
    correct, and the assessable denominator without unscorable rows (analysis-plan-B.md).
    `use(slot)` gives the item a view counts for a slot, or None to leave the slot out."""
    out, totals = {}, {arm: Counter() for arm in frozen.ARMS}
    for task in frozen.TASKS:
        out[task] = {}
        for arm in frozen.ARMS:
            group = [use(s) for s in slots if s["task"] == task and s["arm"] == arm]
            kept = [item for item in group if item is not None]
            cell = Counter({"slots": len(group), "in_table": len(kept),
                            "correct": sum(item["counted"] for item in kept),
                            "unscorable": sum(item.get("hand_verdict") == "unscorable" for item in kept),
                            "closed": sum(item["outcome"] == voids.CLOSED for item in kept),
                            "timeouts": sum(item["timeout"] for item in kept)})
            cell["assessable"] = cell["in_table"] - cell["unscorable"]
            out[task][arm] = dict(cell)
            totals[arm].update(cell)
        difference = out[task]["full-block"]["correct"] - out[task]["matched-briefing"]["correct"]
        # Reporting rule 3: two runs per condition, so one correct answer or less is no difference.
        out[task]["full_block_minus_matched_correct"] = difference
        out[task]["reading"] = ("no observable difference" if abs(difference) <= 1
                                else f"{'full block' if difference > 0 else 'matched briefing'} correct more often "
                                     f"by {abs(difference)}")
    return {"per_task": out, "per_arm": {arm: dict(cell) for arm, cell in totals.items()}}


def pairs(slots):
    """Each task and repeat's two slots, full block minus matched briefing. A void or a slot the
    block closed makes the pair's differences not comparable (reporting rule 1), never 0."""
    out = []
    for task in frozen.TASKS:
        for repeat in (1, 2):
            pair = {s["arm"]: s for s in slots if (s["task"], s["repeat"]) == (task, repeat)}
            a, b = pair["full-block"], pair["matched-briefing"]
            usable = all(s["outcome"] not in (voids.VOID, voids.CLOSED, NOT_STARTED) for s in (a, b))
            out.append({"task": task, "repeat": repeat, "arms": pair,
                        "comparable": usable or "not comparable: " + ", ".join(
                            f"{s['arm']} {s['outcome']}" for s in (a, b)
                            if s["outcome"] in (voids.VOID, voids.CLOSED, NOT_STARTED)),
                        "full_block_minus_matched": {f: a[f] - b[f] if usable else None for f in DIFFERENCES}})
    return out


def analyse(study, bundle):
    bundle = Path(bundle)
    human, manifest = completed_review(study, bundle)  # before the private key is opened
    key_path = bundle / "private-arm-key.json"
    require(blind.digest(key_path) == manifest["private_arm_key_sha256"], "The private key changed.")
    key = blind.read_json(key_path)
    require(key.get("study_id") == study.study_id and set(key["codes"]) == set(human)
            and {name: sha for name, (_, sha) in key["stages"].items()} == manifest["stages_sha256"],
            "The private key does not cover the review.")
    for path, wanted in key["inputs"].items():
        require(blind.digest(path) == wanted, "A file bound at preparation changed.")
    stages = key["stages"]
    loaded = load_study(study, stages.get(CONTINUATION), stages.get(RERUN))
    require(loaded["inputs"] == key["inputs"], "The study's files are not the set bound at preparation.")
    spec = loaded["spec"]
    truth = verify_cells.ground_truth(verify_cells.fixture_for(spec))
    market = verify_cells.market_urls(spec)
    keys = score.keys_for(frozen.task_path(loaded["protocol"]))
    by_run = {}
    for code, mapped in key["codes"].items():
        by_run[(mapped["stage"], mapped["slot"])] = (code, mapped)
    items = {PRIMARY: [], RERUN: []}
    for runs, kind in ((loaded["runs"], PRIMARY), (loaded["reruns"], RERUN)):
        on_sheet = {run["slot"]: fields for run, fields in frozen.review_rows(frozen_study(loaded, runs))}
        for run in runs:
            hand = {"code": None, "hand_verdict": None, "note": None}
            if run["slot"] in on_sheet:
                code, mapped = by_run.pop((run["stage"], run["slot"]))
                fields = on_sheet[run["slot"]]
                actual = {k: human[code][k] for k in ("question", "key", "answer")}
                require(all(mapped[k] == run[k] for k in ("arm", "task", "repeat", "batch", "record_sha256", "log_sha256"))
                        and actual == fields and frozen.object_digest(actual) == mapped["fields_sha256"],
                        "Reviewed evidence differs from its run or its key.")
                hand = {"code": code, "hand_verdict": human[code]["hand_verdict"], "note": human[code]["note"]}
            item = measured(loaded, run, hand, keys, truth, market)
            outcome, reason = classified(run)
            item.update(stage=run["stage"], classification=outcome, classification_reason=reason,
                        timeout=timed_out(run))
            item["counted"] = counted(item) if outcome != voids.VOID else None
            items[kind].append(item)
    require(not by_run, "The private key names a run the study does not hold.")
    slots = items[PRIMARY] + [{**left, "timeout": False, "counted": None, "batch": None}
                              for left in loaded["left"].values()]
    slots.sort(key=lambda s: s["slot"])
    require([s["slot"] for s in slots] == list(range(1, 17)), "The 16 slots are not each held once.")
    reruns = {item["slot"]: item for item in items[RERUN]}

    def primary(s):
        return None if s["outcome"] in (voids.VOID, NOT_STARTED) else s

    def without_timeouts(s):
        return None if primary(s) is None or s["timeout"] else s

    def with_rerun(s):
        if primary(s) is None:
            return None
        rerun = reruns.get(s["slot"])
        if s["timeout"] and rerun and rerun["outcome"] != voids.VOID:
            return rerun
        return s

    timeouts = [s for s in slots if s["timeout"]]
    by_code = {s["code"]: s for s in slots + items[RERUN] if s.get("code")}
    graded = list(by_code.values())
    disagreements = []
    for s in graded:
        lean = claim.lean_of(s["automatic_verdict"], claim.HAND_VERDICTS[s["hand_verdict"]])
        if lean:
            disagreements.append({"slot": s["slot"], "stage": s["stage"], "code": s["code"], "arm": s["arm"],
                                  "hand": s["hand_verdict"], "automatic": s["automatic_verdict"], "difference": lean})
    slot16 = next(s for s in slots if s["slot"] == 16)
    return {
        "study_id": study.study_id, "scope": frozen.STUDIES[study.study_id], "scorer_version": score.VERSION,
        "stages": {name: {"configuration": path, "sha256": sha} for name, (path, sha) in stages.items()},
        "integrity": preamble_check(loaded),
        "slot_16": {"state": ("run again on the student's ruling, labelled" if loaded["ruling"] else
                              slot16["outcome"]),
                    "ruling": loaded["ruling"], "partial_run": loaded["partial_run"],
                    "stage": slot16.get("stage"), "outcome": slot16["outcome"],
                    "note": "amendment 4, correction of 12:30: the primary run started slot 16 and its budget "
                            "stop ended it with no record. A technical void unless the student ruled otherwise"},
        "primary": {**table(slots, primary),
                    "role": "pre-registered, descriptive: the student's grade. A timeout scores 0 (amendment 4). "
                            "A slot the block closed counts not correct (rule 1). Unscorable rows leave the "
                            "assessable denominator. Voids and slots not started are left out with their charges"},
        "timeouts_per_arm": {arm: {"timeouts": sum(s["arm"] == arm for s in timeouts),
                                   "slots": [s["slot"] for s in timeouts if s["arm"] == arm]} for arm in frozen.ARMS},
        "sensitivity_1_timeouts_left_out": {**table(slots, without_timeouts),
                                            "role": "amendment 4: timed-out slots left out"},
        "sensitivity_2_timeouts_replaced_by_rerun": {
            **table(slots, with_rerun),
            "substituted": [{"slot": s["slot"], "arm": s["arm"], "rerun": bool(reruns.get(s["slot"])),
                             "rerun_outcome": (reruns.get(s["slot"]) or {}).get("outcome"),
                             "used": "rerun with its clock doubled to 3600 s" if with_rerun(s) is not s
                             else "no rerun outcome: the primary timeout kept, counted 0"} for s in timeouts],
            "role": "amendment 4, secondary: each timed-out slot counts its rerun, run once with its clock doubled"},
        "paired_by_task_repeat": pairs(slots),
        "slots": slots,
        "reruns": {"role": "never pooled into a primary figure, used only by sensitivity 2",
                   "trials": items[RERUN], "not_run": loaded["reruns_not_run"]},
        "human_automatic_disagreements": disagreements,
        # A row the void rules call reported, not correct but the student graded correct keeps its
        # grade (the plan's verdict of record), apart from a timeout, which amendment 4 scores 0.
        "graded_correct_but_reported_not_correct": [
            {"slot": s["slot"], "stage": s["stage"], "code": s["code"], "reason": s["classification_reason"],
             "counted": s["counted"]} for s in graded
            if s["hand_verdict"] == "correct" and s["classification"] == voids.NOT_CORRECT],
        "charges": {"known_usd": round(sum(r["cost_usd"] for r in loaded["runs"] + loaded["reruns"]), 6),
                    # A started slot no runner recorded: its charges only from its own run logs, by
                    # the frozen trace reader, as the later stages' carryover counts them.
                    "slots_without_a_record": [
                        {"slot": s["slot"], "logged_charges_usd": (s["partial_run"] or {}).get("charges_usd"),
                         "logged_charged_calls": (s["partial_run"] or {}).get("charged_calls")}
                        for s in slots if s["outcome"] == voids.VOID and s.get("cost_usd") is None]},
        "technical_rule": "Original voids.classify; voids excluded, charges retained; no automatic replay.",
        "no_significance_test": "analysis-plan-B.md declares none. Totals are exact counts with no significance claim"}


def stage_arguments(args):
    return {name: (Path(value[0]), value[1]) for name, value in ((CONTINUATION, args.continuation),
                                                                 (RERUN, args.rerun)) if value}


def main(study=STUDY_B):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    prep = modes.add_parser("prepare")
    prep.add_argument("--bundle", type=Path, required=True)
    for flag in ("--continuation", "--rerun"):
        prep.add_argument(flag, nargs=2, metavar=("CONFIG", "SHA256"),
                          help="a later stage's configuration and the SHA-256 its verifier's receipt names")
    check = modes.add_parser("validate")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--reviewed", type=Path, required=True)
    check.add_argument("--save", action="store_true", help="write the completed review and its receipt")
    report = modes.add_parser("analysis")
    report.add_argument("--bundle", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            stages = stage_arguments(args)
            count, integrity = prepare(study, args.bundle, stages.get(CONTINUATION), stages.get(RERUN))
            print(f"Prepared {count} blank review rows. No answer displayed or scored.")
            print(f"Reporting rule 5: {len(integrity['slots_checked'])} slots and {len(integrity['reruns_checked'])} "
                  f"reruns carry {len(integrity['preamble_sha256'])} preamble_sha256 "
                  f"({'one briefing' if integrity['one_preamble'] else 'MORE THAN ONE: inspect before review'}).")
            print(f"Open {(args.bundle / 'review.html').resolve()}")
        elif args.mode == "validate":
            done, total = blind.validate(study, args.bundle, args.reviewed, args.save)
            print(f"{done}/{total} reviewed; the blank sheet is unchanged. No private key, record or scorer read.")
            if done != total:
                return 2
        else:
            require(not args.output.exists(), "Refusing to overwrite the analysis output.")
            result = analyse(study, args.bundle)
            blind.write_json(args.output, result)
            print(json.dumps({k: result[k] for k in ("integrity", "slot_16", "timeouts_per_arm")}
                             | {"primary_per_arm": result["primary"]["per_arm"],
                                "sensitivity_1_per_arm": result["sensitivity_1_timeouts_left_out"]["per_arm"],
                                "sensitivity_2_per_arm": result["sensitivity_2_timeouts_replaced_by_rerun"]["per_arm"]},
                             indent=2, default=str))
    except Refused as error:
        print(f"Review operation refused: {error}", file=sys.stderr)
        return 1
    except (ValueError, OSError, KeyError, TypeError, csv.Error) as error:
        # Other errors may carry answer text, so only their kind is shown.
        print(f"Review operation refused ({type(error).__name__}). No answer content displayed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
