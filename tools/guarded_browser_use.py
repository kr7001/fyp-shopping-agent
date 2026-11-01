#!/usr/bin/env python3
"""Verified, single-process Browser Use pilot launcher and per-request spending gate.

Validation is free. --execute additionally requires hash-bound independent verification
and recorded user approval. No implicit resume: a spent/uncertain pilot needs a new
reviewed recovery command. The $20 account reserve differs from request reservations.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
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


def account_snapshot(key):
    try:
        data = {}
        for endpoint in ("key", "credits"):
            request = urllib.request.Request(f"https://openrouter.ai/api/v1/{endpoint}",
                                             headers={"Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(request, timeout=6) as response:
                data[endpoint] = json.load(response)["data"]
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
    if shared != 2 or carryover + number(config["cap_usd"]) > shared + 1e-12:
        raise Stop("recovery would exceed the original shared $2 cap")
    unsettled = minimum_carry = inherited_minimum = inherited_unsettled = 0.0
    for prior_path in prior_paths:
        prior = json.loads(prior_path.read_text())
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
    if carryover + 1e-12 < max(minimum_carry, inherited_minimum):
        raise Stop("recovery carryover omits prior charges or unsettled reservations")
    expected_hashes = {name: sha(path) for name, path in zip(names, prior_paths)}
    recorded_hashes = reconciliation.get("prior_ledger_sha256")
    if len(names) == 1 and isinstance(recorded_hashes, str):
        recorded_hashes = {names[0]: recorded_hashes}
    if (recorded_hashes != expected_hashes
            or number(reconciliation.get("carryover_usd")) != carryover):
        raise Stop("recovery reconciliation does not bind the prior ledger and carryover")
    return carryover, max(unsettled, inherited_unsettled)


class CallBudget:
    def __init__(self, config, ledger_path, account_reader, *, clock=time.time):
        self.config = config
        self.path = Path(ledger_path)
        if self.path.exists():
            raise Stop("ledger already exists; implicit resume is forbidden")
        self.account_reader, self.clock = account_reader, clock
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
                    (self.config.get("stage") in REPEAT_STAGES and
                     time.monotonic() >= self.monotonic_deadline - 15)):
                self._block("absolute deadline reached")
            try:
                verify_identity(self.config)
                bound = request_bound(self.config, metadata)
                self._account()
            except Exception as error:
                self._block(str(error) if isinstance(error, Stop) else "account or request validation failed")
            charged = self.state["charged_usd"]
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
                self._block("a request has an unknown charge; reconciliation required")
            self.state["charged_usd"] += charge
            allowed = self.config.get("allowed_served_providers", [])
            if response_json.get("provider") not in allowed:
                self._block("missing or unexpected serving provider; reconciliation required")
            if charge > item["reserved_usd"] + 1e-9:
                self._block("provider charge exceeded the verified request bound")
            self._save()
            if error:
                self._block("request failed; no automatic paid recovery")


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
    if config.get("stage") not in REPEAT_STAGES:
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


def validate_review_receipt(config, receipt, head, digest, command):
    if (receipt.get("verdict") != "PASS" or receipt.get("config_sha256") != digest
            or receipt.get("head") != head or receipt.get("request_bound_verified") is not True):
        raise Stop("independent verification does not bind this command and request bound")
    if config["stage"] in REPEAT_STAGES:
        # The user authorized Codex's final recovery verification and continuation.
        # Identify the actual independent reviewer honestly.
        verifier = "codex-independent" if config["stage"] == REPEAT_RECOVERY_STAGE else "claude"
        if (receipt.get("verifier") != verifier or receipt.get("independent") is not True
                or receipt.get("command") != command
                or (config["stage"] == REPEAT_RECOVERY_STAGE
                    and receipt.get("reviewer_identity") != "browser_transfer_analysis")):
            raise Stop("plain repeats require the designated independent review of the exact command")


def validate_config(path, *, require_approval=False):
    path = Path(path).resolve()
    config = json.loads(path.read_text())
    repo = Path(config["repo"]).resolve()
    if repo != ROOT:
        raise Stop("configuration belongs to another checkout")
    if config.get("stage") not in ({"pilot", REPEAT_STAGE} | RECOVERY_STAGES) or config.get("version") != 1:
        raise Stop("only a separately approved development pilot is supported")
    recovery_limits(config)
    if config["stage"] in REPEAT_STAGES:
        validate_repeat_budget(config)
    if not 0 < number(config["cap_usd"]) <= 2 or number(config["minimum_balance_usd"]) < 20:
        raise Stop("pilot cap must be at most $2 and account reserve at least $20")
    if number(config["estimate_usd"]) > config["cap_usd"]:
        raise Stop("estimate exceeds pilot cap")
    if deadline_epoch(config["deadline"]) <= time.time() + 30:
        raise Stop("deadline leaves no launch window")
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
    if config.get("stage") not in REPEAT_STAGES:
        return
    validate_repeat_budget(config)
    marker = Path(config["ledger_path"]).with_name(f"attempt{config['attempt']}.launch.json")
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise Stop("repeat attempt already claimed; concurrent launch or implicit resume forbidden") from None
    with os.fdopen(descriptor, "w") as handle:
        json.dump({"study_budget_id": REPEAT_BUDGET, "attempt": config["attempt"], "config_sha256": sha(config_path),
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


def execute(path):
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
                if time.time() >= stop_at or (config["stage"] in REPEAT_STAGES and time.monotonic() >= monotonic_stop):
                    raise Stop("absolute deadline reached")
                if config["stage"] in REPEAT_STAGES and time.time() - last_watchdog_tick > 60:
                    raise Stop("watchdog suspended over 60 seconds; retain interruption without replay")
                last_watchdog_tick = time.time()
                if sha(path) != env["IGR_BROWSER_USE_CONFIG_SHA256"]:
                    raise Stop("configuration changed during pilot")
                time.sleep(1)
            if child.returncode:
                reason = "pilot worker did not complete"
                if ledger.exists() and json.loads(ledger.read_text()).get("blocked_reason") == "absolute deadline reached":
                    reason = "absolute deadline reached"
                raise Stop(reason)
        ledger_data = json.loads(ledger.read_text())
        if ledger_data["blocked_reason"] or ledger_data["inflight"]:
            raise Stop("pilot charges or pending requests need reconciliation")
        after = account_snapshot(key)
        atomic_json(status_path, {"status": "complete", "config_sha256": sha(path),
                                 "charged_usd": ledger_data["charged_usd"], "account_before": before,
                                 "carryover_usd": carryover, "shared_cost_upper_usd": carryover + ledger_data["charged_usd"],
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
