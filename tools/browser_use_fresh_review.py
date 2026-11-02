#!/usr/bin/env python3
"""Blind review of Study A, Browser Use on the fresh market, prepared and validated offline.

Study A (notes/fresh-market-2-nov/analysis-plan-A.md) runs 32 Browser Use trials on Rookmere,
seed 1002: 8 questions, 2 arms, repeats 1 and 2. They ran in stages (amendments 3, 4 and 6,
2 November 2026): attempt 1; attempt 2, its continuation; attempt 3, for any slot attempt 2 left
never started; attempt 4, for any slot attempt 3 left never started; and one timeout rerun of each
slot whose primary record reached its 2700 s clock, with the clock doubled. `prepare` checks every stage against the configuration it ran under and
against the stages before it, then copies the answer text of every trial the agent ran, primary
or rerun, into one blank sheet under random codes, failed and timed-out trials included. The
student sees the question, the key and the full answer only: no arm, repeat, attempt, stage,
rerun flag, outcome, cost, time or automatic score. Which code is which trial goes to a separate
private file. Trials the block closed are not on the sheet: the frozen reading rules keep them
off it ("Not on the sheet") and the plan counts them 0. `validate` reads only the public
manifest, the blank sheet and the student's CSV, and with --save writes the completed-review
receipt that browser_use_fresh_analysis.py needs before it opens the private file. Nothing here
scores an answer or calls a model, a provider or an account.

Written 2 November 2026 on the pattern of browser_use_repeat_review.py, which is bound to
Quenby's commands, task-file hashes and the 32-slot repeats 2-3 schedule. Here everything a
review is bound to is one `Study` value, so the tests run the same code on synthetic stages.

    python3 tools/browser_use_fresh_review.py prepare \\
        --attempt1 notes/fresh-market-2-nov/study-a-command.json <its SHA-256> \\
        --attempt2 notes/fresh-market-2-nov/study-a-continuation-command.json <its SHA-256> \\
        [--attempt3 <attempt 3's configuration> <its SHA-256>] \\
        [--attempt4 <attempt 4's configuration> <its SHA-256>] \\
        [--rerun <the timeout reruns' configuration> <its SHA-256>] \\
        --bundle notes/fresh-market-2-nov/study-a-review
    python3 tools/browser_use_fresh_review.py validate \\
        --bundle notes/fresh-market-2-nov/study-a-review --reviewed <the student's CSV> --save
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402,F401  (puts runners/ and analysis/ on the import path)
import browser_use_transfer as transfer  # noqa: E402  (the runner's own schedule, warning and stage rules)
import guarded_browser_use as guard  # noqa: E402  (the launcher's stage names and question builder)
import hand_review as review  # noqa: E402  (the tested sheet reader, merger and reader page)

TERMINAL = ("answered", "failed", "timeout", "closed by the block")  # the worker saved a record
CLOSED = "closed by the block"
GUARD_STOPPED = ("interrupted", "time_censored")  # the launcher stopped the slot while it ran
NOT_STARTED = "not_started"
# What every trial record of the cohort's adapter carries (browser_use_runner.run_trial).
ADAPTER = {"scaffold": "browser-use", "browser_use_version": "0.13.14",
           "dropdown_semantics": "native-disabled-state-v1",
           "evaluate_semantics": "fresh-local-script-scope-v1", "offline_scripted": False}
# The launch settings a trial record repeats in its "settings", each compared with the
# configuration, so a trial run under another setting cannot join the review. The clock is the
# slot's own: 2700 s, or 5400 s for a timeout rerun (amendment 4).
SETTINGS = ("model", "provider", "temperature", "frequency_penalty", "top_p", "max_input_bytes",
            "max_output_tokens", "max_steps", "max_failures", "clock_s", "llm_timeout",
            "browser_executable")
RULES = ROOT / "docs/content/claim2-reading-rules.md"
# The adapter's save_as_pdf result shows the agent its output path, which holds the slot id and
# so the arm (the verifier's receipt for Study A, 2 November 2026). An answer that repeats it
# names its arm to the student: it is copied as it is, flagged and listed, never edited. None of
# the 48 stored answers of the earlier Browser Use studies matches. A rerun's path also names its
# stage folder, so the same flag covers it.
ARM_LABEL = re.compile(r"-r\d+-(?:block|baseline)\b", re.I)
# Amendment 1: Browser Use writes a saved file's full path into the agent's memory as
# "Full path: ..." (browser_use/tools/service.py 1666-1673). A slot whose conversation holds it
# is listed with its arm. Read from the slot's conversation files, as the cohort's were.
FULL_PATH = "Full path:"

NOTE = """Browser Use fresh-market review (Rookmere), 2 November 2026

