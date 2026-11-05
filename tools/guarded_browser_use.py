#!/usr/bin/env python3
"""Verified, single-process Browser Use pilot launcher and per-request spending gate.

Validation is free. --execute additionally requires hash-bound independent verification
and recorded user approval. No implicit resume: a spent/uncertain pilot needs a new
reviewed recovery command. The $20 account reserve differs from request reservations.
"""
from __future__ import annotations
import argparse
import contextlib
import datetime as dt
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPEAT_STAGE = "plain-repeat-transfer"
REPEAT_RECOVERY_STAGE = "plain-repeat-recovery"
REPEAT_STAGES = {REPEAT_STAGE, REPEAT_RECOVERY_STAGE}
RECOVERY_STAGES = {"pilot-recovery", "overnight-transfer", "monitored-transfer", REPEAT_RECOVERY_STAGE}
REPEAT_BUDGET = "browser-use-plain-repeat-2026-11-01"
LEGACY_UNSETTLED_USD = 0.2117632
REPEAT_ATTEMPT1_SHA256 = "2a1b0ec9f9a58e047fed80680b03252a30a2c8d2f9594381f9c32257e762d700"
REPEAT_CARRYOVER_USD = 0.28053916066
REFERENCE_CONFIG_SHA256 = "404e45a0f7e029047a5a35394fbcbe79354bb53a9a13b2972a83478bc970e4ed"
# The fresh held-out market of 2 November 2026 (notes/fresh-market-2-nov/protocol.md and
# analysis-plan-A.md): the repeats 2-3 cohort's condition on a newly drawn market, as one
# attempt with its own budget, cap and deadline. Only the market and its questions, the repeat
# numbers, the study identity, the budget and the paths change; everything the agent receives
# is checked against the cohort's command before a call is paid for.
FRESH_STAGE = "fresh-market-transfer"
FRESH_BUDGET = "browser-use-fresh-market-2026-11-02"
FRESH_CAP_USD = 3.0
FRESH_ESTIMATE_USD = 1.5
FRESH_LATEST = "2026-11-03T12:00:00+08:00"  # the protocol's absolute stop, before the talk
FRESH_NOTES = "notes/fresh-market-2-nov"
# The cohort's continuation command (attempt 2 at 966e711), whose settings and frozen sources
# the fresh stage keeps.
FRESH_REFERENCE_SHA256 = "d92255c29e88f96631126c647bf67fdefb94276c7db255ed17a2331418d92d8d"
# What the agent receives is decided by these definitions of browser_use_transfer.py, which
# gained the fresh stage beside them. Each is pinned by the SHA-256 of its source text at
# 966e711, so a change to the question, the warning, the page read or the schedule stops the
# launch even though the file's own hash moved (`agent_facing_digests`).
AGENT_FACING = {
    "ARMS": "4e6ea65d67b7dbc3311e2983f392fbdb75dfa306885eea398b9703ec91a2b481",
    "TASK_IDS": "73b9b3f3cdd8343799643635b9189fe81193e9099459a5bce12716ed82e353f5",
    "QUESTION_FIELDS": "a01d64c5307bafe167e71f32311df18c4df87596c705606355c8ea85202a94c4",
    "COMMON_BRIEFING": "01e8f26824ffc34c4f2c74230ab88b17e80534477f0e379575f9161e623106d6",
    "validate_questions": "8d9ebba12ad7ac2c4797f207c6df555fb21cbcabe4cf8164bbc48d314c8fccc2",
    "schedule": "344b768b047c2aa6edb43e89e23c97fdf9d5d682d0cb8d210547a453d46d34b4",
    "validate_observation": "60b1657328d22118705b47d2b3a9e7ba8b6460fc502e60e13bb4d1d6bcc6eb3c",
    "build_query": "54f02bc99012ae0cbbf2ed86c8d02c0e693629cc96c7efe353911eae7beb4c5b",
    "read_observation": "47a13bd36a4c95b5ea195fd804db8b320774e9b0f8c8d8706f8a28420ab56f10",
}
# The fresh market's one continuation, 2 November 2026. Attempt 1 stopped at 08:21 when
# Browser Use's 120 s LLM timeout cancelled executor request call-00253: no response and no
# usage, so its charge was unknown and the guard refused every later call. Four slots had
# answered, the fifth was interrupted (a technical void, never replayed) and 27 never started.
# The continuation keeps those five as they are, runs only the 27 in their scheduled order
# under attempt 1's condition, and carries attempt 1's known charges plus call-00253 at its
# full bound into the same USD 3 cap and deadline. protocol.md allows one such recovery.
FRESH_CONTINUATION_STAGE = "fresh-market-continuation"
FRESH_STAGES = {FRESH_STAGE, FRESH_CONTINUATION_STAGE}
FRESH_ATTEMPT1_SHA256 = "ee4708f1ffd64dcc694d0acec03e0082eb25f822054499f5a700e0c0ed207925"  # study-a-command.json
FRESH_ATTEMPT1_LEDGER_SHA256 = "7cdd459886422a33243869bf06c3a888a739060695bf2fa2440a1dd29c791633"  # as it stopped
FRESH_KEPT_ANSWERED, FRESH_KEPT_INTERRUPTED = 4, 1  # attempt 1's slots in schedule order, then 27 unstarted
FRESH_CONTINUATION_FILES = {"ledger_path": "study-a-continuation.ledger.json",
                            "status_path": "study-a-continuation.status.json",
                            "output_dir": "study-a-continuation.results",
                            "log_path": "study-a-continuation.log"}
FRESH_RECONCILIATION = f"{FRESH_NOTES}/study-a-continuation-reconciliation.json"
# In the continuation only, an executor request that ends in error with no response and no
# usage is settled at its reserved bound, at most this many times; the next one stops the batch.
# A request the 2700 s trial clock cancels is settled too, but not counted toward this limit.
FRESH_NO_RESPONSE_SETTLEMENTS = 3
# In the continuation only, a trial that reaches its clock and one left without an answer after
# a settled request each end their slot and the batch goes on (browser_use_transfer.py); this
# many slots in a row without an answer stop it, since something systemic is then likely wrong.
FRESH_NO_ANSWER_STOP = 3
# Amendment 4, 2 November 2026 (notes/fresh-market-2-nov/amendment-4-2-nov.md): stages that start
# after attempt 2 ends, each after its own verifier pass. They share Study A's total cap, raised
# to USD 10 for them (point 5; attempt 2 keeps its USD 3), carry every earlier attempt's counted
# spend into it, and stop starting trials at their configuration's `start_cutoff`. Amendment 3's
# rules hold but one (point 5): a request the provider leaves without a response is settled at its
# bound with no count limit, and 3 executor requests in a row with no response stop the batch,
# since a provider outage is then likely.
#   attempt 3      the slots attempt 2 left never started, in their order, under its condition
#   timeout-rerun  each slot whose primary record reached its 2700 s clock, once more, in schedule
#                  order, with its clock doubled and nothing else changed: a record of its own,
#                  linked to the primary one, which it never replaces or edits
FRESH_ATTEMPT3_STAGE = "fresh-market-attempt-3"
FRESH_RERUN_STAGE = "timeout-rerun"
FRESH_RERUN_ATTEMPT = "timeout-rerun"  # a rerun record's attempt, never a primary attempt's number
# Amendment 6 (17:40): attempt 3 stopped at 17:31 when executor request call-00909 came back as an
# error reply with no usage. Attempt 4 runs only the slots attempt 3 never started, under its
# condition and its USD 10 cap. In attempt 4 and the reruns an executor's error reply without a
# charge is settled at its bound like a request with no response, and counts toward the same run
# of 3 that stops the batch; attempts 1 to 3 keep their rules.
FRESH_ATTEMPT4_STAGE = "fresh-market-attempt-4"
FRESH_ERROR_REPLY_STAGES = {FRESH_ATTEMPT4_STAGE, FRESH_RERUN_STAGE}
FRESH_ATTEMPT3_SHA256 = "c06e8b5d244045e60295ca5b3f0ffda6883d23ce76366af6ffb9d7b802ed8df1"  # attempt 3's command
FRESH_A4_STAGES = {FRESH_ATTEMPT3_STAGE, FRESH_ATTEMPT4_STAGE, FRESH_RERUN_STAGE}
FRESH_A4_CAP_USD = 10.0
# Amendment 4 point 6 (12:50): the rerun stage's share of Study A's total cap is USD 15, since
# settlements at the reserved bound run far ahead of the account. Attempt 3 keeps USD 10. An A
# rerun starts only if its doubled clock, and this margin for the page read and the browser,
# fits before the deadline's stop, as B's guard already checks.
FRESH_RERUN_CAP_USD = 15.0
FRESH_RERUN_FIT_MARGIN_S = 300
NO_TIME_REASON = "no time for a full rerun trial before the deadline"
FRESH_STAGES = FRESH_STAGES | FRESH_A4_STAGES
# The stages under amendment 3's settlement and batch rules.
FRESH_SETTLING_STAGES = {FRESH_CONTINUATION_STAGE} | FRESH_A4_STAGES
FRESH_NO_RESPONSE_RUN_STOP = 3
FRESH_START_CUTOFF = "2026-11-03T12:00:00+08:00"  # amendment 4's default; a configuration may set it earlier
START_CUTOFF_REASON = "start cutoff reached; no new trial"
# Every stage's files sit beside the others in FRESH_NOTES, named by one prefix: its ledger,
# status, launch claim, log and results folder. Fixed, so a budget cannot be reset by renaming.
FRESH_PREFIX = {FRESH_STAGE: "study-a", FRESH_CONTINUATION_STAGE: "study-a-continuation",
                FRESH_ATTEMPT3_STAGE: "study-a-attempt3", FRESH_ATTEMPT4_STAGE: "study-a-attempt4",
                FRESH_RERUN_STAGE: "study-a-rerun"}
FRESH_LEDGER = {stage: f"{FRESH_NOTES}/{prefix}.ledger.json" for stage, prefix in FRESH_PREFIX.items()}
FRESH_A4_RECONCILIATION = {FRESH_ATTEMPT3_STAGE: f"{FRESH_NOTES}/study-a-attempt3-reconciliation.json",
                           FRESH_ATTEMPT4_STAGE: f"{FRESH_NOTES}/study-a-attempt4-reconciliation.json",
                           FRESH_RERUN_STAGE: f"{FRESH_NOTES}/study-a-rerun-reconciliation.json"}
FRESH_CONTINUATION_SHA256 = "4b8c88dbd01af0ea9ad787a860e70e65396a33952b1844ee1348da0fcff37d9a"  # attempt 2's command
# The settings validate_fresh_continuation held attempt 2 to; every later stage keeps them.
FRESH_CONDITION = ("python", "page_python", "environment_file", "model", "provider", "allowed_served_providers",
                   "maximum_input_tokens", "max_input_bytes", "max_output_tokens", "max_steps", "clock_s",
                   "llm_timeout", "temperature", "frequency_penalty", "top_p", "use_vision", "browser_executable",
                   "preflight_browser_version", "max_failures", "dependencies_lock", "questions_file", "questions",
                   "repeats", "protocol_file", "analysis_plan_file", "reference_config_file", "tasks_file",
                   "market_files", "market", "study_budget_id", "legacy_unsettled_reserve_usd", "minimum_balance_usd")
# The launcher and the runner's scheduling code may change between stages; every other file a
# stage ran with keeps its hash, and the agent-facing definitions are checked by their own pins.
FRESH_RENEWED = {"tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py"}
# How a slot of a stage can end (browser_use_transfer.execute_study and mark_unfinished).
FRESH_NOT_RUN = {"interrupted", "time_censored", "not_started"}
GUARDED_STAGES = REPEAT_STAGES | FRESH_STAGES
# The continuation is a recovery too: it carries a prior ledger and its reconciliation.
RECOVERY_STAGES = RECOVERY_STAGES | {FRESH_CONTINUATION_STAGE} | FRESH_A4_STAGES
# A slot the worker saved a record for (browser_use_transfer.execute_study).
TERMINAL = {"answered", "failed", "timeout", "closed by the block"}


