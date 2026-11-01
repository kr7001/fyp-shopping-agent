#!/usr/bin/env python3
"""Write the launch inputs of the two fresh-market studies of 2 November 2026. Free.

notes/fresh-market-2-nov/protocol.md fixed both studies before the market was drawn. This
writes, from the repository and nothing typed, what the two guarded launchers read:

    protocol    experiments/tasks/matched_briefing_2_nov.json, Study B's analysis file: the
                29 October file's schedule, conditions and routing, with the fresh market's
                inputs, identity and budget (committed)
    inputs      Study A's runtime questions, from the generated task file; Study B's recorded
                parser replies for its dry runs; the cohort's reference command, its model
                metadata and the Browser Use environment's package list (local, in notes/)
    preflight   Study A's free preflight receipt, from the test and live-check logs
    configs     both launch configurations at the checked-out commit, their exact commands,
                and Study A's approval record, prepared but not approved (local, in notes/)

No model, account or provider is contacted; `configs` reads the Chrome build and nothing
else outside the repository.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import guarded_browser_use as guard_a  # noqa: E402
import guarded_matched_briefing as guard_b  # noqa: E402

NOTES = ROOT / "notes/fresh-market-2-nov"
FIXTURE = "env/fixtures/tee_fresh_2_nov.json"
SEARCH = "env/manifests/tee_fresh_2_nov-search.json"
TASKS = "experiments/tasks/tasks_tee_fresh_2_nov.json"
READINGS = "experiments/tasks/readings_tee_fresh_2_nov.json"
B_PROTOCOL = "experiments/tasks/matched_briefing_2_nov.json"
B_OLD = "experiments/tasks/matched_briefing_29_oct.json"
B_STUDY = "matched-briefing-fresh-2026-11-02"
APPROVAL = "notes/fresh-market-2-nov/student-approval-2-nov.md"
DEADLINE = "2026-11-03T12:00:00+08:00"  # the protocol's absolute stop
# The repeats 2-3 cohort's continuation command and its sibling inputs, kept beside its notes.
COHORT = ROOT / "notes/browser-use-repeat-1-nov/attempt2-complete-1-nov"
# The 29 October study's launch, whose steps, interpreter and environment B repeats.
B_OLD_CONFIG = ROOT / "notes/replication-prep/matched-briefing-command-29-oct.json"
B_OLD_MANIFEST = ROOT / "experiments/results/matched-briefing-29-oct.manifest"
B_ESTIMATE, B_CAP, B_RESERVE = 1.2, 2.0, 0.5


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value, *, fresh=True):
    path = Path(path)
    if fresh and path.exists():
        raise SystemExit(f"{path} exists; move it away first")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    return path


def market():
    """The accepted market, from its seed search and task file."""
    search = json.loads((ROOT / SEARCH).read_text())
    accepted = search["tried"][-1]
    if accepted.get("outcome") != "accepted":
        raise SystemExit("the fresh market's seed search has not accepted a seed")
    tasks = json.loads((ROOT / TASKS).read_text())
    if (tasks["brand"], f"env/fixtures/{tasks['fixture']}") != (search["brand"], FIXTURE):
        raise SystemExit("the task file is not the accepted market's")
    return {"fixture": FIXTURE, "search_record": SEARCH, "brand": search["brand"],
            "sku_prefix": search["sku_prefix"], "seed": accepted["seed"]}


def twenty_ninth():
    """The 29 October study's slots, from its manifest: suite payloads of every slot."""
    rows = []
    for line in B_OLD_MANIFEST.read_text().splitlines():
        if line.startswith("batch|"):
            rows.append(json.loads((Path(line.split("|")[1]) / "suite.json").read_text()))
    return rows


# ------------------------------------------------------------------------------ protocol


