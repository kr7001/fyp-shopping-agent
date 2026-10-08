#!/usr/bin/env python3
"""Count what a browser run actually did, from its stdout trace.

The runtime emits no tool-execution events, but every `llm_call_end` carries the
whole conversation so far. The last such record therefore holds the complete
tool-call history, and that is what this reads.

The RQ3 metric is interactions spent per correct answer, so tool calls are split
into actions that change page state and observations that only read it.

    python experiments/trace_stats.py experiments/runs/<stamp>.log
    python experiments/trace_stats.py experiments/runs/*.log --update-json
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

MCP_PREFIX = "mcp_playwright-official_"

# Actions change page state and are what a retrieval policy pays for.
ACTIONS = {
    "browser_click", "browser_select_option", "browser_fill_form", "browser_type",
    "browser_press_key", "browser_drag", "browser_hover", "browser_navigate",
    "browser_navigate_back", "browser_batch_interact", "browser_file_upload",
    "browser_handle_dialog", "browser_custom_action",
}

# Observations only read the page. Cheap individually, but they dominate token cost.
OBSERVATIONS = {
    "browser_snapshot", "browser_take_screenshot", "browser_probe_cards",
    "browser_probe_interactives", "browser_find", "browser_evaluate",
    "browser_wait_for", "browser_console_messages", "browser_network_requests",
    "browser_list_custom_actions", "browser_generate_locator",
}

# The naive loop's four tools, in the same two categories, so one counter serves both
# scaffolds. Its log is a different shape, printed by the loop itself as it runs.
ACTIONS |= {"goto", "select_option"}
OBSERVATIONS |= {"read_page"}
NAIVE_STEP = re.compile(r"^\[tool ([a-z_]+)\] (\{.*\})$", re.MULTILINE)
NAIVE_KEY_ARG = ("url", "label", "answer")

# What a run cost, and how that is worked out. OpenRouter reports the exact charge for every
# completion, caching included, and the runtime prints it, so the honest figure is the sum of
# those. Two other methods are in this repository's history and both are wrong here:
#
#   the account delta   a before and after reading of lifetime spend. It lags, so a run is
#                       charged for the previous run's settling spend. On 7 Oct 2026 a run of
#                       4,158 tokens was billed $0.1936 this way against $0.0060 of its own
#                       tokens, a factor of 32
#   tokens times price  ignores prompt caching, which this agent leans on heavily. The same
#                       run priced at $2.15 from its 2.1 million prompt tokens against the
#                       $0.30 actually charged, because nearly all of them were cache reads
#
# Token counts are still recorded, because they describe the work done rather than its price.
USAGE = re.compile(
    r"CompletionUsage\(completion_tokens=(\d+),\s*prompt_tokens=(\d+),\s*total_tokens=(\d+)")
# Anchored on the field that follows it in the provider's response, because a bare
# `cost=` also matches the runner's own summary line, and matching that made a run look
# as though it had reported a figure it had only echoed.
COST_FIELD = re.compile(r"(?<![\w_])cost=([0-9.]+),\s*is_byok")


def tokens_used(text: str) -> dict:
    """Every completion's token counts, summed."""
    out = {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
    for completion, prompt, total in USAGE.findall(text):
        out["completion"] += int(completion)
        out["prompt"] += int(prompt)
        out["total"] += int(total)
        out["calls"] += 1
    return out


def cost_reported(text: str) -> float | None:
    """What the provider says this run cost, summed over its completions."""
    charges = [float(x) for x in COST_FIELD.findall(text)]
    return round(sum(charges), 6) if charges else None



# The argument that says what an action touched. Tool names alone are not evidence:
# a run of five actions was once described as "open A, select the pack, open B, select
# the pack" when the breakdown held zero selections, and nobody could tell, because the
# record kept only names. Recording the target makes that claim checkable.
# This build of the Playwright MCP names the interaction argument `target`, which is
# either a URL or an accessibility ref, so `element` and `ref` are kept as fallbacks
# rather than assumed.
KEY_ARG = {
    "browser_navigate": ("url", "target"),
    "browser_select_option": ("values", "target", "element"),
    "browser_click": ("target", "element", "ref"),
    "browser_type": ("text", "target", "element"),
    "browser_fill_form": ("fields",),
    "browser_hover": ("target", "element"),
    "browser_press_key": ("key",),
    "browser_find": ("query", "text", "pattern"),
}


def normalise(name: str) -> str:
    return name[len(MCP_PREFIX):] if name.startswith(MCP_PREFIX) else name


def target_of(name: str, raw_arguments) -> str:
    """The one argument worth keeping for this tool, rendered short."""
    if isinstance(raw_arguments, str):
        try:
            arguments = json.loads(raw_arguments or "{}")
        except json.JSONDecodeError:
            return ""
    else:
        arguments = raw_arguments or {}
    if not isinstance(arguments, dict):
        return ""
    for key in KEY_ARG.get(name, ()):
        if key in arguments and arguments[key] not in (None, "", [], {}):
            value = arguments[key]
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            return str(value)[:120]
    return ""


def final_messages(log_path: pathlib.Path) -> list[dict]:
    """The longest conversation seen in the trace, i.e. the last turn's history."""
    best: list[dict] = []
    for line in log_path.read_text(errors="replace").splitlines():
        start = line.find('{"event_id"')
        if start < 0:
            continue
        try:
            event = json.loads(line[start:])
        except json.JSONDecodeError:
            continue
        messages = event.get("messages")
        if isinstance(messages, list) and len(messages) > len(best):
            best = messages
    return best


SELECT_OPS = ("select_option", "select_visible_text")


def batch_ops(raw_arguments) -> list[dict]:
    """The operations inside one `browser_batch_interact` call, as op and target.

    A batch is one tool call that can hold up to 25 steps, and openJiuwen uses it to choose
    sizes as well as to navigate. Counting selections from `browser_select_option` alone
    missed every size chosen inside a batch: 17 of them in cell 2 on 7 October 2026, so a
    run reported as "selected 0" had chosen eleven. The model sometimes sends the step list
    as a JSON string rather than a list, so both are read.
    """
    try:
        arguments = (json.loads(raw_arguments or "{}") if isinstance(raw_arguments, str)
                     else raw_arguments or {})
    except json.JSONDecodeError:
        return []
    steps = arguments.get("steps") if isinstance(arguments, dict) else None
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except json.JSONDecodeError:
            return []
    out = []
    for step in steps if isinstance(steps, list) else []:
        if isinstance(step, str):
            try:
                step = json.loads(step)
            except json.JSONDecodeError:
                continue
        if not isinstance(step, dict):
            continue
        value = next((step[k] for k in ("option_text", "choose_text", "value", "values",
                                        "url", "ref", "selector") if step.get(k)), "")
        target = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        out.append({"op": str(step.get("op") or ""), "target": target[:120]})
    return out


def tool_steps(messages: list[dict]) -> list[dict]:
    """Every tool call in order, with the argument that says what it touched."""
    steps = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            name = function.get("name")
            if not name:
                continue
            name = normalise(name)
            step = {"tool": name, "target": target_of(name, function.get("arguments"))}
            if name == "browser_batch_interact":
                step["batch"] = batch_ops(function.get("arguments"))
            steps.append(step)
    return steps


def selections(steps: list[dict]) -> list[str]:
    """Every option the run chose, in order, whether alone or inside a batch."""
    chosen = []
    for step in steps:
        if step["tool"] in ("browser_select_option", "select_option"):
            chosen.append(step["target"])
        chosen.extend(op["target"] for op in step.get("batch", []) if op["op"] in SELECT_OPS)
    return chosen


def naive_steps(log_path: pathlib.Path) -> list[dict]:
    """The naive loop prints each call as it makes it, so its log is the record.

    Reading it here rather than trusting the runner's own count means a stored naive run
    can be re-examined the same way an openJiuwen one can. Backfilling without this
    silently replaced every naive trace with an empty one, because the openJiuwen parser
    finds no events in a log that has none.
    """
    steps = []
    for name, raw in NAIVE_STEP.findall(log_path.read_text(errors="replace")):
        try:
            arguments = json.loads(raw)
        except json.JSONDecodeError:
            arguments = {}
        target = next((str(arguments[k]) for k in NAIVE_KEY_ARG if arguments.get(k)), "")
        steps.append({"tool": name, "target": target[:120]})
    return steps


def stats(log_path: pathlib.Path) -> dict:
    messages = final_messages(log_path)
    steps = tool_steps(messages)
    if not steps:
        steps = naive_steps(log_path)
    text = log_path.read_text(errors="replace")
    sequence = [step["tool"] for step in steps]
    counts = collections.Counter(sequence)
    actions = sum(n for tool, n in counts.items() if tool in ACTIONS)
    observations = sum(n for tool, n in counts.items() if tool in OBSERVATIONS)
    unclassified = sorted(t for t in counts if t not in ACTIONS and t not in OBSERVATIONS)
    return {
        "tool_calls_total": len(sequence),
        "actions": actions,
        "observations": observations,
        "unclassified_tools": unclassified,
        "assistant_turns": sum(1 for m in messages if m.get("role") == "assistant"),
        "by_tool": dict(counts.most_common()),
        # What the run selected, which is the claim that went unchecked for three weeks.
        "selections": selections(steps),
        "opened": [step["target"] for step in steps
                   if step["tool"] in ("browser_navigate", "goto")],
        "steps": steps,
        "sequence": sequence,
        "tokens": tokens_used(text),
        "cost_reported_usd": cost_reported(text),
    }


def sibling_json(log_path: pathlib.Path) -> pathlib.Path | None:
    """The run record written alongside this log.

    The suite names both files after the task, so an exact stem match is the answer
    whenever there is one. The older single runs are different: the runner names its
    JSON at finish time and the shell names the log at start time, so the stamps differ
    by the run duration, and nearest-later wins. Trying the exact name first matters,
    because on a directory of named runs the timestamp rule matches alphabetically and
    happily writes one run's trace into another run's record.
    """
    exact = log_path.with_suffix(".json")
    if exact.exists():
        return exact
    stem = log_path.stem
    candidates = sorted(p for p in log_path.parent.glob("*.json") if p.stem[:15] >= stem[:15])
    for candidate in candidates:
        # A record that names its own log is the authority on which log is its own. The
        # timestamp rule is a guess for the records that predate that field, and it guessed
        # wrong here: a directory holding two logs and one record had the second log's trace
        # written into the first run's record, and the record's own `log` field said so.
        try:
            named = json.loads(candidate.read_text()).get("log")
        except (OSError, json.JSONDecodeError):
            named = None
        if named and named != log_path.name:
            continue
        return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--update-json", action="store_true",
                        help="write the counts into the matching run record")
    parser.add_argument("--verbose", action="store_true",
                        help="print every step with the page or option it touched")
    args = parser.parse_args()

    for log_path in args.logs:
        result = stats(log_path)
        print(f"{log_path.name}: {result['tool_calls_total']} tool calls "
              f"({result['actions']} actions, {result['observations']} observations), "
              f"{result['assistant_turns']} model turns")
        print("  " + " -> ".join(result["sequence"]) if result["sequence"] else "  (no tool calls)")
        if result["unclassified_tools"]:
            print(f"  unclassified: {result['unclassified_tools']}")
        # Printed rather than buried, so a claim about what the run clicked can be read
        # off the run instead of inferred from the action count.
        print(f"  opened {len(result['opened'])} pages, "
              f"selected {len(result['selections'])} options"
              + (f": {result['selections']}" if result["selections"] else ""))
        if args.verbose:
            for step in result["steps"]:
                print(f"    {step['tool']:28} {step['target']}")

        if args.update_json:
            target = sibling_json(log_path)
            if target is None:
                print("  no matching run record")
                continue
            record = json.loads(target.read_text())
            record["trace"] = result
            record["trace_log"] = log_path.name
            target.write_text(json.dumps(record, indent=2, default=str) + "\n")
            print(f"  updated {target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
