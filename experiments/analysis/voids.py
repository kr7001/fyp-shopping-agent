#!/usr/bin/env python3
"""Which runs of a batch are void, and which reported without a correct answer, decided from
the log and the record before any answer is judged against a key.

The claim protocol voids a run whose machine or provider failed, and re-runs it once at the
end; it counts a run that ran out of steps or time, or gave no answer, as not correct, and
excludes nothing else (docs/content/claim-protocol.md, Exclusions). So each run is put in
one of three classes, in this order, and the first that fits wins:

  void                    the log is silent for longer than the suspended-run rule allows
                          (`verify_cells.SUSPENDED_AFTER_S`, reused, not redefined); or the
                          runner wrote no record; or the run has no final completion and
                          a provider or runner error says why: an HTTP error from the
                          provider, an exception in the runner, a runtime failure, or an
                          LLM call error in the log
  reported, not correct   the step budget, the 600 second clock, no answer, an abstention
  answered                everything else, which the scorer then judges

The void decision reads no answer at all, only whether a final exists, so whether a run is
voided cannot depend on whether it was right. The abstention reads the answer the run
reported for hedges, with the scorer's own rule (`score.abstained`), and never a key.

The markers, from the stored records and logs and from the code that writes them (read on
20 October 2026). No batch under experiments/results holds a provider error or a runner
exception, and one, 20260910T000521, holds a log with no record, a batch stopped mid-run;
experiments/runs holds four provider errors and one runtime failure, from 8 September:

  provider    openJiuwen's model client raises `[181001] model call failed, reason: openAI
              API async invoke error: RateLimitError: Error code: 429 - ...` and logs an
              event `"event_type": "llm_call_error"`; its runtime then ends the run with
              `ok` false, an empty final and that text as `result.error`
              (experiments/runs/20260908T215305-deepseek_deepseek-chat.json and three more).
              The second agent writes `"error": "<status> <body>"` and an empty final
              (`naive_agent.py`, when the reply is not a 200)
  runner      `run_browser_task.py` catches an exception as `"error": "<Type>: <message>"`
              and writes no result; the suite writes `runner wrote no record` when no record
              appears; the runtime's own failures are `Browser worker did not return valid
              JSON output` (experiments/runs/20260908T221542-google_gemini-2.5-flash-lite.json,
              with an empty final), `unknown browser execution error`, `restart_failed` and
              `cancelled_by_frontend` (openJiuwen's playwright_runtime/service.py)
  budget      `result.error` `max_iterations_reached` and the final `Max iterations reached
              without completion` (three stored runs); for the second agent an empty final
              after its 100 calls (`naive_agent.STEP_LIMIT`)
  clock       `result.error` `task_timeout: exceeded 600s`, with an empty final (two stored
              runs, both also silent for over 60 seconds, so void by the first rule)

    python3 experiments/analysis/voids.py experiments/results/<batch> [...]
    python3 experiments/analysis/voids.py experiments/results/2026* --all
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import score as scoring  # noqa: E402
import suite  # noqa: E402  (the agent's default limits, one definition)
import trace_stats  # noqa: E402
import verify_cells  # noqa: E402  (the suspended-run rule, one definition)

VOID = "void"
NOT_CORRECT = "reported, not correct"
ANSWERED = "answered"
CLOSED = "closed by the box"        # an ask or a refusal: no agent ran, nothing to classify

# A provider's refusal, as openJiuwen's model client and the OpenAI SDK word it.
PROVIDER = re.compile(r"model call failed|Error code: \d{3}|\b(?:RateLimit|APIStatus|APIConnection|"
                      r"APITimeout|InternalServer|BadRequest|Authentication|PermissionDenied)Error\b")
# The second agent's own record of a reply that was not a 200: the status, then the body.
NAIVE_HTTP = re.compile(r"^\d{3}\b")
# The runtime's own failures, where a run ends on something other than the agent's answer.
RUNTIME = re.compile(r"^(?:Browser worker did not return valid JSON output|unknown browser "
                     r"execution error|restart_failed|cancelled_by_frontend)")
LLM_CALL_ERROR = '"event_type": "llm_call_error"'
NO_RECORD = "runner wrote no record"
BUDGET = "max_iterations_reached"
MAX_ITERATIONS = "max iterations reached without completion"
CLOCK = re.compile(r"^task_timeout\b")
# `naive_agent.STEP_LIMIT`, restated because that module imports Playwright; a test reads
# the runner's own line so the two cannot drift.
NAIVE_STEP_LIMIT = 100

# A run's file name: the task, the repeat, and the policy's second attempt when there was one.
TAG = re.compile(r"^(?P<task>.+?)-(?P<repeat>\d+)(?:-(?P<mode>retry|investigate))?$")


@dataclasses.dataclass(frozen=True)
class Run:
    batch: str
    name: str                   # the run's file name without its suffix
    task: str | None
    repeat: int | None
    outcome: str                # VOID, NOT_CORRECT, ANSWERED or CLOSED
    reason: str                 # which rule: suspended, no record, provider error, ...
    why: str                    # the evidence, quoted from the log or the record
    log_read: bool              # False when the log is not here, so silence went unmeasured


def classify(record: dict | None, log: str | None, reported: str | None = None,
             row: dict | None = None) -> tuple[str, str, str]:
    """(outcome, reason, why) for one run. `log` is its log's text, None when the log is
    not on this machine; `reported` the answer the batch reported, when a policy replaced
    the run's own; `row` its suite.json row, for a run the runner wrote no record of."""
    if log is not None:
        silent = verify_cells.longest_silence(log)
        if silent > verify_cells.SUSPENDED_AFTER_S:
            return (VOID, "suspended", f"the log is silent for {silent:.0f}s, over the "
                                       f"{verify_cells.SUSPENDED_AFTER_S}s suspended-run rule")
    if record is None:
        return VOID, "no record", f"the runner wrote no record ({(row or {}).get('error') or 'no file'})"
    result = record.get("result") if isinstance(record.get("result"), dict) else None
    final = str((result or {}).get("final") or "").strip()
    error = str(record.get("error") or "").strip()
    ended = str((result or {}).get("error") or "").strip()
    calls = log.count(LLM_CALL_ERROR) if log else 0
    if not final:
        if error:
            reason = "provider error" if NAIVE_HTTP.match(error) or PROVIDER.search(error) else "runner error"
            return VOID, reason, f"no final, and the record's error: {error[:160]}"
        if PROVIDER.search(ended):
            return VOID, "provider error", f"no final, and the run ended on: {ended[:160]}"
        if RUNTIME.match(ended):
            return VOID, "runner error", f"no final, and the run ended on: {ended[:160]}"
        if result is None:
            return VOID, "runner error", "the record holds no result at all"
        if calls:
            return (VOID, "provider error", f"no final, and the log holds {calls} LLM call "
                                            f"error{'s' if calls > 1 else ''}; the run ended on: "
                                            f"{ended or 'nothing recorded'}")
    if ended == BUDGET or MAX_ITERATIONS in final.lower():
        return NOT_CORRECT, "step budget", f"{ended or final[:80]}"
    if not final and record.get("scaffold") == "naive" and \
            ((record.get("tokens") or {}).get("calls") or 0) >= NAIVE_STEP_LIMIT:
        return NOT_CORRECT, "step budget", f"no final after {record['tokens']['calls']} calls"
    if CLOCK.match(ended):
        return NOT_CORRECT, "clock", ended
    ok = (result or {}).get("ok") in (True, "True")
    if not ok or not final:
        return (NOT_CORRECT, "no answer", "an empty final" if not final
                else f"ended without ok{': ' + ended[:120] if ended else ''}")
    answer = final if reported is None else reported
    if scoring.abstained(answer):
        return NOT_CORRECT, "abstention", answer[:120]
    return ANSWERED, "", ""


