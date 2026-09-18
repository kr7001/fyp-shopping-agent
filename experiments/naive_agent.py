#!/usr/bin/env python3
"""A browser agent with no retrieval policy of its own, as the floor to compare against.

Every failure measured so far was produced by one agent, openJiuwen, whose prompt tells it
to use the smallest probe available and whose card probe reads the visible window only. At
1200 x 701 that is one row of four cards, and the agent has no signal that eleven more
listings exist. So "the agent reads the first screen as the whole market" might be a fact
about agents, or it might be a fact about that probe.

This is the control for that question. It drives Playwright directly with four tools and no
advice: go to a URL, read what is on the page, choose an option, answer. There is no probe,
no compaction, no instruction about how much to look, and nothing that reports a candidate
count. If the model still stops at the first screen here, the behaviour belongs to the model
rather than to the scaffold. If it paginates, the finding narrows to openJiuwen's default,
which is a weaker claim and worth knowing.

The prediction, recorded before the first run: the second model already opened 7 to 10
listings inside openJiuwen where the first opened 4, so the habit is not the probe alone.
The naive loop should therefore under-retrieve less than openJiuwen does and still fail on
the questions whose answer sits outside the first screen.

Deliberately matched to the openJiuwen runs so the two are comparable:

- the same model, through the same account, priced the same way
- the same step budget, 100 tool calls
- the same viewport, 1200 x 701, so "the first screen" means the same thing
- every tool result is prefixed with `Page URL:`, which is what the listing counter reads,
  so coverage is measured by the same code for both scaffolds

    python experiments/naive_agent.py "Go to http://localhost:7770/... and answer X" --out run.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import time

import requests
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
RUNS = HERE / "runs"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
USAGE = "https://openrouter.ai/api/v1/key"

STEP_LIMIT = 100
VIEWPORT = {"width": 1200, "height": 701}
# Page text is the whole observation here, and an unbounded one would cost more per step
# than openJiuwen's compacted snapshot, which would confound cost with scaffold. This is
# generous enough to hold a full search page of fifteen cards.
PAGE_LIMIT = 7000
# Enough for a full search page of fifteen cards plus the site's own navigation.
LINK_LIMIT = 80

SYSTEM = """You are answering a question about an online shop by browsing it.

You have four tools. Use them as you see fit. Nothing here tells you how much to look,
because how much to look is your decision.

