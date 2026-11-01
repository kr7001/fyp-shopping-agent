#!/usr/bin/env python3
"""Offline blind review preparation and validation. No model calls or scoring.

Preparation mechanically copies final answers into a local student reader without
printing them. Validation reads only the original blind sheet, its checksum and
the student's download. It never opens the arm mapping or raw trial records.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import json
from pathlib import Path
import secrets
import sys
from zoneinfo import ZoneInfo

import hand_review as review

TASK_IDS = ("tee-target-price", "tee-cheapest-target", "tee-count-buyable",
            "tee-exists-under", "tee-top-3", "tee-xs-price", "tee-promo-check", "tee-headline")
STUDY = "browser-use-transfer-2026-10-31"
CONFIG_SHA256 = "404e45a0f7e029047a5a35394fbcbe79354bb53a9a13b2972a83478bc970e4ed"
TASKS_SHA256 = "f4f048b7ae95b58add97a07538d185721c09cacb62c1324574fc692b8acb7ba8"
RULES_SHA256 = "9433423f14f4de200da4b0376e84839c57751af93b98c9f8e599b35a6d274bb4"
SHEET = "browser-use-1-nov.sheet.csv"
RULE_NOTE = """Browser Use transfer review, 1 November 2026

There are 16 answers in random order. Judge only the final commitment using the
expected answer and frozen rules below. Do not grade the amount of browsing,
evidence sufficiency, presentation quality or cost. A correct commitment may
still have weak supporting evidence; that is a separate later trace audit.
No verdict has been supplied by AI. Arm labels, costs and automatic verdicts
are absent, although answer style may suggest the condition. Preserve the full
answer and your independent judgement. The historical references to other
studies or a second reader below do not add rows to this 16-answer review.