def logs_by_record(folder: pathlib.Path) -> dict[str, pathlib.Path]:
    """Each run record's own log: the record's `log` field, the file of the same name, or,
    for the single runs whose log is named when it starts and the record when it ends,
    `trace_stats.sibling_json`'s rule read backwards."""
    found = {}
    for log in sorted(folder.glob("*.log")):
        record = trace_stats.sibling_json(log)
        if record is not None:
            found.setdefault(record.name, log)
    for record in folder.glob("*.json"):
        try:
            named = json.loads(record.read_text()).get("log")
        except (OSError, json.JSONDecodeError, AttributeError):
            continue
        if named and (folder / named).exists():
            found[record.name] = folder / named
    return found


def batch_runs(folder: pathlib.Path) -> list[Run]:
    """Every run of one batch folder, classified, with the slots the box closed and the
    rows the runner wrote no record for."""
    suite_path = folder / "suite.json"
    payload = json.loads(suite_path.read_text()) if suite_path.exists() else {}
    rows = {(row["task"], row["repeat"]): row for row in payload.get("rows", [])}
    policy = payload.get("policy") or "off"
    logs = logs_by_record(folder)
    runs, recorded = [], set()
    for record_path in sorted(folder.glob("*.json")):
        if record_path.name == "suite.json":
            continue
        try:
            record = json.loads(record_path.read_text())
        except json.JSONDecodeError:
            record = None
        tag = TAG.match(record_path.stem)
        task, repeat = (tag.group("task"), int(tag.group("repeat"))) if tag else (None, None)
        recorded.add((task, repeat))
        row = rows.get((task, repeat))
        log_path = logs.get(record_path.name)
        log = log_path.read_text(errors="replace") if log_path else None
        # Under a policy the row reports the policy's answer, the gate's abstention or the
        # retry's answer, and that is what this run reported unless a later attempt of the
        # same row did the reporting: a first attempt that was retried reported nothing.
        retried = tag is not None and tag.group("mode") is None and any(
            (folder / f"{record_path.stem}-{mode}.json").exists() for mode in ("retry", "investigate"))
        reported = row.get("answer") if row is not None and policy != "off" and not retried else None
        outcome, reason, why = classify(record, log, reported, row)
        runs.append(Run(folder.name, record_path.stem, task, repeat, outcome, reason, why,
                        log is not None))
    # A log with no record of its own name is a run that started and left no record: the
    # runner failed, or the batch was stopped before it finished (20260910T000521 holds
    # one, with no suite.json). Its silence is still measured first.
    for log_path in sorted(folder.glob("*.log")):
        tag = TAG.match(log_path.stem)
        if tag is None or (folder / f"{log_path.stem}.json").exists():
            continue
        task, repeat = tag.group("task"), int(tag.group("repeat"))
        recorded.add((task, repeat))
        outcome, reason, why = classify(None, log_path.read_text(errors="replace"),
                                        row=rows.get((task, repeat)))
        runs.append(Run(folder.name, log_path.stem, task, repeat, outcome, reason, why, True))
    for (task, repeat), row in rows.items():
        if (task, repeat) in recorded:
            continue
        if row.get("verdict") in ("asked", "refused"):
            runs.append(Run(folder.name, f"{task}-{repeat}", task, repeat, CLOSED, row["verdict"],
                            "the box closed the slot and no agent ran", True))
        else:
            outcome, reason, why = classify(None, None, row=row)
            runs.append(Run(folder.name, f"{task}-{repeat}", task, repeat, outcome, reason, why, False))
    return runs