def b_protocol():
    old = json.loads((ROOT / B_OLD).read_text())
    slots = twenty_ninth()
    charges = [payload["rows"][0]["cost_usd"] for payload in slots]
    fresh = market()
    inputs = [TASKS, READINGS, FIXTURE, SEARCH, "docs/content/claim2-reading-rules.md",
              "notes/fresh-market-2-nov/protocol.md", "notes/fresh-market-2-nov/analysis-plan-B.md"]
    new = {**old,
           "study_id": B_STUDY,
           "protocol": "notes/fresh-market-2-nov/protocol.md",
           "analysis_plan": "notes/fresh-market-2-nov/analysis-plan-B.md",
           "design_of": {"study_id": old["study_id"], "file": B_OLD, "sha256": sha(ROOT / B_OLD)},
           "tasks_file": Path(TASKS).name,
           "market": fresh,
           "input_sha256": {path: sha(ROOT / path) for path in inputs},
           "analysis": {**old["analysis"],
                        "scope": "the 29 October design on the fresh held-out market of 2 November 2026",
                        "pooling": "no pooling with the 29 October Quenby study or any other",
                        "reporting_rules": "notes/replication-prep/matched-briefing-pre-unblinding-note-29-oct.md"},
           "budget": {"cap_usd": B_CAP, "minimum_key_credit_usd": 20, "inflight_reserve_usd": B_RESERVE,
                      "deadline": DEADLINE, "estimate_usd": B_ESTIMATE},
           "historical_reference": {"matched_briefing_29_oct_usd": round(sum(charges), 6),
                                    "largest_trial_usd": max(charges), "slots": len(charges)},
           "integrity_notes": [
               "Protocol and analysis plans committed before the market was drawn; no outcome-informed change.",
               "matched_briefing.py is byte-identical to afba41b; matched_briefing_study.py only sets its study identity.",
               "Only the factual briefing is matched; the full block also supplies its plan and reporting rules.",
               "Report provider charges separately from local browser and page-reading compute."],
           "status": "frozen"}
    for key in ("version", "model", "arms", "tasks", "repeats", "schedule", "require", "arm_require",
                "provider_routing", "technical_failures"):
        assert new[key] == old[key], key
    return write_json(ROOT / B_PROTOCOL, new)


# ------------------------------------------------------------------------------ inputs


def inputs():
    reference = json.loads((COHORT / "attempt2-command.json").read_text())
    tasks = json.loads((ROOT / TASKS).read_text())
    ids = tuple(question["id"] for question in reference["questions"])
    written = [write_json(NOTES / "study-a-runtime-questions.json",
                          {"questions": guard_a.runtime_questions(tasks, ids)})]
    # The cohort's command, byte for byte, and its model metadata, so the identity check reads
    # them inside this checkout.
    for source, target in ((COHORT / "attempt2-command.json", NOTES / "reference/attempt2-command.json"),
                           (COHORT / "model-metadata-31-oct.json", NOTES / "model-metadata-31-oct.json")):
        if target.exists():
            raise SystemExit(f"{target} exists; move it away first")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        written.append(target)
    if sha(NOTES / "reference/attempt2-command.json") != guard_a.FRESH_REFERENCE_SHA256:
        raise SystemExit("the reference command is not the cohort's")
    frozen = subprocess.run([reference["python"], "-m", "pip", "freeze", "--all"],
                            capture_output=True, text=True, check=True).stdout
    target = NOTES / "installed-packages.txt"
    if target.exists():
        raise SystemExit(f"{target} exists; move it away first")
    target.write_text(frozen)
    written.append(target)
    # Study B's dry runs: the model parser's replies to the same four templates on 29 October,
    # repeat 1. Each reply is a form with no market in it (sizes, availability, k), and each
    # equalled the rules' form there.
    replies = {}
    for payload in twenty_ninth():
        row = payload["rows"][0]
        if payload.get("condition") == "full-block" and row["repeat"] == 1:
            replies[row["task"]] = row["box"]["parse"]["reply"]
    written.append(write_json(NOTES / "study-b-parser-replies.json", {
        "_about": "Recorded model-parser replies, 29 October 2026, repeat 1 of the full block; for dry runs only",
        "replies": replies}))
    return written


