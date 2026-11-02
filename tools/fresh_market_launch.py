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


def continuation_preflight(tests_log, packages=None, *, receipt_path=None, attempt=2):
    """The continuation's free preflight receipt: the Study A suites at the checked-out code
    (a new log), the Browser Use environment's packages read again against the frozen lock, the
    Chrome build now, and attempt 1's live shop check reused with its own date, not run again.
    `packages` is a test seam for the package list. Amendment 4's stages (2 November 2026) write
    the same receipt to their own `receipt_path`, their package list beside it."""
    receipt_file = CONTINUATION_PREFLIGHT if receipt_path is None else Path(receipt_path).resolve()
    package_file = (CONTINUATION_PACKAGES if receipt_path is None
                    else receipt_file.with_name(receipt_file.stem + "-installed-packages.txt"))
    if receipt_file.exists():
        raise SystemExit(f"{receipt_file} exists; move it away first")
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
    if package_file.exists():
        raise SystemExit(f"{package_file} exists; move it away first")
    package_file.write_text(packages)
    build = chrome_build(reference["browser_executable"])
    matches = package_file.read_bytes() == (ROOT / reference["dependencies_lock"]).read_bytes()
    receipt = {"verdict": "PASS" if matches and build == reference["preflight_browser_version"] else "FAIL",
               "scope": ("free preparation of the continuation" if receipt_path is None else
                         "free preparation of amendment 4's stages") + "; the verifier's command review is a separate receipt",
               "study_id": guard_a.FRESH_BUDGET, "attempt": attempt, "model_calls": 0, "browser_version": build,
               "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
               "synthetic_tests": {"run": int(ran.group(1)), "failed": 0,
                                   "log": str(Path(tests_log).resolve().relative_to(ROOT)), "log_sha256": sha(tests_log)},
               "dependencies_match_frozen_lock": matches,
               "installed_packages": str(package_file.relative_to(ROOT)),
               "shop_check": {**shop, "reused": "attempt 1's live check, run 2 November 02:09 to 02:17 "
                                                "before attempt 1; not run again for the continuation"
                                                + ("" if receipt_path is None else " or amendment 4's stages"),
                              "from_receipt": "notes/fresh-market-2-nov/study-a-preflight.json"},
               "source_sha256": {name: sha(ROOT / name) for name in (
                   "tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                   "experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py")}}
    return write_json(receipt_file, receipt)


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


# ------------------------------------------------------------------------------ amendment 4
#
# notes/fresh-market-2-nov/amendment-4-2-nov.md: stages that start after attempt 2 ends, each
# prepared from what the stages before it left, then verified and approved on its own. Study A
# shares a total cap of USD 10 across them; every earlier attempt's counted spend carries over.

CONTINUATION_COMMAND = f"{guard_a.FRESH_NOTES}/study-a-continuation-command.json"
AMENDMENTS = [f"{guard_a.FRESH_NOTES}/amendment-3-2-nov.md", f"{guard_a.FRESH_NOTES}/amendment-4-2-nov.md"]


def counted_spend(stage, names):
    """The carryover of a stage of amendment 4: what the guard counts the attempts in `names`
    spent (`carried_spend`), with each attempt's parts beside it for the reconciliation file."""
    parts = []
    for name in names:
        ledger = json.loads((ROOT / name).read_text())
        pending = (sum(c["reserved_usd"] for c in ledger["calls"] if c["cost_usd"] is None)
                   + sum(c["reserved_usd"] for c in ledger["inflight"].values()))
        known = sum(c["cost_usd"] for c in ledger["calls"] if c["cost_usd"] is not None)
        account = max(0, ledger["highwater_usage"] - ledger["start_usage"])
        parts.append({"ledger": name, "ledger_sha256": sha(ROOT / name), "calls": len(ledger["calls"]),
                      "in_flight": len(ledger["inflight"]), "known_charge_usd": known,
                      "without_known_charge_at_bound_usd": pending, "account_usage_usd": account,
                      "counted_usd": max(max(known, ledger["charged_usd"]) + pending, account),
                      "blocked_reason": ledger["blocked_reason"]})
    carryover, unsettled = guard_a.carried_spend([ROOT / name for name in names], names)
    return carryover, {
        "study_budget_id": guard_a.FRESH_BUDGET, "stage": stage,
        "prior_ledger_sha256": {part["ledger"]: part["ledger_sha256"] for part in parts},
        "attempts": parts, "carryover_usd": carryover, "held_back_from_account_usd": unsettled,
        "shared_cap_usd": guard_a.FRESH_A4_CAP_USD, "remaining_allowance_usd": guard_a.FRESH_A4_CAP_USD - carryover,
        "rule": "each attempt counts the larger of its known charges plus every request without a known "
                "charge at its reserved bound (settled, unknown or in flight), and the account's usage over "
                "its own run; guarded_browser_use.carried_spend, the computation the launcher checks",
        "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(), "model_calls": 0,
        "account_read": "none here; the launcher reads the account before its first call"}


def charge_per_started_slot(names, started):
    """The provider's known charges in these ledgers over the slots their attempts started
    (LESSONS 41): settlements are not charges, so they are left out, as in the continuation's."""
    known = sum(call["cost_usd"] for name in names for call in json.loads((ROOT / name).read_text())["calls"]
                if call["cost_usd"] is not None)
    return known / started


def up_to_ten_cents(value):
    return math.ceil(round(value * 10, 9)) / 10


def a4_receipt(preflight):
    """The a4-preflight receipt, refused unless it passed, before anything is written."""
    receipt = json.loads(Path(preflight).read_text())
    if receipt.get("verdict") != "PASS" or receipt.get("attempt") != "amendment-4":
        raise SystemExit("amendment 4's stages need a passing a4-preflight receipt")
    return receipt


def a4_config(stage, commit, output, preflight, deadline, start_cutoff, evidence, carryover, estimate, **fields):
    """Attempt 2's configuration with a stage of amendment 4's identity, budget, cutoff, paths,
    preflight and commit, and `evidence` bound by hash beside every file attempt 2 ran with."""
    prior = json.loads((ROOT / CONTINUATION_COMMAND).read_text())
    if sha(ROOT / CONTINUATION_COMMAND) != guard_a.FRESH_CONTINUATION_SHA256:
        raise SystemExit("study-a-continuation-command.json is not attempt 2's command")
    receipt = a4_receipt(preflight)
    folder = Path(output).resolve().parent
    runtime = list(dict.fromkeys([*prior["runtime_input_files"], receipt["synthetic_tests"]["log"],
                                  receipt["installed_packages"], *AMENDMENTS]))
    config = {**prior, "stage": stage, "estimate_usd": estimate,
              "cap_usd": guard_a.FRESH_A4_CAP_USD - carryover, "carryover_usd": carryover,
              "shared_cap_usd": guard_a.FRESH_A4_CAP_USD, "deadline": deadline, "start_cutoff": start_cutoff,
              "preflight_receipt": str(Path(preflight).resolve().relative_to(ROOT)), "runtime_input_files": runtime,
              "verification_receipt": str(folder / f"{guard_a.FRESH_PREFIX[stage]}.verification.json"),
              "approval_record": str(folder / f"{guard_a.FRESH_PREFIX[stage]}.approval.json"),
              **{field: str(NOTES / name) for field, name in guard_a.fresh_files(stage).items()},
              "reconciliation_file": guard_a.FRESH_A4_RECONCILIATION[stage], **fields, "expected_head": commit}
    config.pop("prior_ledger_file", None)
    names = set(prior["hashes"]) | set(runtime) | set(evidence) | {config["preflight_receipt"]}
    config["hashes"] = {name: sha(ROOT / name) for name in sorted(names)}
    moved = sorted(name for name, digest in prior["hashes"].items()
                   if name not in guard_a.FRESH_RENEWED and config["hashes"][name] != digest)
    if moved:
        raise SystemExit("files attempt 2 ran with have changed: " + ", ".join(moved))
    return config


def write_a4(stage, output, config, summary):
    """The configuration at `output`, its exact command beside it, and its approval record,
    prepared but not approved: the session that holds the student's approval records their words."""
    path = write_json(output, config)
    command = [config["python"], str(ROOT / "tools/guarded_browser_use.py"), "--config", str(Path(path).resolve()),
               "--execute"]
    approval = write_json(config["approval_record"], {
        "approved": False, "config_sha256": sha(path), "command": command, "user_message": "",
        "approval_needed": f"the student's own words approving {summary}",
        "amendment": AMENDMENTS[-1], "amendment_sha256": sha(ROOT / AMENDMENTS[-1]),
        "estimate_usd": config["estimate_usd"], "cap_usd": config["cap_usd"], "carryover_usd": config["carryover_usd"],
        "shared_cap_usd": config["shared_cap_usd"], "deadline": config["deadline"],
        "start_cutoff": config["start_cutoff"], "prepared_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "to_launch": "after the verifier's PASS receipt binds this config_sha256, head and command, the "
                     "launching session records the student's approval in user_message, sets approved to "
                     "true and records when"})
    return [path, write_json(Path(path).with_suffix(".argv.json"), command), approval]


def attempt3(output, preflight, *, deadline=guard_a.FRESH_LATEST, start_cutoff=guard_a.FRESH_START_CUTOFF):
    """Study A's attempt 3: the slots attempt 2 left never started, in their order, under its
    condition, with attempts 1 and 2's counted spend carried into the USD 10 cap. With none left the
    configuration still says so, and its launch ends without a paid call."""
    commit, stage, notes = head(), guard_a.FRESH_ATTEMPT3_STAGE, guard_a.FRESH_NOTES
    a4_receipt(preflight)
    if sha(ROOT / CONTINUATION_COMMAND) != guard_a.FRESH_CONTINUATION_SHA256:
        raise SystemExit("study-a-continuation-command.json is not attempt 2's command")
    first = json.loads((NOTES / "study-a.results/schedule.json").read_text())["slots"]
    given = first[guard_a.FRESH_KEPT_ANSWERED + guard_a.FRESH_KEPT_INTERRUPTED:]
    try:
        statuses, bound = guard_a.ended_stage(ROOT, guard_a.FRESH_CONTINUATION_STAGE,
                                              guard_a.FRESH_CONTINUATION_SHA256, 2, given)
    except guard_a.Stop as stop:
        raise SystemExit(f"attempt 2 cannot be continued as it stands: {stop}") from None
    remaining = [slot["id"] for slot in given if statuses[slot["id"]]["status"] == "not_started"]
    names = [guard_a.FRESH_LEDGER[guard_a.FRESH_STAGE], guard_a.FRESH_LEDGER[guard_a.FRESH_CONTINUATION_STAGE]]
    carryover, reconciliation = counted_spend(stage, names)
    started = (guard_a.FRESH_KEPT_ANSWERED + guard_a.FRESH_KEPT_INTERRUPTED
               + sum(row["status"] != "not_started" for row in statuses.values()))
    estimate = up_to_ten_cents(charge_per_started_slot(names, started) * len(remaining)) if remaining else 0
    written = [write_json(ROOT / guard_a.FRESH_A4_RECONCILIATION[stage], reconciliation)]
    fields = {"attempt": 3, "prior_config_file": CONTINUATION_COMMAND,
              "prior_status_file": f"{notes}/study-a-continuation.status.json",
              "prior_schedule_file": f"{notes}/study-a-continuation.results/schedule.json",
              "prior_slot_status_file": f"{notes}/study-a-continuation.results/slot-status.json",
              "prior_ledger_files": names, "slot_ids": remaining}
    evidence = [*bound, CONTINUATION_COMMAND, guard_a.FRESH_A4_RECONCILIATION[stage], *AMENDMENTS]
    config = a4_config(stage, commit, output, preflight, deadline, start_cutoff, evidence, carryover, estimate,
                       **fields)
    guard_a.validate_fresh_budget(config)
    if guard_a.validate_fresh_attempt3(config) != remaining:
        raise SystemExit("attempt 3's guard reads other slots than the builder")
    written += write_a4(stage, output, config, f"attempt 3 of Study A, its {len(remaining)} slots never "
                                               f"started, within Study A's USD 10 cap")
    ended = json.loads((NOTES / "study-a-continuation.status.json").read_text())
    print(f"attempt 2 ended {ended['status']} ({ended.get('reason', 'all its slots')}); attempt 3 runs "
          f"{len(remaining)} slot(s); carryover USD {carryover:.10f}, cap USD {config['cap_usd']:.10f}, "
          f"estimate USD {estimate}" + ("" if remaining else "; its launch ends without a paid call"))
    return written


def a_rerun(output, preflight, *, deadline=guard_a.FRESH_LATEST, start_cutoff=guard_a.FRESH_START_CUTOFF):
    """Study A's timeout reruns: every slot whose primary record reached its 2700 s clock, once,
    in schedule order, with its clock doubled to 5400 s and nothing else changed, carrying the
    counted spend of attempts 1, 2 and 3 (when it ran) into the USD 10 cap. With no timeout the
    configuration still says so, and its launch ends without a paid call."""
    commit, stage = head(), guard_a.FRESH_RERUN_STAGE
    a4_receipt(preflight)
    if sha(ROOT / CONTINUATION_COMMAND) != guard_a.FRESH_CONTINUATION_SHA256:
        raise SystemExit("study-a-continuation-command.json is not attempt 2's command")
    if guard_a.launched(ROOT, stage):
        raise SystemExit("the timeout-rerun stage has already been launched; each slot is rerun once")
    try:
        chain, bound, timeouts = guard_a.ended_primary_stages(ROOT)
    except guard_a.Stop as stop:
        raise SystemExit(f"the reruns cannot be prepared as the attempts stand: {stop}") from None
    carryover, reconciliation = counted_spend(stage, chain)
    # Twice the provider's known charges of each timed-out record, for twice its clock.
    known = sum(call["cost_usd"] for row in timeouts for call in json.loads((ROOT / row["record"]).read_text())["calls"]
                if call.get("cost_usd") is not None)
    estimate = up_to_ten_cents(2 * known) if timeouts else 0
    written = [write_json(ROOT / guard_a.FRESH_A4_RECONCILIATION[stage], reconciliation)]
    fields = {"attempt": guard_a.FRESH_RERUN_ATTEMPT, "prior_config_file": CONTINUATION_COMMAND,
              "prior_ledger_files": chain, "rerun_slots": timeouts, "rerun_clock_s": 2 * 2700}
    evidence = [*bound, CONTINUATION_COMMAND, guard_a.FRESH_A4_RECONCILIATION[stage], *AMENDMENTS]
    config = a4_config(stage, commit, output, preflight, deadline, start_cutoff, evidence, carryover, estimate,
                       **fields)
    for field in ("prior_status_file", "prior_schedule_file", "prior_slot_status_file"):
        config.pop(field, None)  # attempt 1's, as attempt 2 named them; the rerun reads them through its evidence
    guard_a.validate_fresh_budget(config)
    if guard_a.validate_fresh_rerun(config) != timeouts:
        raise SystemExit("the rerun's guard reads other slots than the builder")
    written += write_a4(stage, output, config, f"the timeout reruns of Study A, {len(timeouts)} slot(s) with "
                                               f"their clock doubled, within Study A's USD 10 cap")
    print(f"Study A timeout reruns: {len(timeouts)} slot(s) {[row['slot'] for row in timeouts]}; carryover USD "
          f"{carryover:.10f} from {len(chain)} attempts, cap USD {config['cap_usd']:.10f}, estimate USD {estimate}"
          + ("" if timeouts else "; its launch ends without a paid call"))
    return written


def agent_check():
    """openJiuwen's checked-out commit and the digest of its local patch, as config_b reads them."""
    agent = ROOT / "agent/agent-core"
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=agent, capture_output=True, text=True,
                            check=True).stdout.strip()
    patch = subprocess.run(["git", "diff", "--binary", "HEAD"], cwd=agent, capture_output=True, check=True).stdout
    return [{"cwd": "agent/agent-core", "head": commit, "diff_sha256": hashlib.sha256(patch).hexdigest()}]


def b_later(stage, commit, output, deadline, start_cutoff, steps, carryover, estimate, evidence, header, **fields):
    """Study B's primary configuration with a later stage's identity, cap, reserve, carryover,
    cutoff, paths, steps and commit, every file the primary run bound at its hash and `evidence`
    bound beside them. Its sheet is prepared once every stage has ended, so no review paths."""
    primary = json.loads((ROOT / guard_b.FRESH_PRIMARY_CONFIG).read_text())
    if agent_check() != primary["git_checks"]:
        raise SystemExit("openJiuwen's commit or local patch differs from the primary run's")
    build = chrome_build("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    config = {key: value for key, value in primary.items()
              if key not in ("review_sheet", "review_html", "preparation_log", "preparation_status")}
    stop = guard_b.LATER_CAP - guard_b.LATER_RESERVE
    config.update({"stage": stage, "expected_head": commit, "deadline": deadline, "start_cutoff": start_cutoff,
                   "cap_usd": guard_b.LATER_CAP, "shared_cap_usd": guard_b.LATER_CAP,
                   "reserve_usd": guard_b.LATER_RESERVE, "carryover_usd": carryover,
                   **guard_b.LATER[stage], "declared_estimate_usd": estimate,
                   "verification_receipt": str(Path(output).resolve().with_name(f"study-b-{stage}.verification.json")),
                   "manifest_header": [
                       f"study {guard_b.FRESH} {header}; amendment 4; no pooling with Quenby",
                       f"conditions commit {commit} browser Google Chrome {build}; the primary run's agent, steps "
                       f"and protocol, {guard_b.FRESH_PRIMARY_CONFIG} sha256 {guard_b.FRESH_PRIMARY_SHA256}",
                       f"conditions amendment {guard_b.AMENDMENT} sha256 {sha(ROOT / guard_b.AMENDMENT)}",
                       f"WATCHDOG USD{guard_b.LATER_CAP:g} shared study cap; carryover USD{carryover:.10f}; "
                       f"USD{guard_b.LATER_RESERVE:.2f} inflight reserve, a running trial stops at USD{stop:.2f} "
                       f"counted; no trial starts at or after {start_cutoff}; preserve USD20 key credit; "
                       f"no automatic retries"],
                   "steps": steps, **fields})
    names = set(primary["hashes"]) | set(evidence)
    config["hashes"] = {name: sha(ROOT / name) for name in sorted(names)}
    moved = sorted(name for name, digest in primary["hashes"].items()
                   if name not in guard_b.RENEWED and config["hashes"][name] != digest)
    if moved:
        raise SystemExit("files the primary run ran with have changed: " + ", ".join(moved))
    return config


def write_b(output, config):
    path = write_json(output, config)
    validated, _ = guard_b.validate_config(path)
    print(f"Study B {config['stage']}: {sum(s['kind'] == 'paid' for s in config['steps'])} paid step(s); carryover "
          f"USD {config['carryover_usd']:.10f}, cap USD {config['cap_usd']}, a running trial stops at USD "
          f"{config['cap_usd'] - config['reserve_usd']:.2f}; declared estimate USD {config['declared_estimate_usd']}")
    return [path]


def b_continuation(output, ruling=None, *, deadline=guard_a.FRESH_LATEST, start_cutoff=guard_a.FRESH_START_CUTOFF):
    """Study B's continuation: the primary run's steps it never completed (slot 16), unchanged,
    after the same live check, with the primary run's counted spend carried into USD 2.75. When
    the primary run had started such a step before it stopped, the configuration says so and
    needs the student's ruling, since amendment 4 point 4 forbids replaying a started slot."""
    commit = head()
    if sha(ROOT / guard_b.FRESH_PRIMARY_CONFIG) != guard_b.FRESH_PRIMARY_SHA256:
        raise SystemExit("study-b-command.json is not the primary run's command")
    primary = json.loads((ROOT / guard_b.FRESH_PRIMARY_CONFIG).read_text())
    status = json.loads((ROOT / primary["status"]).read_text())
    if status.get("status") not in ("complete", "stopped"):
        raise SystemExit("the primary run has not ended")
    completed = status["completed_steps"]
    steps = [primary["steps"][0]] + [step for step in primary["steps"][1:] if step["id"] not in completed]
    if len(steps) < 2:
        raise SystemExit("the primary run completed every step; nothing to continue")
    partial = guard_b.partial_run(ROOT, primary, status)
    fields = {}
    if partial:
        if not ruling or not ruling.strip():
            raise SystemExit(
                f"the primary run started {partial['step']} before it stopped: its launcher log "
                f"{partial['log']} names results folder {partial['results_folder']}, which holds "
                f"{partial['results_files']} and no suite record. Running it again replays a started slot, "
                f"which amendment 4 point 4 forbids unless the student rules otherwise; pass that ruling "
                f"with --ruling")
        fields = {"partial_run": partial, "partial_run_ruling": ruling}
    carryover = guard_b.primary_spent(status)
    recorded = guard_b.batch_slots(ROOT / primary["manifest"])
    estimate = up_to_ten_cents(status["recorded_usd"] / len(recorded) * (len(steps) - 1))
    evidence = [guard_b.FRESH_PRIMARY_CONFIG, primary["status"], primary["manifest"], guard_b.AMENDMENT,
                *([partial["log"]] if partial else [])]
    slots = ", ".join(str(step["study_slot"]["slot"]) for step in steps[1:])
    config = b_later(guard_b.CONTINUATION, commit, output, deadline, start_cutoff, steps, carryover, estimate,
                     evidence, f"continuation of the primary run, slot(s) {slots} unchanged", **fields)
    return write_b(output, config)


def b_rerun(output, *, deadline=guard_a.FRESH_LATEST, start_cutoff=guard_a.FRESH_START_CUTOFF):
    """Study B's timeout reruns: every slot whose primary record reached its 1800 s clock, in the
    primary manifest or the continuation's, once, in slot order, its primary step with the clock
    doubled to 3600 s and nothing else changed, carrying every earlier stage's counted spend into
    USD 2.75. With no timeout there is nothing to write."""
    commit, stage = head(), guard_b.RERUN
    if sha(ROOT / guard_b.FRESH_PRIMARY_CONFIG) != guard_b.FRESH_PRIMARY_SHA256:
        raise SystemExit("study-b-command.json is not the primary run's command")
    if guard_b.launched(ROOT, stage):
        raise SystemExit("the timeout reruns have already been launched; each slot is rerun once")
    primary = json.loads((ROOT / guard_b.FRESH_PRIMARY_CONFIG).read_text())
    status = json.loads((ROOT / primary["status"]).read_text())
    if status.get("status") not in ("complete", "stopped"):
        raise SystemExit("the primary run has not ended")
    try:
        carryover, manifests, later = guard_b.rerun_carryover(ROOT, primary, status)
        timeouts = guard_b.primary_timeouts(ROOT, manifests)
    except guard_b.original.Stop as stop:
        raise SystemExit(f"the reruns cannot be prepared as the stages stand: {stop}") from None
    if not timeouts:
        raise SystemExit("no primary record of Study B reached its clock; there is nothing to rerun")
    by_slot = {step["study_slot"]["slot"]: step for step in primary["steps"][1:]}
    steps = [primary["steps"][0]] + [guard_b.rerun_step(by_slot[row["slot"]], row) for row in timeouts]
    charges = [json.loads((ROOT / row["record"]).read_text()).get("cost_usd") or 0 for row in timeouts]
    estimate = up_to_ten_cents(2 * sum(charges))
    evidence = [guard_b.FRESH_PRIMARY_CONFIG, primary["status"], primary["manifest"], guard_b.AMENDMENT, *later,
                *(name for row in timeouts for name in (row["suite"], row["record"], row["log"]))]
    slots = ", ".join(str(row["slot"]) for row in timeouts)
    config = b_later(stage, commit, output, deadline, start_cutoff, steps, carryover, estimate, evidence,
                     f"timeout reruns of slot(s) {slots}, each its primary step with the clock doubled to 3600 s")
    return write_b(output, config)


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
    # Amendment 4's stages (2 November 2026), each written to the path given, never over a file.
    a4 = modes.add_parser("a4-preflight")
    a4.add_argument("--tests-log", type=Path, required=True)
    a4.add_argument("--output", type=Path, required=True)
    third = modes.add_parser("attempt3")
    third.add_argument("--preflight", type=Path, required=True, help="the a4-preflight receipt")
    b16 = modes.add_parser("b-continuation")
    b16.add_argument("--ruling", help="the student's ruling, when the primary run had started the step")
    reruns = modes.add_parser("a-rerun")
    reruns.add_argument("--preflight", type=Path, required=True, help="the a4-preflight receipt")
    b_reruns = modes.add_parser("b-rerun")
    for stage in (third, b16, reruns, b_reruns):
        stage.add_argument("--output", type=Path, required=True, help="where the configuration is written")
        stage.add_argument("--deadline", default=guard_a.FRESH_LATEST,
                           help="no paid call after this (default and latest: the protocol's absolute stop)")
        stage.add_argument("--start-cutoff", default=guard_a.FRESH_START_CUTOFF,
                           help="no trial starts at or after this (default 2026-11-03T12:00:00+08:00)")
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
    elif args.mode == "a4-preflight":
        receipt = continuation_preflight(args.tests_log, receipt_path=args.output, attempt="amendment-4")
        written = [receipt, receipt.with_name(receipt.stem + "-installed-packages.txt")]
    elif args.mode == "attempt3":
        written = attempt3(args.output, args.preflight, deadline=args.deadline, start_cutoff=args.start_cutoff)
    elif args.mode == "b-continuation":
        written = b_continuation(args.output, args.ruling, deadline=args.deadline, start_cutoff=args.start_cutoff)
    elif args.mode == "a-rerun":
        written = a_rerun(args.output, args.preflight, deadline=args.deadline, start_cutoff=args.start_cutoff)
    elif args.mode == "b-rerun":
        written = b_rerun(args.output, deadline=args.deadline, start_cutoff=args.start_cutoff)
    elif args.mode == "continuation":
        written = continuation()
    else:
        written = configs()
    for path in written:
        print(f"written {Path(path).relative_to(ROOT)}  sha256 {sha(path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
