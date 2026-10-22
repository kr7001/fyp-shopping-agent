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

    python experiments/analysis/verify_cells.py experiments/results/<batch> [...]
    python experiments/analysis/verify_cells.py <batches> --answers     # every answer, in full
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import datetime as dt
import json
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import form as form_module  # noqa: E402  (the box's parser: the floor reads the question with it)
import score as scoring  # noqa: E402
import sufficiency  # noqa: E402
import suite as suite_module  # noqa: E402  (for box_counts, the one rule for the box's counts)
import trace_stats  # noqa: E402

FIXTURE = paths.FIXTURES / "scaled_apparel.json"

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


def ground_truth(fixture: pathlib.Path = FIXTURE) -> dict:
    """Per listing: seller, the advertised price, what size M is, and every size's price,
    with `buyable` holding only the sizes that can be bought (the generator's
    `price_for` and `buyable_price_for`, which a test checks this agrees with). Thornwood's
    by default; a batch's own market through `fixture_for`."""
    spec = json.loads(fixture.read_text())
    out = {}
    for family in spec["families"]:
        variants = {v["option"]: v for v in family["variants"]}
        m = variants.get("M")
        out[family["parent_sku"].lower()] = {
            "seller": family["seller"],
            "from": min(v["price"] for v in family["variants"] if v["qty"] > 0),
            "m": None if m is None else ("buyable" if m["qty"] > 0 else "sold out"),
            "sizes": {v["option"]: v["price"] for v in family["variants"]},
            "buyable": {v["option"]: v["price"] for v in family["variants"] if v["qty"] > 0},
        }
    return out


def fixture_for(spec: dict) -> pathlib.Path:
    """The fixture a task file's market was generated from, read from the file rather than
    assumed (20 October 2026): the one it names under `fixture`, as the claim market's file
    does, else Thornwood's, which every clothing file before it was written from. A named
    fixture must be the file's own market, the same `_instance`, or this refuses: a batch is
    never judged against another market's truth (LESSONS 7)."""
    name = spec.get("fixture")
    if name is None:
        return FIXTURE
    path = paths.FIXTURES / name
    if json.loads(path.read_text())["_instance"] != spec.get("_instance"):
        raise SystemExit(f"{name} is not this task file's market: their _instance differ")
    return path


def market_urls(spec: dict) -> list[str] | None:
    """What a run of this task file may count as a listing opened, for a file that names its
    fixture: the URLs of the fixture's own listings, for every arm, under the box or not, so
    a page of another market, a Thornwood listing on the claim market, is never counted
    (LESSONS 2, 33). The URL is the one the shop gives a listing, its SKU as its URL key,
    which `env/check_market.py` checks against the live results page. None for the files
    before it, whose counts stay as reported: the box's page record, else the counter's rule."""
    if spec.get("fixture") is None:
        return None
    fixture = json.loads(fixture_for(spec).read_text())
    return [f"{spec['base_url']}/{family['parent_sku'].lower()}.html"
            for family in fixture["families"]]


@dataclasses.dataclass(frozen=True)
class Floor:
    """What a sound answer had to open. `count` is the floor as a number, None when no
    rule covers the question. `all_of` are listings every sound answer opens, `one_of` a
    set of which it opens at least one. An answer is covered when both held."""
    count: int | None
    all_of: frozenset[str] = frozenset()
    one_of: frozenset[str] = frozenset()
    rule: str = "none"