# ------------------------------------------------------------------------------ preflight


def chrome_build(executable):
    found = re.search(r"\b\d+\.\d+\.\d+\.\d+\b", subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=True).stdout)
    return found.group() if found else None


def preflight(tests_log, shop_log):
    reference = json.loads((NOTES / "reference/attempt2-command.json").read_text())
    tests = Path(tests_log).read_text()
    shop = Path(shop_log).read_text()
    ran = re.search(r"^Ran (\d+) tests? in", tests, re.M)
    checks = re.search(r"^(\d+) checks, (\d+) failed$", shop, re.M)
    failed_tests = 0 if re.search(r"^OK(?: \(.*\))?$", tests, re.M) else None
    market_line = re.search(r"^tee_fresh_2_nov\.json: .* 45 listings, prefix IGR-FM02$", shop, re.M)
    if not ran or failed_tests is None or not checks or not market_line:
        raise SystemExit("the logs do not show a passing test run and a live check of the fresh market")
    build = chrome_build(reference["browser_executable"])
    lock = (ROOT / reference["dependencies_lock"]).read_bytes()
    matches = (NOTES / "installed-packages.txt").read_bytes() == lock
    receipt = {"verdict": "PASS" if (matches and build == reference["preflight_browser_version"]
                                      and int(checks.group(2)) == 0) else "FAIL",
               "scope": "free preparation; the verifier's command review is a separate receipt",
               "study_id": guard_a.FRESH_BUDGET, "model_calls": 0, "browser_version": build,
               "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "synthetic_tests": {"run": int(ran.group(1)), "failed": failed_tests,
                                   "log": str(Path(tests_log).resolve().relative_to(ROOT)), "log_sha256": sha(tests_log)},
               "dependencies_match_frozen_lock": matches,
               "shop_check": {"fixture": Path(FIXTURE).name, "checks": int(checks.group(1)),
                              "failed": int(checks.group(2)),
                              "log": str(Path(shop_log).resolve().relative_to(ROOT)), "log_sha256": sha(shop_log)},
               "source_sha256": {name: sha(ROOT / name) for name in (
                   "tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                   "experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py")}}
    return write_json(NOTES / "study-a-preflight.json", receipt)


# ------------------------------------------------------------------------------ configs


# Where experiment code and inputs live; results and notes are not code.
CODE = ("experiments/box", "experiments/runners", "experiments/analysis", "experiments/tests",
        "experiments/tasks", "experiments/water", "experiments/paths.py", "tools", "env")


def head():
    """The checked-out commit, refused while experiment code differs from it or is uncommitted."""
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *CODE], cwd=ROOT, capture_output=True,
                           text=True, check=True).stdout.strip()
    if dirty:
        raise SystemExit("experiment code differs from HEAD or is uncommitted; commit first:\n" + dirty)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def config_a(commit, fresh):
    reference = json.loads((NOTES / "reference/attempt2-command.json").read_text())
    settings = ("python", "page_python", "environment_file", "model", "provider", "allowed_served_providers",
                "maximum_input_tokens", "max_input_bytes", "max_output_tokens", "max_steps", "clock_s",
                "llm_timeout", "temperature", "frequency_penalty", "top_p", "use_vision", "browser_executable",
                "preflight_browser_version", "max_failures", "dependencies_lock")
    questions = json.loads((NOTES / "study-a-runtime-questions.json").read_text())["questions"]
    runtime = ["notes/fresh-market-2-nov/study-a-runtime-questions.json",
               "notes/fresh-market-2-nov/model-metadata-31-oct.json",
               "notes/fresh-market-2-nov/installed-packages.txt", APPROVAL,
               json.loads((NOTES / "study-a-preflight.json").read_text())["synthetic_tests"]["log"],
               json.loads((NOTES / "study-a-preflight.json").read_text())["shop_check"]["log"]]
    base = NOTES
    config = {"version": 1, "stage": guard_a.FRESH_STAGE, "repo": str(ROOT),
              **{key: reference[key] for key in settings},
              "estimate_usd": guard_a.FRESH_ESTIMATE_USD, "cap_usd": guard_a.FRESH_CAP_USD,
              "shared_cap_usd": guard_a.FRESH_CAP_USD, "carryover_usd": 0,
              "minimum_balance_usd": 20 + guard_a.LEGACY_UNSETTLED_USD,
              "legacy_unsettled_reserve_usd": guard_a.LEGACY_UNSETTLED_USD, "deadline": DEADLINE,
              "study_budget_id": guard_a.FRESH_BUDGET, "attempt": 1,
              "questions_file": str(NOTES / "study-a-runtime-questions.json"), "questions": questions,
              "repeats": [1, 2], "protocol_file": "notes/fresh-market-2-nov/protocol.md",
              "analysis_plan_file": "notes/fresh-market-2-nov/analysis-plan-A.md",
              "reference_config_file": "notes/fresh-market-2-nov/reference/attempt2-command.json",
              "preflight_receipt": "notes/fresh-market-2-nov/study-a-preflight.json",
              "tasks_file": TASKS, "market_files": [FIXTURE, SEARCH, READINGS], "market": fresh,
              "runtime_input_files": runtime,
              "verification_receipt": str(base / "study-a.verification.json"),
              "approval_record": str(base / "study-a.approval.json"),
              "ledger_path": str(base / "study-a.ledger.json"), "status_path": str(base / "study-a.status.json"),
              "log_path": str(base / "study-a.log"), "output_dir": str(base / "study-a.results"),
              "expected_head": commit}
    bound = {"tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
             "experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py",
             "experiments/paths.py", config["protocol_file"], config["analysis_plan_file"],
             config["dependencies_lock"], config["reference_config_file"], config["preflight_receipt"],
             TASKS, *config["market_files"], *runtime}
    bound.update(str(p.relative_to(ROOT)) for p in (ROOT / "experiments/box").glob("*.py"))
    config["hashes"] = {name: sha(ROOT / name) for name in sorted(bound)}
    return config


