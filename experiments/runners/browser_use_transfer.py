#!/usr/bin/env python3
"""Separate Browser Use transfer study; preparation is free, execution is guarded.

The model sees only a question and rendered search cards. The frozen block, parser
prompt and plans are imported unchanged. No automatic scoring or analysis occurs here.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "tools"))
import paths  # noqa: E402
import box  # noqa: E402
import browser_use_fetches  # noqa: E402  (the fresh market's passive script-fetch listener)
import page as page_module  # noqa: E402
import primitives  # noqa: E402
from guarded_browser_use import CallBudget, Stop, account_snapshot, atomic_json, read_key, sha, validate_config, verify_browser_version, REPEAT_STAGE, REPEAT_BUDGET, REPEAT_STAGES, REPEAT_RECOVERY_STAGE, validate_repeat_recovery  # noqa: E402
# The fresh held-out market of 2 November 2026: the cohort's condition, its own identity.
from guarded_browser_use import FRESH_BUDGET, FRESH_STAGE, GUARDED_STAGES  # noqa: E402
# Its one continuation: attempt 1's unstarted slots only (2 November 2026).
from guarded_browser_use import (FRESH_CONTINUATION_STAGE, FRESH_KEPT_ANSWERED, FRESH_KEPT_INTERRUPTED,  # noqa: E402
                                 FRESH_STAGES, validate_fresh_continuation)

STUDY_ID = "browser-use-transfer-2026-10-31"
ARMS = ("baseline", "block")
TASK_IDS = ("tee-target-price", "tee-cheapest-target", "tee-count-buyable", "tee-exists-under",
            "tee-top-3", "tee-xs-price", "tee-promo-check", "tee-headline")
QUESTION_FIELDS = {"id", "query", "start_url"}
COMMON_BRIEFING = primitives.LABEL_NOTE


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def validate_questions(questions):
    if not questions or len({q["id"] for q in questions}) != len(questions):
        raise ValueError("questions must have distinct IDs")
    for question in questions:
        if set(question) != QUESTION_FIELDS:
            raise ValueError("runtime question may contain only id, query and start_url")
        if not all(isinstance(question[k], str) and question[k] for k in QUESTION_FIELDS):
            raise ValueError("question fields must be nonempty strings")
        parsed = urlparse(question["start_url"])
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("only an explicitly local development/benchmark shop is supported")
        if question["start_url"] not in question["query"]:
            raise ValueError("question must contain its declared start URL")


def schedule(questions, repeats=(1, 2)):
    """Balanced, deterministic paired order. Never selected from outcomes."""
    validate_questions(questions)
    if not repeats or any(type(r) is not int or r < 1 for r in repeats) or len(set(repeats)) != len(repeats):
        raise ValueError("repeat IDs must be unique positive integers")
    rows = []
    for repeat in repeats:
        for i, question in enumerate(questions):
            arms = ARMS if (i + repeat) % 2 else tuple(reversed(ARMS))
            for condition in arms:
                rows.append({"id": f"{question['id']}-r{repeat}-{condition}", "question": question,
                             "condition": condition, "repeat": repeat})
    return rows


def validate_observation(observed):
    if (observed.reader != "rendered" or observed.next_page or not observed.listings
            or observed.total != len(observed.listings) or observed.scope is not None):
        raise ValueError("a complete, unpruned rendered search observation is required")


def build_query(question, condition, observed, call=None):
    """No task key, fixture, grade, correctness or run outcome enters this boundary."""
    validate_questions([question])
    validate_observation(observed)
    if condition not in ARMS:
        raise ValueError("unknown study condition")
    if condition == "baseline":
        return COMMON_BRIEFING + "\n\n" + question["query"], None
    if call is None:
        raise ValueError("block execution requires the guarded model-parser callback")
    # The task subset is explicitly unambiguous; no key-derived scripted reading.
    decision = box.decide(question["query"], observed, reply=None, parser="model", call=call, rate="bound")
    return ((COMMON_BRIEFING + "\n\n" + decision.query) if decision.query else None), decision


def read_observation(config, question):
    """Run the frozen rendered reader directly with the declared Playwright Python."""
    argv = [config["page_python"], str(ROOT / "experiments/box/page.py"), question["start_url"],
            "--reader", "rendered", "--user-agent", page_module.GATED_UA]
    result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise Stop("rendered page reader failed; no model call launched for this slot")
    observed = page_module.from_record(json.loads(result.stdout))
    validate_observation(observed)
    return observed


def preview(config):
    questions = config["questions"]
    if config.get("questions_file"):
        saved = json.loads(Path(config["questions_file"]).read_text())["questions"]
        if saved != questions:
            raise ValueError("runtime questions differ from the hash-bound question file")
    validate_questions(questions)
    if config.get("stage") == "pilot":
        if len(questions) != 2 or config.get("repeats") != [1]:
            raise ValueError("pilot is two questions, two arms, one repeat")
    elif config.get("stage") in REPEAT_STAGES:
        if (tuple(q["id"] for q in questions) != TASK_IDS or config.get("repeats") != [2, 3]
                or config.get("clock_s") != 2700):
            raise ValueError("plain repeats require all eight questions, repeats 2 and 3, and 2700 seconds")
    elif config.get("stage") in FRESH_STAGES:
        if (tuple(q["id"] for q in questions) != TASK_IDS or config.get("repeats") != [1, 2]
                or config.get("clock_s") != 2700):
            raise ValueError("the fresh market requires all eight questions, repeats 1 and 2, and 2700 seconds")
    elif config.get("stage") in {"pilot-recovery", "overnight-transfer", "monitored-transfer"}:
        pilot_clock = 1800 if config["stage"] == "pilot-recovery" else 2700
        expected_ids = ["tee-count-buyable"] if config["stage"] == "monitored-transfer" else ["tee-cheapest-target", "tee-count-buyable"]
        if ([q["id"] for q in questions] != expected_ids or config.get("repeats") != [1]
                or config.get("clock_s") != pilot_clock):
            raise ValueError(f"recovery requires {expected_ids}, both arms, one repeat, with {pilot_clock} seconds per arm")
    else:
        if tuple(q["id"] for q in questions) != TASK_IDS or config.get("repeats") != [1, 2]:
            raise ValueError("formal transfer grid differs from the declared 32 slots")
    slots = schedule(questions, config["repeats"])
    if config["stage"] in {"overnight-transfer", "monitored-transfer"}:
        transfer = config["transfer_questions"]
        saved = json.loads(Path(config["transfer_questions_file"]).read_text())["questions"]
        if (transfer != saved or tuple(q["id"] for q in transfer) != TASK_IDS
                or config.get("transfer_clock_s") != 2700):
            raise ValueError("overnight transfer requires the fixed eight questions and 2700-second limit")
        if config["stage"] == "monitored-transfer":
            slots.reverse()  # Count retains the original pilot's block/baseline order.
        for slot in slots:
            slot.update(id="pilot-" + slot["id"], phase="pilot", clock_s=config["clock_s"])
        for slot in schedule(transfer, (1,)):
            slot.update(id="transfer-" + slot["id"], phase="transfer", clock_s=2700)
            slots.append(slot)
    if config["stage"] in GUARDED_STAGES:
        for slot in slots:
            slot.update(id="transfer-" + slot["id"], phase="transfer", clock_s=2700)
    if config["stage"] == REPEAT_RECOVERY_STAGE:
        remaining = validate_repeat_recovery(config, expected_slots=slots)
        slots = [slot for slot in slots if slot["id"] in remaining]
    continuation = {}
    if config["stage"] == FRESH_CONTINUATION_STAGE:
        # Attempt 1's schedule filtered to the slots it never started, in their order; its four
        # answered slots and its interrupted fifth stay as they are, never replayed.
        remaining = validate_fresh_continuation(config, expected_slots=slots)
        kept = [slot["id"] for slot in slots if slot["id"] not in remaining]
        slots = [slot for slot in slots if slot["id"] in remaining]
        if [slot["id"] for slot in slots] != remaining or len(kept) != FRESH_KEPT_ANSWERED + FRESH_KEPT_INTERRUPTED:
            raise Stop("the continuation's slots are not attempt 1's unstarted ones in their order")
        continuation = {"attempt": 2, "prior_completed_count": FRESH_KEPT_ANSWERED,
                        "prior_interrupted": kept[FRESH_KEPT_ANSWERED:], "original_slot_count": len(kept) + len(slots)}
    fresh = config["stage"] in FRESH_STAGES
    return {"study_id": FRESH_BUDGET if fresh else STUDY_ID, "stage": config["stage"], "paid_calls": 0,
            **({"prior_completed_count": 6, "original_slot_count": 32} if config["stage"] == REPEAT_RECOVERY_STAGE else {}),
            **continuation,
            **({"batch_id": REPEAT_BUDGET} if config["stage"] in REPEAT_STAGES else {}),
            **({"batch_id": FRESH_BUDGET} if fresh else {}),
            "warning_sha256": digest(COMMON_BRIEFING), "warning": COMMON_BRIEFING,
            "slots": slots,
            "block_preview": "The model parser is not called in preview. Its prompt and frozen logic are inspected separately."}


def validate_pilot_record(record, phase="pilot"):
    """Called only after the original record has been saved, including failures."""
    if phase == "transfer":
        if record.get("trace", {}).get("measurement_valid") is not True:
            raise Stop("transfer response measurement failed; no further paid trial permitted")
        if record.get("outcome") not in {"answered", "closed by the block", "failed", "timeout"}:
            raise Stop("unknown transfer outcome; inspect it before continuing")
        if (record.get("outcome") == "answered" and isinstance(record.get("answer"), str) and record["answer"].strip()
                and not record.get("error") and not record.get("error_type")):
            return  # Recovered tool mistakes remain in history but do not filter completed answers.
        if record.get("outcome") == "timeout" and record.get("timeout_kind") != "trial_clock":
            raise Stop("unclassified or infrastructure timeout; inspect it before continuing")
        errors = [record.get("error"), record.get("error_type"), *(record.get("agent_errors") or [])]
        infrastructure = re.compile(r"cdp|websocket|connect|disconnect|network|socket|provider|http|openrouter|rate.limit|timed?\s*out|timeout|(?:browser|target|session).{0,12}closed|apierror", re.I)
        ordinary = re.compile(r"syntaxerror|javascript (?:syntax|execution failed|execution error)|unexpected token|(?:option.{0,30}disabled|disabled.{0,30}option)|stale.?element|stale.{0,20}node|max(?:imum)?[ _-]?steps?|no (?:final )?(?:answer|result)", re.I)
        for error in filter(None, errors):
            # Native evaluate errors append source code, which can contain URLs.
            # Classify the error header, not the explicitly labelled code echo.
            text = re.split(r"\n\s*Validated Code\b", str(error), maxsplit=1)[0]
            absent_node = re.fullmatch(r"Element index -?\d+ not found in browser state", text.strip())
            if infrastructure.search(text) or not (ordinary.search(text) or absent_node):
                raise Stop("infrastructure or unknown agent error; inspect it before continuing")
        return  # Ordinary failures are observations, not grounds for selective replay.
    if record.get("error") or record.get("error_type") or record.get("outcome") not in {"answered", "closed by the block"}:
        raise Stop("pilot slot failed; inspect it before any paid continuation")
    if record.get("trace", {}).get("measurement_valid") is False:
        raise Stop("pilot response measurement failed; inspect it before any paid continuation")


def technical_gate(records, budget_state, expected=4, allow_agent_failures=False):
    """Check operability, without reading answer keys or selecting correct answers."""
    clear = len(records) == expected and not budget_state["blocked_reason"] and not budget_state["inflight"]
    passed = (clear
              and all(r.get("outcome") == "answered" and isinstance(r.get("answer"), str) and r["answer"].strip()
                      and r.get("trace", {}).get("measurement_valid") is True
                      and not r.get("error") and not r.get("error_type")
                      for r in records))
    if allow_agent_failures and clear:
        try:
            for record in records:
                validate_pilot_record(record, "transfer")
            passed = True
        except Stop:
            passed = False
    return {"passed": bool(passed), "kind": "technical_only", "answers": "unscored; await human review",
            "records_checked": len(records)}


def charge_total(calls):
    """The provider's charges summed, or None when one is unknown: in the fresh continuation a
    request settled at its bound has no provider charge (2 November 2026). Every earlier stage
    blocks on an unknown charge before a record is written, so its sums are unchanged."""
    costs = [call["cost_usd"] for call in calls]
    return None if any(cost is None for cost in costs) else sum(costs)


async def execute_study(config_path):
    config = validate_config(config_path, require_approval=True)
    if (not os.environ.get("IGR_BROWSER_USE_GUARD")
            or os.environ.get("IGR_BROWSER_USE_CONFIG_SHA256") != sha(config_path)):
        raise Stop("execute only through the verified spending watchdog")
    plan = preview(config)
    from browser_use_runner import create_llm, close_llm, run_trial, configure_private_runtime
    configure_private_runtime()
    from browser_use.llm.messages import UserMessage
    key = read_key(config["environment_file"])
    budget = CallBudget(config, config["ledger_path"], lambda: account_snapshot(key))
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=False)
    atomic_json(output_dir / "schedule.json", plan)
    statuses = {slot["id"]: {"phase": slot.get("phase", "pilot"), "status": "scheduled"} for slot in plan["slots"]}
    atomic_json(output_dir / "slot-status.json", {"slots": statuses})
    loop = asyncio.get_running_loop()
    completed = []
    pilot_records = []
    pilot_passed = config["stage"] in GUARDED_STAGES  # No new paid diagnostics in the repeat or fresh batch.
    for slot in plan["slots"]:
        verify_browser_version(config)  # Before the parser or executor can make a paid call.
        if slot.get("phase") == "transfer" and not pilot_passed:
            gate = technical_gate(pilot_records, budget.state, expected=2 if config["stage"] == "monitored-transfer" else 4,
                                  allow_agent_failures=config["stage"] == "monitored-transfer")
            atomic_json(output_dir / "development-gate.json", gate)
            if gate.get("passed") is not True:
                raise Stop("development technical gate failed; no transfer trial permitted")
            pilot_passed = True
        statuses[slot["id"]]["status"] = "running"
        atomic_json(output_dir / "slot-status.json", {"slots": statuses})
        observed = await asyncio.to_thread(read_observation, config, slot["question"])
        parser_llm = None
        pending_parser_tasks = set()
        before_calls = len(budget.state["calls"])
        started = time.perf_counter()
        try:
            if slot["condition"] == "block":
                parser_config = {**config, "temperature": 0, "frequency_penalty": None, "top_p": None}
                parser_llm = create_llm(parser_config, budget, key, role="parser")

                async def invoke_parser(prompt):
                    task = asyncio.current_task()
                    pending_parser_tasks.add(task)
                    try:
                        return await parser_llm.ainvoke([UserMessage(content=prompt)])
                    finally:
                        pending_parser_tasks.discard(task)

                def parse(prompt):
                    future = asyncio.run_coroutine_threadsafe(invoke_parser(prompt), loop)
                    try:
                        reply = future.result(timeout=130)
                    except TimeoutError:
                        future.cancel()
                        with budget.lock:
                            budget._block("parser timed out; charge reconciliation required")
                    if not isinstance(reply.completion, str):
                        raise ValueError("model parser returned a nontext completion")
                    return reply.completion
            else:
                parse = None
            query, decision = await asyncio.to_thread(build_query, slot["question"], slot["condition"], observed, parse)
            # A fallback may swallow a parser exception; financial uncertainty must still stop the pilot.
            if budget.state["blocked_reason"] or budget.state["inflight"]:
                raise Stop(budget.state["blocked_reason"] or "parser request remains in flight")
            call_start = len(budget.state["calls"])
            if query is None:
                record = {"answer": decision.refuse or decision.ask, "outcome": "closed by the block",
                          "cost_usd": 0, "trace": {"opened": 0, "measurement_valid": True}, "elapsed_s": 0}
            else:
                trial = {**config, "query": query, "start_url": slot["question"]["start_url"],
                         "clock_s": slot.get("clock_s", config["clock_s"]),
                         "candidate_urls": [item.url for item in observed.listings],
                         "out_dir": str(output_dir / slot["id"])}
                if config["stage"] in FRESH_STAGES:
                    # The same trial, with product pages fetched by script recorded beside it.
                    with browser_use_fetches.recording(sys.modules["browser_use_runner"],
                                                       trial["candidate_urls"]) as fetches:
                        record = await run_trial(trial, budget, api_key=key)
                    record["script_fetches"] = fetches.record()
                else:
                    record = await run_trial(trial, budget, api_key=key)
            if budget.state["blocked_reason"] or budget.state["inflight"]:
                atomic_json(output_dir / f"{slot['id']}.interrupted.json", record)
                raise Stop(budget.state["blocked_reason"] or "request remains in flight")
            new_calls = budget.state["calls"][before_calls:]
            parser_calls = budget.state["calls"][before_calls:call_start]
            record.update(study_id=plan["study_id"], stage=config["stage"], phase=slot.get("phase", "pilot"), slot=slot["id"], condition=slot["condition"],
                          repeat=slot["repeat"], task=slot["question"]["id"], question=slot["question"]["query"],
                          sent_query=query, briefing_sha256=digest(COMMON_BRIEFING), page=observed.record(),
                          box=decision.record() if decision else None, calls=new_calls,
                          parse_cost_usd=charge_total(parser_calls),
                          total_cost_usd=charge_total(new_calls),
                          elapsed_with_parser_s=time.perf_counter() - started)
            if config["stage"] in REPEAT_STAGES:
                record["batch_id"] = REPEAT_BUDGET
            if config["stage"] in FRESH_STAGES:
                # Which market, configuration and commit produced this record.
                record.update(batch_id=FRESH_BUDGET, market=config["market"],
                              config_sha256=os.environ["IGR_BROWSER_USE_CONFIG_SHA256"],
                              head=config["expected_head"])
            if config["stage"] == FRESH_CONTINUATION_STAGE:
                # Which attempt, and the requests settled at their bound, apart from the charges.
                settled = [call for call in new_calls if "settled_usd" in call]
                record.update(attempt=config["attempt"], no_response_settlements=len(settled),
                              settled_bound_usd=sum(call["settled_usd"] for call in settled))
            atomic_json(output_dir / f"{slot['id']}.json", record)
            statuses[slot["id"]]["status"] = record["outcome"]
            atomic_json(output_dir / "slot-status.json", {"slots": statuses})
            if slot.get("phase") == "pilot":
                pilot_records.append(record)
            completed.append(slot["id"])
            atomic_json(output_dir / "completed.json", {"completed": completed, "expected": len(plan["slots"])})
            validate_pilot_record(record, "transfer" if config["stage"] == "monitored-transfer" else slot.get("phase", "pilot"))
        finally:
            pending = list(pending_parser_tasks)
            for task in pending:
                task.cancel()
            if pending:
                try:
                    await asyncio.wait_for(asyncio.gather(*pending, return_exceptions=True), timeout=5)
                except asyncio.TimeoutError:
                    with budget.lock:
                        budget._block("parser cancellation unresolved; charge reconciliation required")
            if parser_llm is not None:
                await close_llm(parser_llm)
    return completed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    try:
        if args.execute:
            asyncio.run(execute_study(args.config))
        else:
            print(json.dumps(preview(json.loads(Path(args.config).read_text())), indent=2))
    except (Stop, ValueError, OSError, KeyError) as error:
        print(f"STOP: {str(error) if isinstance(error, (Stop, ValueError)) else type(error).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