def fresh_files(stage):
    """A fresh-market stage's own ledger, status, results folder and log, inside FRESH_NOTES."""
    prefix = FRESH_PREFIX[stage]
    return {"ledger_path": f"{prefix}.ledger.json", "status_path": f"{prefix}.status.json",
            "output_dir": f"{prefix}.results", "log_path": f"{prefix}.log"}


def fresh_shared_cap(stage):
    """Study A's total cap as each stage counts it: USD 3 to attempt 2, USD 10 to attempt 3 and
    USD 15 to the timeout reruns (amendment 4, points 5 and 6)."""
    if stage == FRESH_RERUN_STAGE:
        return FRESH_RERUN_CAP_USD
    return FRESH_A4_CAP_USD if stage in FRESH_A4_STAGES else FRESH_CAP_USD


class Stop(RuntimeError):
    pass


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise Stop("invalid financial value")
    return float(value)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
        json.dump(value, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def deadline_epoch(value):
    deadline = dt.datetime.fromisoformat(value)
    if deadline.tzinfo is None:
        raise Stop("deadline must include a timezone")
    return deadline.timestamp()


def agent_facing_digests(source):
    """SHA-256 of the source text of each top-level definition named in AGENT_FACING, read
    from a browser_use_transfer.py source with `ast`, without importing it (2 November 2026)."""
    import ast
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        else:
            continue
        if name in AGENT_FACING:
            if name in found:
                raise Stop("an agent-facing definition appears twice")
            found[name] = hashlib.sha256(ast.get_source_segment(source, node).encode()).hexdigest()
    return found


def runtime_questions(task_data, ids):
    """The questions as the agent receives them, from a generated task file: for each id, in
    the given order, the template's query with the shop's address filled in and the brand's
    results page it opens with. Only id, query and start_url, never a key (2 November 2026)."""
    tasks = {task["id"]: task for task in task_data["tasks"]}
    base, brand = task_data["base_url"], task_data["brand"]
    start = f"{base}/catalogsearch/result/?q={brand}"
    questions = []
    for task_id in ids:
        query = tasks[task_id]["query"].format(base=base)
        if not query.startswith(f"Go to {start} . "):
            raise Stop("a generated question does not open the brand's results page")
        questions.append({"id": task_id, "query": query, "start_url": start})
    return questions


def read_key(path):
    """Read one explicitly configured key; never expose it or an exception body."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        for line in Path(path).read_text().splitlines():
            name, separator, value = line.removeprefix("export ").partition("=")
            if separator and name.strip() == "OPENROUTER_API_KEY":
                key = value.strip().strip("\"'")
                break
    if not key:
        raise Stop("OpenRouter credential unavailable")
    return key


# A read of /key waits up to 20 s a request and is tried three times, 2 s and then 5 s apart, on
# network and HTTP errors and timeouts only: on 2 November 2026 at 13:18 attempt 2 stopped when
# one reply outlasted a 6 s timeout (5.5 to 9.2 s a reply that afternoon). A reply that cannot
# be read as an account still stops at once. The whole read stays within 90 s, inside Browser
# Use's 120 s LLM timeout, because before_call reads the account in a thread and a request
# cancelled meanwhile would leave its reservation in flight.
ACCOUNT_TIMEOUT_S, ACCOUNT_RETRY_WAITS_S, ACCOUNT_BUDGET_S = 20, (2, 5), 90


def account_snapshot(key, *, sleep=None, clock=None):
    sleep, clock = sleep or time.sleep, clock or time.monotonic  # looked up when called
    started = clock()
    try:
        for wait in (*ACCOUNT_RETRY_WAITS_S, None):
            try:
                bodies = {}
                for endpoint in ("key", "credits"):
                    request = urllib.request.Request(f"https://openrouter.ai/api/v1/{endpoint}",
                                                     headers={"Authorization": f"Bearer {key}"})
                    timeout = min(ACCOUNT_TIMEOUT_S, ACCOUNT_BUDGET_S - (clock() - started))
                    if timeout <= 0:
                        raise TimeoutError("account read budget spent")
                    with urllib.request.urlopen(request, timeout=timeout) as response:
                        bodies[endpoint] = response.read()
                break
            except (OSError, http.client.HTTPException):  # network, HTTP status and timeouts only
                if wait is None or clock() - started + wait >= ACCOUNT_BUDGET_S:
                    raise
                sleep(wait)
        data = {endpoint: json.loads(body)["data"] for endpoint, body in bodies.items()}
        credits = number(data["credits"]["total_credits"]) - number(data["credits"]["total_usage"])
        data = data["key"]
        usage = number(data["usage"])
        remaining = data.get("limit_remaining")
        if remaining is None:
            remaining = number(data["limit"]) - usage
        # A key's allowance is not purchased account credit. Both must cover the
        # untouched reserve; never expose the larger account total as our budget.
        return {"usage": usage, "remaining": min(number(remaining), number(credits))}
    except Exception:
        raise Stop("account check failed; no further model call permitted") from None


def request_bound(config, metadata):
    """Upper bound at price ceilings and the verified maximum provider context window.

    The adapter must include messages, tool definitions and schema in prompt_bytes.
    Positive provider ceilings and explicit nonstreaming max_tokens are verified before
    each outbound request. No retry, helper or parser request may bypass this gate.
    """
    if metadata.get("model") != config["model"] or metadata.get("provider") != config["provider"]:
        raise Stop("request model/provider differs from the verified configuration")
    size, output = metadata.get("prompt_bytes"), metadata.get("max_output_tokens")
    if type(size) is not int or not 0 <= size <= config["max_input_bytes"]:
        raise Stop("request input exceeds the verified bound")
    if type(output) is not int or not 0 < output <= config["max_output_tokens"]:
        raise Stop("request output exceeds the verified bound")
    prices = config["provider"].get("max_price", {})
    inp, out = number(prices.get("prompt")), number(prices.get("completion"))
    if inp <= 0 or out <= 0 or prices.get("request") != 0 or set(prices) != {"prompt", "completion", "request"}:
        raise Stop("positive prompt/completion price ceilings required")
    if metadata.get("nontext_or_plugins") is not False:
        raise Stop("only text requests without plugins or non-token fees are permitted")
    context = config.get("maximum_input_tokens")
    if type(context) is not int or context <= 0:
        raise Stop("verified provider context-window bound is required")
    return (context * inp + output * out) / 1_000_000


def prior_ledger_names(config):
    names = config.get("prior_ledger_files", [config["prior_ledger_file"]] if "prior_ledger_file" in config else [])
    if (not isinstance(names, list) or not names or any(not isinstance(name, str) for name in names)
            or len(set(names)) != len(names)):
        raise Stop("recovery requires a nonempty, unique prior-ledger chain")
    if config.get("prior_ledger_file") and config["prior_ledger_file"] not in names:
        raise Stop("recovery ledger chain omits the original ledger")
    return names


def recovery_limits(config):
    """Carry every unsettled prior request at its full bound into a new pilot."""
    if config.get("stage") not in RECOVERY_STAGES:
        return 0.0, 0.0
    repo = Path(config["repo"]).resolve()
    names = prior_ledger_names(config)
    paths = [(repo / name).resolve() for name in names + [config["reconciliation_file"]]]
    if any(not path.is_relative_to(repo) for path in paths):
        raise Stop("recovery evidence must be inside the verified checkout")
    prior_paths, reconciliation_path = paths[:-1], paths[-1]
    reconciliation = json.loads(reconciliation_path.read_text())
    carryover = number(config["carryover_usd"])
    shared = number(config["shared_cap_usd"])
    # The fresh market's continuation shares its study's USD 3 cap, amendment 4's stages USD 10;
    # every earlier recovery $2.
    original = (fresh_shared_cap(config["stage"]) if config.get("stage") in FRESH_SETTLING_STAGES else 2)
    if shared != original or carryover + number(config["cap_usd"]) > shared + 1e-12:
        raise Stop(f"recovery would exceed the original shared ${original:g} cap")
    minimum, unsettled = carried_spend(prior_paths, names)
    if carryover + 1e-12 < minimum:
        raise Stop("recovery carryover omits prior charges or unsettled reservations")
    expected_hashes = {name: sha(path) for name, path in zip(names, prior_paths)}
    recorded_hashes = reconciliation.get("prior_ledger_sha256")
    if len(names) == 1 and isinstance(recorded_hashes, str):
        recorded_hashes = {names[0]: recorded_hashes}
    if (recorded_hashes != expected_hashes
            or number(reconciliation.get("carryover_usd")) != carryover):
        raise Stop("recovery reconciliation does not bind the prior ledger and carryover")
    return carryover, unsettled


def carried_spend(prior_paths, names):
    """What the prior attempts spent as the cap counts it, and what of that is not a known charge.
    Each attempt counts the larger of its known charges plus every request without one at its
    reserved bound (settled, unknown or in flight), and the account's usage over its own run; an
    attempt's own carryover counts too, so a chain can never shrink. Moved out of recovery_limits
    unchanged on 2 November 2026, so amendment 4's stages compute their carryover with it."""
    unsettled = minimum_carry = inherited_minimum = inherited_unsettled = 0.0
    for prior_path in prior_paths:
        prior = json.loads(Path(prior_path).read_text())
        if not set(prior.get("prior_ledger_files", [])) <= set(names):
            raise Stop("recovery ledger chain omits an earlier attempt")
        pending = sum(number(c["reserved_usd"]) for c in prior["calls"] if c.get("cost_usd") is None)
        pending += sum(number(c["reserved_usd"]) for c in prior["inflight"].values())
        known = max(number(prior["charged_usd"]), sum(number(c["cost_usd"]) for c in prior["calls"] if c.get("cost_usd") is not None))
        account_spend = max(0, number(prior["highwater_usage"]) - number(prior["start_usage"]))
        attempt_bound = max(known + pending, account_spend)
        minimum_carry += attempt_bound
        unsettled += pending
        inherited_minimum = max(inherited_minimum, number(prior.get("carryover_usd", 0)) + attempt_bound)
        inherited_unsettled = max(inherited_unsettled, number(prior.get("prior_unsettled_reserve_usd", 0)))
    return max(minimum_carry, inherited_minimum), max(unsettled, inherited_unsettled)


class CallBudget:
    def __init__(self, config, ledger_path, account_reader, *, clock=time.time, monotonic=time.monotonic):
        self.config = config
        self.path = Path(ledger_path)
        if self.path.exists():
            raise Stop("ledger already exists; implicit resume is forbidden")
        self.account_reader, self.clock = account_reader, clock
        # When the running trial's clock is due, on `monotonic`'s scale (`trial_clock`).
        self.monotonic, self.trial_clock_at = monotonic, None
        self.deadline = deadline_epoch(config["deadline"])
        self.monotonic_deadline = time.monotonic() + max(0, self.deadline - self.clock())
        self.cap = number(config["cap_usd"])
        self.reserve = number(config["minimum_balance_usd"])
        self.carryover, self.prior_unsettled = recovery_limits(config)
        if self.cap <= 0 or self.reserve < 20:
            raise Stop("positive cap and at least $20 account reserve required")
        self.lock = threading.RLock()
        self.state = {"schema": 1, "charged_usd": 0.0, "inflight": {}, "calls": [],
                      "blocked_reason": None, "start_usage": None, "highwater_usage": None,
                      "start_remaining": None, "minimum_remaining": None,
                      "account_decreases": 0, "deadline": config["deadline"], "cap_usd": self.cap,
                      "carryover_usd": self.carryover, "prior_unsettled_reserve_usd": self.prior_unsettled}
        self.state["prior_ledger_files"] = prior_ledger_names(config) if config.get("stage") in RECOVERY_STAGES else []
        if config.get("stage") in REPEAT_STAGES:
            validate_repeat_budget(config)
            self.state.update(study_budget_id=REPEAT_BUDGET, attempt=config["attempt"], shared_cap_usd=2,
                              legacy_unsettled_reserve_usd=LEGACY_UNSETTLED_USD,
                              minimum_balance_usd=self.reserve)
        if config.get("stage") in FRESH_STAGES:
            validate_fresh_budget(config)
            self.state.update(study_budget_id=FRESH_BUDGET, attempt=config["attempt"],
                              shared_cap_usd=fresh_shared_cap(config["stage"]),
                              legacy_unsettled_reserve_usd=LEGACY_UNSETTLED_USD,
                              minimum_balance_usd=self.reserve)
        if config.get("stage") == FRESH_CONTINUATION_STAGE:
            # Requests settled at their bound, kept apart from the provider's charges: those
            # with no response from the provider, which the limit counts, and those the trial
            # clock cancelled, which it does not.
            self.state.update(settled_usd=0.0, no_response_settlements=0, clock_settlements=0,
                              no_response_settlement_limit=FRESH_NO_RESPONSE_SETTLEMENTS)
        if config.get("stage") in FRESH_A4_STAGES:
            # Amendment 4, point 5: no limit on the provider's no-responses, but a run of them
            # in a row, the executor's requests with a response in between resetting it.
            self.state.update(settled_usd=0.0, no_response_settlements=0, clock_settlements=0,
                              no_response_settlement_limit=None, no_response_run=0,
                              no_response_run_stop=FRESH_NO_RESPONSE_RUN_STOP)
        if config.get("stage") in FRESH_ERROR_REPLY_STAGES:
            self.state.update(error_reply_settlements=0)  # amendment 6
        self._account()
        self._save()

    def _save(self):
        self.state["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        atomic_json(self.path, self.state)

    def _account(self):
        snapshot = self.account_reader()
        usage, remaining = number(snapshot["usage"]), number(snapshot["remaining"])
        if self.state["start_usage"] is None:
            self.state.update(start_usage=usage, highwater_usage=usage,
                              start_remaining=remaining, minimum_remaining=remaining)
        else:
            if usage < self.state["highwater_usage"]:
                self.state["account_decreases"] += 1
            self.state["highwater_usage"] = max(self.state["highwater_usage"], usage)
            self.state["minimum_remaining"] = min(self.state["minimum_remaining"], remaining)
        return snapshot

    def _block(self, reason):
        self.state["blocked_reason"] = reason
        self._save()
        raise Stop(reason)

    def before_call(self, metadata):
        with self.lock:
            if self.state["blocked_reason"]:
                raise Stop(self.state["blocked_reason"])
            if (self.clock() >= self.deadline - 15 or
                    (self.config.get("stage") in GUARDED_STAGES and
                     time.monotonic() >= self.monotonic_deadline - 15)):
                self._block("absolute deadline reached")
            try:
                verify_identity(self.config)
                bound = request_bound(self.config, metadata)
                self._account()
            except Exception as error:
                self._block(str(error) if isinstance(error, Stop) else "account or request validation failed")
            # A request settled at its bound counts as spent (the fresh continuation only).
            charged = self.state["charged_usd"] + self.state.get("settled_usd", 0.0)
            spent = max(charged, self.state["highwater_usage"] - self.state["start_usage"])
            inflight = sum(row["reserved_usd"] for row in self.state["inflight"].values())
            remaining = min(self.state["minimum_remaining"], self.state["start_remaining"] - charged) - self.prior_unsettled
            if spent + inflight + bound > self.cap + 1e-12:
                self._block("pilot spending cap would be exceeded")
            if remaining - inflight - bound < self.reserve - 1e-12:
                self._block("account reserve would be breached")
            reservation = f"call-{len(self.state['calls']) + len(self.state['inflight']) + 1:05d}"
            self.state["inflight"][reservation] = {"reserved_usd": bound, "role": metadata.get("role", "agent"),
                                                   "requested_at": self.clock()}
            self._save()
            return reservation

    def after_call(self, reservation, response_json=None, error=None):
        with self.lock:
            if reservation not in self.state["inflight"]:
                raise Stop("unknown or already settled request")
            item = self.state["inflight"].pop(reservation)
            usage = response_json.get("usage") if isinstance(response_json, dict) else None
            try:
                charge = number(usage.get("cost")) if isinstance(usage, dict) else None
            except Stop:
                charge = None
            item.update(reservation=reservation, cost_usd=charge,
                        generation_id=response_json.get("id") if isinstance(response_json, dict) else None,
                        provider=response_json.get("provider") if isinstance(response_json, dict) else None,
                        usage=usage, completed_at=self.clock(), error=bool(error))
            self.state["calls"].append(item)
            if charge is None:
                if self._settle_without_response(item, response_json, usage, error):
                    return
                self._block("a request has an unknown charge; reconciliation required")
            self.state["charged_usd"] += charge
            if "no_response_run" in self.state and item.get("role") == "executor":
                self.state["no_response_run"] = 0  # the provider answered: the run is broken
            allowed = self.config.get("allowed_served_providers", [])
            if response_json.get("provider") not in allowed:
                self._block("missing or unexpected serving provider; reconciliation required")
            if charge > item["reserved_usd"] + 1e-9:
                self._block("provider charge exceeded the verified request bound")
            self._save()
            if error:
                self._block("request failed; no automatic paid recovery")

    @contextlib.contextmanager
    def trial_clock(self, clock_s):
        """While a continuation trial runs, when its clock is due (2 November 2026). The worker
        enters this as the trial starts; the runner's own clock starts later, once the browser
        is open, so every request the clock cancels ends at or after this moment. A provider's
        own timeout that ends in those few seconds just before the clock counts as the clock's."""
        with self.lock:
            self.trial_clock_at = self.monotonic() + clock_s
        try:
            yield
        finally:
            with self.lock:
                self.trial_clock_at = None

    def _settle_without_response(self, item, response_json, usage, error):
        """The fresh continuation only (2 November 2026): an executor request that ended in
        error with no response and no usage, as call-00253 did when Browser Use's 120 s LLM
        timeout cancelled it, is settled at its reserved bound, the most the provider can
        charge for it, and the agent goes on as Browser Use does after a timeout. The provider's
        charge stays unknown (`cost_usd` None); the bound counts as spent against the cap. At
        most three settlements of requests the provider left without a response: the fourth
        stops the batch, its charge unknown. A request the trial's 2700 s clock cancelled (a
        cancellation at or after the clock was due, `trial_clock`) is settled the same way and
        counts against the cap, but not toward that limit, since the clock stops every slow
        trial while a request is almost always in flight. A parser request is never settled,
        since the block would fall back to the rules' form, and a response without usage still
        blocks. Returns whether the request was settled.

        Amendment 4's stages (point 5, 2 November 2026) settle the provider's no-responses with
        no count limit. The third executor request in a row with no response is settled too, then
        stops the batch: a provider outage is then likely. A clock settlement neither counts toward
        that run nor breaks it, and an executor request with a response breaks it (after_call).

        Attempt 4 and the reruns (amendment 6, 2 November 2026) also settle an executor's error
        reply that carries no charge, no usage or a usage without its cost, as call-00909 was, at
        its bound, labelled apart, counted in the same run of 3. A reply with a charge, a reply
        that is not an error, one from an unexpected provider, and a parser's still block."""
        stage = self.config.get("stage")
        if stage not in FRESH_SETTLING_STAGES or item.get("role") != "executor":
            return False
        reply = response_json is not None
        if not reply and (usage is not None or not error):
            return False
        if reply and not self._error_reply_without_charge(response_json, usage, error):
            return False
        unlimited = stage in FRESH_A4_STAGES
        by_clock = (not reply and str(error) == "CancelledError" and self.trial_clock_at is not None
                    and self.monotonic() >= self.trial_clock_at)
        done = self.state["no_response_settlements"]
        item["error_name"] = str(error) if error else None
        if reply:
            run = self.state["no_response_run"] + 1
            item.update(error_reply=error_message(response_json), settled_usd=item["reserved_usd"],
                        settlement_kind="error reply without usage",
                        settlement=f"an error reply without usage; settled at its reserved bound, "
                                   f"{run} in a row of {FRESH_NO_RESPONSE_RUN_STOP} that stop the batch")
            self.state["settled_usd"] += item["reserved_usd"]
            self.state.update(error_reply_settlements=self.state["error_reply_settlements"] + 1, no_response_run=run)
            if run >= FRESH_NO_RESPONSE_RUN_STOP:
                self._block(f"{run} executor requests in a row ended with no response or an error reply "
                            "without usage; a provider outage is likely")
            self._save()
            return True
        if not by_clock and not unlimited and done >= FRESH_NO_RESPONSE_SETTLEMENTS:
            item["settlement"] = f"not settled: request {done + 1} with no response stops the batch"
            self._block(f"a request ended with no response after {done} settlements; reconciliation required")
        item["settled_usd"] = item["reserved_usd"]
        self.state["settled_usd"] += item["reserved_usd"]
        if by_clock:
            item.update(settlement_kind="trial clock",
                        settlement="cancelled by the trial clock; settled at its reserved bound, "
                                   "not counted toward the limit")
            self.state["clock_settlements"] += 1
        elif unlimited:
            run = self.state["no_response_run"] + 1
            item.update(settlement_kind="no response",
                        settlement=f"no response and no usage; settled at its reserved bound, "
                                   f"{run} in a row of {FRESH_NO_RESPONSE_RUN_STOP} that stop the batch")
            self.state.update(no_response_settlements=done + 1, no_response_run=run)
            if run >= FRESH_NO_RESPONSE_RUN_STOP:
                self._block(f"{run} executor requests in a row ended with no response; "
                            "a provider outage is likely")
        else:
            item.update(settlement_kind="no response",
                        settlement=f"no response and no usage; settled at its reserved bound, "
                                   f"{done + 1} of {FRESH_NO_RESPONSE_SETTLEMENTS}")
            self.state["no_response_settlements"] = done + 1
        self._save()
        return True

    def _error_reply_without_charge(self, reply, usage, error):
        """An executor's error reply that carries no charge: attempt 4 and the reruns only."""
        if self.config.get("stage") not in FRESH_ERROR_REPLY_STAGES or not isinstance(reply, dict):
            return False
        failed = bool(error) or "error" in reply
        uncharged = usage is None or (isinstance(usage, dict) and usage.get("cost") is None)
        provider = reply.get("provider")
        known = provider is None or provider in self.config.get("allowed_served_providers", [])
        return failed and uncharged and known


def error_message(reply):
    """What an error reply said, for the ledger: its error's message, else its code, at most 300
    characters. The reply carries no key."""
    error = reply.get("error")
    text = (error.get("message") or error.get("code")) if isinstance(error, dict) else error
    return None if text is None else str(text)[:300]


def verify_identity(config):
    # Direct unit tests can use pure financial settings. Executable configurations
    # must contain these identity fields, as validate_config enforces before launch.
    if "expected_head" not in config:
        return
    repo = Path(config["repo"]).resolve()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    if head != config["expected_head"]:
        raise Stop("checkout HEAD differs from verified command")
    for relative, digest in config["hashes"].items():
        source = (repo / relative).resolve()
        if not source.is_relative_to(repo) or sha(source) != digest:
            raise Stop("source hash mismatch or path outside checkout")
    return head


def verify_browser_version(config):
    if config.get("stage") not in GUARDED_STAGES:
        return
    try:
        result = subprocess.run([config["browser_executable"], "--version"],
                                capture_output=True, text=True, timeout=15, check=True)
        version = re.search(r"\b\d+\.\d+\.\d+\.\d+\b", result.stdout)
        if version is None or version.group() != config["preflight_browser_version"]:
            raise Stop("browser build changed since the verified free preflight")
    except (OSError, subprocess.SubprocessError):
        raise Stop("browser version check failed before any new trial call") from None


def validate_repeat_budget(config):
    """One original attempt and one verified continuation under the same $2 cap."""
    recovery = config.get("stage") == REPEAT_RECOVERY_STAGE
    attempt, carryover, estimate = (2, REPEAT_CARRYOVER_USD, 1.3) if recovery else (1, 0, 1.6)
    if (config.get("study_budget_id") != REPEAT_BUDGET
            or config.get("attempt") != attempt or number(config.get("carryover_usd")) != carryover
            or config.get("shared_cap_usd") != 2 or abs(number(config.get("cap_usd")) - (2-carryover)) > 1e-12
            or config.get("estimate_usd") != estimate
            or config.get("legacy_unsettled_reserve_usd") != LEGACY_UNSETTLED_USD
            or number(config.get("minimum_balance_usd")) < 20 + LEGACY_UNSETTLED_USD
            or (not recovery and any(config.get(k) for k in ("prior_ledger_file", "prior_ledger_files", "reconciliation_file")))):
        raise Stop("plain repeats require the fixed attempt budget, cumulative cap and legacy reserve")
    base = Path(config["repo"]).resolve() / "notes/browser-use-repeat-1-nov"
    for field, suffix in {"ledger_path": "ledger.json", "status_path": "status.json",
                          "output_dir": "results", "log_path": "log"}.items():
        if Path(config[field]).resolve() != base / f"attempt{attempt}.{suffix}":
            raise Stop("plain-repeat paths cannot reset the shared budget")
    if deadline_epoch(config["deadline"]) > deadline_epoch("2026-11-03T00:00:00+08:00"):
        raise Stop("no paid repeat calls are authorized from Tuesday onward")


def validate_repeat_recovery(config, expected_slots=None):
    """Select only the unstarted suffix; do not consult answer contents or grades."""
    repo = Path(config["repo"]).resolve()
    fields = ("prior_config_file", "prior_status_file", "prior_slot_status_file", "prior_schedule_file")
    files = {field: (repo / config[field]).resolve() for field in fields}
    if any(not path.is_relative_to(repo) for path in files.values()):
        raise Stop("repeat recovery evidence must remain inside the checkout")
    if sha(files["prior_config_file"]) != REPEAT_ATTEMPT1_SHA256:
        raise Stop("repeat recovery must bind the exact original repeat command")
    prior = json.loads(files["prior_config_file"].read_text())
    if (prior.get("stage") != REPEAT_STAGE or prior.get("attempt") != 1
            or prior.get("study_budget_id") != REPEAT_BUDGET or prior.get("shared_cap_usd") != 2
            or prior.get("cap_usd") != 2 or prior.get("carryover_usd") != 0
            or prior.get("questions") != config["questions"] or prior.get("repeats") != [2, 3]):
        raise Stop("repeat recovery is limited to the first attempt of this unchanged batch")
    status = json.loads(files["prior_status_file"].read_text())
    if status.get("status") != "stopped" or status.get("config_sha256") != REPEAT_ATTEMPT1_SHA256:
        raise Stop("repeat recovery requires the terminal stopped first attempt")
    names = prior_ledger_names(config)
    if len(names) != 1:
        raise Stop("only one prior repeat attempt is permitted")
    ledger = json.loads((repo / names[0]).read_text())
    if (ledger.get("study_budget_id") != REPEAT_BUDGET or ledger.get("attempt") != 1
            or ledger.get("shared_cap_usd") != 2 or ledger.get("carryover_usd") != 0
            or ledger.get("inflight") or ledger.get("blocked_reason")
            or len(ledger.get("calls", [])) != 424
            or any(call.get("cost_usd") is None for call in ledger["calls"])):
        raise Stop("repeat recovery requires all first-attempt charges to be settled")
    known = sum(number(call["cost_usd"]) for call in ledger["calls"])
    spend = max(known, number(ledger["charged_usd"]), number(ledger["highwater_usage"])-number(ledger["start_usage"]))
    carryover, unsettled = recovery_limits(config)
    if abs(spend-REPEAT_CARRYOVER_USD) > 1e-12 or carryover != REPEAT_CARRYOVER_USD or unsettled:
        raise Stop("repeat recovery must preserve the complete first-attempt cost")
    plan = json.loads(files["prior_schedule_file"].read_text())
    slots = plan.get("slots", [])
    if (plan.get("stage") != REPEAT_STAGE or plan.get("batch_id") != REPEAT_BUDGET
            or len(slots) != 32 or len({slot["id"] for slot in slots}) != 32
            or (expected_slots is not None and slots != expected_slots)):
        raise Stop("repeat recovery prior schedule differs from the original 32 slots")
    statuses = json.loads(files["prior_slot_status_file"].read_text())["slots"]
    ids = [slot["id"] for slot in slots]
    terminal = {"answered", "failed", "timeout", "closed by the block"}
    if (set(statuses) != set(ids)
            or any(statuses[key].get("status") not in terminal for key in ids[:6])
            or any(statuses[key].get("status") != "not_started" for key in ids[6:])
            or any(statuses[key].get("phase") != "transfer" for key in ids)):
        raise Stop("repeat recovery must retain six terminal slots and continue only 26 unstarted slots")
    results = files["prior_slot_status_file"].parent
    completed_path = results / "completed.json"
    completed = json.loads(completed_path.read_text())
    if completed.get("completed") != ids[:6] or completed.get("expected") != 32:
        raise Stop("repeat recovery completed manifest differs from the retained prefix")
    required = {str(path.relative_to(repo)) for path in files.values()}
    required.add(str(completed_path.relative_to(repo)))
    for slot in slots[:6]:
        path = results / (slot["id"] + ".json")
        if not path.resolve().is_relative_to(results) or not path.is_file():
            raise Stop("repeat recovery is missing a retained first-attempt record")
        # Inspect identifiers and terminal status only. Never select on the answer.
        record = json.loads(path.read_text())
        if any(record.get(field) != expected for field, expected in {
                "slot": slot["id"], "task": slot["question"]["id"], "repeat": slot["repeat"],
                "condition": slot["condition"], "phase": "transfer", "batch_id": REPEAT_BUDGET,
                "outcome": statuses[slot["id"]]["status"]}.items()):
            raise Stop("repeat recovery retained-record identity differs from its slot")
        required.add(str(path.relative_to(repo)))
    if not required <= set(config["hashes"]):
        raise Stop("repeat recovery metadata and every retained record must be hash-bound")
    for relative in required:
        if sha(repo / relative) != config["hashes"][relative]:
            raise Stop("repeat recovery evidence changed after it was bound")
    return ids[6:]


def validate_repeat_identity(config):
    """Preserve the original experimental inputs, while changing only scheduling."""
    repo = Path(config["repo"]).resolve()
    reference_path = repo / config["reference_config_file"]
    if sha(reference_path) != REFERENCE_CONFIG_SHA256:
        raise Stop("plain repeats must bind the exact original monitored command")
    reference = json.loads(reference_path.read_text())
    fields = ("python", "page_python", "model", "provider", "allowed_served_providers",
              "maximum_input_tokens", "max_input_bytes", "max_output_tokens", "max_steps",
              "clock_s", "llm_timeout", "temperature", "frequency_penalty", "top_p",
              "use_vision", "browser_executable", "preflight_browser_version", "max_failures",
              "dependencies_lock")
    if any(config.get(field) != reference.get(field) for field in fields):
        raise Stop("plain-repeat execution settings differ from the original monitored command")
    if config.get("questions") != reference["transfer_questions"] or config.get("repeats") != [2, 3]:
        raise Stop("plain repeats must retain all eight original questions and use repeats 2 and 3")
    if "observation_contract" in config:
        raise Stop("plain repeats cannot enable an observation adapter")
    frozen = {"experiments/runners/browser_use_runner.py", "experiments/paths.py", config["dependencies_lock"]}
    frozen.update(str(p.relative_to(repo)) for p in (repo / "experiments/box").glob("*.py"))
    for relative in frozen:
        if sha(repo / relative) != reference["hashes"].get(relative):
            raise Stop("plain repeats changed the frozen runner, block/parser or dependency lock")
    verify_browser_version(config)
    preflight = json.loads((repo / config["preflight_receipt"]).read_text())
    if (preflight.get("verdict") != "PASS" or preflight.get("study_id") != REPEAT_BUDGET
            or preflight.get("model_calls") != 0
            or preflight.get("browser_version") != config["preflight_browser_version"]):
        raise Stop("plain repeats require their free preflight receipt")
    for relative in ("tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                     "experiments/runners/browser_use_runner.py"):
        if preflight.get("source_sha256", {}).get(relative) != sha(repo / relative):
            raise Stop("free repeat checks predate the current code")


def validate_fresh_budget(config):
    """One attempt on the fresh market under its own cap: no carry from another study, fixed
    paths so the budget cannot be reset by renaming them, and no call after the protocol's
    absolute stop. Its one continuation (attempt 2) carries attempt 1's spend, call-00253 at
    its bound included, into the same USD 3 cap, with its own fixed paths beside attempt 1's."""
    files = {"ledger_path": "study-a.ledger.json", "status_path": "study-a.status.json",
             "output_dir": "study-a.results", "log_path": "study-a.log"}
    if config.get("stage") == FRESH_CONTINUATION_STAGE:
        carryover = number(config.get("carryover_usd"))
        if (config.get("study_budget_id") != FRESH_BUDGET or config.get("attempt") != 2
                or not 0 < carryover < FRESH_CAP_USD or config.get("shared_cap_usd") != FRESH_CAP_USD
                or abs(number(config.get("cap_usd")) - (FRESH_CAP_USD - carryover)) > 1e-12
                or not 0 < number(config.get("estimate_usd")) <= number(config.get("cap_usd"))
                or config.get("legacy_unsettled_reserve_usd") != LEGACY_UNSETTLED_USD
                or number(config.get("minimum_balance_usd")) < 20 + LEGACY_UNSETTLED_USD
                or config.get("prior_ledger_files") != [f"{FRESH_NOTES}/study-a.ledger.json"]
                or config.get("reconciliation_file") != FRESH_RECONCILIATION):
            raise Stop("the fresh continuation carries attempt 1 into the same USD 3 cap, once")
        files = FRESH_CONTINUATION_FILES
    elif config.get("stage") in FRESH_A4_STAGES:
        # Amendment 4's stages: every earlier attempt carried into Study A's USD 10 total.
        carryover, estimate = number(config.get("carryover_usd")), number(config.get("estimate_usd"))
        ledgers = [FRESH_LEDGER[stage] for stage in (FRESH_STAGE, FRESH_CONTINUATION_STAGE, FRESH_ATTEMPT3_STAGE,
                                                    FRESH_ATTEMPT4_STAGE)]
        chains = {FRESH_ATTEMPT3_STAGE: [ledgers[:2]], FRESH_ATTEMPT4_STAGE: [ledgers[:3]],
                  FRESH_RERUN_STAGE: [ledgers[:2], ledgers[:3], ledgers[:4]]}[config["stage"]]
        attempt = {FRESH_ATTEMPT3_STAGE: 3, FRESH_ATTEMPT4_STAGE: 4}.get(config["stage"], FRESH_RERUN_ATTEMPT)
        shared = fresh_shared_cap(config["stage"])
        if (config.get("study_budget_id") != FRESH_BUDGET or config.get("attempt") != attempt
                or not 0 < carryover < shared or config.get("shared_cap_usd") != shared
                or abs(number(config.get("cap_usd")) - (shared - carryover)) > 1e-12
                or estimate > number(config.get("cap_usd"))
                or config.get("legacy_unsettled_reserve_usd") != LEGACY_UNSETTLED_USD
                or number(config.get("minimum_balance_usd")) < 20 + LEGACY_UNSETTLED_USD
                or config.get("prior_ledger_files") not in chains
                or config.get("reconciliation_file") != FRESH_A4_RECONCILIATION[config["stage"]]):
            raise Stop("amendment 4's stages carry attempts 1 and 2, and attempt 3 once it ran, into "
                       "Study A's cap for the stage, USD 10 for attempt 3 and USD 15 for the reruns, once")
        cutoff = config.get("start_cutoff")
        if not isinstance(cutoff, str) or deadline_epoch(cutoff) > deadline_epoch(config["deadline"]):
            raise Stop("amendment 4's stages stop starting trials at a start cutoff no later than the deadline")
        files = fresh_files(config["stage"])
    elif (config.get("study_budget_id") != FRESH_BUDGET or config.get("attempt") != 1
            or number(config.get("carryover_usd")) != 0
            or config.get("shared_cap_usd") != FRESH_CAP_USD or number(config.get("cap_usd")) != FRESH_CAP_USD
            or config.get("estimate_usd") != FRESH_ESTIMATE_USD
            or config.get("legacy_unsettled_reserve_usd") != LEGACY_UNSETTLED_USD
            or number(config.get("minimum_balance_usd")) < 20 + LEGACY_UNSETTLED_USD
            or any(config.get(k) for k in ("prior_ledger_file", "prior_ledger_files", "reconciliation_file"))):
        raise Stop("the fresh market requires its own single attempt, cap, estimate and reserve")
    base = Path(config["repo"]).resolve() / FRESH_NOTES
    for field, name in files.items():
        if Path(config[field]).resolve() != base / name:
            raise Stop("fresh-market paths are fixed so the budget cannot be reset")
    if deadline_epoch(config["deadline"]) > deadline_epoch(FRESH_LATEST):
        raise Stop("no paid fresh-market call is authorized after the protocol's absolute stop")


def validate_fresh_identity(config):
    """The cohort's condition on the fresh market (analysis-plan-A.md, identity table): the
    bound reference command's settings by value, its frozen adapter, block, import paths and
    dependency lock by hash, the agent-facing definitions by the hash of their source, the
    questions exactly as the generator wrote them, and a free preflight of the current code."""
    repo = Path(config["repo"]).resolve()
    reference_path = repo / config["reference_config_file"]
    if sha(reference_path) != FRESH_REFERENCE_SHA256:
        raise Stop("the fresh market must bind the repeats 2-3 cohort's exact command")
    reference = json.loads(reference_path.read_text())
    fields = ("python", "page_python", "model", "provider", "allowed_served_providers",
              "maximum_input_tokens", "max_input_bytes", "max_output_tokens", "max_steps",
              "clock_s", "llm_timeout", "temperature", "frequency_penalty", "top_p",
              "use_vision", "browser_executable", "preflight_browser_version", "max_failures",
              "dependencies_lock")
    if any(config.get(field) != reference.get(field) for field in fields):
        raise Stop("fresh-market execution settings differ from the cohort's command")
    if config.get("repeats") != [1, 2] or "observation_contract" in config:
        raise Stop("the fresh market runs repeats 1 and 2 of the cohort's plain condition")
    frozen = {"experiments/runners/browser_use_runner.py", "experiments/paths.py", config["dependencies_lock"]}
    frozen.update(str(p.relative_to(repo)) for p in (repo / "experiments/box").glob("*.py"))
    for relative in frozen:
        if sha(repo / relative) != reference["hashes"].get(relative):
            raise Stop("the fresh market changed the frozen adapter, block/parser or dependency lock")
    transfer = (repo / "experiments/runners/browser_use_transfer.py").read_text()
    if agent_facing_digests(transfer) != AGENT_FACING:
        raise Stop("the agent-facing definitions differ from the cohort's")
    ids = tuple(question["id"] for question in reference["questions"])
    task_data = json.loads((repo / config["tasks_file"]).read_text())
    if config.get("questions") != runtime_questions(task_data, ids):
        raise Stop("the questions differ from the fresh market's generated task file")
    # The market stamped on every record is the one the task file and its seed search name.
    market = config.get("market") or {}
    search = json.loads((repo / market.get("search_record", "")).read_text()) if market.get("search_record") else {}
    accepted = (search.get("tried") or [{}])[-1]
    if (market.get("fixture") != f"env/fixtures/{task_data.get('fixture')}" or market.get("brand") != task_data.get("brand")
            or not {market.get("fixture"), market.get("search_record")} <= set(config.get("market_files", []))
            or (search.get("brand"), search.get("sku_prefix")) != (market.get("brand"), market.get("sku_prefix"))
            or (accepted.get("seed"), accepted.get("outcome")) != (market.get("seed"), "accepted")):
        raise Stop("the market identity differs from the task file and its seed search")
    verify_browser_version(config)
    preflight = json.loads((repo / config["preflight_receipt"]).read_text())
    if (preflight.get("verdict") != "PASS" or preflight.get("study_id") != FRESH_BUDGET
            or preflight.get("model_calls") != 0
            or preflight.get("browser_version") != config["preflight_browser_version"]
            or preflight.get("dependencies_match_frozen_lock") is not True
            or (preflight.get("shop_check") or {}).get("failed") != 0):
        raise Stop("the fresh market requires its free preflight receipt")
    for relative in ("tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                     "experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py"):
        if preflight.get("source_sha256", {}).get(relative) != sha(repo / relative):
            raise Stop("free fresh-market checks predate the current code")


def validate_fresh_continuation(config, expected_slots=None):
    """Attempt 1 of the fresh market as it stopped, bound by hash, and the ids of the slots it
    never started, in their scheduled order (2 November 2026). Its four answered slots and its
    interrupted fifth are kept and never replayed. Reads identifiers, dispositions and charges,
    never an answer. Every file attempt 1 ran with keeps its hash, except this launcher and the
    runner's scheduling code, whose agent-facing definitions `validate_fresh_identity` checks."""
    repo = Path(config["repo"]).resolve()
    base = repo / FRESH_NOTES
    fixed = {"prior_config_file": "study-a-command.json", "prior_status_file": "study-a.status.json",
             "prior_schedule_file": "study-a.results/schedule.json",
             "prior_slot_status_file": "study-a.results/slot-status.json"}
    files = {field: (repo / config[field]).resolve() for field in fixed}
    if (any(files[field] != base / name for field, name in fixed.items())
            or prior_ledger_names(config) != [f"{FRESH_NOTES}/study-a.ledger.json"]
            or config.get("reconciliation_file") != FRESH_RECONCILIATION):
        raise Stop("the continuation reads attempt 1's own files, nothing else")
    if sha(files["prior_config_file"]) != FRESH_ATTEMPT1_SHA256:
        raise Stop("the continuation must bind attempt 1's exact command")
    prior = json.loads(files["prior_config_file"].read_text())
    condition = ("python", "page_python", "environment_file", "model", "provider", "allowed_served_providers",
                 "maximum_input_tokens", "max_input_bytes", "max_output_tokens", "max_steps", "clock_s",
                 "llm_timeout", "temperature", "frequency_penalty", "top_p", "use_vision", "browser_executable",
                 "preflight_browser_version", "max_failures", "dependencies_lock", "questions_file", "questions",
                 "repeats", "protocol_file", "analysis_plan_file", "reference_config_file", "tasks_file",
                 "market_files", "market", "study_budget_id", "legacy_unsettled_reserve_usd", "minimum_balance_usd")
    if (prior.get("stage") != FRESH_STAGE or prior.get("attempt") != 1 or prior.get("carryover_usd") != 0
            or prior.get("cap_usd") != FRESH_CAP_USD or any(config.get(k) != prior.get(k) for k in condition)
            or deadline_epoch(config["deadline"]) > deadline_epoch(prior["deadline"])):
        raise Stop("the continuation runs attempt 1's condition unchanged, by its deadline")
    renewed = {"tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py"}
    if any(config["hashes"].get(name) != digest for name, digest in prior["hashes"].items() if name not in renewed):
        raise Stop("the continuation changed a file attempt 1 ran with")
    status = json.loads(files["prior_status_file"].read_text())
    if status.get("status") != "stopped" or status.get("config_sha256") != FRESH_ATTEMPT1_SHA256:
        raise Stop("the continuation requires attempt 1's terminal stopped status")
    ledger_name = prior_ledger_names(config)[0]
    if sha(repo / ledger_name) != FRESH_ATTEMPT1_LEDGER_SHA256:
        raise Stop("attempt 1's ledger changed after it stopped")
    ledger = json.loads((repo / ledger_name).read_text())
    calls = ledger.get("calls", [])
    unknown = [call for call in calls if call.get("cost_usd") is None]
    if (ledger.get("study_budget_id") != FRESH_BUDGET or ledger.get("attempt") != 1
            or ledger.get("carryover_usd") != 0 or ledger.get("inflight") or len(unknown) != 1
            or unknown[0] is not calls[-1] or unknown[0].get("error") is not True
            or any(unknown[0].get(k) is not None for k in ("usage", "generation_id", "provider"))
            or ledger.get("blocked_reason") != "a request has an unknown charge; reconciliation required"):
        raise Stop("attempt 1's ledger is not the one that stopped on its one request with no response")
    # The carryover is attempt 1's known charges plus that request at its full bound, as the
    # reconciliation records it, and no less than the account's usage since attempt 1 began;
    # recovery_limits checks that the reconciliation binds this ledger.
    known = sum(number(call["cost_usd"]) for call in calls if call.get("cost_usd") is not None)
    settled = number(unknown[0]["reserved_usd"])
    carryover, unsettled = recovery_limits(config)
    reconciliation = json.loads((repo / config["reconciliation_file"]).read_text())
    if (abs(carryover - (known + settled)) > 1e-12 or unsettled != settled
            or reconciliation.get("settled_usd") != {unknown[0]["reservation"]: settled}
            or number(reconciliation.get("account_usage_since_attempt1_usd")) > carryover + 1e-9
            or abs(number(config["cap_usd"]) - (FRESH_CAP_USD - carryover)) > 1e-12):
        raise Stop("the carryover must be attempt 1's known charges plus its unknown request at its bound")
    plan = json.loads(files["prior_schedule_file"].read_text())
    slots = plan.get("slots", [])
    if (plan.get("stage") != FRESH_STAGE or plan.get("study_id") != FRESH_BUDGET
            or plan.get("batch_id") != FRESH_BUDGET or len(slots) != 32
            or len({slot["id"] for slot in slots}) != 32
            or (expected_slots is not None and slots != expected_slots)):
        raise Stop("attempt 1's schedule differs from the planned 32 slots")
    ids = [slot["id"] for slot in slots]
    statuses = json.loads(files["prior_slot_status_file"].read_text())["slots"]
    done, cut = FRESH_KEPT_ANSWERED, FRESH_KEPT_ANSWERED + FRESH_KEPT_INTERRUPTED
    if (set(statuses) != set(ids) or any(statuses[key].get("phase") != "transfer" for key in ids)
            or any(statuses[key].get("status") not in TERMINAL for key in ids[:done])
            or any(statuses[key].get("status") != "interrupted" for key in ids[done:cut])
            or any(statuses[key].get("status") != "not_started" for key in ids[cut:])):
        raise Stop("the continuation keeps attempt 1's four answered slots and its interrupted fifth, "
                   "and runs only the 27 never started")
    results = files["prior_slot_status_file"].parent
    completed = json.loads((results / "completed.json").read_text())
    marker = json.loads((base / "study-a.launch.json").read_text())
    if (completed.get("completed") != ids[:done] or completed.get("expected") != 32
            or marker.get("config_sha256") != FRESH_ATTEMPT1_SHA256 or marker.get("attempt") != 1):
        raise Stop("attempt 1's completed list or launch claim differs from its kept slots")
    required = {str(path.relative_to(repo)) for path in files.values()}
    required |= {f"{FRESH_NOTES}/study-a.results/completed.json", f"{FRESH_NOTES}/study-a.launch.json",
                 ledger_name, config["reconciliation_file"]}
    for slot in slots[:done]:
        if not (results / (slot["id"] + ".json")).is_file():
            raise Stop("a kept record of attempt 1 is missing")
        # Identifiers and disposition only. Never select on the answer.
        record = json.loads((results / (slot["id"] + ".json")).read_text())
        if any(record.get(field) != expected for field, expected in {
                "slot": slot["id"], "task": slot["question"]["id"], "repeat": slot["repeat"],
                "condition": slot["condition"], "phase": "transfer", "stage": FRESH_STAGE,
                "study_id": FRESH_BUDGET, "batch_id": FRESH_BUDGET, "config_sha256": FRESH_ATTEMPT1_SHA256,
                "outcome": statuses[slot["id"]]["status"]}.items()):
            raise Stop("a kept record of attempt 1 differs from its slot")
        required.add(f"{FRESH_NOTES}/study-a.results/{slot['id']}.json")
    for slot in slots[done:cut]:
        if not (results / (slot["id"] + ".interrupted.json")).is_file():
            raise Stop("attempt 1's interrupted record is missing")
        required.add(f"{FRESH_NOTES}/study-a.results/{slot['id']}.interrupted.json")
    if not required <= set(config["hashes"]):
        raise Stop("attempt 1's command, ledger, statuses and every kept record must be hash-bound")
    for relative in required:
        if sha(repo / relative) != config["hashes"][relative]:
            raise Stop("attempt 1's evidence changed after it was bound")
    return ids[cut:]


def ended_stage(repo, stage, config_sha256, attempt, slots):
    """One earlier stage of Study A as it ended, whatever ended it (amendment 4, 2 November 2026):
    its status, launch claim, ledger, schedule, slot statuses and completed list, and the record of
    every slot it ran, checked against each other by identifier and disposition, never by answer.
    `slots` are the slots it was given, in order. Returns the slot statuses and the files a later
    stage must bind by hash. A slot it interrupted, as its no-response limit or cap does mid-trial,
    or cut at the deadline, keeps that status: a technical void, never run again."""
    prefix, notes = FRESH_PREFIX[stage], FRESH_NOTES
    base = repo / notes
    files = {name: f"{notes}/{prefix}.{name}" for name in ("status.json", "launch.json", "ledger.json")}
    files.update({name: f"{notes}/{prefix}.results/{name}" for name in ("schedule.json", "slot-status.json",
                                                                       "completed.json")})
    status = json.loads((repo / files["status.json"]).read_text())
    if status.get("status") not in ("complete", "stopped") or status.get("config_sha256") != config_sha256:
        raise Stop(f"{prefix}: a later stage needs this stage's terminal status under its own command")
    marker = json.loads((repo / files["launch.json"]).read_text())
    ledger = json.loads((repo / files["ledger.json"]).read_text())
    if ((marker.get("study_budget_id"), marker.get("attempt"), marker.get("config_sha256"))
            != (FRESH_BUDGET, attempt, config_sha256)
            or (ledger.get("study_budget_id"), ledger.get("attempt")) != (FRESH_BUDGET, attempt)):
        raise Stop(f"{prefix}: its launch claim or ledger is not this stage's")
    plan = json.loads((repo / files["schedule.json"]).read_text())
    if ((plan.get("stage"), plan.get("study_id"), plan.get("batch_id")) != (stage, FRESH_BUDGET, FRESH_BUDGET)
            or plan.get("slots") != slots):
        raise Stop(f"{prefix}: its schedule differs from the slots it was given")
    ids = [slot["id"] for slot in slots]
    statuses = json.loads((repo / files["slot-status.json"]).read_text())["slots"]
    if set(statuses) != set(ids) or any(row.get("phase") != "transfer" or row.get("status") not in TERMINAL | FRESH_NOT_RUN
                                        for row in statuses.values()):
        raise Stop(f"{prefix}: a slot is still running or ended in a way no later stage reads; inspect it")
    ran = [slot_id for slot_id in ids if statuses[slot_id]["status"] in TERMINAL]
    completed = json.loads((repo / files["completed.json"]).read_text())
    if completed.get("completed") != ran or completed.get("expected") != len(ids):
        raise Stop(f"{prefix}: its completed list differs from the slots it saved a record for")
    bound = list(files.values())
    for slot in slots:
        record_path = base / f"{prefix}.results/{slot['id']}.json"
        if slot["id"] not in ran:
            if record_path.exists():
                raise Stop(f"{prefix}: a slot marked {statuses[slot['id']]['status']} has a saved record; inspect it")
            if (base / f"{prefix}.results/{slot['id']}.interrupted.json").is_file():
                bound.append(f"{notes}/{prefix}.results/{slot['id']}.interrupted.json")
            continue
        # Identifiers and disposition only. Never select on the answer.
        record = json.loads(record_path.read_text())
        if any(record.get(field) != expected for field, expected in {
                "slot": slot["id"], "task": slot["question"]["id"], "repeat": slot["repeat"],
                "condition": slot["condition"], "phase": "transfer", "stage": stage, "attempt": attempt,
                "study_id": FRESH_BUDGET, "batch_id": FRESH_BUDGET, "config_sha256": config_sha256,
                "outcome": statuses[slot["id"]]["status"]}.items()):
            raise Stop(f"{prefix}: a record differs from its slot")
        bound.append(f"{notes}/{prefix}.results/{slot['id']}.json")
    return statuses, bound


def validate_fresh_attempt3(config, expected_slots=None):
    """Attempt 2 as it ended, bound by hash, and the ids of the slots it left never started, in
    their scheduled order (amendment 4, 2 November 2026). Whatever ended attempt 2, done, its cap,
    its no-response limit, the deadline or its systemic stop, only a slot it never started runs:
    one it ran stays as it ended, and one it interrupted is a technical void, never re-run. The
    carryover is attempts 1 and 2's counted spend as `carried_spend` computes it, no more, no
    less. Every file attempt 2 ran with keeps its hash except the launcher and the runner's
    scheduling code, whose agent-facing definitions `validate_fresh_identity` checks."""
    repo = Path(config["repo"]).resolve()
    notes = FRESH_NOTES
    if launched(repo, FRESH_RERUN_STAGE):
        raise Stop("attempt 3 comes before the timeout reruns, whose carryover leaves it out, never after")
    fixed = {"prior_config_file": f"{notes}/study-a-continuation-command.json",
             "prior_status_file": f"{notes}/study-a-continuation.status.json",
             "prior_schedule_file": f"{notes}/study-a-continuation.results/schedule.json",
             "prior_slot_status_file": f"{notes}/study-a-continuation.results/slot-status.json"}
    if any(config.get(field) != name for field, name in fixed.items()):
        raise Stop("attempt 3 reads attempt 2's own files, nothing else")
    if sha(repo / fixed["prior_config_file"]) != FRESH_CONTINUATION_SHA256:
        raise Stop("attempt 3 must bind attempt 2's exact command")
    prior = json.loads((repo / fixed["prior_config_file"]).read_text())
    if (prior.get("stage") != FRESH_CONTINUATION_STAGE or prior.get("attempt") != 2
            or any(config.get(key) != prior.get(key) for key in FRESH_CONDITION)):
        raise Stop("attempt 3 runs attempt 2's condition unchanged")
    if any(config["hashes"].get(name) != digest for name, digest in prior["hashes"].items() if name not in FRESH_RENEWED):
        raise Stop("attempt 3 changed a file attempt 2 ran with")
    first = json.loads((repo / notes / "study-a.results/schedule.json").read_text()).get("slots", [])
    if len(first) != 32 or (expected_slots is not None and first != expected_slots):
        raise Stop("attempt 1's schedule differs from the planned 32 slots")
    given = first[FRESH_KEPT_ANSWERED + FRESH_KEPT_INTERRUPTED:]
    statuses, bound = ended_stage(repo, FRESH_CONTINUATION_STAGE, FRESH_CONTINUATION_SHA256, 2, given)
    ledger = json.loads((repo / FRESH_LEDGER[FRESH_CONTINUATION_STAGE]).read_text())
    if (ledger.get("carryover_usd") != prior.get("carryover_usd")
            or ledger.get("prior_ledger_files") != [FRESH_LEDGER[FRESH_STAGE]]):
        raise Stop("attempt 2's ledger does not carry attempt 1 as its command did")
    names = prior_ledger_names(config)
    carryover, _ = recovery_limits(config)
    if abs(carryover - carried_spend([repo / name for name in names], names)[0]) > 1e-9:
        raise Stop("the carryover must be attempts 1 and 2's counted spend, as the guard computes it")
    required = set(bound) | {fixed["prior_config_file"], config["reconciliation_file"], f"{notes}/amendment-4-2-nov.md"}
    if not required <= set(config["hashes"]):
        raise Stop("attempt 2's command, ledger, statuses, every record and amendment 4 must be hash-bound")
    for relative in required:
        if sha(repo / relative) != config["hashes"][relative]:
            raise Stop("attempt 2's evidence changed after it was bound")
    remaining = [slot["id"] for slot in given if statuses[slot["id"]]["status"] == "not_started"]
    if config.get("slot_ids") != remaining:
        raise Stop("attempt 3's slots are not the ones attempt 2 left never started, in their order")
    if remaining and not number(config["estimate_usd"]) > 0:
        raise Stop("attempt 3 needs a positive estimate for its slots")
    return remaining


def validate_fresh_attempt4(config, expected_slots=None):
    """Attempt 3 as it ended at 17:31, bound by hash, and the ids of the slots it left never
    started, in their scheduled order (amendment 6, 2 November 2026). Its interrupted slot is a
    technical void, never re-run, and every slot it ran keeps its record. Attempt 3's own slots
    are checked again to be the ones attempt 2 left never started. The carryover is attempts 1 to
    3's counted spend as `carried_spend` computes it. Every file attempt 3 ran with keeps its hash
    except the launcher and the runner's scheduling code. Reads identifiers, dispositions and
    charges, never an answer."""
    repo = Path(config["repo"]).resolve()
    notes = FRESH_NOTES
    if launched(repo, FRESH_RERUN_STAGE):
        raise Stop("attempt 4 comes before the timeout reruns, whose carryover leaves it out, never after")
    fixed = {"prior_config_file": f"{notes}/study-a-attempt3-command.json",
             "prior_status_file": f"{notes}/study-a-attempt3.status.json",
             "prior_schedule_file": f"{notes}/study-a-attempt3.results/schedule.json",
             "prior_slot_status_file": f"{notes}/study-a-attempt3.results/slot-status.json"}
    if any(config.get(field) != name for field, name in fixed.items()):
        raise Stop("attempt 4 reads attempt 3's own files, nothing else")
    if sha(repo / fixed["prior_config_file"]) != FRESH_ATTEMPT3_SHA256:
        raise Stop("attempt 4 must bind attempt 3's exact command")
    prior = json.loads((repo / fixed["prior_config_file"]).read_text())
    if (prior.get("stage") != FRESH_ATTEMPT3_STAGE or prior.get("attempt") != 3
            or any(config.get(key) != prior.get(key) for key in FRESH_CONDITION)):
        raise Stop("attempt 4 runs attempt 3's condition unchanged")
    if any(config["hashes"].get(name) != digest for name, digest in prior["hashes"].items() if name not in FRESH_RENEWED):
        raise Stop("attempt 4 changed a file attempt 3 ran with")
    first = json.loads((repo / notes / "study-a.results/schedule.json").read_text()).get("slots", [])
    if len(first) != 32 or (expected_slots is not None and first != expected_slots):
        raise Stop("attempt 1's schedule differs from the planned 32 slots")
    second, _ = ended_stage(repo, FRESH_CONTINUATION_STAGE, FRESH_CONTINUATION_SHA256, 2,
                            first[FRESH_KEPT_ANSWERED + FRESH_KEPT_INTERRUPTED:])
    given = [slot for slot in first[FRESH_KEPT_ANSWERED + FRESH_KEPT_INTERRUPTED:]
             if second[slot["id"]]["status"] == "not_started"]
    if [slot["id"] for slot in given] != prior.get("slot_ids"):
        raise Stop("attempt 3's slots are not the ones attempt 2 left never started")
    statuses, bound = ended_stage(repo, FRESH_ATTEMPT3_STAGE, FRESH_ATTEMPT3_SHA256, 3, given)
    ledger = json.loads((repo / FRESH_LEDGER[FRESH_ATTEMPT3_STAGE]).read_text())
    if (ledger.get("carryover_usd") != prior.get("carryover_usd")
            or ledger.get("prior_ledger_files") != prior.get("prior_ledger_files")):
        raise Stop("attempt 3's ledger does not carry attempts 1 and 2 as its command did")
    names = prior_ledger_names(config)
    carryover, _ = recovery_limits(config)
    if abs(carryover - carried_spend([repo / name for name in names], names)[0]) > 1e-9:
        raise Stop("the carryover must be attempts 1 to 3's counted spend, as the guard computes it")
    required = set(bound) | {fixed["prior_config_file"], config["reconciliation_file"], f"{notes}/amendment-6-2-nov.md"}
    if not required <= set(config["hashes"]):
        raise Stop("attempt 3's command, ledger, statuses, every record and amendment 6 must be hash-bound")
    for relative in required:
        if sha(repo / relative) != config["hashes"][relative]:
            raise Stop("attempt 3's evidence changed after it was bound")
    remaining = [slot["id"] for slot in given if statuses[slot["id"]]["status"] == "not_started"]
    if config.get("slot_ids") != remaining:
        raise Stop("attempt 4's slots are not the ones attempt 3 left never started, in their order")
    if remaining and not number(config["estimate_usd"]) > 0:
        raise Stop("attempt 4 needs a positive estimate for its slots")
    return remaining


def launched(repo, stage):
    """Whether a stage of Study A has left any file: its launch claim, status, ledger or results."""
    prefix = Path(repo) / FRESH_NOTES / FRESH_PREFIX[stage]
    return any(Path(f"{prefix}.{name}").exists() for name in ("launch.json", "status.json", "ledger.json", "results"))


def ended_primary_stages(repo):
    """Attempts 1 to 3 of Study A as they ended, for the timeout reruns (amendment 4, 2 November
    2026): the ledgers they spent from, the files that must stay bound, and every slot whose
    primary record reached its 2700 s clock, in the original schedule's order. A clock timeout is
    a slot its stage recorded with outcome and disposition `timeout`, whose record shows its own
    elapsed time at or past its 2700 s clock. In attempts 2 and 3 a timeout without that
    disposition did not reach its clock or failed the frozen classification, so amendment 2
    point 1 makes it a technical void, and it is not rerun. Attempt 1's launcher set no
    disposition, and under amendment 2 point 1 a timeout of its that reached the clock would
    count as a timeout, scored 0. Attempt 1 has none to rerun: its five started slots ended as
    four answers and one interrupted slot (FRESH_KEPT_ANSWERED, FRESH_KEPT_INTERRUPTED), which
    the continuation checks. Reads identifiers, dispositions, clocks and charges, never an answer.
    (Docstring corrected 2 November 2026 to match amendment 2. The code is unchanged.)"""
    repo = Path(repo).resolve()
    notes = FRESH_NOTES
    first = json.loads((repo / notes / "study-a.results/schedule.json").read_text()).get("slots", [])
    if len(first) != 32:
        raise Stop("attempt 1's schedule differs from the planned 32 slots")
    given = first[FRESH_KEPT_ANSWERED + FRESH_KEPT_INTERRUPTED:]
    statuses, bound = ended_stage(repo, FRESH_CONTINUATION_STAGE, FRESH_CONTINUATION_SHA256, 2, given)
    chain, ran = [FRESH_LEDGER[FRESH_STAGE], FRESH_LEDGER[FRESH_CONTINUATION_STAGE]], [(FRESH_CONTINUATION_STAGE, 2, statuses)]
    # Amendment 4 point 6 and amendment 6: the reruns start only after attempt 3 has ended when
    # attempt 2 left a slot never started, and after attempt 4 has ended when attempt 3 left one.
    for stage, attempt in ((FRESH_ATTEMPT3_STAGE, 3), (FRESH_ATTEMPT4_STAGE, 4)):
        given = [slot for slot in given if statuses[slot["id"]]["status"] == "not_started"]
        prefix = f"{notes}/{FRESH_PREFIX[stage]}"
        if not launched(repo, stage):
            if given:
                raise Stop(f"attempt {attempt - 1} left slots never started and attempt {attempt} has not run; "
                           f"the reruns start only after attempt {attempt} has ended")
            later = [later for later in (FRESH_ATTEMPT4_STAGE,) if later != stage and launched(repo, later)]
            if later:
                raise Stop(f"a later attempt ran though attempt {attempt} did not; inspect it")
            break
        if not given:
            raise Stop(f"attempt {attempt} ran though the attempt before it left no slot never started; inspect it")
        if not (repo / f"{prefix}.status.json").exists():
            raise Stop(f"attempt {attempt} has not ended")
        status = json.loads((repo / f"{prefix}.status.json").read_text())
        if status.get("status") not in ("complete", "stopped"):
            raise Stop(f"attempt {attempt}: a later stage needs this stage's terminal status")
        if (repo / f"{prefix}.results").exists():
            statuses, files = ended_stage(repo, stage, status.get("config_sha256"), attempt, given)
            chain.append(FRESH_LEDGER[stage])
            ran.append((stage, attempt, statuses))
            bound += files
        elif (repo / f"{prefix}.ledger.json").exists():
            raise Stop(f"attempt {attempt} left a ledger without its results; inspect it")
        else:  # it stopped before its worker started, with no call
            bound += [f"{prefix}.{name}" for name in ("status.json", "launch.json") if (repo / f"{prefix}.{name}").exists()]
            break
    order = [slot["id"] for slot in first]
    timeouts = []
    for stage, attempt, rows in ran:
        prefix = FRESH_PREFIX[stage]
        for slot_id, row in rows.items():
            if row.get("status") != "timeout" or row.get("disposition") != "timeout":
                continue
            relative = f"{notes}/{prefix}.results/{slot_id}.json"
            record = json.loads((repo / relative).read_text())
            elapsed, clock = record.get("elapsed_s"), (record.get("settings") or {}).get("clock_s")
            if (record.get("outcome") != "timeout" or record.get("disposition") != "timeout" or clock != 2700
                    or not isinstance(elapsed, (int, float)) or elapsed < clock):
                raise Stop(f"{slot_id}: recorded as a clock timeout, but its record does not show its 2700 s "
                           f"clock reached; inspect it")
            timeouts.append({"slot": slot_id, "stage": stage, "attempt": attempt, "record": relative,
                             "record_sha256": sha(repo / relative), "elapsed_s": elapsed, "clock_s": clock})
    timeouts.sort(key=lambda row: order.index(row["slot"]))
    if len({row["slot"] for row in timeouts}) != len(timeouts):
        raise Stop("a slot has two primary records")
    return chain, bound, timeouts


def own_claim(repo, stage, config_sha256):
    """Whether a stage's launch claim is this configuration's own: its worker validates the
    configuration again after the launcher has claimed the stage (2 November 2026)."""
    marker = Path(repo) / FRESH_NOTES / f"{FRESH_PREFIX[stage]}.launch.json"
    if not config_sha256 or not marker.exists():
        return False
    return json.loads(marker.read_text()).get("config_sha256") == config_sha256


def validate_fresh_rerun(config, expected_slots=None, config_sha256=None):
    """The timeout reruns (amendment 4, 2 November 2026): every slot of Study A whose primary
    record reached its 2700 s clock, each once, in schedule order, with its clock doubled to
    5400 s and nothing else changed, under attempt 2's condition and the reruns' USD 15 cap with
    every earlier attempt's counted spend carried. Refuses a slot that is not such a timeout, a
    slot listed twice, and any rerun once this stage has been launched by another configuration
    or before it has started: `config_sha256` names the configuration whose own claim this is, as
    the worker does after the launcher's claim (a check that refused that claim too would leave
    the stage blocking itself). A second launch of the same configuration is refused by the
    launcher, whose claim and status files already exist. Returns the rows of `rerun_slots`,
    each naming the primary record it reruns."""
    repo = Path(config["repo"]).resolve()
    notes = FRESH_NOTES
    clock = config.get("clock_s")
    if clock != 2700 or config.get("rerun_clock_s") != 2 * clock:
        raise Stop("the rerun doubles the 2700 s trial clock to 5400 s and changes nothing else")
    if config.get("prior_config_file") != f"{notes}/study-a-continuation-command.json":
        raise Stop("the rerun holds itself to attempt 2's own command, nothing else")
    if sha(repo / config["prior_config_file"]) != FRESH_CONTINUATION_SHA256:
        raise Stop("the rerun must bind attempt 2's exact command")
    prior = json.loads((repo / config["prior_config_file"]).read_text())
    if any(config.get(key) != prior.get(key) for key in FRESH_CONDITION):
        raise Stop("the rerun runs attempt 2's condition unchanged")
    if any(config["hashes"].get(name) != digest for name, digest in prior["hashes"].items() if name not in FRESH_RENEWED):
        raise Stop("the rerun changed a file attempt 2 ran with")
    first = json.loads((repo / notes / "study-a.results/schedule.json").read_text()).get("slots", [])
    if expected_slots is not None and first != expected_slots:
        raise Stop("attempt 1's schedule differs from the planned 32 slots")
    if launched(repo, FRESH_RERUN_STAGE) and not own_claim(repo, FRESH_RERUN_STAGE, config_sha256):
        raise Stop("each timed-out slot is rerun once; the timeout-rerun stage has already been launched")
    chain, bound, timeouts = ended_primary_stages(repo)
    if prior_ledger_names(config) != chain:
        raise Stop("the rerun carries every earlier attempt's ledger, attempt 3's once it ran")
    rows = config.get("rerun_slots")
    eligible = {row["slot"] for row in timeouts}
    if not isinstance(rows, list):
        raise Stop("the rerun lists its slots")
    for row in rows:
        if row.get("slot") not in eligible:
            raise Stop(f"{row.get('slot')} is not a timeout: only a slot whose primary record reached its "
                       f"clock is rerun")
    if len({row["slot"] for row in rows}) != len(rows):
        raise Stop("a slot is rerun once only")
    if rows != timeouts:
        raise Stop("the rerun list is not every timed-out slot, with its record, in schedule order")
    carryover, _ = recovery_limits(config)
    if abs(carryover - carried_spend([repo / name for name in chain], chain)[0]) > 1e-9:
        raise Stop("the carryover must be every earlier attempt's counted spend, as the guard computes it")
    required = set(bound) | {config["prior_config_file"], config["reconciliation_file"], f"{notes}/amendment-4-2-nov.md"}
    if not required <= set(config["hashes"]):
        raise Stop("every earlier attempt's statuses, ledgers, records and amendment 4 must be hash-bound")
    for relative in required:
        if sha(repo / relative) != config["hashes"][relative]:
            raise Stop("an earlier attempt's evidence changed after it was bound")
    if rows and not number(config["estimate_usd"]) > 0:
        raise Stop("the rerun needs a positive estimate for its slots")
    return rows


def validate_review_receipt(config, receipt, head, digest, command):
    if (receipt.get("verdict") != "PASS" or receipt.get("config_sha256") != digest
            or receipt.get("head") != head or receipt.get("request_bound_verified") is not True):
        raise Stop("independent verification does not bind this command and request bound")
    if config["stage"] in REPEAT_STAGES:
        # The receipt names the reviewer who checked the exact command: an independent one
        # for the repeat's recovery, the project's verifier otherwise.
        verifier = "codex-independent" if config["stage"] == REPEAT_RECOVERY_STAGE else "claude"
        if (receipt.get("verifier") != verifier or receipt.get("independent") is not True
                or receipt.get("command") != command
                or (config["stage"] == REPEAT_RECOVERY_STAGE
                    and receipt.get("reviewer_identity") != "browser_transfer_analysis")):
            raise Stop("plain repeats require the designated independent review of the exact command")
    if config["stage"] in FRESH_STAGES:
        # The project's verifier passes the exact command, and the approval is a separate
        # record. The continuation is reviewed the same way.
        if (receipt.get("verifier") != "claude" or receipt.get("independent") is not True
                or receipt.get("command") != command):
            raise Stop("the fresh market requires the verifier's review of the exact command")


def validate_config(path, *, require_approval=False):
    path = Path(path).resolve()
    config = json.loads(path.read_text())
    repo = Path(config["repo"]).resolve()
    if repo != ROOT:
        raise Stop("configuration belongs to another checkout")
    if (config.get("stage") not in ({"pilot", REPEAT_STAGE} | FRESH_STAGES | RECOVERY_STAGES)
            or config.get("version") != 1):
        raise Stop("only a separately approved development pilot is supported")
    recovery_limits(config)
    if config["stage"] in REPEAT_STAGES:
        validate_repeat_budget(config)
    if config["stage"] in FRESH_STAGES:
        validate_fresh_budget(config)
    # The fresh market's own cap is USD 3 (its protocol), USD 10 for amendment 4's stages; every
    # earlier stage keeps USD 2.
    limit = fresh_shared_cap(config["stage"]) if config["stage"] in FRESH_STAGES else 2
    if not 0 < number(config["cap_usd"]) <= limit or number(config["minimum_balance_usd"]) < 20:
        raise Stop(f"cap must be at most ${limit:g} and account reserve at least $20")
    if number(config["estimate_usd"]) > config["cap_usd"]:
        raise Stop("estimate exceeds pilot cap")
    if deadline_epoch(config["deadline"]) <= time.time() + 30:
        raise Stop("deadline leaves no launch window")
    if config["stage"] in FRESH_A4_STAGES and deadline_epoch(config["start_cutoff"]) <= time.time() + 30:
        raise Stop("the start cutoff leaves no launch window")
    if config.get("max_input_bytes", 0) <= 0 or config.get("max_output_tokens", 0) <= 0:
        raise Stop("request limits must be explicit")
    request_bound(config, {"model": config["model"], "provider": config["provider"],
                           "prompt_bytes": config["max_input_bytes"],
                           "max_output_tokens": config["max_output_tokens"], "nontext_or_plugins": False})
    if not config.get("allowed_served_providers"):
        raise Stop("allowed serving-provider response names must be explicit")
    required = {"tools/guarded_browser_use.py", "experiments/runners/browser_use_transfer.py",
                "experiments/runners/browser_use_runner.py", config["protocol_file"], config["dependencies_lock"]}
    required.update(str(p.relative_to(repo)) for p in (repo / "experiments/box").glob("*.py"))
    required.update(config["runtime_input_files"])
    if config["stage"] in REPEAT_STAGES:
        required.update({config["reference_config_file"], config["analysis_plan_file"], config["preflight_receipt"],
                         "experiments/paths.py"})
    if config["stage"] in FRESH_STAGES:
        # The market itself and the passive script-fetch listener the worker adds are bound too.
        required.update({config["reference_config_file"], config["analysis_plan_file"], config["preflight_receipt"],
                         "experiments/paths.py", "experiments/runners/browser_use_fetches.py",
                         config["tasks_file"], *config["market_files"]})
    if config["stage"] in RECOVERY_STAGES:
        required.update(prior_ledger_names(config))
        required.add(config["reconciliation_file"])
    if config["stage"] in {"overnight-transfer", "monitored-transfer"}:
        transfer_path = Path(config["transfer_questions_file"]).resolve()
        if not transfer_path.is_relative_to(repo):
            raise Stop("transfer questions must be inside the verified checkout")
        required.add(str(transfer_path.relative_to(repo)))
    questions_path = Path(config["questions_file"]).resolve()
    if not questions_path.is_relative_to(repo):
        raise Stop("runtime questions must be inside this checkout")
    required.add(str(questions_path.relative_to(repo)))
    if not required <= set(config["hashes"]):
        raise Stop("launcher, adapter, protocol, dependency lock, block/parser and inputs must be hash-bound")
    head = verify_identity(config)
    if config["stage"] in REPEAT_STAGES:
        validate_repeat_identity(config)
        if config["stage"] == REPEAT_RECOVERY_STAGE:
            validate_repeat_recovery(config)
    if config["stage"] in FRESH_STAGES:
        validate_fresh_identity(config)
    if config["stage"] == FRESH_CONTINUATION_STAGE:
        validate_fresh_continuation(config)
    if config["stage"] == FRESH_ATTEMPT3_STAGE:
        validate_fresh_attempt3(config)
    if config["stage"] == FRESH_ATTEMPT4_STAGE:
        validate_fresh_attempt4(config)
    if config["stage"] == FRESH_RERUN_STAGE:
        validate_fresh_rerun(config, config_sha256=sha(path))
        if deadline_epoch(config["deadline"]) - 15 - time.time() < config["rerun_clock_s"] + FRESH_RERUN_FIT_MARGIN_S:
            raise Stop("the deadline leaves no time for a full rerun trial")
    if require_approval:
        digest = sha(path)
        receipt = json.loads(Path(config["verification_receipt"]).read_text())
        approval = json.loads(Path(config["approval_record"]).read_text())
        command = [config["python"], str(repo / "tools/guarded_browser_use.py"), "--config", str(path), "--execute"]
        validate_review_receipt(config, receipt, head, digest, command)
        if (approval.get("approved") is not True or approval.get("config_sha256") != digest
                or approval.get("command") != command or not approval.get("user_message")):
            raise Stop("concrete user approval is missing")
    return config


def terminate_owned(child):
    if child is None or child.poll() is not None:
        return
    os.killpg(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=3)


def claim_repeat_launch(config, config_path):
    """Retained exclusive marker prevents duplicate workers under one allowance."""
    if config.get("stage") not in GUARDED_STAGES:
        return
    if config["stage"] in FRESH_STAGES:
        # The fresh market's attempt, its continuation, or a stage of amendment 4, each marked
        # beside its own ledger.
        validate_fresh_budget(config)
        name = f"{FRESH_PREFIX[config['stage']]}.launch.json"
        budget_id, marker = FRESH_BUDGET, Path(config["ledger_path"]).with_name(name)
    else:
        validate_repeat_budget(config)
        budget_id = REPEAT_BUDGET
        marker = Path(config["ledger_path"]).with_name(f"attempt{config['attempt']}.launch.json")
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise Stop("repeat attempt already claimed; concurrent launch or implicit resume forbidden") from None
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"study_budget_id": budget_id, "attempt": config["attempt"], "config_sha256": sha(config_path),
                   "launcher_pid": os.getpid(), "claimed_at": time.time()}, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())


def mark_unfinished(config, reason):
    path = Path(config["output_dir"]) / "slot-status.json"
    if not path.exists():
        return
    manifest = json.loads(path.read_text())
    for row in manifest["slots"].values():
        if row["status"] == "running":
            row.update(status="time_censored" if "deadline" in reason else "interrupted", reason=reason)
        elif row["status"] == "scheduled":
            row.update(status="not_started", reason=reason)
    atomic_json(path, manifest)


def nothing_left(path):
    """Attempt 3 when attempt 2 left no slot never started, or the timeout reruns when no primary
    record is a timeout (amendment 4, 2 November 2026): the configuration is checked in full, free,
    against the bound evidence, and the stage then ends without a claim, a ledger or a paid call."""
    config = json.loads(Path(path).read_text())
    empty = {FRESH_ATTEMPT3_STAGE: config.get("slot_ids") == [], FRESH_ATTEMPT4_STAGE: config.get("slot_ids") == [],
             FRESH_RERUN_STAGE: config.get("rerun_slots") == []}
    if not empty.get(config.get("stage")):
        return False
    validate_config(path)
    return True


def worker_stop_reason(config, blocked):
    """Why a stage of amendment 4 stopped, when its worker stopped it: the guard's blocked reason
    (its cap, a run of no-responses), or the reason the worker wrote on the slots it did not start
    (its start cutoff, or slots in a row without an answer). None when neither says."""
    if blocked:
        return f"pilot worker did not complete: {blocked}"
    path = Path(config["output_dir"]) / "slot-status.json"
    rows = json.loads(path.read_text())["slots"].values() if path.exists() else []
    reasons = {row["reason"] for row in rows if row.get("status") == "not_started" and row.get("reason")}
    return f"pilot worker did not complete: {reasons.pop()}" if len(reasons) == 1 else None


def execute(path):
    if nothing_left(path):
        print("No slot is left for this stage; it ends without a paid call.")
        return
    config = validate_config(path, require_approval=True)
    status_path, ledger = Path(config["status_path"]), Path(config["ledger_path"])
    if status_path.exists() or ledger.exists():
        raise Stop("pilot artifacts already exist; no implicit resume")
    claim_repeat_launch(config, path)
    key = read_key(config["environment_file"])
    before = account_snapshot(key)
    carryover, prior_unsettled = recovery_limits(config)
    if before["remaining"] < config["minimum_balance_usd"] + config["cap_usd"] + prior_unsettled:
        raise Stop("insufficient balance for pilot cap and reserved credit")
    token = secrets.token_hex(24)
    env = dict(os.environ, OPENROUTER_API_KEY=key, IGR_BROWSER_USE_GUARD=token,
               IGR_BROWSER_USE_CONFIG_SHA256=sha(path), ANONYMIZED_TELEMETRY="false")
    argv = [config["python"], str(ROOT / "experiments/runners/browser_use_transfer.py"),
            "--config", str(Path(path).resolve()), "--execute"]
    child = caffeinate = None
    stop_at = deadline_epoch(config["deadline"]) - 15
    monotonic_stop = time.monotonic() + max(0, stop_at - time.time())
    try:
        atomic_json(status_path, {"status": "running", "config_sha256": sha(path), "started_at": time.time()})
        log_path = Path(config["log_path"])
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("x") as log:
            child = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            if sys.platform == "darwin":
                caffeinate = subprocess.Popen(["/usr/bin/caffeinate", "-i", "-w", str(child.pid)], start_new_session=True)
            last_watchdog_tick = time.time()
            while child.poll() is None:
                if time.time() >= stop_at or (config["stage"] in GUARDED_STAGES and time.monotonic() >= monotonic_stop):
                    raise Stop("absolute deadline reached")
                if config["stage"] in GUARDED_STAGES and time.time() - last_watchdog_tick > 60:
                    raise Stop("watchdog suspended over 60 seconds; retain interruption without replay")
                last_watchdog_tick = time.time()
                if sha(path) != env["IGR_BROWSER_USE_CONFIG_SHA256"]:
                    raise Stop("configuration changed during pilot")
                time.sleep(1)
            if child.returncode:
                reason = "pilot worker did not complete"
                blocked = json.loads(ledger.read_text()).get("blocked_reason") if ledger.exists() else None
                if blocked == "absolute deadline reached":
                    reason = "absolute deadline reached"
                elif config["stage"] in FRESH_A4_STAGES:
                    reason = worker_stop_reason(config, blocked) or reason
                raise Stop(reason)
        ledger_data = json.loads(ledger.read_text())
        if ledger_data["blocked_reason"] or ledger_data["inflight"]:
            raise Stop("pilot charges or pending requests need reconciliation")
        after = account_snapshot(key)
        # Requests settled at their bound (the continuation and later) count in the upper bound.
        settled = ledger_data.get("settled_usd", 0.0)
        atomic_json(status_path, {"status": "complete", "config_sha256": sha(path),
                                 "charged_usd": ledger_data["charged_usd"], "account_before": before,
                                 "carryover_usd": carryover,
                                 "shared_cost_upper_usd": carryover + ledger_data["charged_usd"] + settled,
                                 **({"settled_usd": settled} if config["stage"] in FRESH_SETTLING_STAGES else {}),
                                 "account_after": after, "completed_at": time.time()})
    except BaseException as error:
        terminate_owned(child)
        reason = str(error) if isinstance(error, Stop) else type(error).__name__
        mark_unfinished(config, reason)
        atomic_json(status_path, {"status": "stopped", "config_sha256": sha(path),
                                 "reason": reason,
                                 "stopped_at": time.time()})
        raise
    finally:
        terminate_owned(child)
        terminate_owned(caffeinate)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.execute:
            execute(args.config)
        else:
            validate_config(args.config)
            print("Offline configuration checks passed; no paid call made. Independent verification and user approval still required.")
    except (Stop, KeyError, ValueError, OSError) as error:
        print(f"STOP: {str(error) if isinstance(error, Stop) else type(error).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