def config_b(commit, fresh):
    old = json.loads(B_OLD_CONFIG.read_text())
    python = old["steps"][1]["argv"][0]
    environment = old["steps"][1]["env"]
    protocol = json.loads((ROOT / B_PROTOCOL).read_text())
    common = ["--protocol", B_PROTOCOL]
    steps = [{"id": "live-market-check", "kind": "preflight",
              "argv": [str(ROOT / ".venv-naive/bin/python"), "env/check_aplus_market.py", "--fixture",
                       Path(FIXTURE).name, "--no-browser"], "max_seconds": 180, "env": environment}]
    for slot in protocol["schedule"]:
        args = ["--condition", slot["arm"], *common, "--slot-id", str(slot["slot"]), "--tasks", TASKS,
                "--only", slot["task"], "--repeats", "1", "--repeat-start", str(slot["repeat"]),
                "--page-reader", "rendered", "--max-steps", "300", "--clock", "1800"]
        steps.append({"id": f"slot-{slot['slot']:02d}-{slot['arm']}-{slot['task']}-r{slot['repeat']}",
                      "kind": "paid", "study_slot": slot,
                      "argv": [python, "experiments/runners/matched_briefing_study.py", *args],
                      "env": environment, "max_seconds": 1920,
                      "estimate_usd": round(B_ESTIMATE / len(protocol["schedule"]), 6),
                      "output_kind": "suite", "expected_tasks": [slot["task"]], "repeat": slot["repeat"],
                      "manifest_line_template": "batch|{batch}|" + " ".join(args)})
    agent = ROOT / "agent/agent-core"
    agent_head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=agent, capture_output=True, text=True,
                                check=True).stdout.strip()
    patch = subprocess.run(["git", "diff", "--binary", "HEAD"], cwd=agent, capture_output=True, check=True).stdout
    build = chrome_build("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    bound = set(old["hashes"]) | {B_PROTOCOL, TASKS, READINGS, FIXTURE, SEARCH, APPROVAL,
                                  "experiments/runners/matched_briefing_study.py",
                                  "notes/fresh-market-2-nov/protocol.md",
                                  "notes/fresh-market-2-nov/analysis-plan-B.md",
                                  "tools/guarded_matched_briefing.py", "tools/guarded_replication.py",
                                  "experiments/analysis/matched_briefing_analysis.py"}
    stem = "experiments/results/matched-briefing-fresh-2-nov"
    return {"repo": str(ROOT), "expected_head": commit, "study_id": B_STUDY, "protocol": B_PROTOCOL,
            "round": 1, "deadline": DEADLINE, "cap_usd": B_CAP, "reserve_usd": B_RESERVE,
            "manifest": stem + ".manifest", "status": stem + ".status.json", "log_dir": stem + ".logs",
            "results_dir": "experiments/results",
            "verification_receipt": "notes/fresh-market-2-nov/study-b.verification.json",
            "review_sheet": stem + ".sheet.csv",
            "review_html": "notes/fresh-market-2-nov/study-b-review.html",
            "preparation_log": stem + ".preparation.log",
            "preparation_status": stem + ".preparation.status.json",
            "git_checks": [{"cwd": "agent/agent-core", "head": agent_head,
                            "diff_sha256": hashlib.sha256(patch).hexdigest()}],
            "manifest_header": [
                f"study {B_STUDY} the 29 October matched-briefing design on the fresh held-out market "
                f"{fresh['brand']} seed {fresh['seed']}; no pooling with Quenby",
                f"conditions commit {commit} browser Google Chrome {build}; frozen executor and model parser; "
                f"matched_briefing.py byte-identical to afba41b",
                f"conditions approval {APPROVAL} sha256 {sha(ROOT / APPROVAL)}",
                f"WATCHDOG USD{B_CAP:g} study cap; USD{B_RESERVE:.2f} inflight reserve; preserve USD20 key credit; "
                f"no automatic retries"],
            "declared_estimate_usd": B_ESTIMATE,
            "hashes": {name: sha(ROOT / name) for name in sorted(bound)},
            "steps": steps}


