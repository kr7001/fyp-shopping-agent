"""A synthetic Study A batch for the fresh-market review and analysis tests (2 November 2026).

Not a test module itself: tests/test_browser_use_fresh_review.py and
tests/test_browser_use_fresh_analysis.py import it. In a temporary folder it writes every file
a fresh-market Browser Use batch leaves, shaped as guarded_browser_use.py and
browser_use_transfer.py write them: the configuration with its verifier's receipt and the
student's approval, the launch claim, the ledger, the status, the schedule from the runner's
own `preview`, the slot statuses, the completed list and one record per slot that ran. The
questions, keys and answers are synthetic; no model, browser or shop is involved.

A slot's kind says what its trial did:

    answered      a committed answer naming its slot's price
    wrong         a committed answer naming another price
    failed        the agent stopped without a final answer, after an ordinary error
    closed        the block refused, so no agent ran (block slots only)
    timeout       no answer when the 2700 s trial clock ran out
    short         a timeout well before the trial clock: the classification's void
    infra         a failure after an infrastructure error: the classification's void
    interrupted   the guard stopped the slot while it ran; no record, only its calls
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402,F401
import browser_use_fetches as fetches  # noqa: E402
import browser_use_fresh_review as blind  # noqa: E402
import browser_use_transfer as transfer  # noqa: E402
import guarded_browser_use as guard  # noqa: E402

SHOP = "http://localhost:7770"
START = f"{SHOP}/catalogsearch/result/?q=Rookmere"
LISTINGS = [f"{SHOP}/igr-syn-{n:02}.html" for n in range(1, 6)]
PROVIDER = {"order": ["gmicloud", "deepinfra", "streamlake"], "allow_fallbacks": False,
            "quantizations": ["fp8"], "max_price": {"prompt": 0.2, "completion": 0.5, "request": 0}}
MARKET = {"fixture": "env/fixtures/synthetic.json", "search_record": "env/manifests/synthetic-search.json",
          "brand": "Rookmere", "sku_prefix": "IGR-SYN", "seed": 9999}
TASKS_FILE, READINGS_FILE = "experiments/tasks/tasks_synthetic.json", "experiments/tasks/readings_synthetic.json"
FROZEN = (TASKS_FILE, READINGS_FILE, MARKET["fixture"], MARKET["search_record"], "notes/protocol.md", "notes/plan.md")
EXECUTOR_USD, PARSER_USD = 0.00125, 0.0005


def price(task_index):
    """Each question's synthetic key, a price no other question shares."""
    return round(10 + 1.25 * task_index, 2)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def answer_for(kind, slot):
    task = transfer.TASK_IDS.index(slot["question"]["id"])
    if kind == "answered":
        # Markup that must stay inert in the reader page.
        return f"The answer is ${price(task):.2f}. Literal </script><img src=x> stays text."
    if kind == "wrong":
        return f"The answer is ${price(task) + 3:.2f}."
    if kind == "failed":
        return "Partial text from the last extraction, not a final answer."
    return None


