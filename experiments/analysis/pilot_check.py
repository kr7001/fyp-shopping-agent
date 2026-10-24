#!/usr/bin/env python3
"""The pilot's gate (24 October 2026): four checks on the pilot's records alone, never on
whether an answer is right, and the smallest fix for any that fails.

The pilot of the morning (handover section 6, command 1) runs twelve questions on the
development market before stage 1 runs on the claim market. Its chain ends by running this,
which writes PASS or FAIL for each rule below, the pilot's cost, the projected stage-1 cost
and a proposed fix, into a summary file the student reads at about 10:40. The pilot is
development only: its results may change limits or caps, never the design or the questions.

Nothing here reads a verdict of correct or wrong, a key or an answer's text: a test plants
flipped verdicts and holds the output unchanged. The rules, fixed here and quoted in the
protocol:

1.  **No harness error and no void.** Every run of every batch the manifest names is put in
    its class by voids.py's rule (`voids.batch_runs`: a log silent over the suspended-run
    limit, no record, a provider or runner error), and none is void; and no run's record
    carries an error other than the step budget's or the clock's markers, which are rule 2's.
    A failure proposes no change of limit or cap: the fault is looked at before stage 1.
2.  **No run at or within 80% of its step or clock limit.** For every run, its tool calls (the
    trace's `tool_calls_total`, the figure the protocol compared with the step limit) are
    under 0.8 times its record's `max_steps`, and its `elapsed_s` under 0.8 times its
    `clock_s`. When any run, open everything's above all, is at or over either, the fix is
    both limits raised for every arm alike: each to the first multiple of 50 steps or 300
    seconds at which the pilot's largest figure is under 80%, and never lowered.
3.  **Every answer to a keyed question keyable.** No row of a keyed question has the verdict
    "unscored", the scorer's word for a run with no key for the reading it answered under.
    The keyless questions, the task file's tasks with no key (`stage_plan.keyless_of`, the
    declines), are excepted; a slot the box closed is not an unscored row. A failure proposes
    no change of limit or cap: the task file's sidecar lacks a key.
4.  **The projected stage-1 cost within the stage-1 cap.** Each question of stage 1's plan
    (`stage_plan.stage1_invocations`, from the analysis file and the claim market's task file)
    is priced by the pilot's mean cost per run for the same arm and the question's kind
    (`stage_plan.kind_of`; a held-out task by its template's kind), the parse's charge
    included. An (arm, kind) the pilot did not run is priced by these rules, in order:
      a. a block arm's headline is priced as its lookup: both read one page;
      b. the block (rules) by the block (model) for the same kind: the same box text, the
         parse's charge aside;
      c. open everything by the dearest kind it measured: its work is every listing,
         whatever the question;
      d. shipped by its mean over every run it measured: its work does not follow the
         question's kind;
      e. anything else is unpriceable, and the check fails saying which pair.
    Added to the plan: the routing gate at what the pilot's own gate probe charged, DeepSeek's
    reading tests at that probe's charge per call times the entries they parse, and Haiku's
    at the 23 October Haiku probe's charge per call (`stage_plan.HAIKU_PROBE`) times the same entries.
    No allowance is made for void re-runs; the chain's cap gate holds them. The development
    market is taken to have the claim market's shape, the same listings over the same pages,
    so nothing is scaled. When the projection is over the cap, the fix proposed is the cap at
    the projection plus 10%, rounded up to the dollar, with what fewer open-everything rounds
    would cost printed beside it; the student decides.

    python3 experiments/analysis/pilot_check.py --manifest experiments/results/<tag>.manifest \\
        --protocol experiments/tasks/claim2_analysis.json --pilot-tasks experiments/tasks/<dev>.json \\
        --stage1-tasks experiments/tasks/<claim>.json --stage1-cap 69 \\
        --reading-files experiments/tasks/paraphrases_v2.json experiments/tasks/<the v3 file>.json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402
import stage_plan  # noqa: E402
import voids  # noqa: E402  (the void rule, one definition)

VERSION = 1
NEAR = 0.8                       # a run at or within this share of a limit fails rule 2
STEP_ROUND, CLOCK_ROUND = 50, 300      # the units a proposed limit is rounded up to
CAP_MARGIN = 1.10                # a proposed cap is the projection plus 10%, to the dollar
# The errors rule 2 reads and rule 1 leaves alone, as voids.py names them.
LIMIT_MARKERS = (voids.BUDGET, "task_timeout")
UNSCORED = "unscored"
ARM_LINE = re.compile(r"\barm=(.*?) round=(\d+)\b")


def manifest_lines(text: str) -> dict:
    """The manifest's batch folders with the arm each line names, its probe result files,
    and the account's usage at the start and the end (None where unwritten)."""
    found = {"batches": [], "probes": [], "start": None, "end": None}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("batch|"):
            _, folder, args = (line.split("|", 2) + [""])[:3]
            named = ARM_LINE.search(args)
            found["batches"].append({"folder": folder.strip(), "arm": named.group(1) if named else None,
                                     "round": int(named.group(2)) if named else None})
        elif line.startswith("probe|"):
            found["probes"].append(line.split("|", 2)[1].strip())
        elif line.startswith("start "):
            found["start"] = amount(line.split()[3])
        elif line.startswith("end "):
            found["end"] = amount(line.split()[3])
    return found


