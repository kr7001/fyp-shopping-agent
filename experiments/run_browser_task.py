#!/usr/bin/env python3
"""Run one openJiuwen browser task and log it.

`playwright_runtime.main` is an interactive REPL. Experiments need one task, one
record, one exit, so this drives the runtime directly and writes a run log to
experiments/runs/ with the model, timing and whatever usage the runtime reports.

Run it against the agent-core virtualenv, and keep the full runtime trace. The
runtime logs every tool call to stdout, which is the only record of what the
agent actually retrieved, so never pipe this through `tail` or the trace is lost:

    cd agent/agent-core
    uv run python ../../experiments/run_browser_task.py "your question" \
        2>&1 | tee ../../experiments/runs/$(date +%Y%m%dT%H%M%S).log
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import pathlib
import time

import requests

from openjiuwen.harness.tools.browser_move.playwright_runtime.config import (
    MISSING_API_KEY_MESSAGE,
    build_runtime_settings,
    load_repo_dotenv,
)
from openjiuwen.harness.tools.browser_move.playwright_runtime.runtime import (
    BrowserAgentRuntime,
)

# The "see everything" arm, applied before the agent is built so the patched tool is the one
# the agent is handed. Off unless IGR_SEE_EVERYTHING is set, and recorded in the run record
# either way, so a run can never be mistaken for the other arm.
import sys as _sys
_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import see_everything as _see

RUNS = pathlib.Path(__file__).resolve().parent / "runs"
OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"


def openrouter_usage_after(before: float | None, attempts: int = 12,
                           pause: float = 2.5) -> float | None:
    """Usage once OpenRouter has settled this run's spend.

    The usage endpoint lags the completion by a few seconds, so reading it
    immediately returns the pre-run figure and the delta comes out as a false
    zero. Poll until it moves, and give up rather than report a zero we do not
    believe.
    """
    if before is None:
        return None
    for _ in range(attempts):
        current = openrouter_usage()
        if current is not None and current > before:
            return current
        time.sleep(pause)
    return None


def openrouter_usage() -> float | None:
    """Cumulative spend on the OpenRouter key, in dollars.

    The runtime does not surface token counts, so cost per run is measured by
    sampling this before and after. Only valid while runs are serial, which they
    are. Returns None when the key is absent or the call fails, so a logging
    problem never takes down a run.
    """
    key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("API_KEY") or "").strip()
    if not key:
        return None
    try:
        response = requests.get(OPENROUTER_KEY_URL,
                                headers={"Authorization": f"Bearer {key}"}, timeout=30)
        response.raise_for_status()
        return float(response.json()["data"]["usage"])
    except Exception:
        return None


def find_usage(payload: object) -> list[dict]:
    """Collect any token-usage dicts anywhere in the result.

    The runtime's result shape is not documented, so rather than guess a path this
    walks the structure and keeps every mapping that looks like usage accounting.
    """
    found = []
    stack = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            keys = {k.lower() for k in node}
            if keys & {"prompt_tokens", "completion_tokens", "total_tokens", "input_tokens"}:
                found.append(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


async def run(args: argparse.Namespace) -> int:
    if not load_repo_dotenv():
        print("warning: no .env loaded")
    settings = build_runtime_settings()
    if not settings.api_key:
        raise SystemExit(MISSING_API_KEY_MESSAGE)

    probe_setting = _see.apply()
    print(f"card probe: {probe_setting}")

    runtime = BrowserAgentRuntime(
        provider=settings.provider,
        api_key=settings.api_key,
        api_base=settings.api_base,
        model_name=settings.model_name,
        mcp_cfg=settings.mcp_cfg,
        guardrails=settings.guardrails,
    )

    print(f"provider={settings.provider} model={settings.model_name}")
    print(f"task: {args.query}\n")

    usage_before = openrouter_usage()
    started = time.time()
    result, error = None, None
    try:
        await runtime.ensure_started()
        result = await runtime.run_browser_task(
            task=args.query, session_id=args.session, timeout_s=args.timeout)
    except Exception as exc:  # noqa: BLE001 - a failed run is still a run worth logging
        error = f"{type(exc).__name__}: {exc}"
    finally:
        elapsed = round(time.time() - started, 1)
        usage_after = openrouter_usage_after(usage_before)
        try:
            await runtime.shutdown()
        except Exception as exc:  # noqa: BLE001
            print(f"shutdown warning: {exc}")

    RUNS.mkdir(parents=True, exist_ok=True)
    if args.out:
        path = pathlib.Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
        path = RUNS / f"{stamp}-{settings.model_name.replace('/', '_')}.json"
    path.write_text(json.dumps({
        "ran_at": dt.datetime.now().isoformat(timespec="seconds"),
        "provider": settings.provider,
        "model": settings.model_name,
        "query": args.query,
        "elapsed_s": elapsed,
        "cost_usd": (None if usage_before is None or usage_after is None
                     else round(usage_after - usage_before, 6)),
        "cost_note": (None if usage_after is not None
                      else "OpenRouter usage did not settle within the poll window"),
        "spend_before_usd": usage_before,
        "spend_after_usd": usage_after,
        "error": error,
        "usage": find_usage(result),
        "result": result,
    }, indent=2, default=str) + "\n")

    cost = (None if usage_before is None or usage_after is None
            else round(usage_after - usage_before, 6))
    print(f"\nelapsed {elapsed}s  cost ${cost}" if cost is not None
          else f"\nelapsed {elapsed}s  cost unavailable")
    print(f"log: {path}")
    if error:
        print(f"FAILED: {error}")
        return 1
    print("\nresult:")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str)[:3000])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("query")
    parser.add_argument("--session", default="smoke")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--out", help="write the run record here instead of a timestamped name")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
