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
            steps.append({"tool": name, "target": target_of(name, function.get("arguments"))})
    return steps


def stats(log_path: pathlib.Path) -> dict:
    messages = final_messages(log_path)
    steps = tool_steps(messages)
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
        "selections": [step["target"] for step in steps
                       if step["tool"] == "browser_select_option"],
        "opened": [step["target"] for step in steps if step["tool"] == "browser_navigate"],
        "steps": steps,
        "sequence": sequence,
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
    return candidates[0] if candidates else None


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