def amount(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


def read_batch(folder: pathlib.Path, name: str | None = None) -> dict | None:
    """A batch's payload and each run's figures: the row's task, repeat, verdict, cost,
    tool calls and elapsed, with the limits its record ran under (the payload's where the
    record has none). `name` is the protocol's arm name from the manifest's line, for the
    report; `arm` the suite's, which prices. None when the folder holds no suite.json."""
    suite = folder / "suite.json"
    if not suite.exists():
        return None
    payload = json.loads(suite.read_text())
    runs = []
    for row in payload.get("rows", []):
        record_path = folder / f"{row['task']}-{row['repeat']}.json"
        record = json.loads(record_path.read_text()) if record_path.exists() else {}
        trace = record.get("trace") or {}
        runs.append({"task": row["task"], "repeat": row["repeat"], "verdict": row.get("verdict"),
                     "cost": row.get("cost_usd"), "error": row.get("error"),
                     "tool_calls": trace.get("tool_calls_total", row.get("tool_calls")),
                     "elapsed": record.get("elapsed_s", row.get("elapsed_s")),
                     "max_steps": record.get("max_steps") or payload.get("max_steps"),
                     "clock_s": record.get("clock_s") or payload.get("clock_s"),
                     "ran": record_path.exists()})
    return {"folder": folder, "arm": payload.get("arm"), "name": name or payload.get("arm"),
            "model": payload.get("model"), "runs": runs}


def check_voids(batches: list[dict]) -> dict:
    """Rule 1."""
    void, errors, total = [], [], 0
    for batch in batches:
        classified = voids.batch_runs(batch["folder"])
        total += len(classified)
        void += [f"{batch['folder'].name}/{run.name}: {run.reason}, {run.why}" for run in classified
                 if run.outcome == voids.VOID]
        for run in batch["runs"]:
            error = str(run["error"] or "")
            if error and not any(error.startswith(marker) for marker in LIMIT_MARKERS):
                errors.append(f"{batch['folder'].name}/{run['task']}-{run['repeat']}: {error[:100]}")
    passed = not void and not errors
    return {"rule": "no harness error and no void", "pass": passed,
            "numbers": f"{total} runs, {len(void)} void, {len(errors)} with a harness error",
            "detail": void + errors,
            "fix": None if passed else "look at the fault before stage 1; this rule proposes no change of limit or cap"}


def check_limits(batches: list[dict]) -> dict:
    """Rule 2."""
    near, most_steps, most_clock, limit_steps, limit_clock = [], 0, 0.0, None, None
    for batch in batches:
        for run in batch["runs"]:
            if not run["ran"]:
                continue
            steps, clock = run["tool_calls"] or 0, float(run["elapsed"] or 0)
            most_steps, most_clock = max(most_steps, steps), max(most_clock, clock)
            limit_steps, limit_clock = run["max_steps"], run["clock_s"]
            over = []
            if run["max_steps"] and steps >= NEAR * run["max_steps"]:
                over.append(f"{steps} of {run['max_steps']} steps")
            if run["clock_s"] and clock >= NEAR * run["clock_s"]:
                over.append(f"{clock:.0f} of {run['clock_s']} s")
            if over:
                near.append(f"{batch['name']} {run['task']}-{run['repeat']}: {', '.join(over)}")
    passed = not near
    fix = None
    if not passed:
        steps_to = max(limit_steps or 0, math.ceil(most_steps / NEAR / STEP_ROUND) * STEP_ROUND)
        clock_to = max(limit_clock or 0, math.ceil(most_clock / NEAR / CLOCK_ROUND) * CLOCK_ROUND)
        fix = (f"raise both limits for every arm alike, to --max-steps {steps_to} --clock {clock_to}, "
               f"the first multiples of {STEP_ROUND} steps and {CLOCK_ROUND} s with the pilot's largest "
               f"figures under {NEAR:.0%}; a new stage-1 command then needs a new dry run and stamp")
    return {"rule": f"no run at or within {NEAR:.0%} of its step or clock limit", "pass": passed,
            "numbers": (f"the most steps {most_steps} of {limit_steps}, the longest {most_clock:.0f} s of "
                        f"{limit_clock}; {len(near)} runs at or within {NEAR:.0%}"),
            "detail": near, "fix": fix}


def check_keyable(batches: list[dict], keyless: set[str]) -> dict:
    """Rule 3."""
    unscored, keyed = [], 0
    for batch in batches:
        for run in batch["runs"]:
            if run["task"] in keyless:
                continue
            keyed += 1
            if run["verdict"] == UNSCORED:
                unscored.append(f"{batch['name']} {run['task']}-{run['repeat']}")
    passed = not unscored
    return {"rule": "every answer to a keyed question keyable", "pass": passed,
            "numbers": f"{len(unscored)} unscored rows among {keyed} on keyed questions; keyless declines excepted",
            "detail": unscored,
            "fix": None if passed else "give the task file's sidecar a key for the reading these runs answered "
                                       "under; this rule proposes no change of limit or cap"}


def measured_means(batches: list[dict], analysis: dict, spec: dict) -> tuple[dict, list[str]]:
    """The pilot's mean cost per run by (suite arm, kind), and the runs whose cost is unknown."""
    sums: dict[tuple[str, str], list[float]] = collections.defaultdict(list)
    unknown = []
    for batch in batches:
        for run in batch["runs"]:
            kind = stage_plan.kind_of(stage_plan.template_of(spec, run["task"]))
            if run["cost"] is None:
                unknown.append(f"{batch['name']} {run['task']}-{run['repeat']}")
                continue
            sums[(batch["arm"], kind)].append(float(run["cost"]))
    return {pair: sum(v) / len(v) for pair, v in sums.items()}, unknown


def price(arm: str, kind: str, means: dict) -> tuple[float | None, str]:
    """A run's price for a suite arm and a kind, by the pilot's mean or rules a to e."""
    if (arm, kind) in means:
        return means[(arm, kind)], "measured"
    if arm in stage_plan.BLOCK_ARMS and kind == "headline" and (arm, "lookup") in means:
        return means[(arm, "lookup")], "a: headline as lookup"
    if arm == "box":
        model_price, how = price("box-model", kind, means)
        if model_price is not None:
            return model_price, f"b: the block (model)'s ({how})"
    if arm == "exhaustive-product":
        mine = [v for (a, _), v in means.items() if a == arm]
        if mine:
            return max(mine), "c: open everything's dearest kind"
    if arm == "none":
        mine = [v for (a, _), v in means.items() if a == arm]
        if mine:
            return sum(mine) / len(mine), "d: shipped's mean"
    return None, "e: unpriceable"


def project(batches: list[dict], analysis: dict, pilot_spec: dict, stage1: dict, model: str, haiku: str,
            cap: float, reading_files: list[pathlib.Path], probe_paths: list[str], chunk: int,
            results: pathlib.Path | None = None) -> dict:
    """Rule 4: the projection, by arm and kind, with its extras and what fewer
    open-everything rounds would cost. `pilot_spec` is the development market's task file,
    by which each pilot run's kind is read; `stage1` the claim market's."""
    means, unknown = measured_means(batches, analysis, pilot_spec)
    by_suite = stage_plan.arms_by_suite_name(analysis)
    invocations = stage_plan.stage1_invocations(analysis, stage1, model, chunk)
    lines, unpriceable, total = [], [], 0.0
    per_arm_round: dict[tuple[str, int], float] = collections.defaultdict(float)
    for inv in invocations:
        arm = stage_plan.suite_arm(analysis, inv.arm)
        for question in inv.questions:
            kind = stage_plan.kind_of(stage_plan.template_of(stage1, question))
            value, how = price(arm, kind, means)
            if value is None:
                unpriceable.append(f"{inv.arm}, {kind} ({question})")
                continue
            total += value
            per_arm_round[(inv.arm, inv.round)] += value
            lines.append((inv.round, inv.arm, question, kind, value, how))
    results = results or paths.RESULTS
    gate_file = next((pathlib.Path(p) for p in probe_paths if pathlib.Path(p).exists()), None)
    gate_charge = json.loads(gate_file.read_text()).get("charged_usd") if gate_file else None
    deepseek_call = stage_plan.probe_charge_per_call(gate_file) if gate_file else None
    deepseek_from = gate_file.name if deepseek_call is not None else stage_plan.DEEPSEEK_PROBE
    if deepseek_call is None:
        deepseek_call = stage_plan.probe_charge_per_call(results / stage_plan.DEEPSEEK_PROBE) or 0.0
        gate_charge = gate_charge if gate_charge is not None else deepseek_call * stage_plan.GATE_PROBE_CALLS
    haiku_call = stage_plan.probe_charge_per_call(results / stage_plan.HAIKU_PROBE) or 0.0
    entries = stage_plan.reading_entries(reading_files, stage_plan.templates_of(stage1))
    extras = {"routing gate": float(gate_charge or 0.0),
              f"reading tests, {model} ({entries} entries at ${deepseek_call:.5f} a call, from {deepseek_from})":
                  entries * deepseek_call,
              f"reading tests, {haiku} ({entries} entries at ${haiku_call:.5f} a call, from {stage_plan.HAIKU_PROBE})":
                  entries * haiku_call}
    projection = total + sum(extras.values())
    oe = by_suite.get("exhaustive-product")
    oe_rounds = sorted({r for (arm, r) in per_arm_round if arm == oe})
    fewer = []
    running = projection
    for r in reversed(oe_rounds):
        running -= per_arm_round[(oe, r)]
        fewer.append((r, running))
    passed = projection < cap and not unpriceable and not unknown
    fix = None
    if not passed:
        if unpriceable or unknown:
            fix = "price the unpriceable pairs by hand before stage 1, or run them in a second pilot"
        else:
            fix = (f"a stage-1 cap of ${math.ceil(projection * CAP_MARGIN):.2f} (the projection plus 10%, to the "
                   f"dollar); or fewer open-everything rounds: " + "; ".join(
                       f"without round {r} ${v:.2f}" for r, v in fewer) + ". The student decides")
    return {"rule": "the projected stage-1 cost within the stage-1 cap", "pass": passed,
            "numbers": f"projected ${projection:.2f} against the cap ${cap:.2f}; runs ${total:.2f} over "
                       f"{len(lines)} questions, extras ${sum(extras.values()):.2f}",
            "detail": [f"unpriceable: {u}" for u in unpriceable] + [f"cost unknown: {u}" for u in unknown],
            "fix": fix, "means": means, "lines": lines, "extras": extras, "projection": projection,
            "fewer": fewer}


def report(checks: list[dict], manifest: pathlib.Path, batches: list[dict], found: dict) -> str:
    """The summary the student reads: each rule PASS or FAIL with its numbers, the pilot's
    cost from the account and from the records, the projection by arm and kind, and the fix."""
    charged = sum(float(r["cost"]) for b in batches for r in b["runs"] if r["cost"] is not None)
    spent = (found["end"] - found["start"]) if found["start"] is not None and found["end"] is not None else None
    runs = sum(len(b["runs"]) for b in batches)
    out = [f"pilot check v{VERSION} of {manifest}: {len(batches)} batches, {runs} runs; the pilot cost "
           f"${charged:.4f} by its records" + (f", ${spent:.4f} by the account" if spent is not None
                                                else ", the account's end figure not yet written")]
    for n, check in enumerate(checks, 1):
        out.append(f"{n} {'PASS' if check['pass'] else 'FAIL'} {check['rule']}: {check['numbers']}")
        out += [f"     {line}" for line in check["detail"]]
        if check["fix"]:
            out.append(f"     fix: {check['fix']}")
    projection = checks[3]
    out.append("the pilot's mean cost per run by arm and kind, which priced stage 1:")
    for (arm, kind), value in sorted(projection["means"].items()):
        out.append(f"     {arm:20} {kind:9} ${value:.4f}")
    by_pair: dict[tuple[str, str, str], list[float]] = collections.defaultdict(list)
    for _, arm, _, kind, value, how in projection["lines"]:
        by_pair[(arm, kind, how)].append(value)
    out.append("stage 1 priced by arm and kind (runs, each, total; how):")
    for (arm, kind, how), values in sorted(by_pair.items()):
        out.append(f"     {arm:28} {kind:9} {len(values):3} x ${values[0]:.4f} = ${sum(values):7.2f}; {how}")
    for name, value in projection["extras"].items():
        out.append(f"     {name}: ${value:.4f}")
    out.append(f"projected stage 1: ${projection['projection']:.2f}")
    verdict = "PASS" if all(c["pass"] for c in checks) else "FAIL"
    out.append(f"verdict: {verdict}" + ("" if verdict == "PASS" else
                                       "; a changed stage-1 command needs a new dry run and stamp before tap 2"))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    parser.add_argument("--protocol", type=pathlib.Path, required=True, help="the analysis file")
    parser.add_argument("--pilot-tasks", type=pathlib.Path, required=True, help="the development market's task file")
    parser.add_argument("--stage1-tasks", type=pathlib.Path, required=True, help="the claim market's task file")
    parser.add_argument("--stage1-cap", type=float, required=True)
    parser.add_argument("--model", default="deepseek/deepseek-v4-flash")
    parser.add_argument("--haiku-model", default="anthropic/claude-haiku-4.5")
    parser.add_argument("--reading-files", type=pathlib.Path, nargs="*", default=[])
    parser.add_argument("--chunk", type=int, default=8, help="a block invocation's most questions, as the stage command")
    args = parser.parse_args(argv)

    analysis = stage_plan.load(args.protocol)
    pilot_spec, stage1 = stage_plan.load(args.pilot_tasks), stage_plan.load(args.stage1_tasks)
    found = manifest_lines(args.manifest.read_text())
    batches = []
    for line in found["batches"]:
        folder = pathlib.Path(line["folder"]) if line["folder"] else None
        batch = read_batch(folder, line["arm"]) if folder and folder.is_dir() else None
        if batch is None:
            # An invocation that wrote no batch is a harness fault rule 1 reports.
            batches.append({"folder": folder or pathlib.Path("(no folder)"), "arm": line["arm"], "name": line["arm"],
                            "runs": [{"task": "(no batch written)", "repeat": 0, "verdict": None, "cost": None,
                                      "error": "the invocation wrote no batch", "tool_calls": None, "elapsed": None,
                                      "max_steps": None, "clock_s": None, "ran": False}], "no_batch": True})
            continue
        batches.append(batch)
    whole = [b for b in batches if not b.get("no_batch")]
    checks = [check_voids(whole), check_limits(whole), check_keyable(whole, stage_plan.keyless_of(pilot_spec)),
              project(whole, analysis, pilot_spec, stage1, args.model, args.haiku_model, args.stage1_cap,
                      args.reading_files, found["probes"], args.chunk)]
    if any(b.get("no_batch") for b in batches):
        checks[0]["pass"] = False
        checks[0]["detail"] += [f"{b['arm']}: the invocation wrote no batch" for b in batches if b.get("no_batch")]
        checks[0]["fix"] = checks[0]["fix"] or "look at the fault before stage 1; this rule proposes no change of limit or cap"
    print(report(checks, args.manifest, whole, found))
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