When you have the answer, call finish with it. If you cannot determine the answer, say so
in the finish call rather than guessing."""

TOOLS = [
    {"type": "function", "function": {
        "name": "goto", "description": "Navigate to a URL and return the page text.",
        "parameters": {"type": "object", "properties": {"url": {"type": "string"}},
                       "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "read_page", "description": "Return the text of the current page.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "select_option",
        "description": "Choose a value in a dropdown on the current page, then return the "
                       "page text. Use the option's visible label.",
        "parameters": {"type": "object", "properties": {"label": {"type": "string"}},
                       "required": ["label"]}}},
    {"type": "function", "function": {
        "name": "finish", "description": "Give the final answer.",
        "parameters": {"type": "object", "properties": {"answer": {"type": "string"}},
                       "required": ["answer"]}}},
]


def load_env(name: str, default: str = "") -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.split("=", 1)[1].strip()
    return os.getenv(name, default)


def usage(key: str) -> float | None:
    try:
        got = requests.get(USAGE, headers={"Authorization": f"Bearer {key}"}, timeout=20)
        return float(got.json()["data"]["usage"])
    except Exception:
        return None


def usage_after(key: str, before: float | None, attempts: int = 12,
                pause: float = 2.5) -> float | None:
    """Usage once the account has settled this run's spend.

    The endpoint lags the completion by a few seconds, so reading it straight away returns
    the pre-run figure and the delta comes out as a false zero. Poll until it moves, and
    report nothing rather than a zero that is not believed. Same approach as the openJiuwen
    runner, so the two scaffolds' costs are measured the same way.
    """
    if before is None:
        return None
    for _ in range(attempts):
        current = usage(key)
        if current is not None and current > before:
            return current
        time.sleep(pause)
    return None


def page_text(page) -> str:
    """What is on the page, where the browser is, and what can be clicked from here.

    The URL prefix is not decoration. `sufficiency.listings_opened` reads `Page URL:` lines
    to count which listings a run actually opened, and that is the one measure meant to
    survive a change of scaffold. Emitting it here means both scaffolds are counted by the
    same code rather than by two counters that might disagree.

    The links are not an affordance this scaffold is being generous with. Without them the
    agent cannot browse at all: the first version returned visible text only, and the model
    spent its whole budget guessing addresses, trying /p/, /catalog/ and /store/ prefixes
    for a product it could see the name of. Every browser agent can see where a link goes,
    so withholding that measures the harness rather than the model. What is still withheld
    is any hint about how much to look, which is the thing under test.
    """
    try:
        body = page.inner_text("body")
    except Exception as error:  # a navigation mid-read, or a page with no body yet
        body = f"(could not read the page: {error})"
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if len(body) > PAGE_LIMIT:
        body = body[:PAGE_LIMIT] + f"\n... (page text truncated at {PAGE_LIMIT} characters)"

    try:
        anchors = page.eval_on_selector_all(
            "a[href]",
            "els => els.map(e => [e.innerText.trim().replace(/\\s+/g, ' ').slice(0, 70),"
            " e.href]).filter(([t, h]) => t && h.startsWith('http'))")
    except Exception:
        anchors = []
    seen, links = set(), []
    for label, href in anchors:
        if href in seen:
            continue
        seen.add(href)
        links.append(f"{label} -> {href}")
        if len(links) >= LINK_LIMIT:
            break
    listed = "\n".join(links) if links else "(no links on this page)"

    # Which options can be chosen, which is not in the page's text at all. A sold out size
    # renders as a disabled option, and `innerText` prints it exactly like an available one,
    # so without this the naive loop is structurally blind to availability while openJiuwen
    # reads `[disabled]` straight out of the accessibility tree. That would confound the
    # scaffold with what the scaffold can perceive. This is the same fact a screen reader
    # gets, stated in text, and it withholds nothing the other scaffold has.
    try:
        menus = page.eval_on_selector_all("select", """
            els => els.map(e => {
              const label = e.id ? document.querySelector('label[for="' + e.id + '"]') : null;
              const name = (label && label.textContent.trim())
                || e.getAttribute('aria-label') || e.name || 'options';
              const values = Array.from(e.options).map(
                o => o.textContent.trim() + (o.disabled && o.value ? ' [unavailable]' : ''));
              return [name, values];
            })""")
    except Exception:
        menus = []
    options = "\n".join(f"{name}: " + ", ".join(values)
                        for name, values in menus if len(values) > 1)
    menu_text = f"\n\nSelectable options:\n{options}" if options else ""

    return (f"Page URL: {page.url}\n\n{body}{menu_text}"
            f"\n\nLinks on this page:\n{listed}")


def act(page, name: str, args: dict) -> str:
    if name == "goto":
        page.goto(args["url"], wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(700)
        return page_text(page)
    if name == "read_page":
        return page_text(page)
    if name == "select_option":
        label = args.get("label", "")
        try:
            page.select_option(".super-attribute-select", label=label, timeout=8000)
        except Exception:
            try:
                page.select_option("select", label=label, timeout=8000)
            except Exception as error:
                return f"Could not select {label!r}: {error}\n\n{page_text(page)}"
        page.wait_for_timeout(900)
        return page_text(page)
    return f"unknown tool {name}"


def run(task: str, model: str, key: str, user_agent: str | None = None) -> dict:
    started = time.time()
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": task}]
    # Name and target together, the same shape `trace_stats` now records for openJiuwen,
    # so a claim about what either scaffold clicked can be checked rather than inferred.
    steps: list[dict] = []
    calls: list[str] = []
    answer, error = "", None

    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        # The shop decides which theme to serve from the user agent, so this is how the
        # naive loop meets the same shop openJiuwen does. Without it the two scaffolds are
        # not measuring the same page, and nothing in either record would have said so.
        context = browser.new_context(viewport=VIEWPORT,
                                      **({"user_agent": user_agent} if user_agent else {}))
        page = context.new_page()
        for _ in range(STEP_LIMIT):
            reply = requests.post(
                ENDPOINT,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "messages": messages, "tools": TOOLS,
                      "temperature": 0},
                timeout=180,
            )
            if reply.status_code != 200:
                error = f"{reply.status_code} {reply.text[:200]}"
                break
            choice = reply.json()["choices"][0]["message"]
            messages.append(choice)
            wanted = choice.get("tool_calls") or []
            if not wanted:
                answer = choice.get("content") or ""
                break
            for call in wanted:
                name = call["function"]["name"]
                try:
                    args = json.loads(call["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append(name)
                steps.append({"tool": name,
                              "target": str(args.get("url") or args.get("label")
                                            or args.get("answer") or "")[:120]})
                if name == "finish":
                    answer = args.get("answer", "")
                    # Printed like every other call so the log is a complete record. Without
                    # this the log held one fewer call than the runner counted, and a trace
                    # recomputed from the log disagreed with the one written during the run.
                    print(f"[tool {name}] {json.dumps(args)}\n", flush=True)
                    break
                observation = act(page, name, args)
                # Printed as well as kept, because the suite captures stdout as the run's
                # log and the sufficiency rules read that log to see what the run observed.
                # Both scaffolds are then judged from the same kind of record.
                print(f"[tool {name}] {json.dumps(args)}\n{observation}\n", flush=True)
                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": observation})
            if answer:
                break
        browser.close()

    # Counted the same way `trace_stats` counts openJiuwen, so the two are comparable: an
    # action changes the page, an observation only reads it.
    actions = sum(1 for c in calls if c in ("goto", "select_option"))
    return {
        "task": task, "model": model, "scaffold": "naive",
        "user_agent": user_agent,
        "elapsed_s": round(time.time() - started, 1),
        "result": {"final": answer, "ok": bool(answer) and error is None},
        "error": error,
        "trace": {"tool_calls_total": len(calls), "actions": actions,
                  "observations": sum(1 for c in calls if c == "read_page"),
                  "by_tool": {name: calls.count(name) for name in set(calls)},
                  "selections": [s["target"] for s in steps if s["tool"] == "select_option"],
                  "opened": [s["target"] for s in steps if s["tool"] == "goto"],
                  "steps": steps,
                  "sequence": calls},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("task")
    parser.add_argument("--out", type=pathlib.Path)
    parser.add_argument("--model", default=None)
    parser.add_argument("--user-agent", default=None,
                        help="what the browser reports. The gated theme is selected by it")
    args = parser.parse_args()

    key = load_env("OPENROUTER_API_KEY")
    model = args.model or load_env("MODEL_NAME", "anthropic/claude-haiku-4.5")
    if not key:
        print("no OPENROUTER_API_KEY in .env")
        return 1

    before = usage(key)
    record = run(args.task, model, key, user_agent=args.user_agent)
    after = usage_after(key, before)
    record["cost_usd"] = (round(after - before, 6)
                          if before is not None and after is not None else None)

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out = args.out or RUNS / f"{stamp}-naive-{model.replace('/', '_')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2, default=str) + "\n")
    print(f"{record['result']['final'][:160]}")
    print(f"calls={record['trace']['tool_calls_total']} "
          f"actions={record['trace']['actions']} cost={record['cost_usd']} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
