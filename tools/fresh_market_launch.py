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

Study A's one continuation, after attempt 1 stopped at 08:21 on 2 November (LAUNCH.md):

    reconcile               attempt 1's carryover: its known charges plus call-00253 at its
                            reserved bound, checked against the account by the guard's own free
                            account read (the key and credits endpoints)
    continuation-preflight  the continuation's free preflight receipt, from a new test log
    continuation            its configuration at the checked-out commit, its exact command and
                            its approval record, prepared but not approved

No model or provider is contacted, and no account except by `reconcile`; `configs`,
`continuation-preflight` and `continuation` read the Chrome build, and the preflight the
Browser Use environment's package list, and nothing else outside the repository.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
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
# The student's plan: no paid run on Tuesday 3 November or later. Earlier than the protocol's
# absolute stop (3 November 12:00), which each launcher may not pass.
DEADLINE = "2026-11-02T23:59:00+08:00"
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


# ------------------------------------------------------------------------------ continuation
#
# Study A's attempt 1 stopped at 08:21 on 2 November (overnight-log.md): Browser Use's 120 s
# LLM timeout cancelled executor request call-00253, which left no response and no usage, so
# the guard refused every later call. Four slots answered, the fifth was interrupted and 27
# never started. The one continuation runs those 27 only (guarded_browser_use.py).

LEDGER_1 = f"{guard_a.FRESH_NOTES}/study-a.ledger.json"
CONTINUATION_PREFLIGHT = NOTES / "study-a-continuation-preflight.json"
CONTINUATION_PACKAGES = NOTES / "study-a-continuation-installed-packages.txt"


def no_response_request(ledger):
    """Attempt 1's one request with an unknown charge, which must be its last, ended in error
    with no response, no usage, no generation id and no serving provider."""
    calls = ledger["calls"]
    unknown = [call for call in calls if call["cost_usd"] is None]
    if (len(unknown) != 1 or unknown[0] is not calls[-1] or unknown[0]["error"] is not True
            or any(unknown[0][k] is not None for k in ("usage", "generation_id", "provider"))
            or ledger["inflight"]):
        raise SystemExit("attempt 1's ledger is not the one that stopped on one request with no response")
    return unknown[0]


def reconcile(account=None):
    """Attempt 1's carryover: its known charges plus call-00253 settled at its reserved bound,
    the most the provider can charge for that request, checked against the account.

    The rule was fixed before the account was read: the bound, unless the account shows a
    smaller true charge. The account cannot show one. Its usage is the key's total, so it
    cannot tell a request without a generation id from any other use of the key in the window,
    and it lags the provider (LESSONS 6). What it can show is a contradiction: more usage since
    attempt 1 began than attempt 1's known charges plus the bound, which this refuses. `account`
    is a test seam; by default the guard's own read, of the key and credits endpoints only."""
    config = json.loads((NOTES / "study-a-command.json").read_text())
    if sha(NOTES / "study-a-command.json") != guard_a.FRESH_ATTEMPT1_SHA256:
        raise SystemExit("study-a-command.json is not attempt 1's command")
    if sha(ROOT / LEDGER_1) != guard_a.FRESH_ATTEMPT1_LEDGER_SHA256:
        raise SystemExit("attempt 1's ledger is not the one it left when it stopped")
    ledger = json.loads((ROOT / LEDGER_1).read_text())
    request = no_response_request(ledger)
    known = sum(call["cost_usd"] for call in ledger["calls"] if call["cost_usd"] is not None)
    if known != ledger["charged_usd"]:
        raise SystemExit("attempt 1's known charges disagree with its ledger total")
    bound = request["reserved_usd"]
    carryover = known + bound
    if account is None:
        account = guard_a.account_snapshot(guard_a.read_key(config["environment_file"]))
    since = account["usage"] - ledger["start_usage"]
    if since > carryover + 1e-9:
        raise SystemExit("the account shows more usage since attempt 1 began than attempt 1 can have "
                         "been charged; inspect the key's other use before any continuation")
    required = config["minimum_balance_usd"] + (guard_a.FRESH_CAP_USD - carryover) + bound
    return write_json(ROOT / guard_a.FRESH_RECONCILIATION, {
        "study_budget_id": guard_a.FRESH_BUDGET,
        "prior_config_sha256": guard_a.FRESH_ATTEMPT1_SHA256,
        "prior_ledger_sha256": {LEDGER_1: sha(ROOT / LEDGER_1)},
        "prior_calls": len(ledger["calls"]), "known_charge_calls": len(ledger["calls"]) - 1,
        "known_charge_usd": known,
        "unknown_charges": [{k: request[k] for k in ("reservation", "role", "reserved_usd", "requested_at",
                                                     "completed_at", "error", "usage", "generation_id", "provider")}],
        "settled_usd": {request["reservation"]: bound},
        "settlement_rule": "the reserved bound unless the account shows a smaller true charge; the account "
                           "is the key's total, lags the provider and cannot attribute a charge to a request "
                           "with no generation id, so it cannot show one and the bound stands",
        "carryover_usd": carryover, "shared_cap_usd": guard_a.FRESH_CAP_USD,
        "remaining_allowance_usd": guard_a.FRESH_CAP_USD - carryover,
        "account_checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "account_usage_usd": account["usage"], "account_remaining_usd": account["remaining"],
        "attempt1_start_usage_usd": ledger["start_usage"],
        "account_usage_since_attempt1_usd": since,
        "account_usage_since_attempt1_minus_known_usd": since - known,
        "account_within_carryover": since <= carryover + 1e-9,
        "required_remaining_usd": required, "account_remaining_sufficient": account["remaining"] >= required,
        "inflight_requests": 0, "model_calls": 0,
        "account_read": "guarded_browser_use.account_snapshot: GET /api/v1/key and /api/v1/credits"})