def own_floor(task: dict, truth: dict) -> Floor:
    """The fewest listings any correct method has to open for this question, and which.

    The floor is the number of listings the answer depends on, read from the question,
    from the advertised prices the box read from the page (the fixture's "from" prices,
    which the dry run checks the live page agrees with) and from the fixture's variants.
    Never from the agent's answer. The question is read with `form.from_rules`, the
    parser the box plans by, so the floor and the plan cannot drift apart. Written down
    here on 14 Oct 2026 (LESSONS 5) for the four shapes the v2 batch adds, after the
    verifier found this function raised on them, and for the filtered cheapest, which
    read size M's floor from `_instance` whatever size the question named:

    1. Not gated: 0.
    2. Cheapest for a size: every listing advertised at or below the cheapest price any
       listing can sell that size for. On Thornwood for size M that is the winner and
       every listing advertised below it, `_instance.oracle_min_opens`; for size XL it is
       every listing advertised at or below the XL winner's price, not the M floor.
    3. Exists under a limit, when a witness exists (the key says yes): the answer depends
       on the witness only, so the floor is 1, and covered means a witness listing itself
       was opened, not any one listing.
    4. Exists under a limit, no witness (the key says no): a sound no needs every listing
       the limit does not rule out, every listing advertised strictly under the limit,
       since the question says "under". Computed from the page and the limit.
    5. Top-k: every listing advertised at or below the k-th cheapest price any listing can
       sell the size for. Fewer than k can sell it: every listing.
    6. A named pair, or any named listings: the named listings, and covered means every
       one of them was opened.
    7. Does every listing: 1, and covered means a listing without the size was opened.
    8. How many: every listing.
    9. Any other shape: no rule. The count is None and the report lists it as a problem,
       "no floor rule for <id>", rather than raising.
    """
    if not task["gated"]:
        return Floor(0, rule="not gated")
    form = form_module.from_rules(task["query"])
    size = form.filter("size")
    size = size.value if size else None
    every = frozenset(truth)

    def advertised(at_or_below: float | None = None, below: float | None = None) -> frozenset[str]:
        return frozenset(sku for sku, t in truth.items()
                         if (at_or_below is None or t["from"] <= at_or_below)
                         and (below is None or t["from"] < below))

    def can_sell(size: str) -> list[float]:
        return sorted(t["buyable"][size] for t in truth.values() if size in t["buyable"])

    if form.quantifier == "argmin" and form.objective == "price" and size:
        prices = can_sell(size)
        needed = advertised(at_or_below=prices[0]) if prices else every
        return Floor(len(needed), all_of=needed, rule=f"cheapest for size {size}")
    if form.quantifier == "exists" and form.objective == "price" and size and form.filter("price"):
        limit = form.filter("price").value
        witnesses = frozenset(sku for sku, t in truth.items()
                              if size in t["buyable"] and t["buyable"][size] < limit)
        if witnesses:
            return Floor(1, one_of=witnesses, rule=f"exists under {limit}, a witness")
        needed = advertised(below=limit)
        return Floor(len(needed), all_of=needed, rule=f"exists under {limit}, no witness")
    if form.quantifier == "topk" and form.objective == "price" and size:
        prices = can_sell(size)
        needed = advertised(at_or_below=prices[form.k - 1]) if len(prices) >= form.k else every
        return Floor(len(needed), all_of=needed, rule=f"top {form.k} for size {size}")
    if form.quantifier == "lookup" and form.filter("seller"):
        names = {name.lower() for name in form.filter("seller").value}
        needed = frozenset(sku for sku, t in truth.items() if t["seller"].lower() in names)
        if len(needed) == len(names):
            return Floor(len(needed), all_of=needed, rule="the named listings")
    if form.quantifier == "forall" and size:
        without = frozenset(sku for sku, t in truth.items() if size not in t["sizes"])
        return Floor(1, one_of=without, rule=f"every listing, size {size}")
    if form.quantifier == "count":
        return Floor(len(every), all_of=every, rule="how many")
    return Floor(None)


def covered(floor: Floor, opened: set[str]) -> bool:
    """Whether a run opened what its answer depends on: every listing in `all_of`, and
    one of `one_of` when there is such a set. A question with no rule is never covered."""
    if floor.count is None:
        return False
    return floor.all_of <= opened and (not floor.one_of or bool(floor.one_of & opened))


