#!/usr/bin/env python3
"""Prepare and validate the separate 32-slot Browser Use repeat review, offline.

Preparation copies final commitments mechanically and retains the failed slot.
Validation needs only the blank sheet, public manifest and student's edited CSV.
No automatic score or inferred human verdict is produced.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import json
from pathlib import Path
import secrets
import sys
from zoneinfo import ZoneInfo

import browser_use_review as original

review = original.review
require, digest = original.require, original.digest
read_json, write_json = original.read_json, original.write_json
TASK_IDS, TASKS_SHA256, RULES_SHA256 = original.TASK_IDS, original.TASKS_SHA256, original.RULES_SHA256
STUDY = original.STUDY
BATCH = "browser-use-plain-repeat-2026-11-01"
CONFIG_SHAS = ("2a1b0ec9f9a58e047fed80680b03252a30a2c8d2f9594381f9c32257e762d700",
               "d92255c29e88f96631126c647bf67fdefb94276c7db255ed17a2331418d92d8d")
CHECKSUMS_SHA256 = "9db30f10ef3980b65b4e543f9be95b70d9b8f0d95b8ae91a3bea1e3a77342d18"
SHEET = "browser-use-repeats-1-nov.sheet.csv"
RULE_NOTE = """Browser Use repeat review, 1 November 2026

This is a separate review of 32 new trial slots in random order. The original
16-trial review is preserved separately. Judge only the final commitment using
the expected answer and frozen rules below. Do not grade browsing effort,
evidence sufficiency, presentation quality or cost. Empty replies remain in
the review for your judgement. No verdict has been supplied by AI.
Arm labels, repeat labels, execution outcomes, costs and automatic verdicts are
absent, although the answer itself may suggest its condition. Preserve the full
answer and your independent judgement. Historical references to other studies
or a second reader below do not add rows to this 32-slot review.