def configs():
    commit, fresh = head(), market()
    written = []
    a = write_json(NOTES / "study-a-command.json", config_a(commit, fresh))
    command_a = [json.loads(a.read_text())["python"], str(ROOT / "tools/guarded_browser_use.py"),
                 "--config", str(a), "--execute"]
    written += [a, write_json(NOTES / "study-a-command.argv.json", command_a)]
    # Prepared, not approved: the student's approval is on file (APPROVAL), and the session that
    # holds it confirms at launch that it covers this exact command by setting approved to true.
    written.append(write_json(NOTES / "study-a.approval.json", {
        "approved": False, "config_sha256": sha(a), "command": command_a,
        "user_message": "Yes, unattended, cap $10", "approval_file": APPROVAL,
        "approval_file_sha256": sha(ROOT / APPROVAL), "estimate_usd": guard_a.FRESH_ESTIMATE_USD,
        "cap_usd": guard_a.FRESH_CAP_USD, "overall_ceiling_usd": 10,
        "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "to_launch": "after the verifier's PASS receipt binds this config_sha256, head and command, "
                     "the launching session sets approved to true and records when"}))
    b = write_json(NOTES / "study-b-command.json", config_b(commit, fresh))
    written.append(b)
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("protocol")
    modes.add_parser("inputs")
    check = modes.add_parser("preflight")
    check.add_argument("--tests-log", type=Path, required=True)
    check.add_argument("--shop-log", type=Path, required=True)
    modes.add_parser("configs")
    args = parser.parse_args()
    if args.mode == "protocol":
        written = [b_protocol()]
    elif args.mode == "inputs":
        written = inputs()
    elif args.mode == "preflight":
        written = [preflight(args.tests_log, args.shop_log)]
    else:
        written = configs()
    for path in written:
        print(f"written {Path(path).relative_to(ROOT)}  sha256 {sha(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