def rerun_flags(folder: pathlib.Path) -> str:
    """The flags a batch ran under, read from its payload and records, for the re-run lines:
    the task file, one repeat, the arm, the reading, the policy and the scaffold."""
    suite_path = folder / "suite.json"
    if not suite_path.exists():
        return "(no suite.json, so the batch's flags are not known)"
    payload = json.loads(suite_path.read_text())
    flags = [f"--tasks experiments/tasks/{payload.get('tasks_file') or '?'}", "--repeats 1"]
    flags += [f"--{name}" for name in ("box", "box-exhaust", "targeting", "exhaustive")
              if payload.get(name.replace("-", "_"))]
    for name in ("reading", "policy", "confidence"):
        if payload.get(name) not in (None, "off"):
            flags.append(f"--{name} {payload[name]}")
    # The parser and its model are part of the arm since 22 October 2026 (box v13), so a
    # re-run of a model-parser run is one too (LESSONS 29). A batch without the field was
    # read by the rules, the default, which needs no flag.
    if payload.get("parser") == "model":
        flags.append("--parser model")
        if payload.get("parser_model"):
            flags.append(f"--parser-model {payload['parser_model']}")
    # How the box read the results pages (box v16). A box batch without the field read the
    # first page over HTTP, which the fetch reader does today, page after page; the rendered
    # reader is the default and needs no flag.
    if (payload.get("box") or payload.get("box_exhaust")) and payload.get("page_reader") != "rendered":
        flags.append("--page-reader fetch")
    # The agent's limits (22 October 2026). A batch without them ran under the defaults,
    # which need no flag, and a naive batch under its loop's own.
    if payload.get("scaffold") != "naive":
        for flag, key, default in (("--max-steps", "max_steps", suite.DEFAULT_MAX_STEPS),
                                   ("--clock", "clock_s", suite.DEFAULT_CLOCK_S)):
            if payload.get(key) not in (None, default):
                flags.append(f"{flag} {payload[key]}")
    if payload.get("scaffold") == "naive":
        flags.append("--scaffold naive")
    probes = {json.loads(p.read_text()).get("probe") for p in folder.glob("*.json") if p.name != "suite.json"}
    if "whole-page" in probes:
        flags.append("--probe whole-page")
    return " ".join(flags)


