#!/usr/bin/env python3
"""Blind review of Study A, Browser Use on the fresh market, prepared and validated offline.

Study A (notes/fresh-market-2-nov/analysis-plan-A.md) runs 32 Browser Use trials on Rookmere,
seed 1002: 8 questions, 2 arms, repeats 1 and 2. `prepare` checks the batch against the
configuration it ran under, then copies the answer text of every trial the agent ran into a
blank sheet under random codes, failed and timed-out trials included. The student sees the
question, the key and the full answer only: no arm, repeat, outcome, cost or automatic score.
Which code is which slot goes to a separate private file. Slots the block closed are not on
the sheet: the frozen reading rules keep them off it ("Not on the sheet") and the plan counts
them 0. `validate` reads only the public manifest, the blank sheet and the student's CSV, and
with --save writes the completed-review receipt that browser_use_fresh_analysis.py needs
before it opens the private file. Nothing here scores an answer or calls a model, a provider
or an account.

Written 2 November 2026 on the pattern of browser_use_repeat_review.py, which is bound to
Quenby's commands, task-file hashes and the 32-slot repeats 2-3 schedule. Here everything a
review is bound to is one `Study` value, so the tests run the same code on a synthetic batch.

    python3 tools/browser_use_fresh_review.py prepare \\
        --config notes/fresh-market-2-nov/study-a-command.json --config-sha256 <its SHA-256> \\
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
import browser_use_transfer as transfer  # noqa: E402  (the runner's own schedule and warning)
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
# configuration, so a trial run under another setting cannot join the review.
SETTINGS = ("model", "provider", "temperature", "frequency_penalty", "top_p", "max_input_bytes",
            "max_output_tokens", "max_steps", "max_failures", "clock_s", "llm_timeout",
            "browser_executable")
RULES = ROOT / "docs/content/claim2-reading-rules.md"
# The adapter's save_as_pdf result shows the agent its output path, which holds the slot id and
# so the arm (the verifier's receipt for Study A, 2 November 2026). An answer that repeats it
# names its arm to the student: it is copied as it is, flagged and listed, never edited. None of
# the 48 stored answers of the earlier Browser Use studies matches.
ARM_LABEL = re.compile(r"-r\d+-(?:block|baseline)\b", re.I)

NOTE = """Browser Use fresh-market review (Rookmere), 2 November 2026

One row for each Browser Use trial of this study that the agent ran, in random order, with the
answer text that trial recorded; a row is empty when the trial recorded none. Judge only the
final commitment, against the expected answer and the frozen rules below. Do not grade the
amount of browsing, evidence sufficiency, presentation quality or cost. No verdict has been
supplied by AI. This page adds no arm label, repeat label, execution outcome, cost or automatic
verdict. An answer itself may still suggest its condition, and one that quotes a file path of
the agent's may even name it: judge that row by the same rules. Rows from earlier studies are
not part of this review, and the references below to other studies or a second reader add no
rows to it.

"""


@dataclasses.dataclass(frozen=True)
class Study:
    """Everything one blind review is bound to. STUDY_A is the fresh market's; the tests build
    their own on a synthetic batch."""
    study_id: str        # the schedule's, every record's, the ledger's and the launch claim's
    stage: str           # the launcher stage that ran it
    task_ids: tuple      # the question types, in the schedule's order
    repeats: tuple
    clock_s: int
    market: dict         # as the configuration and every record name it
    tasks_file: str      # the generated questions and keys, a repository path
    readings_file: str   # their readings sidecar
    files: dict          # repository path -> SHA-256 of every frozen file the plan names
    rules_sha256: str    # the frozen reading rules the student grades under
    launch_marker: str   # the launcher's one claim of the attempt, beside its ledger
    sheet: str           # the blank sheet's file name, and the reader's download name
    note: str = NOTE     # what the reader says about this review before the rules


# Each SHA-256 below is the committed file's at b1c67c8, the configuration's own hash for it,
# and is checked against the repository by tests/test_browser_use_fresh_review.py.
STUDY_A = Study(
    study_id=guard.FRESH_BUDGET, stage=guard.FRESH_STAGE, task_ids=transfer.TASK_IDS,
    repeats=(1, 2), clock_s=2700,
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
    launch_marker="study-a.launch.json", sheet="study-a-fresh-2-nov.sheet.csv")


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


def check_record(study, config, config_sha256, slot, status, record):
    """One saved record against its slot, its configuration and the arm's design."""
    question = slot["question"]
    identity = {"study_id": study.study_id, "batch_id": study.study_id, "stage": study.stage,
                "phase": "transfer", "slot": slot["id"], "task": question["id"],
                "question": question["query"], "condition": slot["condition"],
                "repeat": slot["repeat"], "outcome": status, "market": config["market"],
                "config_sha256": config_sha256, "head": config["expected_head"],
                "briefing_sha256": text_digest(transfer.COMMON_BRIEFING)}
    require(all(record.get(k) == v for k, v in identity.items()),
            "A record differs from its scheduled slot, configuration or commit.")
    require(record.get("answer") is None or isinstance(record["answer"], str), "Unsupported answer value.")
    require(isinstance(record.get("calls"), list), "A record has no call list.")
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
    require(all(settings.get(k) == config[k] for k in SETTINGS)
            and settings.get("start_url") == question["start_url"],
            "A trial ran under settings other than its configuration's.")
    # Absent only when the trial failed before its browser opened, which its error records.
    version = record.get("browser_version")
    require(version == config["preflight_browser_version"] or (version is None and record.get("error_type")),
            "A trial ran on another browser build.")


