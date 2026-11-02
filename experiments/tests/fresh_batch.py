"""A synthetic Study A for the fresh-market review and analysis tests (2 November 2026).

Not a test module itself: tests/test_browser_use_fresh_review.py and
tests/test_browser_use_fresh_analysis.py import it. In a temporary folder it writes every file
the stages of a fresh-market Browser Use study leave, shaped as guarded_browser_use.py and
browser_use_transfer.py write them: for each stage its configuration with its verifier's
receipt and the student's approval, the launch claim, the ledger, the status, the schedule, the
slot statuses, the completed list, one record per slot that ran and its conversation files.
Attempt 1's schedule is the runner's own `preview`; a later stage is given the slots the one
before it left never started, and the timeout reruns every primary slot that reached its clock,
with the clock doubled (amendments 3 and 4). The questions, keys and answers are synthetic; no
model, browser or shop is involved.

A slot's kind says what its trial did:

    answered          a committed answer naming its slot's price
    wrong             a committed answer naming another price
    failed            the agent stopped without a final answer, after an ordinary error
    closed            the block refused, so no agent ran (block slots only)
    timeout           no answer when the trial clock ran out; in a later stage the clock
                      cancels a request in flight, settled at its bound
    short             a timeout well before the trial clock: the classification's void
    infra             a failure after an infrastructure error: the classification's void
    interrupted       the guard stopped the slot while it ran; no record, only its calls
    answered-settled  a correct answer after a request the provider left without a response
                      (later stages only)
    void-settled      no answer after such a request: the runner's technical void (later stages)
    answered-error-reply, void-error-reply
                      the same after an executor error reply without usage, settled at its bound
                      from attempt 4 (amendment 6)
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
BOUND = 0.2117632  # every request's reserved bound, at which a request with no response is settled
ANSWERS = ("answered", "wrong", "answered-settled", "answered-error-reply")
# Amendment 6's settlement of an error reply without usage, by the launcher's own label.
ERROR_REPLY = blind.ERROR_REPLY_KIND
STOP_REASON = "pilot worker did not complete"


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
    if kind in ("answered", "answered-settled", "answered-error-reply"):
        # Markup that must stay inert in the reader page.
        return f"The answer is ${price(task):.2f}. Literal </script><img src=x> stays text."
    if kind == "wrong":
        return f"The answer is ${price(task) + 3:.2f}."
    if kind == "failed":
        return "Partial text from the last extraction, not a final answer."
    if kind == "timeout":
        return "Partial text when the clock ran out."
    return None


class Stage:
    """One stage's files, as its launcher and worker leave them. `kinds` holds one kind per slot
    the stage ran, in the order it was given them; every later slot never started."""

    def __init__(self, batch, spec, kinds, given=None, full_path=(), bind=(), before_worker=False,
                 unstarted_reason=None):
        self.batch, self.spec, self.kinds = batch, spec, list(kinds)
        # Why the slots after the last one run never started, when no stop in the slots says so:
        # the worker ending, or for the reruns the deadline-fit check (amendment 4 point 6).
        self.unstarted_reason = unstarted_reason or STOP_REASON
        self.calls = []
        # Each stage's share of Study A's total cap: USD 3 to attempts 1 and 2, USD 10 to attempt 3
        # and USD 15 to the reruns (guarded_browser_use.fresh_shared_cap).
        self.shared_cap = guard.fresh_shared_cap(spec.stage)
        notes, prefix = batch.notes, spec.prefix
        self.results = notes / f"{prefix}.results"
        self.config = {
            **batch.base, "stage": spec.stage, "attempt": spec.attempt,
            "verification_receipt": str(notes / f"{prefix}.verification.json"),
            "approval_record": str(notes / f"{prefix}.approval.json"),
            "ledger_path": str(notes / f"{prefix}.ledger.json"), "status_path": str(notes / f"{prefix}.status.json"),
            "log_path": str(notes / f"{prefix}.log"), "output_dir": str(self.results),
            "cap_usd": self.shared_cap, "shared_cap_usd": self.shared_cap,
            "hashes": {**batch.base["hashes"], **{name: sha(batch.repo / name) for name in bind}}}
        if not spec.primary:
            self.config.update(rerun_slots=[slot["rerun_of"] for slot in given], rerun_clock_s=2 * 2700)
        self.config_path = notes / f"{prefix}-command.json"
        put(self.config_path, self.config)
        self.config_sha = sha(self.config_path)
        if spec is blind.ATTEMPT1:
            self.plan = transfer.preview(self.config)  # the schedule exactly as the worker writes it
        else:
            self.plan = {"study_id": guard.FRESH_BUDGET, "stage": spec.stage, "paid_calls": 0,
                         "attempt": spec.attempt, "batch_id": guard.FRESH_BUDGET,
                         "warning_sha256": blind.text_digest(transfer.COMMON_BRIEFING),
                         "warning": transfer.COMMON_BRIEFING, "slots": given}
        self.slots = self.plan["slots"]
        self.write_launch()
        if before_worker:
            # Stopped before its worker started: with a stopped status, or with the launch claim
            # alone when the launcher refused its balance check before writing any status.
            if before_worker != "claim only":
                put(self.config["status_path"], {"status": "stopped", "config_sha256": self.config_sha,
                                                 "reason": "insufficient balance for pilot cap and reserved credit"})
            self.statuses = {slot["id"]: {"phase": "transfer", "status": "not_started"} for slot in self.slots}
        else:
            self.write(set(full_path))

    def call(self, role, settled=None):
        number = len(self.calls) + 1
        cost = PARSER_USD if role == "parser" else EXECUTOR_USD * (1 + number % 3)
        entry = {"reserved_usd": BOUND, "role": role, "requested_at": 1000.0 + number,
                 "reservation": f"call-{number:05d}", "cost_usd": cost, "generation_id": f"gen-{number}",
                 "provider": "DeepInfra", "usage": {"cost": cost, "prompt_tokens": 900, "completion_tokens": 90},
                 "completed_at": 1000.5 + number, "error": False}
        if settled:
            # As CallBudget.settle_no_response writes a request settled at its bound.
            entry.update(cost_usd=None, generation_id=None, provider=None, usage=None, error=True,
                         error_name="CancelledError" if settled == "trial clock" else "ModelProviderError",
                         settled_usd=BOUND, settlement_kind=settled, settlement=f"synthetic {settled} settlement")
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
        if kind in ("answered-settled", "void-settled"):
            executor.insert(1, self.call("executor", settled="no response"))
        if kind in ("answered-error-reply", "void-error-reply"):
            executor.insert(1, self.call("executor", settled=ERROR_REPLY))
        if kind == "timeout" and self.spec.stage in blind.SETTLING:
            executor.append(self.call("executor", settled="trial clock"))
        costs = [c["cost_usd"] for c in executor]
        clock = slot["clock_s"]
        record = {"scaffold": "browser-use", "browser_use_version": "0.13.14", "answer": answer_for(kind, slot),
                  "outcome": {"answered": "answered", "wrong": "answered", "failed": "failed", "infra": "failed",
                              "timeout": "timeout", "short": "timeout", "interrupted": "answered",
                              "answered-settled": "answered", "void-settled": "failed",
                              "answered-error-reply": "answered", "void-error-reply": "failed"}[kind],
                  "model": self.config["model"], "provider_routing": PROVIDER, "offline_scripted": False,
                  "dropdown_semantics": "native-disabled-state-v1", "evaluate_semantics": "fresh-local-script-scope-v1",
                  "settings": {"start_url": START, **{k: self.config[k] for k in blind.SETTINGS}, "clock_s": clock},
                  "browser_version": "156.0.8078.79", "elapsed_s": clock + 0.4 if kind == "timeout" else 300.0,
                  "trace": {"opened": len(opened), "opened_urls": sorted(opened),
                            "navigation_events": [{"url": START, "status": 200, "main_document": True, "page_id": "1",
                                                   "candidate": False, "product_document": False, "counted": False}]
                            + [{"url": url, "status": 200, "main_document": True, "page_id": "1", "candidate": True,
                                "product_document": True, "counted": True} for url in opened],
                            "blocked_requests": [], "observation_errors": [], "measurement_valid": True},
                  "calls": [{"reservation": c["reservation"], "role": "executor", "cost_usd": c["cost_usd"]} for c in executor],
                  "cost_usd": None if None in costs else sum(costs), "measurement_status": "complete",
                  "script_fetches": {"script_fetched": len(fetched), "script_fetched_urls": sorted(fetched),
                                     "script_events": [{"url": url, "status": 200, "kind": "fetch", "product_document": True}
                                                       for url in fetched], "script_errors": [],
                                     "definition": fetches.DEFINITION, "complete": True}}
        if kind in ("answered", "wrong", "failed", "infra", "interrupted", "answered-settled", "void-settled",
                    "answered-error-reply", "void-error-reply"):
            errors = {"failed": "Maximum steps reached", "infra": "CDP connection closed",
                      "void-settled": "Maximum steps reached", "void-error-reply": "Maximum steps reached"}.get(kind)
            record.update(steps=7 if block else 12, agent_errors=[None] * 3 + ([errors] if errors else []))
        return record

    def conversation(self, slot, named):
        folder = self.results / slot["id"] / "conversation"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "conversation_1.txt").write_text("Step 1: read the results page.\n")
        text = "Step 2: compared the listings.\n"
        if named:
            text += f"Saved the page. Full path: {self.results / slot['id']}/agent-files/report.pdf\n"
        (folder / "conversation_2.txt").write_text(text)

    def write_launch(self):
        notes, prefix = self.batch.notes, self.spec.prefix
        put(notes / f"{prefix}.verification.json", {
            "verdict": "PASS", "verifier": "claude", "independent": True, "head": "synthetic-head",
            "config_sha256": self.config_sha, "command": ["python", "guarded_browser_use.py"], "request_bound_verified": True})
        put(notes / f"{prefix}.approval.json", {"approved": True, "config_sha256": self.config_sha,
                                                "command": ["python", "guarded_browser_use.py"],
                                                "user_message": "synthetic approval"})
        put(notes / f"{prefix}.launch.json", {"study_budget_id": guard.FRESH_BUDGET, "attempt": self.spec.attempt,
                                              "config_sha256": self.config_sha, "launcher_pid": 1, "claimed_at": 1.0})

    def write(self, full_path):
        settling = self.spec.stage in blind.SETTLING
        put(self.results / "schedule.json", self.plan)
        statuses, completed = {}, []
        stop_reason = None
        for index, slot in enumerate(self.slots):
            kind = self.kinds[index] if index < len(self.kinds) and stop_reason is None else None
            if kind is None:
                statuses[slot["id"]] = {"phase": "transfer", "status": "not_started",
                                        "reason": stop_reason or self.unstarted_reason}
                continue
            parser = [self.call("parser")] if slot["condition"] == "block" else []
            if kind == "interrupted":
                (self.results / slot["id"]).mkdir(parents=True)
                put(self.results / (slot["id"] + ".interrupted.json"), self.trial(slot, kind))
                stop_reason = STOP_REASON
                statuses[slot["id"]] = {"phase": "transfer", "status": "interrupted", "reason": stop_reason}
                continue
            start = len(self.calls)
            if kind == "closed":
                assert slot["condition"] == "block", "only the block closes a slot"
                record = {"answer": "The shop does not show that; no plan was made.", "outcome": blind.CLOSED,
                          "cost_usd": 0, "trace": {"opened": 0, "measurement_valid": True}, "elapsed_s": 0}
                box_query = None
            else:
                (self.results / slot["id"]).mkdir(parents=True, exist_ok=True)
                (self.results / slot["id"] / "history.json").write_text("{}")
                self.conversation(slot, index in full_path)
                record = self.trial(slot, kind)
                box_query = f"Synthetic plan for {slot['question']['id']}." if slot["condition"] == "block" else None
            new_calls = parser + self.calls[start:]
            prefix = transfer.COMMON_BRIEFING + "\n\n"
            sent = (prefix + slot["question"]["query"] if slot["condition"] == "baseline"
                    else (prefix + box_query if box_query else None))
            record.update(study_id=guard.FRESH_BUDGET, stage=self.spec.stage, phase="transfer", slot=slot["id"],
                          condition=slot["condition"], repeat=slot["repeat"], task=slot["question"]["id"],
                          question=slot["question"]["query"], sent_query=sent,
                          briefing_sha256=blind.text_digest(transfer.COMMON_BRIEFING), page=self.page(),
                          box=({"reading": None, "query": box_query} if slot["condition"] == "block" else None),
                          calls=[dict(c) for c in new_calls],
                          parse_cost_usd=transfer.charge_total(parser),
                          total_cost_usd=transfer.charge_total(new_calls),
                          elapsed_with_parser_s=record["elapsed_s"] + 2.5, batch_id=guard.FRESH_BUDGET,
                          market=MARKET, config_sha256=self.config_sha, head="synthetic-head")
            if not self.spec.primary:
                record["rerun_of"] = slot["rerun_of"]
            row = {"phase": "transfer", "status": record["outcome"]}
            disposition = None
            if settling:
                # As the runner writes them for the stages that settle a request (browser_use_transfer).
                settled = [c for c in new_calls if "settled_usd" in c]
                clock = [c for c in settled if c["settlement_kind"] == "trial clock"]
                record.update(attempt=self.spec.attempt, no_response_settlements=len(settled) - len(clock),
                              clock_settlements=len(clock), settled_bound_usd=sum(c["settled_usd"] for c in settled))
                if self.spec.stage in guard.FRESH_ERROR_REPLY_STAGES:
                    # Of the no-response settlements, the error replies without usage (amendment 6).
                    record["error_reply_settlements"] = sum(c["settlement_kind"] == ERROR_REPLY for c in settled)
                disposition, reason = transfer.continuation_disposition(record)
                if disposition:
                    record.update(disposition=disposition, disposition_reason=reason)
                    row.update(disposition=disposition, reason=reason)
            put(self.results / (slot["id"] + ".json"), record)
            statuses[slot["id"]] = row
            completed.append(slot["id"])
            if disposition is None:
                try:
                    transfer.validate_pilot_record(record, "transfer")
                except transfer.Stop:
                    stop_reason = STOP_REASON  # the classification stopped the batch
        self.statuses = statuses
        put(self.results / "slot-status.json", {"slots": statuses})
        if completed:
            put(self.results / "completed.json", {"completed": completed, "expected": len(self.slots)})
        charged = sum(c["cost_usd"] for c in self.calls if c["cost_usd"] is not None)
        settled = [c for c in self.calls if "settled_usd" in c]
        ledger = {
            "schema": 1, "charged_usd": charged, "inflight": {}, "calls": self.calls,
            "blocked_reason": None, "start_usage": 100.0, "highwater_usage": 100.0 + charged, "start_remaining": 50.0,
            "minimum_remaining": 50.0 - charged, "account_decreases": 0, "deadline": "2026-11-02T23:59:00+08:00",
            "cap_usd": self.shared_cap, "carryover_usd": 0.0, "prior_unsettled_reserve_usd": 0.0,
            "prior_ledger_files": [], "study_budget_id": guard.FRESH_BUDGET, "attempt": self.spec.attempt,
            "shared_cap_usd": self.shared_cap,
            "legacy_unsettled_reserve_usd": 0.2117632, "minimum_balance_usd": 20.2117632}
        if settling:
            ledger.update(settled_usd=sum(c["settled_usd"] for c in settled),
                          clock_settlements=sum(c["settlement_kind"] == "trial clock" for c in settled),
                          no_response_settlements=sum(c["settlement_kind"] == "no response" for c in settled))
        put(self.config["ledger_path"], ledger)
        if stop_reason is None and len(completed) == len(self.slots):
            put(self.config["status_path"], {"status": "complete", "config_sha256": self.config_sha,
                                             "charged_usd": charged, "carryover_usd": 0, "shared_cost_upper_usd": charged})
        else:
            put(self.config["status_path"], {"status": "stopped", "config_sha256": self.config_sha,
                                             "reason": stop_reason or self.unstarted_reason, "stopped_at": 2.0})

    def files(self):
        """Every file this stage left, as repository paths: what a later stage binds by hash."""
        repo, prefix = self.batch.repo, self.spec.prefix
        names = [f"{prefix}-command.json", f"{prefix}.status.json", f"{prefix}.launch.json", f"{prefix}.ledger.json"]
        found = [self.batch.notes / name for name in names] + sorted(self.results.glob("*.json"))
        return [str(path.relative_to(repo)) for path in found if path.exists()]

    def index(self, slot_id):
        return next(i for i, s in enumerate(self.slots) if s["id"] == slot_id)

    def path(self, index, suffix=".json"):
        return self.results / (self.slots[index]["id"] + suffix)

    def edit(self, index, **changes):
        """Change one saved record, as a fault would."""
        record = json.loads(self.path(index).read_text())
        record.update(changes)
        put(self.path(index), record)
        return record


class Batch(Stage):
    """Attempt 1 of one synthetic study, and through `later` every stage after it. `kinds`
    holds one kind per slot that ran, in schedule order; every later slot never started."""

    def __init__(self, folder, kinds, readings=None, full_path=()):
        self.repo = Path(folder).resolve()
        self.notes = self.repo / "notes"
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
            files={name: sha(self.repo / name) for name in FROZEN}, sheet="synthetic.sheet.csv", pinned={})
        self.base = {
            "version": 1, "repo": str(self.repo), "model": "deepseek/deepseek-v4-flash",
            "provider": PROVIDER, "allowed_served_providers": ["GMICloud", "DeepInfra", "StreamLake"],
            "maximum_input_tokens": 1048576, "max_input_bytes": 200000, "max_output_tokens": 4096,
            "max_steps": 150, "clock_s": 2700, "llm_timeout": 120, "temperature": 0.2,
            "frequency_penalty": 0.1, "top_p": None, "use_vision": False, "browser_executable": "chrome",
            "preflight_browser_version": "156.0.8078.79", "max_failures": 5, "estimate_usd": 1.5,
            "cap_usd": 3.0, "study_budget_id": guard.FRESH_BUDGET,
            "questions_file": str(self.notes / "questions.json"), "questions": self.questions,
            "repeats": [1, 2], "protocol_file": "notes/protocol.md", "analysis_plan_file": "notes/plan.md",
            "tasks_file": TASKS_FILE, "market_files": [MARKET["fixture"], MARKET["search_record"], READINGS_FILE],
            "market": MARKET, "expected_head": "synthetic-head",
            "hashes": {**{name: sha(self.repo / name) for name in FROZEN},
                       **{name: sha(ROOT / name) for name in (
                           "experiments/runners/browser_use_runner.py", "experiments/runners/browser_use_fetches.py",
                           "experiments/runners/browser_use_transfer.py", "experiments/paths.py")}}}
        self.stages = []
        super().__init__(self, blind.ATTEMPT1, kinds, full_path=full_path)
        self.stages.append(self)

    def later(self, spec, kinds, full_path=(), bind=True, before_worker=False, unstarted_reason=None):
        """The next stage: a primary attempt is given the slots the one before it left never
        started; the timeout reruns every primary slot that reached its clock, its clock doubled.
        With `bind`, its configuration binds every earlier stage's files by hash, as the launcher's do."""
        primaries = [stage for stage in self.stages if stage.spec.primary]
        if spec.primary:
            last = primaries[-1]
            given = [slot for slot in last.slots if last.statuses[slot["id"]]["status"] == "not_started"]
        else:
            order = [slot["id"] for slot in self.slots]
            rows = []
            for stage in primaries:
                for slot in stage.slots:
                    path = stage.results / (slot["id"] + ".json")
                    record = json.loads(path.read_text()) if path.exists() else {}
                    if record.get("disposition") == "timeout":
                        rows.append({"slot": slot["id"], "stage": stage.spec.stage, "attempt": stage.spec.attempt,
                                     "record": str(path.relative_to(self.repo)), "record_sha256": sha(path),
                                     "elapsed_s": record["elapsed_s"], "clock_s": record["settings"]["clock_s"]})
            rows.sort(key=lambda row: order.index(row["slot"]))
            by_id = {slot["id"]: slot for slot in self.slots}
            given = [{**by_id[row["slot"]], "clock_s": 2 * 2700, "rerun_of": row} for row in rows]
        bound = [name for stage in self.stages for name in stage.files()] if bind else []
        stage = Stage(self, spec, kinds, given=given, full_path=full_path, bind=bound, before_worker=before_worker,
                      unstarted_reason=unstarted_reason)
        self.stages.append(stage)
        return stage

    def stage_args(self):
        """Every stage, by name, as `prepare` is given them on the command line."""
        return {stage.spec.name: (stage.config_path, stage.config_sha) for stage in self.stages}


def kinds_with(changes, ran=32):
    """Every slot answered, apart from the given changes by slot index; slots from `ran` on
    never started."""
    return [changes.get(i, "answered") for i in range(ran)]


def block_index(batch, task=None, repeat=1):
    """The schedule index of a block slot, the first one or the given question's."""
    return next(i for i, s in enumerate(batch.slots) if s["condition"] == "block" and s["repeat"] == repeat
                and (task is None or s["question"]["id"] == task))