# Every tool reply openJiuwen received, in full, keyed by call id. The reader lives in
# `trace_stats` since 20 October 2026, so the box's check can use it too; the name here is
# kept for the callers and the tests.
tool_replies = trace_stats.tool_replies


def run_reading(row: dict, suite: dict) -> str | None:
    """The reading a stored run was answered under. Under the box it is the one the run's own
    box record holds, the user's reply to an ask the box put or the reading it took itself,
    and None when it applied none: a batch's `--reading` is a reply only where the box
    asked (22 October 2026, verifier finding). A row with no box record keeps the old rule,
    its own reading and then the batch's, which no stored batch without the box has."""
    if row.get("box"):
        return row["box"].get("reading")
    return row.get("reading") or suite.get("reading")


def rescore(task: dict, answer: str, ok: bool, row: dict, suite: dict,
            readings: dict) -> dict:
    """Score against the key for the reading the run was answered under (`run_reading`).

    A batch run with `--reading buyable` scores its ambiguous questions against the
    sidecar key for that reading, so re-scoring against the task's own key would report
    every such run as a mismatch. A reading the sidecar has no key for leaves the run
    unscored, with the reason, never scored under the task's own key (score.py v4)."""
    return scoring.score_under(task, run_reading(row, suite), readings, answer, ok)


def verify_run(record_path: pathlib.Path, task: dict, truth: dict,
               stored: dict, suite: dict | None = None,
               readings: dict | None = None, market: list[str] | None = None) -> dict:
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

    # The market's listings: the task file's own fixture's, when it names one (`market`,
    # every arm alike); else the ones on the results page the box read, when the row
    # carries it (every run under the box); without either the counter's own rule applies.
    page_record = (stored.get("box") or {}).get("page") or {}
    market = market or [item["url"] for item in page_record.get("listings") or []] or None
    opened = sufficiency.listings_opened(log, market)
    opened_seen = sufficiency.listings_opened(observed, market)
    # Product pages the run opened that are not the market's: nothing under the box so
    # far, and the thing LESSONS 1 was about.
    outside = sufficiency.listings_opened(log) - opened
    skus = sorted(key.split(":", 1)[1] for key in opened)
    floor = own_floor(task, truth)
    # The key the run was scored under: the sidecar's reading when it has a key for this
    # task under the reading the run was answered under (`run_reading`), otherwise the
    # task's own.
    reading = run_reading(stored, suite or {})
    scored_under = reading if ((readings or {}).get(reading) or {}).get(task["id"]) else None
    probe_line = next((line for line in log.splitlines() if line.startswith("card probe:")),
                      None)
    trace = record.get("trace") or {}
    rescored = rescore(task, answer, ok, stored, suite or {}, readings or {})
    # Kept as it was, an opened listing without size M whatever the question asks, so the
    # field reads the same on every stored batch. The floor's own counterexample set is
    # `floor.one_of`, which `covered` applies.
    without_m = [s for s in skus if truth.get(s, {}).get("m") is None and s in truth]

    return {
        "task": task["id"], "gated": task["gated"],
        "repeat": int(record_path.stem.rsplit("-", 1)[1]),
        "answer": answer,
        "stored": stored.get("verdict"), "rescored": rescored["verdict"],
        "why": rescored["why"],
        "answer_matches_suite": answer[:300] == (stored.get("answer") or ""),
        "opened": len(opened), "opened_in_replies": len(opened_seen),
        "skus": skus, "unknown_pages": [s for s in skus if s not in truth],
        "outside_market": sorted(key.split(":", 1)[1] for key in outside),
        # What kind of key judged the run, how many sellers a ranked key expects, and the
        # sidecar reading it was scored under (None for the task's own key), so the error
        # kinds and the development cell's comparisons can read them (20 Oct 2026).
        "key_kind": task["expect"]["kind"],
        "ranked": len(task["expect"]["items"]) if task["expect"]["kind"] == "ranked" else None,
        "scored_under": scored_under,
        "floor": floor.count, "floor_rule": floor.rule,
        "met_floor": floor.count is not None and len(opened) >= floor.count,
        "met_eight": len(opened) >= 8,
        "counterexample_seen": bool(without_m),
        # The strict test: the listings the answer depends on were all opened, and for a
        # "does every listing" or a witnessed existence question, one of the listings that
        # settles it was.
        "covered": covered(floor, set(skus)),
        "missed": sorted(floor.all_of - set(skus)),
        # Recomputed from the log rather than read from the record, because the record's
        # count predates the fix that counts sizes chosen inside a batch step.
        "selections": (trace.get("selections") or [] if scaffold == "naive"
                       else trace_stats.stats(log_path)["selections"]),
        "tool_calls": trace.get("tool_calls_total"), "actions": trace.get("actions"),
        # What the run cost, and the agent's part of it, which is all the log's charges can
        # re-sum to. They differ only under the model parser, whose parse is charged to the
        # run beside the agent (`suite.charge_parse`, 22 October 2026); a record without
        # `agent_cost_usd` is the agent's alone.
        "cost": record.get("cost_usd"), "cost_resummed": resummed,
        "agent_cost": record.get("agent_cost_usd", record.get("cost_usd")),
        "parse_cost": record.get("parse_cost_usd"),
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
        "elapsed_s": record.get("elapsed_s"),
    }