def continuation_preflight(tests_log, packages=None):
    """The continuation's free preflight receipt: the Study A suites at the checked-out code
    (a new log), the Browser Use environment's packages read again against the frozen lock, the
    Chrome build now, and attempt 1's live shop check reused with its own date, not run again.
    `packages` is a test seam for the package list."""
    prior = json.loads((NOTES / "study-a-preflight.json").read_text())
    reference = json.loads((NOTES / "reference/attempt2-command.json").read_text())
    tests = Path(tests_log).read_text()
    ran = re.search(r"^Ran (\d+) tests? in", tests, re.M)
    if not ran or not re.search(r"^OK(?: \(.*\))?$", tests, re.M):
        raise SystemExit("the log does not show a passing test run")
    shop = prior["shop_check"]
    if prior.get("verdict") != "PASS" or shop.get("failed") != 0 or sha(ROOT / shop["log"]) != shop["log_sha256"]:
        raise SystemExit("attempt 1's live shop check is not the passing one its receipt names")
    if packages is None:
        packages = subprocess.run([reference["python"], "-m", "pip", "freeze", "--all"],
                                  capture_output=True, text=True, check=True).stdout
    if CONTINUATION_PACKAGES.exists():
        raise SystemExit(f"{CONTINUATION_PACKAGES} exists; move it away first")
    CONTINUATION_PACKAGES.write_text(packages)
    build = chrome_build(reference["browser_executable"])
    matches = CONTINUATION_PACKAGES.read_bytes() == (ROOT / reference["dependencies_lock"]).read_bytes()
    receipt = {"verdict": "PASS" if matches and build == reference["preflight_browser_version"] else "FAIL",
               "scope": "free preparation of the continuation; the verifier's command review is a separate receipt",
               "study_id": guard_a.FRESH_BUDGET, "attempt": 2, "model_calls": 0, "browser_version": build,
               "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "synthetic_tests": {"run": int(ran.group(1)), "failed": 0,
                                   "log": str(Path(tests_log).resolve().relative_to(ROOT)), "log_sha256": sha(tests_log)},
               "dependencies_match_frozen_lock": matches,
               "installed_packages": str(CONTINUATION_PACKAGES.relative_to(ROOT)),
               "shop_check": {**shop, "reused": "attempt 1's live check, run 2 November 02:09 to 02:17 "
                                                "before attempt 1; not run again for the continuation",
                              "from_receipt": "notes/fresh-market-2-nov/study-a-preflight.json"},
               "source_sha256": {name: sha(ROOT / name) for name in (
                   "tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                   "experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py")}}
    return write_json(CONTINUATION_PREFLIGHT, receipt)


def continuation_estimate(ledger, slots):
    """The continuation's estimate from attempt 1's own charges (LESSONS 41): its known charges
    over the five slots it started, the interrupted one included, times the slots still to run,
    rounded up to the next ten cents."""
    known = sum(call["cost_usd"] for call in ledger["calls"] if call["cost_usd"] is not None)
    started = guard_a.FRESH_KEPT_ANSWERED + guard_a.FRESH_KEPT_INTERRUPTED
    return math.ceil(round(known / started * slots * 10, 9)) / 10


def config_continuation(commit):
    """Attempt 1's configuration with the continuation's stage, attempt, carryover, cap,
    estimate, paths, preflight and commit, and attempt 1's evidence bound by hash. Every file
    attempt 1 ran with keeps its hash except the launcher and the runner's scheduling code."""
    prior = json.loads((NOTES / "study-a-command.json").read_text())
    if sha(NOTES / "study-a-command.json") != guard_a.FRESH_ATTEMPT1_SHA256:
        raise SystemExit("study-a-command.json is not attempt 1's command")
    reconciliation = json.loads((ROOT / guard_a.FRESH_RECONCILIATION).read_text())
    receipt = json.loads(CONTINUATION_PREFLIGHT.read_text())
    if receipt.get("verdict") != "PASS" or reconciliation["prior_ledger_sha256"] != {LEDGER_1: sha(ROOT / LEDGER_1)}:
        raise SystemExit("the continuation needs a passing preflight and the reconciliation of attempt 1's ledger")
    ledger = json.loads((ROOT / LEDGER_1).read_text())
    plan = json.loads((NOTES / "study-a.results/schedule.json").read_text())
    kept = guard_a.FRESH_KEPT_ANSWERED + guard_a.FRESH_KEPT_INTERRUPTED
    carryover = reconciliation["carryover_usd"]
    base, notes = NOTES, guard_a.FRESH_NOTES
    evidence = [f"{notes}/study-a-command.json", f"{notes}/study-a.status.json", LEDGER_1,
                f"{notes}/study-a.launch.json", f"{notes}/study-a.results/schedule.json",
                f"{notes}/study-a.results/slot-status.json", f"{notes}/study-a.results/completed.json",
                *(f"{notes}/study-a.results/{slot['id']}.json" for slot in plan["slots"][:guard_a.FRESH_KEPT_ANSWERED]),
                *(f"{notes}/study-a.results/{slot['id']}.interrupted.json" for slot in plan["slots"][guard_a.FRESH_KEPT_ANSWERED:kept]),
                guard_a.FRESH_RECONCILIATION]
    runtime = [*prior["runtime_input_files"], receipt["synthetic_tests"]["log"], receipt["installed_packages"]]
    config = {**prior, "stage": guard_a.FRESH_CONTINUATION_STAGE, "attempt": 2,
              "estimate_usd": continuation_estimate(ledger, len(plan["slots"]) - kept),
              "cap_usd": guard_a.FRESH_CAP_USD - carryover, "carryover_usd": carryover,
              "preflight_receipt": str(CONTINUATION_PREFLIGHT.relative_to(ROOT)), "runtime_input_files": runtime,
              "verification_receipt": str(base / "study-a-continuation.verification.json"),
              "approval_record": str(base / "study-a-continuation.approval.json"),
              **{field: str(base / name) for field, name in guard_a.FRESH_CONTINUATION_FILES.items()},
              "prior_config_file": f"{notes}/study-a-command.json", "prior_status_file": f"{notes}/study-a.status.json",
              "prior_schedule_file": f"{notes}/study-a.results/schedule.json",
              "prior_slot_status_file": f"{notes}/study-a.results/slot-status.json",
              "prior_ledger_file": LEDGER_1, "prior_ledger_files": [LEDGER_1],
              "reconciliation_file": guard_a.FRESH_RECONCILIATION, "expected_head": commit}
    names = set(prior["hashes"]) | set(runtime) | set(evidence) | {config["preflight_receipt"]}
    config["hashes"] = {name: sha(ROOT / name) for name in sorted(names)}
    renewed = {"tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py"}
    moved = sorted(name for name, digest in prior["hashes"].items()
                   if name not in renewed and config["hashes"][name] != digest)
    if moved:
        raise SystemExit("files attempt 1 ran with have changed: " + ", ".join(moved))
    return config


def continuation():
    commit = head()
    path = write_json(NOTES / "study-a-continuation-command.json", config_continuation(commit))
    config = json.loads(path.read_text())
    command = [config["python"], str(ROOT / "tools/guarded_browser_use.py"), "--config", str(path), "--execute"]
    # Prepared, not approved. The student's 01:57 approval covered attempt 1; the protocol allows
    # one recovery "separately verified and approved", so the session that holds the student's
    # approval of this continuation records their words and sets approved to true.
    approval = write_json(NOTES / "study-a-continuation.approval.json", {
        "approved": False, "config_sha256": sha(path), "command": command, "user_message": "",
        "approval_needed": "the student's own words approving this continuation of the 27 unstarted slots",
        "attempt1_approval_file": APPROVAL, "attempt1_approval_file_sha256": sha(ROOT / APPROVAL),
        "attempt1_user_message": "Yes, unattended, cap $10",
        "estimate_usd": config["estimate_usd"], "cap_usd": config["cap_usd"], "carryover_usd": config["carryover_usd"],
        "shared_cap_usd": guard_a.FRESH_CAP_USD, "overall_ceiling_usd": 10,
        "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "to_launch": "after the verifier's PASS receipt binds this config_sha256, head and command, the "
                     "launching session records the student's approval in user_message, sets approved to "
                     "true and records when"})
    return [path, write_json(NOTES / "study-a-continuation-command.argv.json", command), approval]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("protocol")
    modes.add_parser("inputs")
    check = modes.add_parser("preflight")
    check.add_argument("--tests-log", type=Path, required=True)
    check.add_argument("--shop-log", type=Path, required=True)
    modes.add_parser("configs")
    modes.add_parser("reconcile")
    again = modes.add_parser("continuation-preflight")
    again.add_argument("--tests-log", type=Path, required=True)
    modes.add_parser("continuation")
    args = parser.parse_args()
    if args.mode == "protocol":
        written = [b_protocol()]
    elif args.mode == "inputs":
        written = inputs()
    elif args.mode == "preflight":
        written = [preflight(args.tests_log, args.shop_log)]
    elif args.mode == "reconcile":
        written = [reconcile()]
    elif args.mode == "continuation-preflight":
        written = [continuation_preflight(args.tests_log), CONTINUATION_PACKAGES]
    elif args.mode == "continuation":
        written = continuation()
    else:
        written = configs()
    for path in written:
        print(f"written {Path(path).relative_to(ROOT)}  sha256 {sha(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
