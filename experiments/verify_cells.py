#!/usr/bin/env python3
"""Re-derive every figure reported for a batch of runs, from the raw records alone.

The suite writes its summary once, as the runs finish, and figures quoted from a batch
have so far come from that summary or from a one-off script. This reads the same runs back
without trusting either. Each answer is re-scored from the record's full text, each listing
count is taken from the log, each cost is re-summed from the provider's own charge for each
completion, and the setting each run was meant to have is checked in what the browser
reported back.

It also replaces one figure that was wrong in kind. "Met the floor" was counted as eight
listings for every gated question, but eight is the floor for the two best-price questions
only. A count over fifteen listings needs all fifteen, and a "does every listing" question
is settled by one counterexample. Each question is now held to its own floor.

    python experiments/verify_cells.py experiments/results/<batch> [...]
    python experiments/verify_cells.py <batches> --answers     # every answer, in full
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score as scoring  # noqa: E402
import sufficiency  # noqa: E402
import trace_stats  # noqa: E402

FIXTURE = HERE.parent / "env" / "fixtures" / "scaled_apparel.json"

# Magento's own 404 page. A listing that was navigated to and answered with this was not
# opened, and the naive scaffold's first runs counted exactly such pages as listings.
NOT_FOUND = re.compile(r"Whoops, our bad|404 Not Found|page you requested was not found",
                       re.IGNORECASE)

# openJiuwen logs a heartbeat about every 30 seconds while a run is alive. A longer silence
# means the process was not running at all, which on 8 October 2026 was the laptop going to
# sleep mid-batch: three runs went silent for 17 to 50 minutes and two of them were then
# failed by the ten minute clock. In every earlier batch the longest silence is 31 seconds.
# A suspended run measures the machine, not the agent, so it is void and is re-run.
SUSPENDED_AFTER_S = 60
STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) \|", re.MULTILINE)


def longest_silence(log: str) -> float:
    """Seconds of the longest gap between consecutive timestamped log lines."""
    stamps = [dt.datetime.strptime(m, "%Y-%m-%d %H:%M:%S") for m in STAMP.findall(log)]
    return max(((b - a).total_seconds() for a, b in zip(stamps, stamps[1:])), default=0.0)


def ground_truth() -> dict:
    """Per listing: seller, the advertised price, and what size M is."""
    spec = json.loads(FIXTURE.read_text())
    out = {}
    for family in spec["families"]:
        variants = {v["option"]: v for v in family["variants"]}
        m = variants.get("M")
        out[family["parent_sku"].lower()] = {
            "seller": family["seller"],
            "from": min(v["price"] for v in family["variants"] if v["qty"] > 0),
            "m": None if m is None else ("buyable" if m["qty"] > 0 else "sold out"),
        }
    return out


def own_floor(task: dict, instance: dict) -> int:
    """The fewest listings any correct method has to open for this question.

    The rule is the question's shape, read with the same patterns the refusal check uses,
    so the floor and the check cannot drift apart.
    """
    question = task["query"]
    if not task["gated"]:
        return 0
    if sufficiency.superlative_over_population(question):
        return instance["oracle_min_opens"]
    if sufficiency.COUNTING_QUESTION.search(question):
        return instance["listings"]
    if sufficiency.UNIVERSAL_QUESTION.search(question):
        return 1
    raise ValueError(f"no floor rule for {task['id']}")


def must_open(task: dict, instance: dict, truth: dict) -> set[str]:
    """The listings this question cannot be answered without, by name rather than number.

    Opening eight listings meets the best-price floor only if they are the right eight:
    every listing whose advertised price is at or below the answer, since none of those
    can be ruled out without opening it. A count needs every listing. A "does every
    listing" question needs any one listing that lacks the size, which is handled
    separately because it is a choice of one from several rather than a fixed set.
    """
    question = task["query"]
    if not task["gated"]:
        return set()
    if sufficiency.superlative_over_population(question):
        best = instance["winner"]["price"]
        return {sku for sku, t in truth.items() if t["from"] <= best}
    if sufficiency.COUNTING_QUESTION.search(question):
        return set(truth)
    return set()


def tool_replies(log_path: pathlib.Path) -> dict[str, tuple[str, str]]:
    """Every tool reply openJiuwen received, in full, keyed by call id.

    The last event's history is not enough on its own, because the runtime trims older
    tool replies to a thousand characters before re-sending them. Every reply is seen
    untrimmed in the event that follows it, so the longest copy of each is the original.
    """
    names: dict[str, str] = {}
    arguments: dict[str, dict] = {}
    replies: dict[str, str] = {}
    for line in log_path.read_text(errors="replace").splitlines():
        start = line.find('{"event_id"')
        if start < 0:
            continue
        try:
            event = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        for message in event.get("messages") or []:
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                names[call.get("id")] = trace_stats.normalise(function.get("name") or "")
                try:
                    arguments[call.get("id")] = json.loads(function.get("arguments") or "{}")
                except (json.JSONDecodeError, TypeError):
                    arguments[call.get("id")] = {}
            if message.get("role") == "tool":
                content = message.get("content")
                content = content if isinstance(content, str) else json.dumps(content)
                key = message.get("tool_call_id")
                if len(content) > len(replies.get(key, "")):
                    replies[key] = content
    return {key: (names.get(key, "?"), text, arguments.get(key) or {})
            for key, text in replies.items()}


def verify_run(record_path: pathlib.Path, task: dict, instance: dict, truth: dict,
               stored: dict) -> dict:
    record = json.loads(record_path.read_text())
    log_path = record_path.with_suffix(".log")
    log = log_path.read_text(errors="replace")
    result = record.get("result") or {}
    answer = str(result.get("final") or "")
    ok = result.get("ok") in (True, "True")
    scaffold = record.get("scaffold")

    if scaffold == "naive":
        observed = log
        probe_flags = collections.Counter()
        agent_set_window = 0
        completions = (record.get("tokens") or {}).get("calls")
        cost_lines = None
        resummed = record.get("cost_reported_usd")
    else:
        replies = tool_replies(log_path)
        observed = "\n".join(text for _, text, _ in replies.values())
        # A window setting the model asked for itself is behaviour, not configuration. On
        # 8 October 2026, told to open everything, the shipped agent passed
        # viewport_only=false itself in 3 of 15 runs, and the first version of this check
        # reported those as a leaked setting. Only a reply whose setting the call did not
        # ask for says anything about how the run was configured.
        probe_flags = collections.Counter(
            f"{tool}:{flag}" for tool, text, args in replies.values()
            if "viewport_only" not in args
            for flag in set(re.findall(r"viewport_only': (True|False)", text)))
        agent_set_window = sum(1 for tool, _, args in replies.values()
                               if tool == "browser_probe_cards" and "viewport_only" in args)
        completions = len(trace_stats.USAGE.findall(log))
        cost_lines = len(trace_stats.COST_FIELD.findall(log))
        resummed = trace_stats.cost_reported(log)

    opened = sufficiency.listings_opened(log)
    opened_seen = sufficiency.listings_opened(observed)
    skus = sorted(key.split(":", 1)[1] for key in opened)
    floor = own_floor(task, instance)
    probe_line = next((line for line in log.splitlines() if line.startswith("card probe:")),
                      None)
    trace = record.get("trace") or {}
    rescored = scoring.score(task, answer, ok)
    without_m = [s for s in skus if truth.get(s, {}).get("m") is None and s in truth]
    needed = must_open(task, instance, truth)
    universal = task["gated"] and not needed

    return {
        "task": task["id"], "gated": task["gated"],
        "repeat": int(record_path.stem.rsplit("-", 1)[1]),
        "answer": answer,
        "stored": stored.get("verdict"), "rescored": rescored["verdict"],
        "why": rescored["why"],
        "answer_matches_suite": answer[:300] == (stored.get("answer") or ""),
        "opened": len(opened), "opened_in_replies": len(opened_seen),
        "skus": skus, "unknown_pages": [s for s in skus if s not in truth],
        "floor": floor, "met_floor": len(opened) >= floor,
        "met_eight": len(opened) >= 8,
        "counterexample_seen": bool(without_m),
        # The strict test: the listings the answer depends on were all opened, or for a
        # "does every listing" question, a listing without the size was.
        "covered": (bool(without_m) if universal else needed <= set(skus)),
        "missed": sorted(needed - set(skus)),
        # Recomputed from the log rather than read from the record, because the record's
        # count predates the fix that counts sizes chosen inside a batch step.
        "selections": (trace.get("selections") or [] if scaffold == "naive"
                       else trace_stats.stats(log_path)["selections"]),
        "tool_calls": trace.get("tool_calls_total"), "actions": trace.get("actions"),
        "cost": record.get("cost_usd"), "cost_resummed": resummed,
        "completions": completions, "cost_lines": cost_lines,
        "spend_before": record.get("spend_before_usd"),
        "spend_after": record.get("spend_after_usd"),
        "error": record.get("error") or result.get("error"),
        "ok": ok,
        "not_found_pages": len(NOT_FOUND.findall(observed)),
        "surcharge_labels": len(sufficiency.DELTA.findall(observed)),
        "probe_line": probe_line, "probe_flags": dict(probe_flags),
        "agent_set_window": agent_set_window,
        "shop": record.get("shop"), "probe": record.get("probe"),
        "scaffold": scaffold, "model": record.get("model"),
        "user_agent": record.get("user_agent"),
        "own_cache": (record_path.parent / "caches" / record_path.stem).is_dir(),
        "longest_silence_s": longest_silence(log),
    }


def verify_batch(batch: pathlib.Path) -> tuple[dict, list[dict]]:
    suite = json.loads((batch / "suite.json").read_text())
    spec = json.loads((HERE / suite["tasks_file"]).read_text())
    tasks = {t["id"]: t for t in spec["tasks"]}
    truth = ground_truth()
    stored = {(row["task"], row["repeat"]): row for row in suite["rows"]}
    runs = []
    for record_path in sorted(batch.glob("*.json")):
        if record_path.name == "suite.json":
            continue
        task_id, repeat = record_path.stem.rsplit("-", 1)
        runs.append(verify_run(record_path, tasks[task_id], spec["_instance"], truth,
                               stored.get((task_id, int(repeat)), {})))
    return suite, runs


def report(batch: pathlib.Path, suite: dict, runs: list[dict], show_answers: bool) -> dict:
    gated = [r for r in runs if r["gated"]]
    control = [r for r in runs if not r["gated"]]
    problems = []

    def problem(text: str) -> None:
        problems.append(text)

    for r in runs:
        tag = f"{r['task']}-{r['repeat']}"
        if r["stored"] != r["rescored"]:
            problem(f"{tag}: stored verdict {r['stored']}, re-scored {r['rescored']}")
        if not r["answer_matches_suite"]:
            problem(f"{tag}: suite row answer differs from the run record")
        if r["opened"] != r["opened_in_replies"]:
            problem(f"{tag}: {r['opened']} listings in the log, "
                    f"{r['opened_in_replies']} in the tool replies")
        if r["unknown_pages"]:
            problem(f"{tag}: opened pages outside the market {r['unknown_pages']}")
        if r["not_found_pages"]:
            problem(f"{tag}: {r['not_found_pages']} not-found pages observed")
        if r["surcharge_labels"]:
            problem(f"{tag}: {r['surcharge_labels']} surcharge labels observed, "
                    f"so this run did not see the gated shop")
        if r["shop"] != "gated":
            problem(f"{tag}: record says shop {r['shop']}")
        if r["cost_lines"] is not None and r["cost_lines"] != r["completions"]:
            problem(f"{tag}: {r['completions']} completions but {r['cost_lines']} charges")
        if r["cost_resummed"] is not None and abs((r["cost"] or 0) - r["cost_resummed"]) > 1e-6:
            problem(f"{tag}: record cost {r['cost']} against re-summed {r['cost_resummed']}")
        if r["longest_silence_s"] > SUSPENDED_AFTER_S:
            problem(f"{tag}: log silent for {r['longest_silence_s']:.0f}s, the run was "
                    f"suspended, so it is void")
        if not r["own_cache"]:
            problem(f"{tag}: no per-run selector cache directory")
        if r["scaffold"] == "naive" and r["user_agent"] != "Mozilla/5.0 IGRGated/1.0":
            problem(f"{tag}: naive run without the gated user agent")
        if r["scaffold"] != "naive":
            want = "True" if r["probe"] == "viewport" else "False"
            wrong = [k for k in r["probe_flags"] if k.startswith("browser_probe_cards:")
                     and not k.endswith(want)]
            if wrong:
                problem(f"{tag}: card probe ran with the wrong window setting")

    def count(rows, key):
        return sum(1 for r in rows if r[key])

    def correct(rows, key):
        return sum(1 for r in rows if r[key] == "correct")

    cost = sum(r["cost"] or 0 for r in runs)
    before = [r["spend_before"] for r in runs if r["spend_before"] is not None]
    print(f"\n=== {batch.name}  scaffold={suite.get('scaffold')}  "
          f"model={suite.get('model')}  draw={suite.get('draw')}")
    print(f"runs {len(runs)}  settings: shop={sorted({r['shop'] for r in runs})} "
          f"probe={sorted({str(r['probe']) for r in runs})} "
          f"probe line={sorted({str(r['probe_line']) for r in runs})}")
    print(f"gated correct   stored {correct(gated, 'stored')} of {len(gated)}, "
          f"re-scored {correct(gated, 'rescored')} of {len(gated)}")
    print(f"control correct stored {correct(control, 'stored')} of {len(control)}, "
          f"re-scored {correct(control, 'rescored')} of {len(control)}")
    print(f"met own floor   {count(gated, 'met_floor')} of {len(gated)}   "
          f"(old measure, eight for every question: {count(gated, 'met_eight')} of "
          f"{len(gated)})")
    print(f"covered         {count(gated, 'covered')} of {len(gated)}   (the listings the "
          f"answer depends on were all opened, or a counterexample was)")
    opened = sorted(r["opened"] for r in gated)
    print(f"listings opened per gated run {opened}, median {statistics.median(opened)}")
    print(f"cost            ${cost:.4f} from the records, "
          f"{len(runs) - sum(1 for r in runs if r['cost'])} runs without a figure")
    if before:
        print(f"account spend   before the first run ${min(before):.4f}")
    print(f"runs with an error: {[(r['task'], r['repeat'], r['error']) for r in runs if r['error']] or 'none'}")
    print("\nper question     own floor  met  covered  correct  opened")
    for task_id in dict.fromkeys(r["task"] for r in runs):
        rows = [r for r in runs if r["task"] == task_id]
        print(f"  {task_id:26} {rows[0]['floor']:>3}  {count(rows, 'met_floor')}/{len(rows)}  "
              f"{count(rows, 'covered')}/{len(rows)}      {correct(rows, 'rescored')}/{len(rows)}"
              f"      {[r['opened'] for r in rows]}")
    print(f"\nproblems found: {len(problems)}")
    for text in problems:
        print(f"  {text}")
    if show_answers:
        print("\nevery answer, in full")
        for r in runs:
            print(f"\n[{r['task']}-{r['repeat']}] {r['rescored']} ({r['why']}), "
                  f"opened {r['opened']} {r['skus'] if r['opened'] < 15 else 'all'}, "
                  f"covered {r['covered']}, selected {len(r['selections'])} "
                  f"{r['selections'][:6]}, ${r['cost']}")
            print("  " + (r["answer"] or "(no answer)").replace("\n", "\n  "))
    return {"batch": batch.name, "runs": runs, "problems": problems, "cost": cost}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batches", nargs="+", type=pathlib.Path)
    parser.add_argument("--answers", action="store_true", help="print every answer in full")
    parser.add_argument("--json", type=pathlib.Path, help="write every run's checks here")
    args = parser.parse_args()
    out = []
    for batch in args.batches:
        suite, runs = verify_batch(batch)
        out.append(report(batch, suite, runs, args.answers))
    if args.json:
        args.json.write_text(json.dumps(out, indent=2, default=str) + "\n")
    return 0 if not any(b["problems"] for b in out) else 1


if __name__ == "__main__":
    raise SystemExit(main())