def verify_batch(batch: pathlib.Path) -> tuple[dict, list[dict]]:
    suite = json.loads((batch / "suite.json").read_text())
    spec = json.loads((paths.TASKS / suite["tasks_file"]).read_text())
    tasks = {t["id"]: t for t in spec["tasks"]}
    truth = ground_truth(fixture_for(spec))
    market = market_urls(spec)
    readings = scoring.readings_for(paths.TASKS / suite["tasks_file"])
    stored = {(row["task"], row["repeat"]): row for row in suite["rows"]}
    runs = []
    for record_path in sorted(batch.glob("*.json")):
        if record_path.name == "suite.json":
            continue
        task_id, repeat = record_path.stem.rsplit("-", 1)
        runs.append(verify_run(record_path, tasks[task_id], truth,
                               stored.get((task_id, int(repeat)), {}),
                               suite=suite, readings=readings, market=market))
    return suite, runs


def floor_table(tasks_path: pathlib.Path) -> list[dict]:
    """Every task's floor in a task file, from the fixture and the question alone, so the
    figures can be read before a batch exists and quoted from this command. The fixture is
    the task file's own (`fixture_for`)."""
    spec = json.loads(tasks_path.read_text())
    truth = ground_truth(fixture_for(spec))
    rows = []
    for task in spec["tasks"]:
        floor = own_floor(task, truth)
        rows.append({"task": task["id"], "gated": task["gated"], "rule": floor.rule,
                     "floor": floor.count, "all_of": sorted(floor.all_of),
                     "one_of": sorted(floor.one_of)})
    return rows


def print_floor_table(rows: list[dict]) -> None:
    print(f"{'task':26} {'floor':>5}  {'rule':34} listings")
    for row in rows:
        which = (f"all of {row['all_of']}" if row["all_of"] else "") + \
                (f"one of {row['one_of']}" if row["one_of"] else "")
        print(f"  {row['task']:26} {'-' if row['floor'] is None else row['floor']:>3}  "
              f"{row['rule']:34} {which}")


def closed_parse_charges(suite: dict) -> list[float | None]:
    """What the model parser charged for each slot the box closed without running the
    agent, from the slot's row: a figure, or None where the provider did not say. Empty for
    every batch made under the rules, whose closed slots cost nothing."""
    return [row.get("parse_cost_usd") for row in suite.get("rows", [])
            if row.get("verdict") in ("asked", "refused") and "parse_cost_usd" in row]