"""


def expected_schedule(questions):
    rows = []
    for repeat in (2, 3):
        for i, question in enumerate(questions):
            arms = ("baseline", "block") if (i + repeat) % 2 else ("block", "baseline")
            for arm in arms:
                rows.append({"id": f"transfer-{question['id']}-r{repeat}-{arm}",
                             "question": question, "condition": arm, "repeat": repeat,
                             "phase": "transfer", "clock_s": 2700})
    return rows


def review_html(rows):
    html = review.make_html(rows, SHEET)
    before, rest = html.split("const payload = ", 1)
    # Scope presentation corrections to this reader, outside the answer payload.
    before = before.replace("</style>", ".primary:hover{background:#23695c;color:#fff}\n</style>")
    before = before.replace("<code>.key.json</code>", "<code>private-arm-key.json</code>")
    before = before.replace("ask Codex to validate and import that CSV before scoring.",
                            "have that CSV validated and imported before scoring.")
    encoded, after = rest.split(";\nconst columns", 1)
    payload = json.loads(encoded)
    payload["rules"] = RULE_NOTE + payload["rules"]
    payload["identity"] = BATCH + "-" + payload["identity"]
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return before + "const payload = " + encoded + ";\nconst columns" + after


def prepare(attempt1, attempt2, tasks_file, bundle, expected_config_shas=CONFIG_SHAS,
            expected_tasks_sha=TASKS_SHA256, expected_checksums_sha=CHECKSUMS_SHA256):
    attempt1, attempt2, tasks_file, bundle = map(Path, (attempt1, attempt2, tasks_file, bundle))
    require(not bundle.exists(), "Bundle already exists; preserve its original random codes.")
    rules = review.ROOT / "docs/content/claim2-reading-rules.md"
    require(digest(tasks_file) == expected_tasks_sha, "Frozen task-key checksum mismatch.")
    require(digest(rules) == RULES_SHA256, "Frozen reading rules changed.")
    checksums_path = attempt2.parent / "attempt2-backup-sha256.json"
    require(digest(checksums_path) == expected_checksums_sha, "Completion checksum manifest changed.")
    checksums = read_json(checksums_path)
    inputs = {str(p.resolve()): digest(p) for p in (tasks_file, rules, checksums_path)}

    def bound_digest(path, number):
        backup = (attempt1, attempt2)[number-1]
        name = ("prior/" if number == 1 else "") + str(path.relative_to(backup))
        value = digest(path)
        require(checksums.get(name) == value, "Source differs from the completion backup checksum.")
        return value

    configs, schedules, status_sets, result_dirs = [], [], [], []
    for number, (backup, expected_sha, stage, terminal) in enumerate(zip(
            (attempt1, attempt2), expected_config_shas,
            ("plain-repeat-transfer", "plain-repeat-recovery"), ("stopped", "complete")), 1):
        config_path, status_path = backup / f"attempt{number}-command.json", backup / f"attempt{number}.status.json"
        require(digest(config_path) == expected_sha, "Configuration checksum mismatch.")
        config, status = read_json(config_path), read_json(status_path)
        require(config.get("stage") == stage and config.get("attempt") == number
                and config.get("study_budget_id") == BATCH and config.get("repeats") == [2, 3],
                "Wrong repeat execution condition.")
        require(status.get("status") == terminal and status.get("config_sha256") == expected_sha,
                "Terminal status does not bind its configuration.")
        results = backup / f"attempt{number}.results"
        schedule_path, statuses_path = results / "schedule.json", results / "slot-status.json"
        schedule, statuses = read_json(schedule_path), read_json(statuses_path)["slots"]
        require(schedule.get("study_id") == STUDY and schedule.get("batch_id") == BATCH
                and schedule.get("stage") == stage, "Wrong repeat schedule identity.")
        configs.append(config)
        schedules.append(schedule)
        status_sets.append(statuses)
        result_dirs.append(results)
        for path in (config_path, status_path, schedule_path, statuses_path, results / "completed.json"):
            inputs[str(path.resolve())] = bound_digest(path, number)
    questions = configs[0]["questions"]
    require(tuple(q["id"] for q in questions) == TASK_IDS and configs[1]["questions"] == questions,
            "Repeat question set changed.")
    task_data = read_json(tasks_file)
    tasks = {task["id"]: task for task in task_data["tasks"]}
    for question in questions:
        task = tasks[question["id"]]
        require(task["query"].format(base=task_data["base_url"]) == question["query"],
                "Frozen task wording differs from the executed question.")
        require(isinstance(task.get("expect"), dict) and task["expect"].get("kind") != "none",
                "Missing expected-answer key.")
    full = expected_schedule(questions)
    require(schedules[0]["slots"] == full and schedules[1]["slots"] == full[6:]
            and schedules[1].get("prior_completed_count") == 6
            and schedules[1].get("original_slot_count") == 32,
            "Repeat schedules must preserve exact disjoint coverage of all 32 slots.")
    ids = [slot["id"] for slot in full]
    require(set(status_sets[0]) == set(ids) and set(status_sets[1]) == set(ids[6:]),
            "Missing or extra repeat slot status.")
    dispositions = [status_sets[0][key].get("status") for key in ids[:6]]
    require(dispositions.count("answered") == 5 and dispositions.count("failed") == 1
            and all(status_sets[0][key].get("status") == "not_started" for key in ids[6:])
            and all(status_sets[1][key].get("status") == "answered" for key in ids[6:])
            and all(row.get("phase") == "transfer" for statuses in status_sets for row in statuses.values()),
            "Unexpected repeat dispositions; no slot was filtered or scored.")
    for results, expected_ids, total in ((result_dirs[0], ids[:6], 32), (result_dirs[1], ids[6:], 26)):
        require({p.stem for p in results.glob("transfer-*.json")} == set(expected_ids),
                "Unexpected, missing or replayed trial record.")
        completed = read_json(results / "completed.json")
        require(completed.get("completed") == expected_ids and completed.get("expected") == total,
                "Completed manifest differs from planned coverage.")
    # The continuation command binds every retained first-attempt record and
    # its operational metadata. Compare those historical hashes before copying.
    recovery = configs[1]
    prior_results = Path(recovery["prior_slot_status_file"]).parent
    prior_bindings = {
        recovery["prior_config_file"]: attempt1 / "attempt1-command.json",
        recovery["prior_status_file"]: attempt1 / "attempt1.status.json",
        recovery["prior_schedule_file"]: result_dirs[0] / "schedule.json",
        recovery["prior_slot_status_file"]: result_dirs[0] / "slot-status.json",
        str(prior_results / "completed.json"): result_dirs[0] / "completed.json",
    }
    prior_bindings.update({str(prior_results / (key + ".json")): result_dirs[0] / (key + ".json")
                           for key in ids[:6]})
    for name, path in prior_bindings.items():
        require(recovery["hashes"].get(name) == digest(path), "Retained first-attempt evidence checksum mismatch.")
    rows, mapping = [], {}
    for i, slot in enumerate(full):
        attempt = 0 if i < 6 else 1
        path = result_dirs[attempt] / (slot["id"] + ".json")
        record_sha = bound_digest(path, attempt + 1)
        record = read_json(path)
        outcome = status_sets[attempt][slot["id"]]["status"]
        require(all(record.get(k) == v for k, v in {
            "study_id": STUDY, "batch_id": BATCH, "stage": configs[attempt]["stage"], "phase": "transfer",
            "slot": slot["id"], "task": slot["question"]["id"], "question": slot["question"]["query"],
            "condition": slot["condition"], "repeat": slot["repeat"], "outcome": outcome,
        }.items()), "Trial metadata differs from its scheduled identity.")
        answer = record.get("answer")
        require(isinstance(answer, str) or answer is None, "Unsupported final-answer value.")
        require(outcome != "answered" or (isinstance(answer, str) and answer.strip()),
                "Answered trial lacks a final commitment.")
        # None means no final answer. Keep the slot with a blank answer and let
        # the student judge it; never insert an AI-generated failure verdict.
        answer = "" if answer is None else answer
        code = secrets.token_hex(6)
        while code in mapping:
            code = secrets.token_hex(6)
        rows.append({"code": code, "question": slot["question"]["query"],
                     "key": json.dumps(tasks[record["task"]]["expect"], sort_keys=True),
                     "answer": answer, "hand_verdict": "", "note": ""})
        inputs[str(path.resolve())] = record_sha
        mapping[code] = {"slot": slot["id"], "task": record["task"], "condition": slot["condition"],
                         "repeat": slot["repeat"], "outcome": outcome, "attempt": attempt + 1,
                         "record": str(path.resolve()), "record_sha256": record_sha}
    secrets.SystemRandom().shuffle(rows)
    html = review_html(rows)
    bundle.mkdir(parents=True, exist_ok=False)
    sheet = bundle / SHEET
    sheet.write_text(review.csv_text(rows), encoding="utf-8", newline="")
    (bundle / "review.html").write_text(html, encoding="utf-8")
    write_json(bundle / "private-arm-key.json", {"study_id": STUDY, "batch_id": BATCH,
                                               "codes": mapping, "inputs": inputs})
    write_json(bundle / "manifest.json", {
        "study_id": STUDY, "batch_id": BATCH, "rows": 32, "original_sheet_sha256": digest(sheet),
        "html_sha256": digest(bundle / "review.html"), "config_sha256": list(expected_config_shas),
        "private_arm_key_sha256": digest(bundle / "private-arm-key.json"),
        "generator_sha256": digest(Path(__file__)), "helper_sha256": digest(Path(original.__file__)),
        "renderer_sha256": digest(review.ROOT / "tools/hand_review.html"),
        "created_singapore": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
        "rules_sha256": digest(rules), "task_keys_sha256": digest(tasks_file),
        "completion_checksum_manifest_sha256": expected_checksums_sha,
        "human_review": "pending", "automatic_scoring": "not performed",
    })
    return len(rows)


def validate(bundle, incoming, save_to=None):
    """Read only public manifest, blank CSV and incoming student CSV."""
    bundle, incoming = Path(bundle), Path(incoming)
    manifest = read_json(bundle / "manifest.json")
    sheet = bundle / SHEET
    require(manifest.get("study_id") == STUDY and manifest.get("batch_id") == BATCH
            and manifest.get("rows") == 32, "Wrong repeat review bundle.")
    require(digest(sheet) == manifest["original_sheet_sha256"], "Original blank sheet changed.")
    original_rows = review.read_sheet(sheet)
    require(len(original_rows) == 32 and all(not r["hand_verdict"] and not r["note"] for r in original_rows),
            "Original sheet must preserve all 32 blank rows.")
    rows = review.merge_verdicts(original_rows, review.read_sheet(incoming))
    done = sum(bool(row["hand_verdict"]) for row in rows)
    if save_to is not None:
        require(done == 32, "Review incomplete; no completed-review receipt written.")
        target = Path(save_to)
        require(not target.exists(), "Validated destination already exists; preserve previous review.")
        target.mkdir(parents=True, exist_ok=False)
        output = target / "reviewed.csv"
        output.write_text(review.csv_text(rows), encoding="utf-8", newline="")
        write_json(target / "validation.json", {
            "study_id": STUDY, "batch_id": BATCH, "rows": 32, "complete": True,
            "original_sheet_sha256": digest(sheet), "incoming_sha256": digest(incoming),
            "reviewed_sha256": digest(output),
            "validated_singapore": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
            "arm_key_read": False, "scored": False,
        })
    return done, len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    prep = modes.add_parser("prepare")
    prep.add_argument("--attempt1", type=Path, required=True)
    prep.add_argument("--attempt2", type=Path, required=True)
    prep.add_argument("--tasks", type=Path, required=True)
    prep.add_argument("--bundle", type=Path, required=True)
    check = modes.add_parser("validate")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--reviewed", type=Path, required=True)
    check.add_argument("--save-to", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            count = prepare(args.attempt1, args.attempt2, args.tasks, args.bundle)
            print(f"Prepared {count} blank repeat review rows. No answers displayed or scored.")
            print(f"Open {(args.bundle / 'review.html').resolve()}")
        else:
            done, total = validate(args.bundle, args.reviewed, args.save_to)
            print(f"{done}/{total} reviewed; immutable evidence validated. No arm key or scorer read.")
            if done != total:
                return 2
    except (ValueError, OSError, KeyError, TypeError, csv.Error):
        print("Review operation refused. No answer content displayed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