def report(folder: pathlib.Path, runs: list[Run], every: bool) -> None:
    counts = collections.Counter(run.outcome for run in runs)
    unread = sum(1 for run in runs if not run.log_read and run.outcome != CLOSED)
    print(f"\n=== {folder.name}  {len(runs)} runs: "
          + ", ".join(f"{counts[o]} {o}" for o in (VOID, NOT_CORRECT, ANSWERED, CLOSED) if counts[o]))
    if unread:
        print(f"  {unread} runs have no log here, so their silence was not measured")
    shown = [run for run in runs if every or run.outcome in (VOID, NOT_CORRECT)]
    if shown:
        width = max(len(run.name) for run in shown)
        print(f"  {'run':{width}} {'outcome':22} {'reason':15} why")
        for run in shown:
            print(f"  {run.name:{width}} {run.outcome:22} {run.reason:15} {run.why}")
    voids = [run for run in runs if run.outcome == VOID]
    if voids:
        print(f"  re-run the {len(voids)} void, each with {rerun_flags(folder)}:")
        for run in voids:
            print(f"    --only {run.task} --repeat-start {run.repeat}" if run.repeat is not None
                  else f"    {run.name}: not a task-repeat run, re-run by hand")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batches", nargs="+", type=pathlib.Path)
    parser.add_argument("--all", action="store_true", help="list every run, answered ones too")
    args = parser.parse_args()
    total = collections.Counter()
    reasons = collections.Counter()
    for folder in args.batches:
        if not folder.is_dir():
            continue
        runs = batch_runs(folder)
        report(folder, runs, args.all)
        total.update(run.outcome for run in runs)
        reasons.update(f"{run.outcome}: {run.reason}" for run in runs
                       if run.outcome in (VOID, NOT_CORRECT))
    print(f"\n{sum(total.values())} runs in {len([b for b in args.batches if b.is_dir()])} folders: "
          + ", ".join(f"{total[o]} {o}" for o in (VOID, NOT_CORRECT, ANSWERED, CLOSED) if total[o]))
    for reason, n in sorted(reasons.items()):
        print(f"  {n:4} {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
