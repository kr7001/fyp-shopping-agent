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


def normalise(name: str) -> str:
    return name[len(MCP_PREFIX):] if name.startswith(MCP_PREFIX) else name


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


def tool_sequence(messages: list[dict]) -> list[str]:
    """Tool names in the order the model called them."""
    calls = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            name = (call.get("function") or {}).get("name")
            if name:
                calls.append(normalise(name))
    return calls


def stats(log_path: pathlib.Path) -> dict:
    messages = final_messages(log_path)
    sequence = tool_sequence(messages)
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
        "sequence": sequence,
    }


def sibling_json(log_path: pathlib.Path) -> pathlib.Path | None:
    """The run record written alongside this log, matched by nearest timestamp.

    The runner names its JSON at finish time and the shell names the log at start
    time, so the stamps differ by the run duration. Nearest-later wins.
    """
    stem = log_path.stem
    candidates = sorted(p for p in log_path.parent.glob("*.json") if p.stem[:15] >= stem[:15])
    return candidates[0] if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("logs", nargs="+", type=pathlib.Path)
    parser.add_argument("--update-json", action="store_true",
                        help="write the counts into the matching run record")
    args = parser.parse_args()

    for log_path in args.logs:
        result = stats(log_path)
        print(f"{log_path.name}: {result['tool_calls_total']} tool calls "
              f"({result['actions']} actions, {result['observations']} observations), "
              f"{result['assistant_turns']} model turns")
        print("  " + " -> ".join(result["sequence"]) if result["sequence"] else "  (no tool calls)")
        if result["unclassified_tools"]:
            print(f"  unclassified: {result['unclassified_tools']}")

        if args.update_json:
            target = sibling_json(log_path)
            if target is None:
                print("  no matching run record")
                continue
            record = json.loads(target.read_text())
            record["trace"] = {k: v for k, v in result.items() if k != "sequence"}
            record["trace"]["sequence"] = result["sequence"]
            record["trace_log"] = log_path.name
            target.write_text(json.dumps(record, indent=2, default=str) + "\n")
            print(f"  updated {target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