class Batch:
    """One synthetic batch: `kinds` holds one kind per slot that ran, in schedule order; every
    later slot never started."""

    def __init__(self, folder, kinds, readings=None):
        self.repo = Path(folder).resolve()
        self.notes = self.repo / "notes"
        self.results = self.notes / "study-a.results"
        self.kinds = list(kinds)
        self.calls = []
        tasks = {"base_url": SHOP, "brand": "Rookmere", "tasks": [
            {"id": task, "query": f"Go to {{base}}/catalogsearch/result/?q=Rookmere . Synthetic question {i}: what is the price?",
             "expect": {"kind": "price", "value": price(i)}} for i, task in enumerate(transfer.TASK_IDS)]}
        put(self.repo / TASKS_FILE, tasks)
        keyed = {task["id"]: task["expect"] for task in tasks["tasks"]}
        put(self.repo / READINGS_FILE, readings or {"two_readings": [], "readings": {"buyable": keyed}})
        for name in FROZEN[2:]:
            put(self.repo / name, {"synthetic": name})
        self.questions = guard.runtime_questions(tasks, transfer.TASK_IDS)
        put(self.notes / "questions.json", {"questions": self.questions})
        self.study = dataclasses.replace(
            blind.STUDY_A, market=MARKET, tasks_file=TASKS_FILE, readings_file=READINGS_FILE,
            files={name: sha(self.repo / name) for name in FROZEN}, sheet="synthetic.sheet.csv")
        self.config_path = self.notes / "study-a-command.json"
        self.config = {
            "version": 1, "stage": guard.FRESH_STAGE, "repo": str(self.repo), "model": "deepseek/deepseek-v4-flash",
            "provider": PROVIDER, "allowed_served_providers": ["GMICloud", "DeepInfra", "StreamLake"],
            "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096,
            "max_steps": 150, "clock_s": 2700, "llm_timeout": 120, "temperature": 0.2,
            "frequency_penalty": 0.1, "top_p": None, "use_vision": False, "browser_executable": "chrome",
            "preflight_browser_version": "156.0.8078.79", "max_failures": 5, "estimate_usd": 1.5,
            "cap_usd": 3.0, "study_budget_id": guard.FRESH_BUDGET, "attempt": 1,
            "questions_file": str(self.notes / "questions.json"), "questions": self.questions,
            "repeats": [1, 2], "protocol_file": "notes/protocol.md", "analysis_plan_file": "notes/plan.md",
            "tasks_file": TASKS_FILE, "market_files": [MARKET["fixture"], MARKET["search_record"], READINGS_FILE],
            "market": MARKET, "verification_receipt": str(self.notes / "study-a.verification.json"),
            "approval_record": str(self.notes / "study-a.approval.json"),
            "ledger_path": str(self.notes / "study-a.ledger.json"), "status_path": str(self.notes / "study-a.status.json"),
            "log_path": str(self.notes / "study-a.log"), "output_dir": str(self.results),
            "expected_head": "synthetic-head",
            "hashes": {**{name: sha(self.repo / name) for name in FROZEN},
                       **{name: sha(ROOT / name) for name in (
                           "experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py",
                           "experiments/runners/browser_use_transfer.py", "experiments/paths.py")}}}
        put(self.config_path, self.config)
        self.config_sha = sha(self.config_path)
        self.plan = transfer.preview(self.config)  # the schedule exactly as the worker writes it
        self.slots = self.plan["slots"]
        self.write()

    def call(self, role):
        number = len(self.calls) + 1
        cost = PARSER_USD if role == "parser" else EXECUTOR_USD * (1 + number % 3)
        entry = {"reserved_usd": 0.2117632, "role": role, "requested_at": 1000.0 + number,
                 "reservation": f"call-{number:05d}", "cost_usd": cost, "generation_id": f"gen-{number}",
                 "provider": "DeepInfra", "usage": {"cost": cost, "prompt_tokens": 900, "completion_tokens": 90},
                 "completed_at": 1000.5 + number, "error": False}
        self.calls.append(entry)
        return entry

    def page(self):
        return {"url": START, "count": len(LISTINGS), "total": len(LISTINGS), "next_page": False, "pages": [START],
                "reader": "rendered", "listings": [{"seller": f"Seller {n}", "advertised": 9.0 + n, "url": url,
                                                    "title": "Rookmere tee"} for n, url in enumerate(LISTINGS)]}

    def trial(self, slot, kind):
        """What run_trial returns for one trial, before the worker adds its fields."""
        block = slot["condition"] == "block"
        opened = LISTINGS[:2] if block else LISTINGS[:4]
        fetched = [] if block else [LISTINGS[4]]
        executor = [self.call("executor") for _ in range(2)]
        record = {"scaffold": "browser-use", "browser_use_version": "0.13.14", "answer": answer_for(kind, slot),
                  "outcome": {"answered": "answered", "wrong": "answered", "failed": "failed", "infra": "failed",
                              "timeout": "timeout", "short": "timeout", "interrupted": "answered"}[kind],
                  "model": self.config["model"], "provider_routing": PROVIDER, "offline_scripted": False,
                  "dropdown_semantics": "native-disabled-state-v1", "evaluate_semantics": "fresh-local-script-scope-v1",
                  "settings": {"start_url": START, **{k: self.config[k] for k in blind.SETTINGS}},
                  "browser_version": "156.0.8078.79", "elapsed_s": 2700.4 if kind == "timeout" else 300.0,
                  "trace": {"opened": len(opened), "opened_urls": sorted(opened),
                            "navigation_events": [{"url": START, "status": 200, "main_document": True, "page_id": "1",
                                                   "candidate": False, "product_document": False, "counted": False}]
                            + [{"url": url, "status": 200, "main_document": True, "page_id": "1", "candidate": True,
                                "product_document": True, "counted": True} for url in opened],
                            "blocked_requests": [], "observation_errors": [], "measurement_valid": True},
                  "calls": [{"reservation": c["reservation"], "role": "executor", "cost_usd": c["cost_usd"]} for c in executor],
                  "cost_usd": sum(c["cost_usd"] for c in executor), "measurement_status": "complete",
                  "script_fetches": {"script_fetched": len(fetched), "script_fetched_urls": sorted(fetched),
                                     "script_events": [{"url": url, "status": 200, "kind": "fetch", "product_document": True}
                                                       for url in fetched], "script_errors": [],
                                     "definition": fetches.DEFINITION, "complete": True}}
        if kind in ("answered", "wrong", "failed", "infra", "interrupted"):
            errors = {"failed": "Maximum steps reached", "infra": "CDP connection closed"}.get(kind)
            record.update(steps=7 if block else 12, agent_errors=[None] * 3 + ([errors] if errors else []))
        return record

    def write(self):
        put(self.notes / "study-a.verification.json", {
            "verdict": "PASS", "verifier": "claude", "independent": True, "head": "synthetic-head",
            "config_sha256": self.config_sha, "command": ["python", "guarded_browser_use.py"], "request_bound_verified": True})
        put(self.notes / "study-a.approval.json", {"approved": True, "config_sha256": self.config_sha,
                                                   "command": ["python", "guarded_browser_use.py"],
                                                   "user_message": "synthetic approval"})
        put(self.notes / "study-a.launch.json", {"study_budget_id": guard.FRESH_BUDGET, "attempt": 1,
                                                 "config_sha256": self.config_sha, "launcher_pid": 1, "claimed_at": 1.0})
        put(self.results / "schedule.json", self.plan)
        statuses, completed = {}, []
        stop_reason = None
        for index, slot in enumerate(self.slots):
            kind = self.kinds[index] if index < len(self.kinds) else None
            if kind is None:
                statuses[slot["id"]] = {"phase": "transfer", "status": "not_started",
                                        "reason": stop_reason or "pilot worker did not complete"}
                continue
            parser = [self.call("parser")] if slot["condition"] == "block" else []
            if kind == "interrupted":
                (self.results / slot["id"]).mkdir(parents=True)
                put(self.results / (slot["id"] + ".interrupted.json"), self.trial(slot, kind))
                stop_reason = "pilot worker did not complete"
                statuses[slot["id"]] = {"phase": "transfer", "status": "interrupted", "reason": stop_reason}
                continue
            if kind == "closed":
                assert slot["condition"] == "block", "only the block closes a slot"
                record = {"answer": "The shop does not show that; no plan was made.", "outcome": blind.CLOSED,
                          "cost_usd": 0, "trace": {"opened": 0, "measurement_valid": True}, "elapsed_s": 0}
                box_query = None
            else:
                (self.results / slot["id"]).mkdir(parents=True)
                (self.results / slot["id"] / "history.json").write_text("{}")
                start = len(self.calls)
                record = self.trial(slot, kind)
                assert len(self.calls) == start + 2
                box_query = f"Synthetic plan for {slot['question']['id']}." if slot["condition"] == "block" else None
            new_calls = self.calls[len(self.calls) - len(parser) - (0 if kind == "closed" else 2):]
            prefix = transfer.COMMON_BRIEFING + "\n\n"
            sent = (prefix + slot["question"]["query"] if slot["condition"] == "baseline"
                    else (prefix + box_query if box_query else None))
            record.update(study_id=guard.FRESH_BUDGET, stage=guard.FRESH_STAGE, phase="transfer", slot=slot["id"],
                          condition=slot["condition"], repeat=slot["repeat"], task=slot["question"]["id"],
                          question=slot["question"]["query"], sent_query=sent,
                          briefing_sha256=blind.text_digest(transfer.COMMON_BRIEFING), page=self.page(),
                          box=({"reading": None, "query": box_query} if slot["condition"] == "block" else None),
                          calls=[dict(c) for c in new_calls],
                          parse_cost_usd=sum(c["cost_usd"] for c in new_calls if c["role"] == "parser"),
                          total_cost_usd=sum(c["cost_usd"] for c in new_calls),
                          elapsed_with_parser_s=record["elapsed_s"] + 2.5, batch_id=guard.FRESH_BUDGET,
                          market=MARKET, config_sha256=self.config_sha, head="synthetic-head")
            put(self.results / (slot["id"] + ".json"), record)
            statuses[slot["id"]] = {"phase": "transfer", "status": record["outcome"]}
            completed.append(slot["id"])
            if kind in ("timeout", "short", "infra"):
                stop_reason = "pilot worker did not complete"  # the classification stopped the batch
        put(self.results / "slot-status.json", {"slots": statuses})
        if completed:
            put(self.results / "completed.json", {"completed": completed, "expected": len(self.slots)})
        charged = sum(c["cost_usd"] for c in self.calls)
        put(self.config["ledger_path"], {
            "schema": 1, "charged_usd": charged, "inflight": {}, "calls": self.calls,
            "blocked_reason": None, "start_usage": 100.0, "highwater_usage": 100.0 + charged, "start_remaining": 50.0,
            "minimum_remaining": 50.0 - charged, "account_decreases": 0, "deadline": "2026-11-02T23:59:00+08:00",
            "cap_usd": 3.0, "carryover_usd": 0.0, "prior_unsettled_reserve_usd": 0.0, "prior_ledger_files": [],
            "study_budget_id": guard.FRESH_BUDGET, "attempt": 1, "shared_cap_usd": 3.0,
            "legacy_unsettled_reserve_usd": 0.2117632, "minimum_balance_usd": 20.2117632})
        if stop_reason is None and len(completed) == len(self.slots):
            put(self.config["status_path"], {"status": "complete", "config_sha256": self.config_sha,
                                             "charged_usd": charged, "carryover_usd": 0, "shared_cost_upper_usd": charged})
        else:
            put(self.config["status_path"], {"status": "stopped", "config_sha256": self.config_sha,
                                             "reason": stop_reason or "pilot worker did not complete",
                                             "stopped_at": 2.0})

    def path(self, index, suffix=".json"):
        return self.results / (self.slots[index]["id"] + suffix)

    def edit(self, index, **changes):
        """Change one saved record, as a fault would."""
        record = json.loads(self.path(index).read_text())
        record.update(changes)
        put(self.path(index), record)
        return record


def kinds_with(changes, ran=32):
    """Every slot answered, apart from the given changes by slot index; slots from `ran` on
    never started."""
    return [changes.get(i, "answered") for i in range(ran)]


def block_index(batch, task=None, repeat=1):
    """The schedule index of a block slot, the first one or the given question's."""
    return next(i for i, s in enumerate(batch.slots) if s["condition"] == "block" and s["repeat"] == repeat
                and (task is None or s["question"]["id"] == task))