"""


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    # Do not echo malformed source lines, which could contain answer text.
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("Invalid JSON input; no source content displayed.") from None


def write_json(path, data):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def review_html(rows, sheet):
    html = review.make_html(rows, sheet)
    # Reuse the tested renderer and unchanged rubric, adding only study scope.
    payload_start = "const payload = "
    before, rest = html.split(payload_start, 1)
    encoded, after = rest.split(";\nconst columns", 1)
    payload = json.loads(encoded)
    payload["rules"] = RULE_NOTE + payload["rules"]
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return before + payload_start + encoded + ";\nconst columns" + after


def prepare(backup, tasks_file, bundle, expected_config_sha=CONFIG_SHA256,
            expected_tasks_sha=TASKS_SHA256):
    backup, tasks_file, bundle = map(Path, (backup, tasks_file, bundle))
    require(not bundle.exists(), "Bundle already exists; preserve its original random codes.")
    require(digest(tasks_file) == expected_tasks_sha, "Frozen task-key checksum mismatch.")
    require(digest(review.ROOT / "docs/content/claim2-reading-rules.md") == RULES_SHA256,
            "Frozen reading rules changed.")
    config_path = backup / "monitored-command-1-nov.json"
    require(digest(config_path) == expected_config_sha, "Configuration checksum mismatch.")
    config = read_json(config_path)
    status_path = backup / "monitored-1-nov.status.json"
    status = read_json(status_path)
    require(status.get("status") == "complete" and status.get("config_sha256") == expected_config_sha,
            "Completion status does not bind this configuration.")
    require(config.get("stage") == "monitored-transfer", "Wrong execution condition.")
    results = backup / "monitored-1-nov.results"
    schedule_path, statuses_path = results / "schedule.json", results / "slot-status.json"
    schedule, statuses = read_json(schedule_path), read_json(statuses_path)["slots"]
    require(schedule.get("study_id") == STUDY and schedule.get("stage") == "monitored-transfer",
            "Wrong schedule identity.")
    questions = config["transfer_questions"]
    require(tuple(q["id"] for q in questions) == TASK_IDS, "Unexpected formal question set.")
    task_data = read_json(tasks_file)
    tasks = {t["id"]: t for t in task_data["tasks"]}
    for question in questions:
        task = tasks[question["id"]]
        require(task["query"].format(base=task_data["base_url"]) == question["query"],
                "Frozen task wording differs from the executed question.")
        require(isinstance(task.get("expect"), dict) and task["expect"].get("kind") != "none",
                "Missing expected-answer key.")
    expected = []
    for index, question in enumerate(questions):
        arms = ("baseline", "block") if index % 2 == 0 else ("block", "baseline")
        for arm in arms:
            expected.append({"id": f"transfer-{question['id']}-r1-{arm}", "question": question,
                             "condition": arm, "repeat": 1, "phase": "transfer", "clock_s": 2700})
    formal = [s for s in schedule["slots"] if s.get("phase") == "transfer"]
    require(formal == expected, "Formal schedule must retain the exact 16 planned slots and order.")
    require({k for k, v in statuses.items() if v.get("phase") == "transfer"} == {s["id"] for s in formal},
            "Missing or extra formal slot status.")
    inputs = {str(p.resolve()): digest(p) for p in
              (config_path, status_path, schedule_path, statuses_path, tasks_file,
               review.ROOT / "docs/content/claim2-reading-rules.md")}
    rows, mapping = [], {}
    for slot in formal:
        path = results / (slot["id"] + ".json")
        record = read_json(path)
        require(all(record.get(k) == v for k, v in {
            "study_id": STUDY, "stage": "monitored-transfer", "phase": "transfer",
            "slot": slot["id"], "condition": slot["condition"], "repeat": 1,
            "task": slot["question"]["id"], "question": slot["question"]["query"],
        }.items()), "Trial metadata differs from its scheduled identity.")
        # This bundle is for the completed all-answered batch. Refuse, never
        # silently filter, a future batch containing terminal failures.
        require(record.get("outcome") == statuses[slot["id"]].get("status") == "answered",
                "Non-answer trial found: retain it and prepare an explicit failure-aware workflow.")
        require(isinstance(record.get("answer"), str) and record["answer"].strip(),
                "Missing final answer; no slot was omitted or scored.")
        code = secrets.token_hex(6)
        while code in mapping:
            code = secrets.token_hex(6)
        rows.append({"code": code, "question": slot["question"]["query"],
                     "key": json.dumps(tasks[record["task"]]["expect"], sort_keys=True),
                     "answer": record["answer"], "hand_verdict": "", "note": ""})
        inputs[str(path.resolve())] = digest(path)
        mapping[code] = {"slot": slot["id"], "task": record["task"],
                         "condition": slot["condition"], "repeat": 1,
                         "record": str(path.resolve()), "record_sha256": digest(path)}
    secrets.SystemRandom().shuffle(rows)
    html = review_html(rows, SHEET)
    # Creation is exclusive. A partial write is preserved for inspection, never
    # regenerated with different codes by a second invocation.
    bundle.mkdir(parents=True, exist_ok=False)
    sheet = bundle / SHEET
    sheet.write_text(review.csv_text(rows), encoding="utf-8", newline="")
    (bundle / "review.html").write_text(html, encoding="utf-8")
    write_json(bundle / "private-arm-key.json", {"study_id": STUDY, "codes": mapping, "inputs": inputs})
    write_json(bundle / "manifest.json", {
        "study_id": STUDY, "rows": len(rows), "original_sheet_sha256": digest(sheet),
        "html_sha256": digest(bundle / "review.html"), "config_sha256": expected_config_sha,
        "private_arm_key_sha256": digest(bundle / "private-arm-key.json"),
        "generator_sha256": digest(Path(__file__)),
        "renderer_sha256": digest(review.ROOT / "tools/hand_review.html"),
        "created_singapore": datetime.now(ZoneInfo("Asia/Singapore")).isoformat(),
        "rules_sha256": digest(review.ROOT / "docs/content/claim2-reading-rules.md"),
        "task_keys_sha256": digest(tasks_file),
        "human_review": "pending", "automatic_scoring": "not performed",
    })
    return len(rows)


def validate(bundle, incoming, save_to=None):
    """No key, schedule, raw trial, trace or scorer is accessed here."""
    bundle, incoming = Path(bundle), Path(incoming)
    manifest = read_json(bundle / "manifest.json")
    sheet = bundle / SHEET
    require(manifest.get("study_id") == STUDY and manifest.get("rows") == 16,
            "Wrong review bundle.")
    require(digest(sheet) == manifest["original_sheet_sha256"], "Original blank sheet changed.")
    original = review.read_sheet(sheet)
    require(len(original) == 16 and all(not r["hand_verdict"] and not r["note"] for r in original),
            "Original sheet must preserve all 16 blank rows.")
    rows = review.merge_verdicts(original, review.read_sheet(incoming))
    done = sum(bool(row["hand_verdict"]) for row in rows)
    if save_to is not None:
        require(done == 16, "Review incomplete; no completed-review receipt written.")
        target = Path(save_to)
        require(not target.exists(), "Validated destination already exists; preserve previous review.")
        target.mkdir(parents=True, exist_ok=False)
        output = target / "reviewed.csv"
        output.write_text(review.csv_text(rows), encoding="utf-8", newline="")
        write_json(target / "validation.json", {
            "study_id": STUDY, "rows": 16, "complete": True,
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
    prep.add_argument("--backup", type=Path, required=True)
    prep.add_argument("--tasks", type=Path, required=True)
    prep.add_argument("--bundle", type=Path, required=True)
    check = modes.add_parser("validate")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--reviewed", type=Path, required=True)
    check.add_argument("--save-to", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            count = prepare(args.backup, args.tasks, args.bundle)
            print(f"Prepared {count} blank review rows. No answers displayed or scored.")
            print(f"Open {(args.bundle / 'review.html').resolve()}")
        else:
            done, total = validate(args.bundle, args.reviewed, args.save_to)
            print(f"{done}/{total} reviewed; immutable evidence validated. No arm key or scorer read.")
            if done != total:
                return 2
    except (ValueError, OSError, KeyError, TypeError, csv.Error):
        # A malformed file may contain arbitrary answer text in exception data.
        print("Review operation refused. Check inputs with synthetic tests; no answer content displayed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