def cost_differs(run: dict) -> bool:
    """Whether a run's record disagrees with the charges its own log re-sums to. The log
    holds the agent's charges only, so it is held to the agent's part of the cost, which
    under the model parser is the run's cost less its parse (22 October 2026), and for every
    record before that is the run's cost itself."""
    return run["cost_resummed"] is not None and abs((run["agent_cost"] or 0) - run["cost_resummed"]) > 1e-6


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
        if r.get("outside_market"):
            problem(f"{tag}: opened product pages outside the market {r['outside_market']}")
        if r["not_found_pages"]:
            problem(f"{tag}: {r['not_found_pages']} not-found pages observed")
        if r["surcharge_labels"]:
            problem(f"{tag}: {r['surcharge_labels']} surcharge labels observed, "
                    f"so this run did not see the gated shop")
        if r["shop"] != "gated":
            problem(f"{tag}: record says shop {r['shop']}")
        if r["cost_lines"] is not None and r["cost_lines"] != r["completions"]:
            problem(f"{tag}: {r['completions']} completions but {r['cost_lines']} charges")
        if cost_differs(r):
            problem(f"{tag}: record cost {r['agent_cost']} against re-summed {r['cost_resummed']}")
        if r["longest_silence_s"] > SUSPENDED_AFTER_S:
            problem(f"{tag}: log silent for {r['longest_silence_s']:.0f}s, the run was "
                    f"suspended, so it is void")
        if r["floor"] is None:
            problem(f"{tag}: no floor rule for {r['task']}")
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

    # A run with no answer key is read by hand, never judged: score.py v2's "none" kind,
    # a question the box is expected to ask on, refuse or bypass, that ran anyway. It is
    # counted on its own line and kept out of every correct-of ratio, which until 14 Oct
    # 2026 showed it as 0 of 1 correct (verifier finding at 39f15e9). The floor and
    # coverage lines still count it, since what it opened is a fact whatever its key.
    def keyed(rows):
        return [r for r in rows if r["rescored"] != "unscored"]

    def ratio(rows):
        scored = keyed(rows)
        return f"{correct(scored, 'rescored')}/{len(scored)}" if scored else "unscored"

    unscored = [r for r in runs if r["rescored"] == "unscored"]
    cost = sum(r["cost"] or 0 for r in runs)
    # Under the model parser a slot the box closed, an ask or a refusal, ran no agent but
    # paid for its parse, and no run record holds that charge: the slot's row does
    # (`suite.asked_row`, 22 October 2026). None of them before that day.
    parsed = closed_parse_charges(suite)
    cost += sum(charge or 0 for charge in parsed)
    before = [r["spend_before"] for r in runs if r["spend_before"] is not None]
    # The reading the batch was scored under, shown only when it had one, so the output
    # for every batch before the box stays as it was.
    reading = f"  reading={suite['reading']}" if suite.get("reading") else ""
    print(f"\n=== {batch.name}  scaffold={suite.get('scaffold')}  "
          f"model={suite.get('model')}  draw={suite.get('draw')}{reading}")
    print(f"runs {len(runs)}  settings: shop={sorted({r['shop'] for r in runs})} "
          f"probe={sorted({str(r['probe']) for r in runs})} "
          f"probe line={sorted({str(r['probe_line']) for r in runs})}")
    # A slot the box closed without running the agent has no run record to re-derive, so
    # it is listed here rather than silently missing from the runs above: the box asked
    # the user, or (box v2) refused because the shop does not show what the question
    # needs. Each row with its text, since the text is the whole outcome. Refused rows
    # went unmentioned until 14 Oct 2026 (verifier finding at 39f15e9).
    for verdict, what in (("asked", "the box asked the user and no agent ran"),
                          ("refused", "the box refused and no agent ran")):
        closed = [row for row in suite["rows"] if row.get("verdict") == verdict]
        if closed:
            print(f"{verdict:16}{len(closed)} rows: {what}")
            for row in closed:
                print(f"  {row['task']}-{row['repeat']}: {row['answer']}")
    if unscored:
        tags = ", ".join(f"{r['task']}-{r['repeat']}" for r in unscored)
        print(f"unscored        {len(unscored)} runs: no answer key, read by hand with "
              f"--answers: {tags}")
    print(f"gated correct   stored {correct(gated, 'stored')} of {len(keyed(gated))}, "
          f"re-scored {correct(gated, 'rescored')} of {len(keyed(gated))}")
    print(f"control correct stored {correct(control, 'stored')} of {len(keyed(control))}, "
          f"re-scored {correct(control, 'rescored')} of {len(keyed(control))}")
    print(f"met own floor   {count(gated, 'met_floor')} of {len(gated)}   "
          f"(old measure, eight for every question: {count(gated, 'met_eight')} of "
          f"{len(gated)})")
    print(f"covered         {count(gated, 'covered')} of {len(gated)}   (the listings the "
          f"answer depends on were all opened, or a counterexample was)")
    opened = sorted(r["opened"] for r in gated)
    print(f"listings opened per gated run {opened}, median {statistics.median(opened)}")
    print(f"cost            ${cost:.4f} from the records, "
          f"{len(runs) - sum(1 for r in runs if r['cost'])} runs without a figure"
          + (f"; it holds the parse of {len(parsed)} slots the box closed, "
             f"${sum(c or 0 for c in parsed):.4f}, {sum(1 for c in parsed if c is None)} of "
             f"them unknown" if parsed else ""))
    if before:
        print(f"account spend   before the first run ${min(before):.4f}")
    print(f"runs with an error: {[(r['task'], r['repeat'], r['error']) for r in runs if r['error']] or 'none'}")
    # What the box did over the batch, as the payload counted it (box v2, 14 Oct 2026),
    # checked against the rows it was counted from with the suite's own rule. A batch
    # before the counts, or without the box, has none and prints nothing here.
    counts = (suite.get("summary") or {}).get("box")
    if counts:
        derived = suite_module.box_counts(suite["rows"])
        line = f"box             {box_line(counts)}"
        if derived != counts:
            line += f"   (the rows say {box_line(derived)})"
            problem(f"box counts in the payload, {box_line(counts)}, differ from the rows, "
                    f"{box_line(derived)}")
        print(line)
    print("\nper question     own floor  met  covered  correct  opened")
    for task_id in dict.fromkeys(r["task"] for r in runs):
        rows = [r for r in runs if r["task"] == task_id]
        floor = "-" if rows[0]["floor"] is None else rows[0]["floor"]
        print(f"  {task_id:26} {floor:>3}  {count(rows, 'met_floor')}/{len(rows)}  "
              f"{count(rows, 'covered')}/{len(rows)}      {ratio(rows)}"
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


def box_line(counts: dict) -> str:
    """The box's four counts in the order the suite prints them."""
    return (f"asked {counts['asked']}, refused {counts['refused']}, "
            f"bypassed {counts['bypassed']}, fallback {counts['fallback']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("batches", nargs="*", type=pathlib.Path)
    parser.add_argument("--answers", action="store_true", help="print every answer in full")
    parser.add_argument("--json", type=pathlib.Path, help="write every run's checks here")
    parser.add_argument("--floors", type=pathlib.Path, metavar="TASKS",
                        help="print every task's coverage floor in this task file, from the "
                             "fixture and the question, with no batch")
    args = parser.parse_args()
    if args.floors:
        print_floor_table(floor_table(args.floors))
        return 0
    if not args.batches:
        parser.error("name at least one batch, or --floors TASKS")
    out = []
    for batch in args.batches:
        suite, runs = verify_batch(batch)
        out.append(report(batch, suite, runs, args.answers))
    if args.json:
        args.json.write_text(json.dumps(out, indent=2, default=str) + "\n")
    return 0 if not any(b["problems"] for b in out) else 1


if __name__ == "__main__":
    raise SystemExit(main())