def load_batch(study, config_path, config_sha256):
    """Every file the batch left, checked against the configuration it ran under, with the
    SHA-256 of each file read. Refuses on any slot added, moved, missing or replayed."""
    config_path = Path(config_path).resolve()
    require(digest(config_path) == config_sha256, "The configuration file is not the one named by its SHA-256.")
    config = read_json(config_path)
    repo = Path(config["repo"]).resolve()
    require(config.get("stage") == study.stage and config.get("study_budget_id") == study.study_id
            and config.get("attempt") == 1 and config.get("repeats") == list(study.repeats)
            and config.get("clock_s") == study.clock_s and config.get("market") == study.market
            and config.get("tasks_file") == study.tasks_file
            and study.readings_file in config.get("market_files", []),
            "The configuration is not this study's.")
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
    status = read_json(config["status_path"])
    ledger_path = Path(config["ledger_path"])
    marker = read_json(ledger_path.with_name(study.launch_marker))
    ledger = read_json(ledger_path)
    receipt = read_json(config["verification_receipt"])
    approval = read_json(config["approval_record"])
    require(status.get("status") in ("complete", "stopped") and status.get("config_sha256") == config_sha256,
            "The batch has not ended under this configuration.")
    require(marker.get("study_budget_id") == study.study_id and marker.get("attempt") == 1
            and marker.get("config_sha256") == config_sha256
            and ledger.get("study_budget_id") == study.study_id and ledger.get("attempt") == 1,
            "The launch claim or the ledger is not this attempt's.")
    require(receipt.get("verdict") == "PASS" and receipt.get("config_sha256") == config_sha256
            and receipt.get("head") == config["expected_head"]
            and approval.get("approved") is True and approval.get("config_sha256") == config_sha256,
            "The batch's configuration lacks the verifier's pass or the student's approval.")
    results = Path(config["output_dir"])
    schedule = read_json(results / "schedule.json")
    slots = expected_slots(config["questions"], study.repeats, study.clock_s)
    require(schedule.get("study_id") == study.study_id and schedule.get("batch_id") == study.study_id
            and schedule.get("stage") == study.stage and schedule.get("paid_calls") == 0
            and schedule.get("slots") == slots
            and schedule.get("warning_sha256") == text_digest(transfer.COMMON_BRIEFING),
            "The schedule is not the planned 32 slots in their planned order.")
    ids = [slot["id"] for slot in slots]
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
    inputs = {str(path.resolve()): digest(path) for path in (
        config_path, Path(config["status_path"]), ledger_path, ledger_path.with_name(study.launch_marker),
        Path(config["verification_receipt"]), Path(config["approval_record"]), Path(config["questions_file"]),
        results / "schedule.json", results / "slot-status.json", RULES,
        *(repo / name for name in study.files), *([done_path] if done_path.exists() else []))}
    records, interrupted = {}, {}
    for slot in slots[:ran]:
        path = results / (slot["id"] + ".json")
        record = read_json(path)
        check_record(study, config, config_sha256, slot, statuses[slot["id"]]["status"], record)
        records[slot["id"]] = record
        inputs[str(path.resolve())] = digest(path)
    for slot_id in stopped:
        path = results / (slot_id + ".interrupted.json")
        if path.exists():
            interrupted[slot_id] = read_json(path)
            inputs[str(path.resolve())] = digest(path)
    return {"config": config, "config_path": str(config_path), "config_sha256": config_sha256, "repo": repo,
            "status": status, "ledger": ledger, "slots": slots, "statuses": statuses, "records": records,
            "interrupted": interrupted, "tasks": tasks, "task_spec": task_spec, "inputs": inputs}