One row for each Browser Use trial of this study that the agent ran, in random order, with the
answer text that trial recorded. A row is empty when the trial recorded none. Judge only the
final commitment, against the expected answer and the frozen rules below. Do not grade the
amount of browsing, evidence sufficiency, presentation quality or cost. No verdict has been
supplied by AI. This page adds no arm label, repeat label, attempt, stage, rerun label,
execution outcome, cost, time or automatic verdict. An answer itself may still suggest its
condition, and one that quotes a file path of the agent's may even name it: judge that row by
the same rules. Rows from earlier studies are not part of this review, and the references below
to other studies or a second reader add no rows to it.

"""


@dataclasses.dataclass(frozen=True)
class Stage:
    """One launch of Study A (amendments 3 and 4, 2 November 2026). A primary stage runs slots of
    the 32-slot plan, each slot in at most one of them; the timeout reruns are records of their
    own, linked to the primary record they rerun, which they never replace."""
    name: str        # what the private key and the analysis call it
    stage: str       # the launcher's stage id
    attempt: object  # 1, 2, 3, or the reruns' "timeout-rerun"
    prefix: str      # its files' names beside the others: ledger, status, launch claim, results
    primary: bool = True


ATTEMPT1 = Stage("attempt 1", guard.FRESH_STAGE, 1, guard.FRESH_PREFIX[guard.FRESH_STAGE])
ATTEMPT2 = Stage("attempt 2", guard.FRESH_CONTINUATION_STAGE, 2, guard.FRESH_PREFIX[guard.FRESH_CONTINUATION_STAGE])
ATTEMPT3 = Stage("attempt 3", guard.FRESH_ATTEMPT3_STAGE, 3, guard.FRESH_PREFIX[guard.FRESH_ATTEMPT3_STAGE])
# Amendment 6 (2 November 2026, 17:40): attempt 4 runs the slots attempt 3 left never started,
# under attempt 3's conditions.
ATTEMPT4 = Stage("attempt 4", guard.FRESH_ATTEMPT4_STAGE, 4, guard.FRESH_PREFIX[guard.FRESH_ATTEMPT4_STAGE])
RERUN = Stage("timeout rerun", guard.FRESH_RERUN_STAGE, guard.FRESH_RERUN_ATTEMPT,
              guard.FRESH_PREFIX[guard.FRESH_RERUN_STAGE], primary=False)
STAGES = (ATTEMPT1, ATTEMPT2, ATTEMPT3, ATTEMPT4, RERUN)
PRIMARY = (ATTEMPT1, ATTEMPT2, ATTEMPT3, ATTEMPT4)
# The stages that end a clock timeout or a void after a settled request as its own slot and go
# on (amendment 3), whose records carry `attempt`, the settlement counts and `disposition`.
SETTLING = guard.FRESH_SETTLING_STAGES
# Attempt 4 and the reruns also settle an executor's error reply without usage at its bound, by
# this label, and their records count those apart in `error_reply_settlements`, as well as inside
# `no_response_settlements` (amendment 6; guarded_browser_use.CallBudget, browser_use_transfer).
ERROR_REPLY_STAGES = guard.FRESH_ERROR_REPLY_STAGES
ERROR_REPLY_KIND = "error reply without usage"


@dataclasses.dataclass(frozen=True)
class Study:
    """Everything one blind review is bound to. STUDY_A is the fresh market's; the tests build
    their own on synthetic stages."""
    study_id: str        # the schedule's, every record's, every ledger's and every launch claim's
    task_ids: tuple      # the question types, in the schedule's order
    repeats: tuple
    clock_s: int
    market: dict         # as the configuration and every record name it
    tasks_file: str      # the generated questions and keys, a repository path
    readings_file: str   # their readings sidecar
    files: dict          # repository path -> SHA-256 of every frozen file the plan names
    rules_sha256: str    # the frozen reading rules the student grades under
    sheet: str           # the blank sheet's file name, and the reader's download name
    pinned: dict         # stage name -> the SHA-256 its configuration must have, where fixed
    note: str = NOTE     # what the reader says about this review before the rules


# Each SHA-256 below is the committed file's at b1c67c8, the configuration's own hash for it,
# and is checked against the repository by tests/test_browser_use_fresh_review.py. Attempts 1
# to 3 ran under the commands the launcher pins; attempt 4's and the reruns' are named on the
# command line with their SHA-256, which their verifier's receipt and launch claim must bind.
STUDY_A = Study(
    study_id=guard.FRESH_BUDGET, task_ids=transfer.TASK_IDS, repeats=(1, 2), clock_s=2700,
    market={"fixture": "env/fixtures/tee_fresh_2_nov.json",
            "search_record": "env/manifests/tee_fresh_2_nov-search.json",
            "brand": "Rookmere", "sku_prefix": "IGR-FM02", "seed": 1002},
    tasks_file="experiments/tasks/tasks_tee_fresh_2_nov.json",
    readings_file="experiments/tasks/readings_tee_fresh_2_nov.json",
    files={
        "experiments/tasks/tasks_tee_fresh_2_nov.json": "2e92b1876d3f7ca6da2440da62dc4aab3e10f91535ca08fc8a4edbc2d06748ef",
        "experiments/tasks/readings_tee_fresh_2_nov.json": "002b29f994dae1c4bab2bf2324a3bafa552a584939391eb3ef85f917899c361a",
        "env/fixtures/tee_fresh_2_nov.json": "48222402dd41b95cf31297996b685e3b3e7f5953c305ba14190f8dcf6f2b0712",
        "env/manifests/tee_fresh_2_nov-search.json": "5aa31e86f992bbc847ec7c2b59478d584726eaa196d8c41c1af1f095900de7a1",
        "notes/fresh-market-2-nov/protocol.md": "d19e2675ebd0edbcffc42689cb6da4f3132993305a2356066390f00646e8b746",
        "notes/fresh-market-2-nov/analysis-plan-A.md": "c0f3703672c3d0d7d4f7785426d65042755e92509e6401873a93d7ed8766852b",
    },
    rules_sha256="9433423f14f4de200da4b0376e84839c57751af93b98c9f8e599b35a6d274bb4",
    sheet="study-a-fresh-2-nov.sheet.csv",
    pinned={ATTEMPT1.name: guard.FRESH_ATTEMPT1_SHA256, ATTEMPT2.name: guard.FRESH_CONTINUATION_SHA256,
            ATTEMPT3.name: guard.FRESH_ATTEMPT3_SHA256})


class Refused(ValueError):
    """A check failed. Its message is fixed text, never answer content, so it may be printed."""


def require(condition, message):
    if not condition:
        raise Refused(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def read_json(path):
    # Never echo a malformed line: it could hold answer text.
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise Refused(f"{Path(path).name} is not valid JSON; no content shown.") from None


def write_json(path, data):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def expected_slots(questions, repeats, clock_s):
    """The 32 slots as the runner's preview builds them for a guarded stage: the frozen
    `schedule` (arms adjacent, the first arm alternating, repeat 2 reversing repeat 1), each id
    prefixed, every slot a transfer slot on the trial clock."""
    slots = transfer.schedule(questions, repeats)
    for slot in slots:
        slot.update(id="transfer-" + slot["id"], phase="transfer", clock_s=clock_s)
    return slots


def launched(notes, spec):
    """Whether a stage has left any file beside the others: its launch claim, status, ledger or
    results (guarded_browser_use.launched, read from attempt 1's own folder). A stage with
    nothing left to run leaves none."""
    return any((Path(notes) / f"{spec.prefix}.{name}").exists()
               for name in ("launch.json", "status.json", "ledger.json", "results"))


def conversation(folder):
    """A trial's conversation files: how many, one SHA-256 over their names and contents, and
    whether any holds Browser Use's "Full path:" line (amendment 1). Text is searched, never
    shown or kept."""
    files = sorted(Path(folder, "conversation").glob("*.txt")) if Path(folder, "conversation").is_dir() else []
    combined = hashlib.sha256()
    found = False
    for path in files:
        data = path.read_bytes()
        combined.update(path.name.encode() + b"\0" + hashlib.sha256(data).digest())
        found = found or FULL_PATH.encode() in data
    return {"files": len(files), "sha256": combined.hexdigest(), "full_path": found}


def check_record(study, spec, config, config_sha256, slot, row, record):
    """One saved record against its slot, its stage's configuration and the arm's design."""
    question, status = slot["question"], row["status"]
    identity = {"study_id": study.study_id, "batch_id": study.study_id, "stage": spec.stage,
                "phase": "transfer", "slot": slot["id"], "task": question["id"],
                "question": question["query"], "condition": slot["condition"],
                "repeat": slot["repeat"], "outcome": status, "market": config["market"],
                "config_sha256": config_sha256, "head": config["expected_head"],
                "briefing_sha256": text_digest(transfer.COMMON_BRIEFING)}
    if spec.stage in SETTLING:
        identity["attempt"] = spec.attempt
    if not spec.primary:
        identity["rerun_of"] = slot["rerun_of"]  # the primary record it reruns, by path and hash
    require(all(record.get(k) == v for k, v in identity.items()),
            f"{spec.name}: a record differs from its scheduled slot, configuration or commit.")
    require(record.get("answer") is None or isinstance(record["answer"], str), "Unsupported answer value.")
    require(isinstance(record.get("calls"), list), "A record has no call list.")
    if spec.stage in SETTLING:
        # The runner counts the requests settled at their bound, by kind (browser_use_transfer).
        settled = [call for call in record["calls"] if "settled_usd" in call]
        by_clock = [call for call in settled if call.get("settlement_kind") == "trial clock"]
        counts = (record.get("no_response_settlements"), record.get("clock_settlements"))
        require(all(type(n) is int for n in counts) and counts == (len(settled) - len(by_clock), len(by_clock))
                and all(call.get("cost_usd") is None for call in settled),
                f"{spec.name}: a record's settlement counts disagree with its calls.")
        # The runner's own rule ends a clock timeout, or a void after a settled request, as its
        # slot; recomputed here, it must agree with what the record and its status say.
        state, _ = transfer.continuation_disposition(record)
        require(record.get("disposition") == state and row.get("disposition") == state,
                f"{spec.name}: a record's disposition differs from the runner's rule.")
        replies = sum(call.get("settlement_kind") == ERROR_REPLY_KIND for call in settled)
        require(record.get("error_reply_settlements") == replies if spec.stage in ERROR_REPLY_STAGES
                else "error_reply_settlements" not in record and not replies,
                f"{spec.name}: a record's error-reply settlements disagree with its calls or its stage.")
    else:
        require("disposition" not in record and "disposition" not in row
                and not any("settled_usd" in call for call in record["calls"]),
                f"{spec.name}: a stage that settles no request has a settled record.")
    page = record.get("page") or {}
    require(page.get("reader") == "rendered" and page.get("listings") and not page.get("next_page")
            and page.get("total") == len(page["listings"]),
            "A record lacks the complete rendered results page its trial started from.")
    prefix = transfer.COMMON_BRIEFING + "\n\n"
    if slot["condition"] == "baseline":
        require(record.get("box") is None and record.get("sent_query") == prefix + question["query"],
                "A baseline record was not sent the warning and the question alone.")
    else:
        box = record.get("box")
        require(isinstance(box, dict), "A block record lacks the block's decision.")
        if status != CLOSED:
            require(isinstance(record.get("sent_query"), str) and record["sent_query"] == prefix + str(box.get("query")),
                    "A block record was not sent the warning and the block's text.")
    if status == CLOSED:
        # The block refused or asked, so no browser and no agent ran (browser_use_transfer).
        require(slot["condition"] == "block" and record.get("sent_query") is None
                and record.get("trace") == {"opened": 0, "measurement_valid": True}
                and record.get("cost_usd") == 0 and "script_fetches" not in record
                and all(call.get("role") == "parser" for call in record["calls"]),
                "A record closed by the block is not shaped as the runner writes one.")
        return
    require(all(record.get(k) == v for k, v in ADAPTER.items())
            and record.get("model") == config["model"] and record.get("provider_routing") == config["provider"],
            "A trial ran under another adapter, model or routing.")
    settings = record.get("settings") or {}
    require(all(settings.get(k) == (slot["clock_s"] if k == "clock_s" else config[k]) for k in SETTINGS)
            and settings.get("start_url") == question["start_url"],
            "A trial ran under settings other than its configuration's.")
    # Absent only when the trial failed before its browser opened, which its error records.
    version = record.get("browser_version")
    require(version == config["preflight_browser_version"] or (version is None and record.get("error_type")),
            "A trial ran on another browser build.")


def load_stage(study, spec, config_path, config_sha256, given=None):
    """One stage's files, checked against the configuration it ran under, with the SHA-256 of
    each file read. `given` is the slots this stage was given, in their order: None for attempt
    1, whose planned 32 are built from its own questions. Refuses on any slot added, moved,
    missing or replayed."""
    config_path = Path(config_path).resolve()
    require(digest(config_path) == config_sha256,
            f"{spec.name}: the configuration file is not the one named by its SHA-256.")
    require(study.pinned.get(spec.name, config_sha256) == config_sha256,
            f"{spec.name}: not the configuration this study ran.")
    config = read_json(config_path)
    repo = Path(config["repo"]).resolve()
    require(config.get("stage") == spec.stage and config.get("attempt") == spec.attempt
            and config.get("study_budget_id") == study.study_id
            and config.get("repeats") == list(study.repeats)
            and config.get("clock_s") == study.clock_s and config.get("market") == study.market
            and config.get("tasks_file") == study.tasks_file
            and study.readings_file in config.get("market_files", [])
            and (spec.primary or config.get("rerun_clock_s") == 2 * study.clock_s),
            f"{spec.name}: the configuration is not this study's.")
    for name, wanted in study.files.items():
        require(config["hashes"].get(name) == wanted and digest(repo / name) == wanted,
                f"{name} is not the frozen file the study names.")
    require(digest(RULES) == study.rules_sha256, "The frozen reading rules changed.")
    task_spec = read_json(repo / study.tasks_file)
    tasks = {task["id"]: task for task in task_spec["tasks"]}
    try:
        generated = guard.runtime_questions(task_spec, study.task_ids)
    except guard.Stop:
        generated = None
    # The questions the agent received are the generator's, byte for byte.
    require(config["questions"] == generated
            and read_json(config["questions_file"])["questions"] == config["questions"],
            "The executed questions differ from the generated task file.")
    readings = read_json(repo / study.readings_file)
    for task_id in study.task_ids:
        expect = tasks[task_id].get("expect")
        require(isinstance(expect, dict) and expect.get("kind") != "none", "A question has no answer key.")
        # One key whatever reading a run took: a reading's own key on the sheet would tell the
        # student which arm read the question that way.
        require(task_id not in readings.get("two_readings", [])
                and all(keyed.get(task_id, expect) == expect for keyed in readings["readings"].values()),
                "A question's key depends on its reading.")
    ledger_path = Path(config["ledger_path"])
    results = Path(config["output_dir"])
    status_path = Path(config["status_path"])
    if status_path.exists():
        status = read_json(status_path)
    else:
        # The launcher refuses its balance check after its launch claim and before its first
        # status (guarded_browser_use.execute, 2 November 2026): a claim and nothing else.
        require(not results.exists() and not ledger_path.exists(),
                f"{spec.name}: the stage left results or a ledger but no status. Inspect it.")
        status = {"status": "stopped", "config_sha256": config_sha256,
                  "reason": "the launcher refused before its first trial: a launch claim and no status"}
    marker_path = ledger_path.with_name(spec.prefix + ".launch.json")
    marker = read_json(marker_path)
    receipt = read_json(config["verification_receipt"])
    approval = read_json(config["approval_record"])
    require(status.get("status") in ("complete", "stopped") and status.get("config_sha256") == config_sha256,
            f"{spec.name}: the stage has not ended under this configuration.")
    require(marker.get("study_budget_id") == study.study_id and marker.get("attempt") == spec.attempt
            and marker.get("config_sha256") == config_sha256,
            f"{spec.name}: the launch claim is not this stage's.")
    require(receipt.get("verdict") == "PASS" and receipt.get("config_sha256") == config_sha256
            and receipt.get("head") == config["expected_head"]
            and approval.get("approved") is True and approval.get("config_sha256") == config_sha256,
            f"{spec.name}: the configuration lacks the verifier's pass or the student's approval.")
    slots = expected_slots(config["questions"], study.repeats, study.clock_s) if given is None else given
    ids = [slot["id"] for slot in slots]
    inputs = {str(path.resolve()): digest(path) for path in (
        config_path, *([status_path] if status_path.exists() else []), marker_path, Path(config["verification_receipt"]),
        Path(config["approval_record"]), Path(config["questions_file"]), RULES, *(repo / name for name in study.files))}
    batch = {"spec": spec, "config": config, "config_path": str(config_path), "config_sha256": config_sha256,
             "repo": repo, "status": status, "slots": slots, "tasks": tasks, "task_spec": task_spec,
             "results": results, "records": {}, "interrupted": {}, "inputs": inputs}
    if not results.exists():
        # The stage stopped before its worker started, as on a refused balance check: no slot
        # ran and no call was paid for, so every slot it was given stays not started.
        ledger = read_json(ledger_path) if ledger_path.exists() else None
        require(status["status"] == "stopped" and not (ledger or {}).get("calls"),
                f"{spec.name}: the stage left calls or ended complete without its results. Inspect it.")
        if ledger is not None:
            inputs[str(ledger_path.resolve())] = digest(ledger_path)
        reason = status.get("reason") or "the stage stopped before its first trial"
        return {**batch, "ledger": ledger, "ran": 0, "stopped": [],
                "statuses": {i: {"phase": "transfer", "status": NOT_STARTED, "reason": reason} for i in ids}}
    ledger = read_json(ledger_path)
    require(ledger.get("study_budget_id") == study.study_id and ledger.get("attempt") == spec.attempt,
            f"{spec.name}: the ledger is not this stage's.")
    schedule = read_json(results / "schedule.json")
    require(schedule.get("study_id") == study.study_id and schedule.get("batch_id") == study.study_id
            and schedule.get("stage") == spec.stage and schedule.get("paid_calls") == 0
            and schedule.get("attempt", 1) == spec.attempt and schedule.get("slots") == slots
            and schedule.get("warning_sha256") == text_digest(transfer.COMMON_BRIEFING),
            f"{spec.name}: the schedule is not the slots this stage was given, in their planned order.")
    statuses = read_json(results / "slot-status.json")["slots"]
    require(set(statuses) == set(ids) and all(statuses[i].get("phase") == "transfer" for i in ids),
            "Missing, extra or foreign slot status.")
    done_path = results / "completed.json"
    done = read_json(done_path) if done_path.exists() else {"completed": [], "expected": len(ids)}
    ran = len(done["completed"])
    # Slots run one at a time in schedule order, so the saved ones are a prefix of it; at most
    # the next one was stopped while it ran, and every later one never started.
    require(done.get("expected") == len(ids) and done["completed"] == ids[:ran], "Completed slots out of order.")
    stopped = [i for i in ids[ran:] if statuses[i]["status"] in GUARD_STOPPED]
    require(all(statuses[i]["status"] in TERMINAL for i in ids[:ran])
            and stopped in ([], ids[ran:ran + 1])
            and all(statuses[i]["status"] == NOT_STARTED for i in ids[ran + len(stopped):])
            and (status["status"] == "stopped" or ran == len(ids)),
            "Slot statuses do not show one sequential run.")
    allowed_files = {"schedule.json", "slot-status.json", "completed.json"}
    allowed_files |= {i + ".json" for i in ids[:ran]} | {i + ".interrupted.json" for i in stopped}
    for entry in results.iterdir():
        if entry.name.startswith("."):
            continue  # the operating system's own files, such as .DS_Store
        require(entry.name in allowed_files if entry.is_file() else entry.name in ids[:ran] + stopped,
                "Unexpected, missing or replayed trial file in the results folder.")
    inputs.update({str(path.resolve()): digest(path) for path in (
        ledger_path, results / "schedule.json", results / "slot-status.json", *([done_path] if done_path.exists() else []))})
    for slot in slots[:ran]:
        path = results / (slot["id"] + ".json")
        record = read_json(path)
        check_record(study, spec, config, config_sha256, slot, statuses[slot["id"]], record)
        batch["records"][slot["id"]] = record
        inputs[str(path.resolve())] = digest(path)
    for slot_id in stopped:
        path = results / (slot_id + ".interrupted.json")
        if path.exists():
            batch["interrupted"][slot_id] = read_json(path)
            inputs[str(path.resolve())] = digest(path)
    return {**batch, "ledger": ledger, "ran": ran, "stopped": stopped, "statuses": statuses}


def timeout_row(batch, slot_id):
    """A primary slot whose record reached its trial clock, as the reruns' configuration names
    it (guarded_browser_use.ended_primary_stages)."""
    spec, record = batch["spec"], batch["records"][slot_id]
    path = batch["results"] / (slot_id + ".json")
    return {"slot": slot_id, "stage": spec.stage, "attempt": spec.attempt,
            "record": str(path.resolve().relative_to(batch["repo"])), "record_sha256": digest(path),
            "elapsed_s": record["elapsed_s"], "clock_s": record["settings"]["clock_s"]}


def load_study(study, stages):
    """Every stage of the study, each checked against its own configuration, the slots it was
    given and the files the stages after it bound. `stages` maps a stage's name to its
    configuration's path and SHA-256: attempt 1 always, and every later stage that was launched.
    Returns the 32 planned slots, which stage holds each (the one that ran it, else the last one
    given it), and the timeout reruns by slot."""
    require(ATTEMPT1.name in stages and set(stages) <= {spec.name for spec in STAGES},
            "Attempt 1's configuration is needed, and only this study's stages.")
    first = load_stage(study, ATTEMPT1, *stages[ATTEMPT1.name])
    repo, notes = first["repo"], Path(first["config"]["ledger_path"]).parent
    loaded, slots = [first], first["slots"]
    left = [slot for slot in slots if first["statuses"][slot["id"]]["status"] == NOT_STARTED]
    for spec in PRIMARY[1:]:
        if spec.name not in stages:
            # A stage nobody named must have left nothing: every answer goes on the one sheet.
            require(not launched(notes, spec), f"{spec.name} was launched: name its configuration.")
            continue
        require(loaded[-1]["spec"] is PRIMARY[PRIMARY.index(spec) - 1],
                f"{spec.name} follows the attempt before it, which was not named.")
        require(left, f"{spec.name} ran though the attempt before it left no slot never started. Inspect it.")
        batch = load_stage(study, spec, *stages[spec.name], given=left)
        loaded.append(batch)
        left = [slot for slot in left if batch["statuses"][slot["id"]]["status"] == NOT_STARTED]
    held = {}
    for batch in loaded:
        for slot in batch["slots"]:
            held[slot["id"]] = {"spec": batch["spec"], "batch": batch, "status": batch["statuses"][slot["id"]],
                                "record": batch["records"].get(slot["id"]),
                                "interrupted": batch["interrupted"].get(slot["id"])}
    # Each slot whose primary record reached its clock is rerun once, in schedule order, with
    # its clock doubled and nothing else changed (amendment 4).
    timeouts = [timeout_row(held[s["id"]]["batch"], s["id"]) for s in slots
                if (held[s["id"]]["record"] or {}).get("disposition") == "timeout"]
    reruns = None
    if RERUN.name in stages:
        # The reruns start only after the last attempt has ended: each attempt runs whenever the one
        # before it left a slot never started (amendment 4 point 6, amendment 6 point 4).
        require(not left or loaded[-1]["spec"] is PRIMARY[-1],
                "The reruns ran before the last attempt, while slots were left never started.")
        by_id = {slot["id"]: slot for slot in slots}
        given = [{**by_id[row["slot"]], "clock_s": 2 * study.clock_s, "rerun_of": row} for row in timeouts]
        reruns = load_stage(study, RERUN, *stages[RERUN.name], given=given)
        require(reruns["config"].get("rerun_slots") == timeouts,
                "The reruns are not every primary timeout, each once, in schedule order.")
    else:
        require(not launched(notes, RERUN), f"{RERUN.name} was launched: name its configuration.")
    every = loaded + ([reruns] if reruns else [])
    inputs = {}
    for batch in every:
        require(batch["repo"] == repo and batch["config"]["questions"] == first["config"]["questions"],
                "The stages ran from different checkouts or questions.")
        inputs.update(batch["inputs"])
    # A later stage bound the earlier stages' files by hash when it was prepared; none may have
    # changed since.
    for batch in every[1:]:
        for name, wanted in batch["config"]["hashes"].items():
            seen = inputs.get(str((repo / name).resolve()))
            require(seen is None or seen == wanted, f"{batch['spec'].name}: a file it bound has changed since.")
    return {"repo": repo, "config": first["config"], "slots": slots, "stages": every, "primary": loaded,
            "held": held, "timeouts": timeouts,
            "reruns": {slot["id"]: {"spec": RERUN, "batch": reruns, "status": reruns["statuses"][slot["id"]],
                                    "record": reruns["records"].get(slot["id"]),
                                    "interrupted": reruns["interrupted"].get(slot["id"])}
                       for slot in reruns["slots"]} if reruns else {},
            "tasks": first["tasks"], "task_spec": first["task_spec"], "inputs": inputs,
            "stage_args": {batch["spec"].name: [batch["config_path"], batch["config_sha256"]] for batch in every}}


def saved_trials(study_batch):
    """Every saved record, primary then rerun, in schedule order, with the facts the private
    key holds about it."""
    for kind in ("held", "reruns"):
        for slot in study_batch["slots"]:
            entry = study_batch[kind].get(slot["id"])
            if not entry or entry["record"] is None:
                continue
            spec, record, batch = entry["spec"], entry["record"], entry["batch"]
            path = (batch["results"] / (slot["id"] + ".json")).resolve()
            yield slot, record, {
                "slot": slot["id"], "task": slot["question"]["id"], "condition": slot["condition"],
                "repeat": slot["repeat"], "stage": spec.stage, "attempt": spec.attempt, "rerun": not spec.primary,
                "outcome": record["outcome"], "disposition": record.get("disposition"),
                "record": str(path), "record_sha256": study_batch["inputs"][str(path)],
                "conversation": conversation(batch["results"] / slot["id"])}


def edit_once(text, old, new):
    require(text.count(old) == 1, "The reader template changed; its wording edits no longer apply.")
    return text.replace(old, new)


def review_html(study, rows):
    """The tested reader with this study's note before the frozen rules, and its saved
    progress kept apart from every other review's. `study` needs only `study_id`, `sheet` and
    `note`, so Study B's review uses it too."""
    before, rest = review.make_html(rows, study.sheet).split("const payload = ", 1)
    before = edit_once(before, "</style>", ".primary:hover{background:#23695c;color:#fff}\n</style>")
    before = edit_once(before, "<code>.key.json</code>", "<code>private-arm-key.json</code>")
    before = edit_once(before, "ask Codex to validate and import that CSV before scoring.",
                       "have that CSV validated and imported before scoring.")
    encoded, after = rest.split(";\nconst columns", 1)
    payload = json.loads(encoded)
    payload["rules"] = study.note + payload["rules"]
    payload["identity"] = study.study_id + "-" + payload["identity"]
    # A literal closing script tag in an answer must stay inert.
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return before + "const payload = " + encoded + ";\nconst columns" + after


def write_bundle(study, bundle, rows, private, public):
    """The blank sheet, the reader page, the private key and the public manifest, written once.
    Rows are shuffled here; `private` maps each code to what it hides."""
    bundle = Path(bundle)
    require(rows, "No trial the agent ran left a record; there is nothing to review.")
    secrets.SystemRandom().shuffle(rows)
    html = review_html(study, rows)
    # Creation is exclusive: a partial bundle is kept for inspection, never redrawn.
    bundle.mkdir(parents=True, exist_ok=False)
    sheet = bundle / study.sheet
    sheet.write_text(review.csv_text(rows), encoding="utf-8", newline="")
    (bundle / "review.html").write_text(html, encoding="utf-8")
    write_json(bundle / "private-arm-key.json", private)
    write_json(bundle / "manifest.json", {
        "study_id": study.study_id, "rows": len(rows), **public,
        "original_sheet_sha256": digest(sheet), "html_sha256": digest(bundle / "review.html"),
        "private_arm_key_sha256": digest(bundle / "private-arm-key.json"),
        "helper_sha256": digest(Path(review.__file__)), "renderer_sha256": digest(review.ROOT / "tools/hand_review.html"),
        "rules_sha256": digest(RULES), "created_singapore": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
        "human_review": "pending", "automatic_scoring": "not performed"})


def new_code(codes):
    code = secrets.token_hex(6)
    while code in codes:
        code = secrets.token_hex(6)
    return code


def prepare(study, stages, bundle):
    """One blind sheet for every answer of every stage: primary slots and reruns mixed under
    random codes. Returns the number of rows and how many answers name an arm label."""
    bundle = Path(bundle)
    require(not bundle.exists(), "The bundle already exists; its random codes are kept, never made again.")
    batch = load_study(study, stages)
    rows, codes, off_sheet = [], {}, []
    for slot, record, mapped in saved_trials(batch):
        if record["outcome"] == CLOSED:
            off_sheet.append({**mapped, "reason": "closed by the block: not on the sheet, counted 0"})
            continue
        code = new_code(codes)
        # Copied as recorded: a failed or timed-out trial keeps whatever text it has, and no
        # answer becomes an empty row for the student to judge, never a generated verdict.
        answer = record.get("answer") or ""
        rows.append({"code": code, "question": slot["question"]["query"],
                     "key": json.dumps(batch["tasks"][slot["question"]["id"]]["expect"], sort_keys=True),
                     "answer": answer, "hand_verdict": "", "note": ""})
        codes[code] = {**mapped, "answer_names_an_arm": bool(ARM_LABEL.search(answer))}
    stage_args = batch["stage_args"]
    write_bundle(study, bundle, rows, {
        "study_id": study.study_id, "stages": stage_args, "codes": codes, "off_sheet": off_sheet,
        "inputs": batch["inputs"]}, {
        "trials_scheduled": len(batch["slots"]) + len(batch["reruns"]),
        "stages_sha256": {name: sha for name, (_, sha) in stage_args.items()},
        "generator_sha256": digest(Path(__file__)), "task_keys_sha256": study.files[study.tasks_file]})
    return len(rows), sum(mapped["answer_names_an_arm"] for mapped in codes.values())


def read_sheets(original, incoming):
    """The blank sheet with the student's verdicts merged in, by the tested reader. Its
    messages name a row or a code, never answer text, so they are passed on."""
    try:
        blank = review.read_sheet(original)
        return blank, review.merge_verdicts(blank, review.read_sheet(incoming))
    except (ValueError, csv.Error) as error:
        raise Refused(f"The CSV was refused: {error}") from None


def validate(study, bundle, incoming, save=False):
    """Reads only the public manifest, the blank sheet and the student's CSV: no private key,
    record, schedule, ledger or scorer. With `save`, a complete review is written once, with
    the receipt the analysis checks before it opens the private key."""
    bundle, incoming = Path(bundle), Path(incoming)
    manifest = read_json(bundle / "manifest.json")
    total = manifest.get("rows")
    require(manifest.get("study_id") == study.study_id and type(total) is int
            and 0 < total <= manifest.get("trials_scheduled", 0), "Not this study's review bundle.")
    sheet = bundle / study.sheet
    require(digest(sheet) == manifest["original_sheet_sha256"], "The original blank sheet changed.")
    original, rows = read_sheets(sheet, incoming)
    require(len(original) == total and all(not r["hand_verdict"] and not r["note"] for r in original),
            "The original sheet must keep every row blank.")
    done = sum(bool(row["hand_verdict"]) for row in rows)
    if save:
        require(done == total, "The review is incomplete; no completed-review receipt written.")
        target = bundle / "validated"
        require(not target.exists(), "A validated review already exists; it is kept.")
        target.mkdir()
        output = target / "reviewed.csv"
        output.write_text(review.csv_text(rows), encoding="utf-8", newline="")
        write_json(target / "validation.json", {
            "study_id": study.study_id, "rows": total, "complete": True,
            "original_sheet_sha256": digest(sheet), "incoming_sha256": digest(incoming),
            "reviewed_sha256": digest(output),
            "validated_singapore": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
            "arm_key_read": False, "scored": False})
    return done, total


def stage_arguments(args):
    """The stages named on the command line, by name: (configuration, SHA-256) each."""
    named = {ATTEMPT1.name: args.attempt1, ATTEMPT2.name: args.attempt2, ATTEMPT3.name: args.attempt3,
             ATTEMPT4.name: args.attempt4, RERUN.name: args.rerun}
    return {name: (Path(value[0]), value[1]) for name, value in named.items() if value}


def main(study=STUDY_A):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    prep = modes.add_parser("prepare")
    for flag, needed in (("--attempt1", True), ("--attempt2", False), ("--attempt3", False), ("--attempt4", False),
                         ("--rerun", False)):
        prep.add_argument(flag, nargs=2, metavar=("CONFIG", "SHA256"), required=needed,
                          help="a stage's configuration and the SHA-256 its verifier's receipt and launch claim name")
    prep.add_argument("--bundle", type=Path, required=True)
    check = modes.add_parser("validate")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--reviewed", type=Path, required=True)
    check.add_argument("--save", action="store_true", help="write the completed review and its receipt")
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            count, named = prepare(study, stage_arguments(args), args.bundle)
            print(f"Prepared {count} blank review rows. No answer displayed or scored.")
            print(f"{named} of them hold an answer that names a slot's arm label (which ones: the private key).")
            print(f"Open {(args.bundle / 'review.html').resolve()}")
        else:
            done, total = validate(study, args.bundle, args.reviewed, args.save)
            print(f"{done}/{total} reviewed; the blank sheet is unchanged. No private key, record or scorer read.")
            if done != total:
                return 2
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