def edit_once(text, old, new):
    require(text.count(old) == 1, "The reader template changed; its wording edits no longer apply.")
    return text.replace(old, new)


def review_html(study, rows):
    """The tested reader with this study's note before the frozen rules, and its saved
    progress kept apart from every other review's."""
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


def prepare(study, config_path, config_sha256, bundle):
    bundle = Path(bundle)
    require(not bundle.exists(), "The bundle already exists; its random codes are kept, never made again.")
    batch = load_batch(study, config_path, config_sha256)
    rows, codes, off_sheet = [], {}, {}
    for slot in batch["slots"]:
        record = batch["records"].get(slot["id"])
        if record is None:
            continue
        path = Path(batch["config"]["output_dir"]) / (slot["id"] + ".json")
        mapped = {"slot": slot["id"], "task": slot["question"]["id"], "condition": slot["condition"],
                  "repeat": slot["repeat"], "outcome": record["outcome"],
                  "record": str(path.resolve()), "record_sha256": batch["inputs"][str(path.resolve())]}
        if record["outcome"] == CLOSED:
            off_sheet[slot["id"]] = {**mapped, "reason": "closed by the block: not on the sheet, counted 0"}
            continue
        code = secrets.token_hex(6)
        while code in codes:
            code = secrets.token_hex(6)
        # Copied as recorded: a failed or timed-out trial keeps whatever text it has, and no
        # answer becomes an empty row for the student to judge, never a generated verdict.
        answer = record.get("answer") or ""
        rows.append({"code": code, "question": slot["question"]["query"],
                     "key": json.dumps(batch["tasks"][slot["question"]["id"]]["expect"], sort_keys=True),
                     "answer": answer, "hand_verdict": "", "note": ""})
        codes[code] = {**mapped, "answer_names_an_arm": bool(ARM_LABEL.search(answer))}
    require(rows, "No trial the agent ran left a record; there is nothing to review.")
    secrets.SystemRandom().shuffle(rows)
    html = review_html(study, rows)
    # Creation is exclusive: a partial bundle is kept for inspection, never redrawn.
    bundle.mkdir(parents=True, exist_ok=False)
    sheet = bundle / study.sheet
    sheet.write_text(review.csv_text(rows), encoding="utf-8", newline="")
    (bundle / "review.html").write_text(html, encoding="utf-8")
    write_json(bundle / "private-arm-key.json", {
        "study_id": study.study_id, "config": batch["config_path"], "config_sha256": config_sha256,
        "codes": codes, "off_sheet": off_sheet, "inputs": batch["inputs"]})
    write_json(bundle / "manifest.json", {
        "study_id": study.study_id, "rows": len(rows), "slots_scheduled": len(batch["slots"]),
        "original_sheet_sha256": digest(sheet), "html_sha256": digest(bundle / "review.html"),
        "config_sha256": config_sha256, "private_arm_key_sha256": digest(bundle / "private-arm-key.json"),
        "generator_sha256": digest(Path(__file__)), "helper_sha256": digest(Path(review.__file__)),
        "renderer_sha256": digest(review.ROOT / "tools/hand_review.html"),
        "rules_sha256": digest(RULES), "task_keys_sha256": study.files[study.tasks_file],
        "created_singapore": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
        "human_review": "pending", "automatic_scoring": "not performed"})
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
            and 0 < total <= manifest.get("slots_scheduled", 0), "Not this study's review bundle.")
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


def main(study=STUDY_A):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    prep = modes.add_parser("prepare")
    prep.add_argument("--config", type=Path, required=True)
    prep.add_argument("--config-sha256", required=True,
                      help="the SHA-256 the verifier's receipt and the launch claim name")
    prep.add_argument("--bundle", type=Path, required=True)
    check = modes.add_parser("validate")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--reviewed", type=Path, required=True)
    check.add_argument("--save", action="store_true", help="write the completed review and its receipt")
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            count, named = prepare(study, args.config, args.config_sha256, args.bundle)
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
