#!/usr/bin/env python3
"""The claim run's analysis, as docs/content/claim-protocol.md fixed it before the run.

    python3 experiments/analysis/claim.py experiments/results/claim-20261020.manifest
    python3 experiments/analysis/claim.py experiments/results/<batch> [...] [--json PATH]

The protocol's Measures, Analysis and Exclusions sections are the specification. Written on
20 October 2026, before the claim run, and tried in-sample on Thornwood, with the box v2
development batches standing for the block and cells 1 and 5 for shipped and open
everything, where it reproduces the verifier's figures (tests/test_claim_analysis.py).

What it reads. The manifest the claim command writes, one line per suite invocation:

    start <iso> usage <x> cap <y>
    batch|<folder>|<the suite.py arguments after --tasks T --repeats 1>
    rerun|<folder>|<original folder> --only <task> --repeat-start <r>
    STOP ...
    end <iso> usage <x>

Or a list of batch folders. No line then says which run replaced a void, so every run that
is not void counts and every void is listed, the way compare_cells has always read cell 5's
three batches.

Arms come from each batch's payload, never from where the batch sits in the manifest: the
retrieval instruction it recorded (`arm`, or for a batch before that field the flags
`suite.arm_of` reads) and, under the box, the scripted user's reading. The model is part of
an arm, so each model is analysed on its own and two are never pooled. So is every other
condition a batch or a run records (LESSONS 7): one arm's runs under two conditions stop the
analysis rather than being pooled.

Exclusions, from the protocol: each run is classed by voids.py from its log and record
before any answer is read. A void is replaced by its re-run, matched on arm, task and
repeat; a re-run that is void again, or a void never re-run, leaves its slot missing. The
step budget, the clock, no answer and an abstention are not correct, stay in, and are
reported apart. Nothing else is excluded.

The report is printed, and the same figures are written as JSON next to the manifest
(`claim-20261020.manifest` gives `claim-20261020.analysis.json`), or where `--json` says.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import hashlib
import itertools
import json
import math
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import compare_cells  # noqa: E402  (stratified_exact, covered, distinct: one definition each)
import leaks  # noqa: E402
import replay_box  # noqa: E402
import score as scoring  # noqa: E402
import sufficiency  # noqa: E402
import suite as suite_module  # noqa: E402  (arm_of, the one rule for a batch's arm)
import toolbar  # noqa: E402  (the results pages a run asked for, from its log)
import trace_stats  # noqa: E402
import verify_cells  # noqa: E402
import voids  # noqa: E402

# Bumped when a figure this prints would change for the same runs, and written into the JSON.
#   1  20 October 2026, before the claim run
#   2  23 October 2026, from the verifier's fairness audit. Every answer is scored with the
#      market's sellers where its task file names its fixture (score v7, `market_sellers`),
#      and a stored verdict is held to that score, not to verify_cells' re-score without
#      them, so a verdict the sellers would move is listed as a problem, never silently
#      applied. Over the first claim's stored runs no verdict moves
VERSION = 2

# The question sets the analysis reads. These are the first claim's (claim-protocol.md), the
# default. Since 22 October 2026 a protocol may name its own in a file (`--sets`,
# `apply_sets`), so the second claim's tee-* and water-* ids, its reading-independent set and
# its "offer" set are named there and not here; the first claim's analysis is the same, byte
# for byte (`tests/test_claim_analysis.py`).
CONTROL = "apparel-headline"
TARGET_PRICE = "apparel-target-price"
CHEAPEST = "apparel-cheapest-target"
ALL_STOCKED = "apparel-all-stocked"
COUNT_STOCKED = "apparel-count-stocked"
COUNT_BUYABLE = "apparel-count-buyable"
GATED = (TARGET_PRICE, CHEAPEST, ALL_STOCKED, COUNT_STOCKED, COUNT_BUYABLE)
QUESTIONS = (CONTROL,) + GATED
# Primary 1: "the four gated questions whose answer does not depend on how 'offer' is read".
INVARIANT = (TARGET_PRICE, CHEAPEST, ALL_STOCKED, COUNT_BUYABLE)
# The two questions that turn on the word "offer", the command's OFFER.
OFFER = (ALL_STOCKED, COUNT_STOCKED)
# Where the stop rule acts, the command's THREE.
STOP_RULE = (TARGET_PRICE, CHEAPEST, ALL_STOCKED)

SHIPPED = "shipped"
OPEN = "open everything"
BLOCK = "the block (menu)"
BUYABLE = "the block (buyable)"
NO_STOP = "the block without its stop rule"
ARMS = (SHIPPED, OPEN, BLOCK, BUYABLE, NO_STOP)
# The protocol's name for each arm a payload records (`suite.arm_of`'s names), with the
# scripted user's reading under the box. Any other pair is named for what it was and never
# enters a test.
NAMES = {("none", None): SHIPPED, ("exhaustive", None): OPEN, ("box", "menu"): BLOCK,
         ("box", "buyable"): BUYABLE, ("box-exhaust", "menu"): NO_STOP}
# The questions each arm asks in each of the three rounds: the command's S, E, B and X.
DESIGN = {SHIPPED: QUESTIONS, OPEN: GATED, BLOCK: QUESTIONS, BUYABLE: OFFER, NO_STOP: STOP_RULE}
ROUNDS = (1, 2, 3)
# The sets a file names, by key, in the first claim's terms, and which name each set's
# questions by id: `control` the questions answered from the results page, `gated` every
# other one analysed, `invariant` the gated ones whose answer does not depend on a reading,
# `offer` those that turn on one, `stop_rule` where the stop rule acts, `count_stocked` the
# one question tabled by key, and `design` the questions each arm asks, by the arm's name.
SET_KEYS = ("control", "gated", "invariant", "offer", "stop_rule", "count_stocked", "design")


def apply_sets(sets: dict) -> None:
    """Analyse under the question sets a protocol names (22 October 2026), in place of the
    first claim's: every set by its questions' ids, checked to be the gated questions' own
    before anything is read, and `design` by the protocol's arm names. The first claim's
    sets are the default and need no file."""
    global CONTROL, GATED, QUESTIONS, INVARIANT, OFFER, STOP_RULE, COUNT_STOCKED, DESIGN
    missing = [key for key in SET_KEYS if key not in sets]
    if missing:
        raise SystemExit(f"the question sets name no {', '.join(missing)}")
    control, gated = tuple(sets["control"]), tuple(sets["gated"])
    if len(control) != 1:
        raise SystemExit(f"the question sets name {len(control)} control questions, where the "
                         f"analysis reads one")
    for key in ("invariant", "offer", "stop_rule"):
        stray = sorted(set(sets[key]) - set(gated))
        if stray:
            raise SystemExit(f"the {key} set names questions that are not gated: {stray}")
    if sets["count_stocked"] not in sets["offer"]:
        raise SystemExit(f"count_stocked, {sets['count_stocked']}, is not in the offer set")
    for arm, questions in sets["design"].items():
        if arm not in ARMS:
            raise SystemExit(f"the design names an arm the analysis has not: {arm!r}")
        stray = sorted(set(questions) - set(control + gated))
        if stray:
            raise SystemExit(f"the design has {arm} ask questions no set names: {stray}")
    CONTROL, GATED = control[0], gated
    QUESTIONS = control + gated
    INVARIANT, OFFER, STOP_RULE = (tuple(sets[key]) for key in ("invariant", "offer", "stop_rule"))
    COUNT_STOCKED = sets["count_stocked"]
    DESIGN = {arm: tuple(questions) for arm, questions in sets["design"].items()}


def read_sets(path: pathlib.Path) -> dict:
    """The question sets a file names: its `claim_sets` when it has them, as a task file may,
    or the whole file."""
    data = json.loads(path.read_text())
    return data.get("claim_sets", data)
# What the protocol holds fixed besides the arm: "openJiuwen as shipped" on the gated shop,
# its own card probe, and nothing added to the question but the arm's instruction. A run
# under anything else is not one of the five arms.
SETTING = {"scaffold": "openjiuwen", "shop": "gated", "probe": "viewport", "policy": "off",
           "confidence": "off", "targeting": False}
# Every condition a payload or a run record says a run was made under. Runs of one arm that
# differ in any of them are two arms (LESSONS 7, 10). The scorer is not among them: every
# answer here is scored again by today's score.py, whatever scored it at the time.
CONDITIONS = ("model", "scaffold", "shop", "probe", "draw", "tasks_file", "policy", "confidence",
              "targeting_version", "planner_version", "box_version", "form_version",
              "primitives_version", "page_reader", "browser_tool", "browser_origins", "browser_flags",
              "agent_core_commit", "agent_core_patch", "max_steps", "clock_s")
# Of those, the ones only an arm under the box has, so they differ between arms by design.
# The page reader is the box's since box v16 (22 October 2026); every batch before has none.
BOX_CONDITIONS = ("targeting_version", "planner_version", "box_version", "form_version",
                  "primitives_version", "page_reader")
# The fields a run record carries for itself; the rest are its batch's. The step and clock
# limits are in both since 22 October 2026; every run before has neither.
RUN_CONDITIONS = ("model", "scaffold", "shop", "probe", "max_steps", "clock_s")
UNRECORDED_BEFORE_LIMITS = ("max_steps", "clock_s")
ALPHA = 0.05


# ---------------------------------------------------------------------------
# The statistics

def midranks(values: list[float]) -> list[float]:
    """Each value's rank among `values`, a tie given the mean of the ranks it spans."""
    order = sorted(values)
    rank = {}
    for value in set(values):
        places = [i for i, x in enumerate(order) if x == value]
        rank[value] = sum(places) / len(places) + 1
    return [rank[value] for value in values]


def stratified_rank_test(a_by_q: dict[str, list[float]],
                         b_by_q: dict[str, list[float]]) -> tuple[float, float, float]:
    """The stratified exact rank test the protocol names for H2 and H3: van Elteren's
    statistic with equal weights, mid-ranks within each question, exact.

    The statistic is the sum over questions of arm A's mid-rank sum. Under the null, within
    each question A's runs are a random subset of the question's pooled runs, so each
    question's distribution is found by enumerating every split, and the questions are
    combined by convolving. Only questions both arms asked count. Two-sided: the probability
    of a sum at least as far from its null mean as the one observed. Returns (observed sum,
    null mean, p).

    Ported from the verifier's logic audit of 20 October 2026 (audit/tools/strat_rank.py,
    `midranks` and `stratified_rank_test`), with its logic unchanged: only the layout, the
    type hints and this docstring differ, and tests/test_claim_analysis.py holds the audit's
    text and checks the two agree.
    """
    dist = {0.0: 1.0}
    observed = 0.0
    mean = 0.0
    for q in sorted(set(a_by_q) & set(b_by_q)):
        a, b = a_by_q[q], b_by_q[q]
        ranks = midranks(a + b)
        na = len(a)
        observed += sum(ranks[:na])
        subsets = list(itertools.combinations(range(len(ranks)), na))
        pmf = collections.Counter(round(sum(ranks[i] for i in s), 6) for s in subsets)
        pmf = {k: v / len(subsets) for k, v in pmf.items()}
        mean += sum(k * p for k, p in pmf.items())
        nxt: dict[float, float] = collections.defaultdict(float)
        for t, p in dist.items():
            for k, q_ in pmf.items():
                nxt[round(t + k, 6)] += p * q_
        dist = nxt
    dev = abs(observed - mean)
    return observed, mean, sum(p for t, p in dist.items() if abs(t - mean) >= dev - 1e-9)


def holm(pvalues: dict[str, float | None]) -> dict[str, float]:
    """Holm's step-down adjustment: the i-th smallest of m p-values times m - i + 1, never
    above 1 and never below the adjusted value before it, so a hypothesis is rejected at a
    level only when every smaller one is too. A test that could not be computed counts as
    p = 1, so m stays the number the protocol names and the others are not favoured."""
    filled = {name: 1.0 if p is None else p for name, p in pvalues.items()}
    adjusted, running = {}, 0.0
    for i, name in enumerate(sorted(filled, key=filled.get)):
        running = max(running, min(1.0, (len(filled) - i) * filled[name]))
        adjusted[name] = running
    return adjusted


Z95 = statistics.NormalDist().inv_cdf(0.975)


def wilson(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson's score interval for one proportion, without continuity correction."""
    p = successes / n
    scale = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / scale
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / scale
    return centre - half, centre + half


def newcombe(x1: int, n1: int, x2: int, n2: int, z: float = Z95) -> tuple[float, float] | None:
    """Newcombe's hybrid score interval for p1 - p2, from each proportion's Wilson interval
    (Newcombe 1998, Statistics in Medicine 17:873-890, method 10). None when an arm has no
    runs."""
    if not n1 or not n2:
        return None
    p1, p2 = x1 / n1, x2 / n2
    l1, u1 = wilson(x1, n1, z)
    l2, u2 = wilson(x2, n2, z)
    d = p1 - p2
    return (d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2),
            d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2))


# ---------------------------------------------------------------------------
# The manifest

@dataclasses.dataclass
class Line:
    kind: str                           # "batch" or "rerun" from a manifest, "folder" from the command line
    folder: pathlib.Path | None         # None when the invocation wrote no batch
    args: str = ""                      # a batch line's suite arguments
    original: pathlib.Path | None = None    # a rerun line: the batch whose void it re-ran
    task: str | None = None             # a rerun line: the void's task and repeat
    repeat: int | None = None


@dataclasses.dataclass
class Manifest:
    lines: list[Line] = dataclasses.field(default_factory=list)
    starts: list[dict] = dataclasses.field(default_factory=list)
    ends: list[dict] = dataclasses.field(default_factory=list)
    stops: list[str] = dataclasses.field(default_factory=list)
    problems: list[str] = dataclasses.field(default_factory=list)


START = re.compile(r"^start (\S+) usage (\S+) cap (\S+)$")
END = re.compile(r"^end (\S+) usage (\S+)$")


def amount(text: str) -> float | None:
    """A dollar figure as the command writes it, "None" when the account could not be read."""
    try:
        return float(text)
    except ValueError:
        return None


def flags(words: list[str]) -> dict[str, list[str]]:
    """A suite argument list as each flag and the words after it, up to the next flag."""
    out: dict[str, list[str]] = {}
    name = None
    for word in words:
        if word.startswith("--"):
            name = word[2:]
            out[name] = []
        elif name is not None:
            out[name].append(word)
    return out


def resolve(text: str) -> pathlib.Path | None:
    """A batch folder as a line names it: as written, else by its name under
    experiments/results, so a manifest written in one checkout reads in another."""
    text = text.strip()
    if not text:
        return None
    path = pathlib.Path(text)
    if not path.is_dir() and (paths.RESULTS / path.name).is_dir():
        return paths.RESULTS / path.name
    return path


def parse_manifest(text: str) -> Manifest:
    """Every line the claim command writes, and a problem for any line it does not."""
    found = Manifest()
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if START.match(line):
            at, usage, cap = START.match(line).groups()
            found.starts.append({"at": at, "usage": amount(usage), "cap": amount(cap)})
        elif END.match(line):
            at, usage = END.match(line).groups()
            found.ends.append({"at": at, "usage": amount(usage)})
        elif line.startswith("STOP"):
            found.stops.append(line)
        elif line.startswith("batch|"):
            _, folder, args = (line.split("|", 2) + [""])[:3]
            found.lines.append(Line("batch", resolve(folder), args=args.strip()))
        elif line.startswith("rerun|"):
            _, folder, what = (line.split("|", 2) + [""])[:3]
            words = what.split()
            named = flags(words[1:])
            try:
                repeat = int((named.get("repeat-start") or [""])[0])
            except ValueError:
                repeat = None
            task = (named.get("only") or [None])[0]
            found.lines.append(Line("rerun", resolve(folder), args=what.strip(),
                                    original=resolve(words[0]) if words else None,
                                    task=task, repeat=repeat))
            if not words or task is None or repeat is None:
                found.problems.append(f"manifest line {number}: a re-run line without its original "
                                      f"folder, task and repeat: {line[:120]}")
        else:
            found.problems.append(f"manifest line {number} is not one the claim command writes: "
                                  f"{line[:120]}")
    return found


def intended(args: str) -> tuple[str, str | None, list[tuple[str, int]]]:
    """What a batch line asked for, from its arguments: the arm, the reading, the slots. The
    parser is part of the box's arm since 22 October 2026, named as `suite.arm_of` names it
    ("box-model", "box-exhaust-model"), so a line under the model parser never stands for
    a batch of the box under the rules (LESSONS 29)."""
    named = flags(args.split())
    arm = ("box-exhaust" if "box-exhaust" in named else "box" if "box" in named
           else "exhaustive" if "exhaustive" in named else "none")
    if arm in ("box", "box-exhaust") and (named.get("parser") or ["rules"])[0] == "model":
        arm += "-model"
    # Open everything naming the question's product is an arm of its own (22 October 2026).
    if arm == "exhaustive" and (named.get("exhaustive-wording") or ["every"])[0] == "product":
        arm = "exhaustive-product"
    reading = (named.get("reading") or [None])[0]
    try:
        start = int((named.get("repeat-start") or ["1"])[0])
    except ValueError:
        start = None
    return arm, reading, [(task, start) for task in named.get("only") or []]


# ---------------------------------------------------------------------------
# The runs

def page_kind(url: str | None, own: set[str] | None) -> str:
    """results, listing or other: the shop's search results page, one of the market's own
    listings, or anything else (a category page, another market's listing, a page the agent
    wrote itself)."""
    if not url:
        return "other"
    url = re.split(r"[\\\s\"'<>]", url)[0]
    if "catalogsearch" in url:
        return "results"
    key = sufficiency.listing_key(url)
    if key is None:
        return "other"
    if own is not None:
        return "listing" if key in own else "other"
    return "listing" if key.startswith("id:") or sufficiency.GENERATED_SLUG.match(key) else "other"


def page_calls(log_path: pathlib.Path, market: list[str] | None
               ) -> tuple[collections.Counter, collections.Counter, list[str]]:
    """An openJiuwen run's tool calls by the kind of page the browser was on after each, and
    the browser actions among them (`trace_stats.ACTIONS`), with every call's tool name.

    A call is placed by the page its reply reports, else the address a navigation asked for,
    else the page before, as the verifier's audit decomposed the runs (20 October 2026,
    audit/tools/pagetype.py, `run_breakdown`). Two rules differ from the audit's. A listing is
    one of the market's own, the task file's fixture's or the results page the box read, and
    only without either a page the counter's own rule takes for a generated listing (LESSONS
    33): the audit took any generated product page for a listing, so a Thornwood listing
    opened on the claim market would have counted as one of its own. And a call with no tool
    name is skipped, as `trace_stats` skips it, so the calls add up to the record's count."""
    own = None if market is None else {sufficiency.listing_key(url) for url in market} - {None}
    replies = trace_stats.tool_replies(log_path)
    calls, actions, names = collections.Counter(), collections.Counter(), []
    where = None
    for message in trace_stats.final_messages(log_path):
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            name = trace_stats.normalise(function.get("name") or "")
            if not name:
                continue
            raw = function.get("arguments")
            try:
                arguments = json.loads(raw or "{}") if isinstance(raw, str) else (raw or {})
            except json.JSONDecodeError:
                arguments = {}
            asked_for = (arguments.get("url") if name == "browser_navigate"
                         and isinstance(arguments, dict) else None)
            reported = sufficiency.PAGE_MARKER.search(replies.get(call.get("id"), ("", "", {}))[1] or "")
            where = reported.group(1) if reported else (asked_for or where)
            kind = page_kind(where, own)
            calls[kind] += 1
            if name in trace_stats.ACTIONS:
                actions[kind] += 1
            names.append(name)
    return calls, actions, names


def flagged_arm(payload: dict) -> str:
    """The arm a payload's flags make, by `suite.arm_of`'s rule, for a batch made before the
    payload named its arm (20 October 2026) and to check one that does. The parser is one of
    the flags since 22 October 2026: a payload without it was read by the rules. So is the
    open-everything wording: a payload without it said every listing."""
    return suite_module.arm_of(argparse.Namespace(**{
        name: bool(payload.get(name)) for name in ("box", "box_exhaust", "targeting", "exhaustive")},
        parser=payload.get("parser") or "rules", exhaustive_wording=payload.get("exhaustive_wording")))


def arm_of(payload: dict, run: dict | None = None, names: dict | None = None) -> str:
    """The protocol's name for the arm a run was made under, from its batch's payload: the
    retrieval instruction (`arm`, or the flags of a batch before that field), the reading
    under the box, and the setting the protocol holds fixed, the shop and probe read from
    the run's own record when there is one. `names` is a protocol's own, the first claim's
    `NAMES` by default."""
    names = NAMES if names is None else names
    recorded = payload.get("arm") or flagged_arm(payload)
    reading = payload.get("reading") if recorded.startswith("box") else None
    setting = {"scaffold": payload.get("scaffold") or "openjiuwen",
               "policy": payload.get("policy") or "off",
               "confidence": payload.get("confidence") or "off",
               "targeting": bool(payload.get("targeting")),
               "shop": (run or {}).get("shop"), "probe": (run or {}).get("probe")}
    odd = [f"{key} {value}" for key, value in setting.items()
           if value is not None and value != SETTING[key]]
    name = names.get((recorded, reading))
    if name is None or odd:
        return "other: " + ", ".join([f"arm {recorded}"] + ([f"reading {reading}"] if reading else [])
                                     + odd)
    return name


def conditions_of(payload: dict, run: dict, keys: tuple = CONDITIONS) -> dict:
    """Every condition this run was made under: the run record's own fields where it has
    them, its batch's payload for the rest. `keys` are the first claim's `CONDITIONS` unless
    a protocol names more."""
    return {key: run.get(key) if key in RUN_CONDITIONS and run.get(key) is not None
            else payload.get(key) for key in keys}


def load_folder(folder: pathlib.Path, names: dict | None = None,
                condition_keys: tuple = CONDITIONS) -> tuple[dict, list[dict], list[str]]:
    """One batch: its payload, a slot for every run voids.py finds in it, and any problem.

    Each slot is classed by voids.py first, from the log and the record and before any
    answer is read. A slot whose run left a record is then re-derived by verify_cells (the
    answer, the listings opened by the market's URLs, the floors, the cost) and measured
    here for the rest. A slot the box closed, asking with no reply or refusing, ran no agent:
    it is kept as a run that answered nothing, opened nothing and cost nothing, since the
    protocol excludes nothing but voids."""
    payload = json.loads((folder / "suite.json").read_text())
    unlogged = sorted(p.name for p in folder.glob("*.json")
                      if p.name != "suite.json" and not p.with_suffix(".log").exists())
    if unlogged:
        raise SystemExit(f"{folder}: no log beside {', '.join(unlogged)}. Every measure reads the "
                         f"logs, which live on the laptop and not in git")
    problems = []
    spec = json.loads((paths.TASKS / payload["tasks_file"]).read_text())
    tasks = {task["id"]: task for task in spec["tasks"]}
    readings = scoring.readings_for(paths.TASKS / payload["tasks_file"])
    buyable = readings.get("buyable") or {}
    # The questions with two readings: those the sidecar names under `two_readings`, since
    # the A+ market's sidecar holds a key for every question (22 October 2026); before it,
    # those it holds a key for, as the first claim's sidecar does.
    named = scoring.two_readings_for(paths.TASKS / payload["tasks_file"])
    ambiguous = set(named) if named is not None else {task for keys in readings.values() for task in keys}
    truth = verify_cells.ground_truth(verify_cells.fixture_for(spec))
    market = verify_cells.market_urls(spec)
    # Every seller of the market, so a best is judged against all of them (score v7), where
    # the task file names its fixture; None before the first claim market's file.
    sellers = scoring.market_sellers(spec)
    rows = {(row["task"], row["repeat"]): row for row in payload.get("rows", [])}
    _, found = verify_cells.verify_batch(folder)
    checked = {(run["task"], run["repeat"]): run for run in found}
    seen = {run.run: run.found for run in leaks.batch_leaks(folder)[0]}
    if payload.get("arm") and payload["arm"] != flagged_arm(payload):
        problems.append(f"{folder.name}: its payload's arm is {payload['arm']}, its flags say "
                        f"{flagged_arm(payload)}")
    slots = []
    for run in voids.batch_runs(folder):
        row = rows.get((run.task, run.repeat)) or {}
        task = tasks.get(run.task) or {}
        record = (row.get("box") or {})
        slot = {"batch": folder.name, "folder": str(folder), "task": run.task, "repeat": run.repeat,
                "outcome": run.outcome, "reason": run.reason, "why": run.why,
                "gated": task.get("gated"), "ambiguous": run.task in ambiguous,
                "asked": bool(record.get("asked")), "measured": False,
                # The box made a plan and the agent ran on it: what replay_box replays.
                "planned": record.get("query") is not None and bool(row.get("log")),
                "reading": row.get("reading") or payload.get("reading"),
                # The reading the run was answered under, from its own box record (score v4),
                # and the template a held-out rewording rewords (22 October 2026).
                "answered": verify_cells.run_reading(row, payload) if row else None,
                "template": task.get("template"), "refused": bool(record.get("refuse"))}
        measured = checked.get((run.task, run.repeat))
        if measured is not None:
            slot.update(measure(measured, folder, row, slot["reading"], task, buyable.get(run.task),
                                truth, market, seen.get(f"{run.task}-{run.repeat}", []),
                                answered=slot["answered"], sellers=sellers))
            if measured["tool_calls"] is not None and measured["tool_calls"] != slot["calls"]:
                problems.append(f"{folder.name}/{run.task}-{run.repeat}: the record counts "
                                f"{measured['tool_calls']} tool calls, the page count {slot['calls']}")
            # The verdict the batch stored against today's scorer under the same reading, so
            # a scorer that changed since is seen, never silently applied (LESSONS 4, 34). The
            # re-score is this analysis's own, with the market's sellers (score v7): until 23
            # October 2026 it was verify_cells', which has none, so a verdict the sellers move
            # would have been applied here without a word.
            rescored = slot["verdict"]
            if measured["stored"] is not None and measured["stored"] != rescored:
                problems.append(f"{folder.name}/{run.task}-{run.repeat}: stored verdict "
                                f"{measured['stored']}, re-scored {rescored}")
        elif run.outcome == voids.CLOSED:
            closed = "closed by the box"
            # What the slot cost: nothing under the rules, and under the model parser the
            # parse, which its row records (`suite.asked_row`), unknown where the provider gave
            # no charge (22 October 2026). No agent ran, so it used no agent tokens.
            charged = row.get("cost_usd", 0.0)
            slot.update({"measured": True, "answer": row.get("answer") or "", "ok": False,
                         "own": closed, "buyable": closed if run.task in buyable else None,
                         "verdict": closed, "tokens_total": 0,
                         "opened": 0, "skus": [], "covered": False, "missed": [],
                         "cost": None if charged is None else float(charged),
                         "calls": 0, "actions": 0, "pages": {"calls": {}, "actions": {}},
                         "agent_asks": 0, "leaks": [], "outside": [], "tokens": (None, None),
                         "model": payload.get("model"), "scaffold": payload.get("scaffold"),
                         "shop": None, "probe": None, "toolbar": None, "taken": None})
        slot["model"] = slot.get("model") or payload.get("model")
        slot["arm"] = arm_of(payload, slot if slot["measured"] else None, names)
        slot["conditions"] = conditions_of(payload, slot, condition_keys)
        slots.append(slot)
    return payload, slots, problems


def measure(run: dict, folder: pathlib.Path, row: dict, reading: str | None, task: dict,
            buyable_key: dict | None, truth: dict, market: list[str] | None,
            leak: list[str], answered: str | None = None, sellers: list[str] | None = None) -> dict:
    """What one run did, from verify_cells' re-derivation and the log: the answer under the
    task's own key and, for the two offer questions, under the buyable key, each judged
    against every seller of the market where `sellers` names them (score v7); the market's
    listings opened, and whether they were what the answer needs under the reading the run
    answered; the cost; the calls by page; the asks; the leaks; the results pages it asked
    for (`toolbar.read`), and the advertised or sold-out prices its answer gives
    (`prices_taken`)."""
    record = json.loads((folder / f"{run['task']}-{run['repeat']}.json").read_text())
    tokens = record.get("tokens") or (record.get("trace") or {}).get("tokens") or {}
    # The listings a page counts as the market's: the task file's fixture's, as verify_cells
    # counts them, else those of the results page the box read.
    page = ((row.get("box") or {}).get("page") or {})
    own = market or [item["url"] for item in page.get("listings") or []] or None
    log = folder / f"{run['task']}-{run['repeat']}.log"
    calls, actions, names = page_calls(log, own)
    answer, ok = run["answer"], run["ok"]
    own = scoring.score(task, answer, ok, sellers)["verdict"]
    under_buyable = (scoring.score({"expect": buyable_key}, answer, ok, sellers)["verdict"]
                     if buyable_key else None)
    total = (tokens.get("prompt") or 0) + (tokens.get("completion") or 0) if tokens else None
    keyed = buyable_key if answered == "buyable" and buyable_key else task.get("expect") or {}
    return {
        "measured": True, "answer": answer, "ok": ok,
        "own": own,
        "buyable": under_buyable,
        # Under the key for the reading the run was answered under, as score v4 scores it: the
        # task's own unless the box record holds another, the buyable key then, and unscored
        # where the sidecar has none. A protocol named in a file reads this (22 October 2026).
        "verdict": (own if answered in (None, scoring.OWN_READING)
                    else under_buyable if answered == "buyable" and under_buyable is not None
                    else "unscored"),
        "tokens_total": total or None,
        "opened": run["opened"], "skus": run["skus"],
        "covered": compare_cells.covered(run, reading or scoring.OWN_READING, truth),
        "missed": run["missed"], "floor_rule": run["floor_rule"],
        "cost": run["cost"], "calls": sum(calls.values()), "actions": sum(actions.values()),
        "pages": {"calls": dict(calls), "actions": dict(actions)},
        # openJiuwen's browser agent has no ask tool in its schema (the `tools` of each
        # llm_call_end event in 20261014T213118/apparel-count-stocked-1.log: 24 tools, none of
        # them an ask), so an ask is the box's. A tool the agent called whose name says it asks
        # is counted all the same (LESSONS 3).
        "agent_asks": sum(1 for name in names if "ask" in name.lower()),
        "leaks": leak, "outside": run["outside_market"],
        "model": run["model"], "scaffold": run["scaffold"], "shop": run["shop"], "probe": run["probe"],
        "tokens": (tokens.get("prompt"), tokens.get("completion")),
        "error": run["error"], "elapsed_s": run["elapsed_s"],
        # The results pages the run asked the shop for: sort, page size, view and page
        # numbers (23 October 2026), for the sorting count and its sensitivity.
        "toolbar": toolbar.read(log),
        "taken": prices_taken(answer, task, keyed, truth),
    }


def key_prices(expect: dict) -> set[float]:
    """Every price an answer key holds as right: a price key's value, a key's price, a ranked
    key's items' prices. A count's value is no price."""
    found = {expect.get("price")} | {item.get("price") for item in expect.get("items") or []}
    if expect.get("kind") == "price":
        found.add(expect.get("value"))
    return {round(price, 2) for price in found if isinstance(price, (int, float))}


def prices_taken(answer: str, task: dict, expect: dict, truth: dict) -> dict:
    """The prices the answer states that are what the results page or a sold-out variant shows
    rather than what can be bought (23 October 2026, for the shipped agent's failure
    breakdown): a listing's advertised card price, or the price of the question's variant at
    a listing where it is sold out, among the listings of the question's product where the
    fixture names products; either way not a price the key `expect` holds as right. The
    fixture is what the shop was seeded from, so a card price here is the one the run's
    results page printed."""
    variant = verify_cells.question_variant(task) if task.get("query") else None
    product = task.get("product")
    listings = [t for t in truth.values() if product is None or t.get("product") in (None, product)]
    cards = {round(t["from"], 2) for t in listings}
    sold_out = {round(t["sizes"][variant], 2) for t in listings
                if variant and variant in t["sizes"] and variant not in t["buyable"]}
    right = key_prices(expect)
    stated = {round(price, 2) for price in scoring.prices_in(answer or "")} - right
    return {"card": sorted(stated & cards), "sold_out": sorted(stated & sold_out)}


# ---------------------------------------------------------------------------
# Which runs count

def assemble(loaded: list[tuple[Line, dict, list[dict]]], manifest: bool) -> dict:
    """The runs the analysis counts, by the protocol's Exclusions.

    From a manifest: a void in a batch is replaced by the run in the re-run line naming that
    batch, task and repeat, when that run is of the same arm and model; if it is void again,
    or there is no such line, the slot is missing. A re-run that replaced nothing is left out
    and listed. From a list of folders: every run that is not void counts, and the voids are
    listed. Either way two runs counted for one arm, model, task and repeat are listed."""
    kept, voided, replaced, missing, problems = [], [], [], [], []
    reruns = [(line, slots) for line, _, slots in loaded if line.kind == "rerun"]
    used = set()
    for line, _, slots in loaded:
        if line.kind == "rerun":
            continue
        for slot in slots:
            if slot["outcome"] != voids.VOID:
                kept.append(slot)
                continue
            voided.append(slot)
            if not manifest:
                continue
            # The run in the re-run line that names this batch, task and repeat, when it is
            # of the same arm and model.
            again = next((rslot for rerun, rslots in reruns
                          if rerun.original is not None and line.folder is not None
                          and rerun.original.name == line.folder.name
                          and (rerun.task, rerun.repeat) == (slot["task"], slot["repeat"])
                          for rslot in rslots if same_slot(rslot, slot)), None)
            if again is None:
                missing.append({**brief(slot), "why": "void, and no re-run of its arm, task and repeat"})
                continue
            used.add(id(again))
            if again["outcome"] == voids.VOID:
                voided.append(again)
                missing.append({**brief(slot), "why": f"void again on its re-run in "
                                f"{again['batch']}: {again['reason']}, {again['why']}"})
            else:
                kept.append(again)
                replaced.append({**brief(slot), "by": again["batch"]})
    for rerun, rslots in reruns:
        for rslot in rslots:
            if id(rslot) not in used:
                problems.append(f"{rslot['batch']}/{rslot['task']}-{rslot['repeat']}: a re-run that "
                                f"replaced no void of its arm, left out")
    counted = collections.Counter((s["arm"], s["model"], s["task"], s["repeat"]) for s in kept)
    for (arm, model, task, repeat), n in sorted(counted.items(), key=str):
        if n > 1:
            problems.append(f"{n} runs counted for {arm}, {model}, {task} repeat {repeat}: "
                            + ", ".join(s["batch"] for s in kept
                                        if (s["arm"], s["model"], s["task"], s["repeat"])
                                        == (arm, model, task, repeat)))
    return {"kept": kept, "voided": voided, "replaced": replaced, "missing": missing,
            "problems": problems}


def same_slot(a: dict, b: dict) -> bool:
    """Two slots of one arm, task and repeat, and of one model where both records say which:
    a run with no record has only its batch's word for the model."""
    return ((a["arm"], a["task"], a["repeat"]) == (b["arm"], b["task"], b["repeat"])
            and (None in (a["model"], b["model"]) or a["model"] == b["model"]))


def brief(slot: dict) -> dict:
    """A slot named by its arm, model, batch, task and repeat, with why it was classed so."""
    return {"arm": slot["arm"], "model": slot["model"], "batch": slot["batch"],
            "task": slot["task"], "repeat": slot["repeat"], "outcome": slot["outcome"],
            "reason": slot["reason"], "evidence": slot["why"]}


def one_condition_each(slots: list[dict], keys: tuple = CONDITIONS) -> dict[tuple[str, str], dict]:
    """Each arm's conditions, by arm and model, or a refusal naming the conditions that
    differ: runs of one arm under two conditions are two arms and are never pooled
    (LESSONS 7). Only runs with a record are read, since a run with none, a void the runner
    left no record of or a slot the box closed, has no record's conditions."""
    found: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for slot in slots:
        if slot["measured"] and slot["outcome"] != voids.CLOSED:
            found[(slot["arm"], slot["model"])].append(slot)
    out = {}
    for (arm, model), runs in found.items():
        seen = {json.dumps(run["conditions"], sort_keys=True) for run in runs}
        if len(seen) > 1:
            differ = sorted({key for run in runs for key in keys
                             if run["conditions"][key] != runs[0]["conditions"][key]})
            values = {key: sorted({str(run["conditions"][key]) for run in runs}) for key in differ}
            raise SystemExit(f"{arm} under {model} has runs under more than one condition, so they "
                             f"are not one arm and are never pooled (LESSONS 7): {values}. Analyse "
                             f"the batches of each condition on their own")
        out[(arm, model)] = runs[0]["conditions"]
    return out


# ---------------------------------------------------------------------------
# The figures

def correct(run: dict, key: str = "own") -> bool:
    return run.get(key) == "correct"


def ordered(arms) -> list[str]:
    return [a for a in ARMS if a in arms] + sorted(a for a in arms if a not in ARMS)


def short(task: str) -> str:
    return task.replace("apparel-", "")


def mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def summary(runs: list[dict], key=None) -> dict:
    """One arm's runs on one question, or pooled, as the tables show them. `key` says whether
    a run was correct, the task's own key by default (`correct`)."""
    key = correct if key is None else key
    def per(kind: str, what: str) -> float | None:
        return mean([run["pages"][what].get(kind, 0) for run in runs])

    costs = [run["cost"] for run in runs if run["cost"] is not None]
    # Under the buyable key where a question has one, and its own key where it has not, so a
    # pooled row reads as cell_facts' "right*" does.
    offer = any(run["buyable"] is not None for run in runs)
    missed = collections.Counter(sku for run in runs for sku in run["missed"])
    reasons = collections.Counter(run["reason"] for run in runs if run["outcome"] == voids.NOT_CORRECT)
    return {"runs": len(runs), "distinct": len(compare_cells.distinct(runs)),
            "correct": sum(key(run) for run in runs),
            "correct_buyable": (sum(correct(run, "own" if run["buyable"] is None else "buyable")
                                    for run in runs) if offer else None),
            "opened": [run["opened"] for run in runs],
            "opened_median": statistics.median(run["opened"] for run in runs) if runs else None,
            "cost_mean": mean(costs), "cost_total": sum(costs), "cost_missing": len(runs) - len(costs),
            "calls": mean([run["calls"] for run in runs]),
            "actions": mean([run["actions"] for run in runs]),
            "calls_results": per("results", "calls"), "calls_listings": per("listing", "calls"),
            "calls_other": per("other", "calls"),
            "actions_results": per("results", "actions"), "actions_listings": per("listing", "actions"),
            "actions_other": per("other", "actions"),
            "covered": sum(bool(run["covered"]) for run in runs), "missed": dict(missed),
            "asks": sum(run["asked"] for run in runs) + sum(run["agent_asks"] for run in runs),
            "agent_asks": sum(run["agent_asks"] for run in runs),
            "step": reasons["step budget"], "clock": reasons["clock"],
            "no_answer": reasons["no answer"], "abstention": reasons["abstention"],
            "closed": sum(run["outcome"] == voids.CLOSED for run in runs),
            "leaks": sum(bool(run["leaks"]) for run in runs),
            "outside": sum(bool(run["outside"]) for run in runs),
            "outside_pages": sorted({page for run in runs for page in run["outside"]})}


def tables(arms: dict[str, list[dict]]) -> dict:
    """Each arm by question, the control first, then pooled over the gated questions."""
    out = {}
    for arm in ordered(arms):
        runs = arms[arm]
        present = [q for q in QUESTIONS if any(run["task"] == q for run in runs)]
        present += sorted({run["task"] for run in runs} - set(QUESTIONS))
        out[arm] = {q: summary([run for run in runs if run["task"] == q]) for q in present}
        gated = [run for run in runs if run["task"] in GATED]
        if gated:
            out[arm]["pooled, gated"] = summary(gated)
    return out


def values(runs: list[dict], questions, value) -> dict[str, list]:
    """A measure by question, for the questions these runs asked."""
    out = {}
    for q in questions:
        got = [value(run) for run in runs if run["task"] == q]
        got = [v for v in got if v is not None]
        if got:
            out[q] = got
    return out


def compare_correct(a: list[dict], b: list[dict], questions, key=lambda run: correct(run)) -> dict:
    """Correct, A against B, by question then pooled, with the stratified exact test."""
    strata, shown = [], []
    for q in questions:
        ra = [run for run in a if run["task"] == q]
        rb = [run for run in b if run["task"] == q]
        if not ra or not rb:
            continue
        strata.append((sum(map(key, ra)), len(ra), sum(map(key, rb)), len(rb)))
        shown.append({"task": q, "a": [strata[-1][0], strata[-1][1]], "b": [strata[-1][2], strata[-1][3]]})
    pooled = [sum(s[0] for s in strata), sum(s[1] for s in strata),
              sum(s[2] for s in strata), sum(s[3] for s in strata)]
    return {"measure": "correct", "test": "stratified exact test by question (compare_cells.stratified_exact)",
            "per_question": shown, "pooled": {"a": pooled[:2], "b": pooled[2:]},
            "p": compare_cells.stratified_exact(strata) if strata else None}


def compare_ranks(a: list[dict], b: list[dict], questions, measure: str) -> dict:
    """A measure, A against B, by question then pooled, with the stratified exact rank test.
    A run without the measure, a cost no record gave, is left out and counted."""
    va = values(a, questions, lambda run: run[measure])
    vb = values(b, questions, lambda run: run[measure])
    both = [q for q in questions if q in va and q in vb]
    unknown = sum(1 for run in a + b if run["task"] in questions and run[measure] is None)
    result = {"measure": measure, "per_question": [{"task": q, "a": va[q], "b": vb[q]} for q in both],
              "pooled": {"a": [v for q in both for v in va[q]], "b": [v for q in both for v in vb[q]]},
              "left_out_without_a_value": unknown,
              "test": "stratified exact rank test (van Elteren, equal weights, mid-ranks)"}
    if not both:
        return {**result, "observed": None, "expected": None, "p": None}
    observed, expected, p = stratified_rank_test({q: va[q] for q in both}, {q: vb[q] for q in both})
    return {**result, "observed": observed, "expected": expected, "p": p}


def primary(arms: dict[str, list[dict]], h1_questions=None, h23_questions=None,
            block: list[dict] | None = None, key=lambda run: correct(run)) -> dict:
    """H1, H2 and H3 with Holm's correction over the three. The questions are the sets'
    unless given, read when called, so a protocol's own sets apply (`apply_sets`)."""
    h1_questions = INVARIANT if h1_questions is None else h1_questions
    h23_questions = GATED if h23_questions is None else h23_questions
    block = arms.get(BLOCK, []) if block is None else block
    tests = {"H1": {"a": BLOCK, "b": SHIPPED, "questions": list(h1_questions),
                    **compare_correct(block, arms.get(SHIPPED, []), h1_questions, key)},
             "H2": {"a": BLOCK, "b": OPEN, "questions": list(h23_questions),
                    **compare_ranks(block, arms.get(OPEN, []), h23_questions, "opened")},
             "H3": {"a": BLOCK, "b": OPEN, "questions": list(h23_questions),
                    **compare_ranks(block, arms.get(OPEN, []), h23_questions, "cost")}}
    adjusted = holm({name: test["p"] for name, test in tests.items()})
    for name, test in tests.items():
        test["p_holm"] = adjusted[name]
        test["rejected"] = adjusted[name] <= ALPHA
    return tests


def against_open(arms: dict[str, list[dict]]) -> dict:
    """Correct, the block against open everything, as counts with Newcombe intervals for the
    difference, by question and pooled, on the four reading-invariant questions. Never a
    test of equivalence."""
    block, other = arms.get(BLOCK, []), arms.get(OPEN, [])
    rows = []
    for q in INVARIANT:
        ra = [run for run in block if run["task"] == q]
        rb = [run for run in other if run["task"] == q]
        if ra and rb:
            rows.append(difference(q, sum(map(correct, ra)), len(ra), sum(map(correct, rb)), len(rb)))
    pooled = difference("pooled", sum(r["a"][0] for r in rows), sum(r["a"][1] for r in rows),
                        sum(r["b"][0] for r in rows), sum(r["b"][1] for r in rows))
    return {"a": BLOCK, "b": OPEN, "per_question": rows, "pooled": pooled}


def difference(task: str, x1: int, n1: int, x2: int, n2: int) -> dict:
    interval = newcombe(x1, n1, x2, n2)
    return {"task": task, "a": [x1, n1], "b": [x2, n2],
            "difference": (x1 / n1 - x2 / n2) if n1 and n2 else None,
            "interval": list(interval) if interval else None}


def stop_rule(arms: dict[str, list[dict]]) -> dict:
    """The block against the block without its stop rule, on the three questions where the
    rule acts: correct, opened and cost, unadjusted, exploratory."""
    a, b = arms.get(BLOCK, []), arms.get(NO_STOP, [])
    return {"a": BLOCK, "b": NO_STOP, "questions": list(STOP_RULE),
            "correct": compare_correct(a, b, STOP_RULE),
            "opened": compare_ranks(a, b, STOP_RULE, "opened"),
            "cost": compare_ranks(a, b, STOP_RULE, "cost")}


def coding_id(run: dict) -> str:
    return hashlib.sha1(f"{run['batch']}/{run['task']}-{run['repeat']}".encode()).hexdigest()[:8]


def count_stocked(arms: dict[str, list[dict]], task: str | None = None, order: list[str] | None = None) -> dict:
    """count-stocked as a table of arm by key, the box's ask counted as one user turn, and
    every answer on a sheet for its declared reading to be coded by hand without seeing the
    arm: ordered by an id made from the run's name, the arm kept apart in `coding_key`. A
    protocol named in a file gives its own count question with two readings and arm order."""
    task = COUNT_STOCKED if task is None else task
    table, sheet, key = {}, [], {}
    for arm in (ordered(arms) if order is None else order):
        if arm not in arms:
            continue
        runs = [run for run in arms[arm] if run["task"] == task]
        if not runs:
            continue
        table[arm] = {"runs": len(runs), "menu_key": sum(correct(run) for run in runs),
                      "buyable_key": sum(correct(run, "buyable") for run in runs),
                      "user_turns": sum(run["asked"] for run in runs)}
        for run in runs:
            sheet.append({"id": coding_id(run), "answer": run["answer"], "declared_reading": None})
            key[coding_id(run)] = {"arm": arm, "batch": run["batch"], "repeat": run["repeat"],
                                   "menu_key": run["own"], "buyable_key": run["buyable"]}
    return {"table": table, "sheet": sorted(sheet, key=lambda row: row["id"]), "coding_key": key}


def asks(arms: dict[str, list[dict]], order: list[str] | None = None) -> dict:
    """Asks on the clear and on the ambiguous questions, by arm: the box's asks and any ask
    the agent made itself. Ambiguous means the task has a second reading in its sidecar,
    written before any run, not whatever the box's own rule says: since the A+ market's,
    whose sidecar keys every question, the ones it names under `two_readings`."""
    out = {}
    for arm in (ordered(arms) if order is None else [a for a in order if a in arms]):
        runs = arms[arm]
        out[arm] = {}
        for label, wanted in (("clear", False), ("ambiguous", True)):
            group = [run for run in runs if run["ambiguous"] == wanted]
            out[arm][label] = {"runs": len(group), "asks": sum(run["asked"] for run in group),
                               "agent_asks": sum(run["agent_asks"] for run in group)}
    return out


def answer_check(arms: dict[str, list[dict]], order: list[str] | None = None) -> dict:
    """The block's answer check replayed from the logs (replay_box), per arm under the box,
    over the runs counted here: the wrong answers it refused and the correct ones, each
    judged under the reading the run answered, as replay_box judges it. An arm without the
    box has no plan to check against and is listed as such.

    replay_box replays a whole batch and stops at a row whose runner wrote no record, a void
    by voids.py's rule, so such a batch is named and left out of the replay, and the figures
    say how many of the arm's runs under the box were replayed."""
    out = {}
    for arm in (ordered(arms) if order is None else [a for a in order if a in arms]):
        runs = arms[arm]
        counted = {(run["batch"], run["task"], run["repeat"]) for run in runs}
        rows, failed = [], []
        for folder in dict.fromkeys(pathlib.Path(run["folder"]) for run in runs):
            try:
                rows += [row for row in replay_box.replay(folder)
                         if (row["batch"], row["task"], row["repeat"]) in counted]
            except FileNotFoundError as error:
                failed.append(f"{folder.name}: {error}")
        planned = sum(1 for run in runs if run["planned"])
        if not rows and not failed:
            out[arm] = None
            continue
        groups = {"wrong": [r for r in rows if r["verdict"] in replay_box.WRONG],
                  "correct": [r for r in rows if r["verdict"] == "correct"],
                  "other": [r for r in rows if r["verdict"] not in replay_box.WRONG + ("correct",)]}
        out[arm] = {"runs": len(rows), "planned": planned, "not_replayed": failed,
                    **{name: len(group) for name, group in groups.items()},
                    **{f"{name}_refused": [f"{r['batch']}/{r['task']}-{r['repeat']}: {r['flag']}"
                                           for r in group if not r["ok"]]
                       for name, group in groups.items()},
                    "not_reproduced": [f"{r['batch']}/{r['task']}-{r['repeat']}: {r['differs']}"
                                       for r in rows if not r["text_reproduced"]],
                    "decided_differently": [f"{r['batch']}/{r['task']}-{r['repeat']}: {r['change']}"
                                            for r in rows if r["today"] == "unexpected"]}
    return out


def sensitivity(arms: dict[str, list[dict]], voided: list[dict]) -> dict:
    """The primary tests again under each sensitivity the protocol names."""
    out = {}
    out["without both offer questions"] = primary(
        arms, [q for q in INVARIANT if q not in OFFER], [q for q in GATED if q not in OFFER])
    out["count-stocked under the menu key"] = primary(arms, INVARIANT + (COUNT_STOCKED,))
    # Under the buyable key the block's count-stocked runs are the ones whose user said
    # buyable, every other question's are the block's own, and count-stocked is scored under
    # the buyable key in both arms.
    block = ([run for run in arms.get(BLOCK, []) if run["task"] != COUNT_STOCKED]
             + [run for run in arms.get(BUYABLE, []) if run["task"] == COUNT_STOCKED])
    out["count-stocked under the buyable key"] = primary(
        arms, INVARIANT + (COUNT_STOCKED,), block=block,
        key=lambda run: correct(run, "buyable" if run["task"] == COUNT_STOCKED else "own"))
    out["distinct runs only"] = primary({arm: compare_cells.distinct(runs) for arm, runs in arms.items()})
    with_voids = {arm: runs + [s for s in voided if s["measured"] and s["arm"] == arm]
                  for arm, runs in arms.items()}
    out["with the voids included"] = primary(with_voids)
    out["without the runs that saw a hidden price"] = primary(
        {arm: [run for run in runs if not run["leaks"]] for arm, runs in arms.items()})
    return out


def analyse(lines: list[Line], manifest: Manifest | None = None) -> dict:
    """Every figure, as data: `render` prints it and the JSON is it."""
    problems = list(manifest.problems) if manifest else []
    if manifest is not None and (len(manifest.starts) != 1 or len(manifest.ends) != 1):
        problems.append(f"the manifest holds {len(manifest.starts)} start and {len(manifest.ends)} "
                        f"end lines, where one run of the command writes one of each")
    loaded = []
    for line in lines:
        if line.folder is None or not (line.folder / "suite.json").exists():
            problems.append(f"a {line.kind} line names no batch folder with a suite.json "
                            f"({line.folder or 'none'}): {line.args}")
            continue
        payload, slots, found = load_folder(line.folder)
        problems += found
        if line.kind == "batch" and line.args:
            arm, reading, wanted = intended(line.args)
            recorded = payload.get("arm") or flagged_arm(payload)
            if recorded != arm or payload.get("reading") != reading:
                problems.append(f"{line.folder.name}: the manifest's arguments ask for arm {arm}, "
                                f"reading {reading}; its payload says {recorded}, "
                                f"{payload.get('reading')}. The payload's is used")
            got = sorted((s["task"], s["repeat"]) for s in slots)
            if got != sorted(wanted):
                problems.append(f"{line.folder.name}: the manifest's arguments ask for "
                                f"{sorted(wanted)}, the batch holds {got}")
        loaded.append((line, payload, slots))
    population = assemble(loaded, manifest is not None)
    problems += population["problems"]
    every = [slot for _, _, slots in loaded for slot in slots]
    conditions = one_condition_each(population["kept"] + population["voided"])
    models = sorted({slot["model"] for slot in population["kept"]} | {m["model"] for m in population["missing"]},
                    key=str)
    out = {"analysis_version": VERSION, "scorer_version": scoring.VERSION,
           "protocol": "docs/content/claim-protocol.md",
           "source": source(lines, manifest, every), "problems": problems, "models": {}}
    for model in models:
        out["models"][str(model)] = per_model(model, population, conditions)
    return out


def source(lines: list[Line], manifest: Manifest | None, every: list[dict]) -> dict:
    """What was read: the lines, and the spend the manifest recorded against the provider's
    charges summed over every run of every folder it names, voids included (LESSONS 6)."""
    charges = sum(slot.get("cost") or 0 for slot in every)
    out = {"lines": [{"kind": line.kind, "folder": str(line.folder) if line.folder else None,
                      "args": line.args} for line in lines],
           "charges": charges}
    if manifest is not None:
        start = manifest.starts[0] if manifest.starts else {}
        end = manifest.ends[-1] if manifest.ends else {}
        moved = (end["usage"] - start["usage"]) if end.get("usage") is not None and \
            start.get("usage") is not None else None
        out.update({"starts": manifest.starts, "ends": manifest.ends, "stops": manifest.stops,
                    "account_moved": moved, "cap": start.get("cap")})
    return out


def question_text(files: dict[str, str]) -> list[str]:
    """Each of the protocol's six questions whose text is not byte for byte the same in every
    arm's task file (LESSONS 10), as the question and the files it differs between. Empty when
    it is the same everywhere. The text is the task's own, before any arm's instruction."""
    texts = {}
    for arm, name in files.items():
        if name and (paths.TASKS / name).exists():
            texts[arm] = {t["id"]: t["query"] for t in json.loads((paths.TASKS / name).read_text())["tasks"]}
    differ = []
    for q in QUESTIONS:
        seen = {arm: text[q] for arm, text in texts.items() if q in text}
        if len(set(seen.values())) > 1:
            differ.append(f"{short(q)}: " + "; ".join(f"{arm} {files[arm]}" for arm in seen))
    return differ


def per_model(model: str | None, population: dict, conditions: dict) -> dict:
    """Everything for one model's arms. Two models are never pooled."""
    kept = [s for s in population["kept"] if s["model"] == model]
    arms = {arm: [s for s in kept if s["arm"] == arm] for arm in ordered({s["arm"] for s in kept})}
    voided = [s for s in population["voided"] if s["model"] == model]
    held, differ = {}, {}
    mine = {arm: conditions[(arm, model)] for arm in arms if (arm, model) in conditions}
    for key in CONDITIONS:
        if key in BOX_CONDITIONS:
            continue
        seen = {arm: c[key] for arm, c in mine.items()}
        if len(set(map(str, seen.values()))) <= 1:
            held[key] = next(iter(seen.values()), None)
        else:
            differ[key] = seen
    # Arms on two markets are not a comparison at all (LESSONS 7, 19): refused, not reported.
    if "draw" in differ:
        raise SystemExit(f"the arms under {model} ran on more than one market draw, so they are "
                         f"never set against each other: {differ['draw']}")
    filled = collections.Counter((s["arm"], s["task"], s["repeat"]) for s in kept)
    design = {"slots": 0, "filled": 0, "missing": [], "outside": []}
    for arm, questions in DESIGN.items():
        for task in questions:
            for repeat in ROUNDS:
                design["slots"] += 1
                if filled[(arm, task, repeat)]:
                    design["filled"] += 1
                else:
                    design["missing"].append(f"{arm}, {short(task)} repeat {repeat}")
    design["outside"] = sorted(f"{arm}, {short(task)} repeat {repeat}"
                               for (arm, task, repeat) in filled
                               if task not in DESIGN.get(arm, ()) or repeat not in ROUNDS)
    not_correct = [brief(s) for s in kept if s["outcome"] == voids.NOT_CORRECT]
    return {
        "arms": {arm: {"batches": sorted({s["batch"] for s in runs}), "runs": len(runs),
                       "repeats": sorted({s["repeat"] for s in runs}),
                       "distinct": len(compare_cells.distinct(runs)), "conditions": mine.get(arm)}
                 for arm, runs in arms.items()},
        "conditions": {"held": held, "differ": differ,
                       "question_text": question_text({arm: c["tasks_file"] for arm, c in mine.items()})},
        "exclusions": {"voids": [brief(s) for s in voided], "replaced": [r for r in population["replaced"]
                                                                       if r["model"] == model],
                       "missing": [m for m in population["missing"] if m["model"] == model],
                       "not_correct": not_correct, "design": design},
        "tables": tables(arms),
        "primary": primary(arms),
        "against_open_everything": against_open(arms),
        "secondary": {"stop_rule": stop_rule(arms), "count_stocked": count_stocked(arms),
                      "asks": asks(arms), "answer_check": answer_check(arms)},
        "sensitivity": sensitivity(arms, voided),
        "runs": [{key: s.get(key) for key in ("arm", "batch", "task", "repeat", "outcome", "reason",
                                              "own", "buyable", "opened", "skus", "covered", "missed",
                                              "cost", "calls", "actions", "pages", "asked",
                                              "agent_asks", "leaks", "outside", "reading", "answer")}
                 for s in kept],
    }


# ---------------------------------------------------------------------------
# The report

def p_text(p: float | None) -> str:
    if p is None:
        return "not computed"
    return f"{p:.5f}" if p >= 1e-4 else f"{p:.2e}"


def money(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def number(value: float | None, digits: int = 1) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def render(result: dict) -> str:
    out = []
    say = out.append
    say(f"The claim analysis, as docs/content/claim-protocol.md fixes it (claim.py v{result['analysis_version']}, "
        f"every answer scored again by score.py v{result['scorer_version']})")
    src = result["source"]
    kinds = collections.Counter(line["kind"] for line in src["lines"])
    say("Read " + ", ".join(f"{n} {kind}{'s' if n > 1 else ''}" if kind == "folder" else
                            f"{n} {kind} line{'s' if n > 1 else ''}" for kind, n in kinds.items())
        + f"; the provider's charges summed over every run in them, voids included: ${src['charges']:.4f}")
    if "starts" in src:
        start = src["starts"][0] if src["starts"] else {}
        end = src["ends"][-1] if src["ends"] else {}
        say(f"Started {start.get('at', '-')}, ended {end.get('at', '-')}; the account moved "
            + (f"${src['account_moved']:.4f}" if src["account_moved"] is not None else "(not read)")
            + f"; cap ${src['cap']}" + (f"; stops: {'; '.join(src['stops'])}" if src["stops"] else "; no stop"))
    say(f"\nProblems found: {len(result['problems'])}")
    for text in result["problems"]:
        say(f"  {text}")
    for model, m in result["models"].items():
        say(f"\n{'=' * 100}\nModel {model}. Each model is its own result and is never pooled with another.")
        render_model(m, say)
    return "\n".join(out)


def held_line(held: dict) -> str:
    """The conditions every arm shares, as the report prints them. A run before 22 October
    2026 recorded no step or clock limit, and is said to have recorded none rather than shown
    as None, which would read as no limit: it ran under the agent's own, 100 steps and 600 s
    (`suite.DEFAULT_MAX_STEPS`, `suite.DEFAULT_CLOCK_S`), unless the shell set another, which
    nothing records. Every other condition is printed as it is."""
    shown = {key: ("not recorded" if value is None and key in UNRECORDED_BEFORE_LIMITS else value)
             for key, value in held.items()}
    return "Held constant across the arms: " + "; ".join(f"{key} {value}" for key, value in shown.items())


def render_model(m: dict, say) -> None:
    say("\nArms, each from its batches' payloads:")
    for arm, a in m["arms"].items():
        say(f"  {arm:34} {a['runs']:>3} runs, {a['distinct']:>3} distinct, repeats "
            f"{', '.join(map(str, a['repeats']))}   batches {', '.join(a['batches'])}")
    say(held_line(m["conditions"]["held"]))
    for key, seen in m["conditions"]["differ"].items():
        say(f"  DIFFERS between arms, {key}: " + "; ".join(f"{arm} {value}" for arm, value in seen.items()))
    say("The six questions' text in the arms' task files: " + (
        "the same byte for byte" if not m["conditions"]["question_text"] else
        "DIFFERS, " + " | ".join(m["conditions"]["question_text"])))

    e = m["exclusions"]
    say("\nExclusions, decided from the logs and the records before any answer was read:")
    say(f"  voids {len(e['voids'])}" + "".join(f"\n    {v['batch']}/{v['task']}-{v['repeat']} ({v['arm']}): "
                                               f"{v['reason']}, {v['evidence']}" for v in e["voids"]))
    for r in e["replaced"]:
        say(f"    replaced by its re-run in {r['by']}: {r['batch']}/{r['task']}-{r['repeat']}")
    say(f"  missing {len(e['missing'])}" + "".join(f"\n    {x['batch']}/{x['task']}-{x['repeat']} "
                                                   f"({x['arm']}): {x['why']}" for x in e["missing"]))
    reasons = collections.Counter(x["reason"] for x in e["not_correct"])
    say("  not correct, kept and reported apart: "
        + (", ".join(f"{reason} {n}" for reason, n in sorted(reasons.items())) or "none")
        + "".join(f"\n    {x['batch']}/{x['task']}-{x['repeat']} ({x['arm']}): {x['reason']}, {x['evidence']}"
                  for x in e["not_correct"]))
    d = e["design"]
    say(f"  the protocol's design, {d['slots']} slots: {d['filled']} filled, {len(d['missing'])} empty"
        + (f": {'; '.join(d['missing'])}" if d["missing"] else "")
        + (f"; outside the design: {'; '.join(d['outside'])}" if d["outside"] else ""))

    say("\n1. Each arm by question, then pooled over the gated questions. The unit is a run.")
    say("   correct: under the task's own key. buyable: under the buyable key on the two offer "
        "questions, and pooled with the own key on the rest.")
    say("   opened: the market's listings opened, median [each run]. needs: opened what the answer needs.")
    say("   $/run: the provider's charge. actions: browser actions a run, all/results page/listings.")
    say("   asks: the box's (one user turn each) and the agent's. step, clock, none, abst: not correct "
        "for the step budget, the clock, no answer, an abstention.")
    for arm, questions in m["tables"].items():
        say(f"  {arm}")
        say(f"    {'question':16} {'runs':>4} {'dist':>4} {'correct':>7} {'buyable':>7}  {'opened':28} "
            f"{'needs':>5} {'$/run':>6} {'actions':>15} {'asks':>4} {'step':>4} {'clock':>5} {'none':>4} "
            f"{'abst':>4} {'leak':>4} {'outside':>7}")
        for q, s in questions.items():
            opened = (f"{s['opened_median']:g} " if s["opened_median"] is not None else "- ") + \
                (str(s["opened"]) if len(s["opened"]) <= 6 else "")
            actions = f"{number(s['actions'])}/{number(s['actions_results'])}/{number(s['actions_listings'])}"
            buyable = f"{s['correct_buyable']}/{s['runs']}" if s["correct_buyable"] is not None else "-"
            say(f"    {short(q):16} {s['runs']:>4} {s['distinct']:>4} {str(s['correct']) + '/' + str(s['runs']):>7} "
                f"{buyable:>7}  {opened:28} {str(s['covered']) + '/' + str(s['runs']):>5} "
                f"{money(s['cost_mean']):>6} {actions:>15} {s['asks']:>4} {s['step']:>4} {s['clock']:>5} "
                f"{s['no_answer']:>4} {s['abstention']:>4} {s['leaks']:>4} {s['outside']:>7}")
            if s["missed"] and q != "pooled, gated":
                say(f"      not opened though the answer needs them: "
                    + ", ".join(f"{sku} ({n})" for sku, n in sorted(s["missed"].items())))
            if s["outside_pages"] and q != "pooled, gated":
                say(f"      product pages outside the market: {', '.join(s['outside_pages'])}")
            if s["cost_missing"]:
                say(f"      {s['cost_missing']} runs with no cost figure")

    say("\n2. Primary tests, two-sided, with Holm's correction over the three")
    labels = {"H1": "correct", "H2": "listings opened", "H3": "cost a run"}
    for name, t in m["primary"].items():
        say(f"  {name} {labels[name]}, {t['a']} against {t['b']}, on "
            + ", ".join(short(q) for q in t["questions"]))
        if not t["per_question"]:
            say("     not computed: an arm has no runs on these questions, so Holm counts it as p = 1")
            continue
        say("     " + render_test(t))
        say(f"     {t['test']}: " + (f"rank sum {number(t['observed'])} against {number(t['expected'])} "
                                      f"expected, " if "observed" in t and t["observed"] is not None else "")
            + f"p = {p_text(t['p'])}, Holm p = {p_text(t['p_holm'])}"
            + ("  rejected at 0.05" if t["rejected"] else "  not rejected at 0.05"))

    o = m["against_open_everything"]
    say(f"\n3. Correct, {o['a']} against {o['b']}, on the four reading-invariant questions: counts and "
        "Newcombe's 95% hybrid score interval for the difference. Never a test of equivalence: so few "
        "runs an arm cannot show two arms are equal (the protocol, Analysis).")
    for row in o["per_question"] + [o["pooled"]]:
        say(f"     {short(row['task']):16} {row['a'][0]}/{row['a'][1]} against {row['b'][0]}/{row['b'][1]}"
            + (f", difference {row['difference']:+.2f}, interval {row['interval'][0]:+.3f} to "
               f"{row['interval'][1]:+.3f}" if row["interval"] else ", no interval: an arm has no runs"))

    s = m["secondary"]
    say("\n4. Secondary and exploratory")
    sr = s["stop_rule"]
    say(f"  a. The stop rule's own effect, {sr['a']} against {sr['b']}, on "
        + ", ".join(short(q) for q in sr["questions"]) + ", unadjusted")
    for what in ("correct", "opened", "cost"):
        t = sr[what]
        say(f"     {what:8} " + (f"{render_test(t)}; p = {p_text(t['p'])}" if t["per_question"] else
                                 "not computed: an arm has no runs on these questions"))
    cs = s["count_stocked"]
    say("  b. count-stocked, arm by key. The box's ask is one user turn.")
    for arm, row in cs["table"].items():
        say(f"     {arm:34} {row['runs']} runs: correct under the menu key {row['menu_key']}, "
            f"under the buyable key {row['buyable_key']}; user turns {row['user_turns']}")
    say(f"     The answers, for their declared reading to be coded by hand without seeing the arm "
        f"({len(cs['sheet'])}; the arm of each id is in the JSON, coding_key):")
    for row in cs["sheet"]:
        say(f"       [{row['id']}] declared reading: ______  " + " ".join(row["answer"].split()))
    say("  c. Asks, the box's and the agent's own, on the clear and the ambiguous questions")
    for arm, row in s["asks"].items():
        say(f"     {arm:34} clear {row['clear']['asks']} of {row['clear']['runs']} runs, ambiguous "
            f"{row['ambiguous']['asks']} of {row['ambiguous']['runs']}"
            + (f" (the agent's own: {row['clear']['agent_asks'] + row['ambiguous']['agent_asks']})"
               if row["clear"]["agent_asks"] + row["ambiguous"]["agent_asks"] else ""))
    say("  d. The answer check replayed from the logs (replay_box), each run judged under the reading "
        "it answered. Blind to a misread price and to a miscount once every listing is opened")
    for arm, row in s["answer_check"].items():
        if row is None:
            say(f"     {arm:34} no plan, so nothing to replay")
            continue
        say(f"     {arm:34} {row['runs']} of the {row['planned']} runs the box planned: wrong "
            f"{row['wrong']}, refused {len(row['wrong_refused'])}; correct {row['correct']}, refused "
            f"{len(row['correct_refused'])}; other {row['other']}, refused {len(row['other_refused'])}")
        for name in ("wrong_refused", "correct_refused", "other_refused", "not_reproduced",
                     "decided_differently", "not_replayed"):
            for text in row[name]:
                say(f"       {name.replace('_', ' ')}: {text}")
    say("  e. Calls by page type, a run: all calls on the results page / on listings / elsewhere, "
        "and the browser actions among them")
    for arm, questions in m["tables"].items():
        for q, t in questions.items():
            say(f"     {arm:34} {short(q):16} calls {number(t['calls'])}: {number(t['calls_results'])} / "
                f"{number(t['calls_listings'])} / {number(t['calls_other'])};  actions {number(t['actions'])}: "
                f"{number(t['actions_results'])} / {number(t['actions_listings'])} / {number(t['actions_other'])}")

    say("\n5. Sensitivity: the primary tests again, p (Holm p)")
    say(f"     {'':44} {'H1 correct':>22} {'H2 opened':>22} {'H3 cost':>22}")
    for name, tests in m["sensitivity"].items():
        say(f"     {name:44} " + " ".join(f"{p_text(t['p']) + ' (' + p_text(t['p_holm']) + ')':>22}"
                                          for t in tests.values()))


def render_test(t: dict) -> str:
    """By question, then pooled: counts for a proportion, medians for the rest (each run's
    value is in the JSON)."""
    if t["measure"] == "correct":
        parts = [f"{short(r['task'])} {r['a'][0]}/{r['a'][1]} against {r['b'][0]}/{r['b'][1]}"
                 for r in t["per_question"]]
        pooled = t["pooled"]
        return ", ".join(parts) + f"; pooled {pooled['a'][0]}/{pooled['a'][1]} against " \
                                  f"{pooled['b'][0]}/{pooled['b'][1]}"
    fmt = (lambda v: f"{v:.3f}") if t["measure"] == "cost" else (lambda v: f"{v:g}")
    parts = [f"{short(r['task'])} {fmt(statistics.median(r['a']))} against {fmt(statistics.median(r['b']))}"
             for r in t["per_question"]]
    pooled = t["pooled"]
    tail = (f"; pooled median {fmt(statistics.median(pooled['a']))} against "
            f"{fmt(statistics.median(pooled['b']))}" if pooled["a"] and pooled["b"] else "")
    left = f"; {t['left_out_without_a_value']} runs without a value left out" \
        if t["left_out_without_a_value"] else ""
    return "medians, " + ", ".join(parts) + tail + left


# ---------------------------------------------------------------------------
# A protocol named in a file: the second claim (22 October 2026)
#
# The first claim's analysis above is written for its five arms and six questions, and is
# the default. A protocol may instead name its arms, question sets, design and primary tests
# in a file (`--protocol`, experiments/tasks/claim2_analysis.json for the second claim), fixed
# before any of its data exists. The machinery is the first claim's: the same slots from
# voids.py and verify_cells, the same exclusions, the same tests and the same Holm. What a
# run counts as correct is the key for the reading it was answered under (score v4), which
# under the first claim's arms was always the task's own.

# Bumped when a figure the protocol path prints would change for the same runs and file.
#   1  22 October 2026, before the second claim run
#   2  23 October 2026, from the verifier's fairness audit, before the second claim run. H2
#      and H3 count only the slots where the agent ran, and list the closed ones beside them
#      by question (`one_test`): a slot the box closes, an ask with no reply or a decline,
#      entered them as 0 listings and the parse's cost, and only the model arm closes them.
#      The runs that sorted the results or changed their page size are counted by arm
#      (`toolbar_table`). H4 is also reported on the pre-specified splits the file names
#      (`split_tests`), unadjusted. Each model's role, primary or replication, is the file's,
#      each with its own Holm over its four. The shipped arm's wrong answers are coded by
#      written rules (`failure_breakdown`). Three sensitivities: the closed slots in H2 and
#      H3, without the runs that sorted or changed the page size, and H4 by rewording
PROTOCOL_ANALYSIS_VERSION = 2
# The conditions a protocol's arms are held to: the first claim's and the model parser's,
# the open-everything wording, the agent's limits. Of them, the ones an arm has by design.
PROTOCOL_CONDITIONS = CONDITIONS + ("parser", "parser_model", "parser_temperature", "prompt_version",
                                    "normalise_version", "exhaustive_wording")
PROTOCOL_ARM_CONDITIONS = BOX_CONDITIONS + ("parser", "parser_model", "parser_temperature", "prompt_version",
                                            "normalise_version", "exhaustive_wording")
TEST_MEASURES = ("correct", "opened", "cost", "tokens_total")
SENSITIVITIES = ("without the two-reading questions", "distinct runs only", "with the voids included",
                 "without the runs that saw a hidden price",
                 # 23 October 2026, from the verifier's fairness audit (protocol analysis v2).
                 "with the closed slots in H2 and H3",
                 "without the runs that sorted or changed the page size",
                 "H4 by rewording, not by run")
# The roles a protocol file gives its models (v2): one primary, whose tests are the claim, and
# replications, each with its own Holm.
ROLES = ("primary", "replication")
# The shipped arm's failure codes, in the order they are tried, each rule `failure_code`'s.
FAILURE_CODES = ("page 2 never reached", "a card or sold-out price taken", "other")
# The sets a protocol file must name, and the one the design calls every template question.
PROTOCOL_SETS = ("control", "decline", "gated", "two_readings", "reading_independent",
                 "count_two_readings", "held_out")


@dataclasses.dataclass
class Protocol:
    """A protocol file, checked, and its sets resolved against the claim's task file."""
    path: pathlib.Path
    config: dict
    names: dict                     # (recorded arm, reading) -> the protocol's arm name
    arms: tuple                     # the arms, in the file's order
    sets: dict                      # name -> question ids, `held_out` from the task file
    templates_of: dict              # a held-out rewording's id -> its template's
    keyed: frozenset                # the questions with an answer key
    design: dict                    # arm -> the questions it asks every round
    rounds: tuple
    tests: dict
    require: dict
    models: tuple
    roles: dict = dataclasses.field(default_factory=dict)      # model -> "primary" or "replication"
    splits: dict = dataclasses.field(default_factory=dict)     # test -> {label: (set, set)}
    breakdown: dict = dataclasses.field(default_factory=dict)  # the shipped arm's failure codes


def check_protocol(config: dict) -> list[str]:
    """Why a protocol file cannot be analysed, before any batch is read: every arm a test,
    the design or the comparison names is one of its arms, every set one it names, every
    measure and sensitivity one this analysis has, and every required condition one a run
    records."""
    found = []
    arms = config.get("arms") or {}
    sets = config.get("sets") or {}
    for key in PROTOCOL_SETS:
        if key not in sets:
            found.append(f"the protocol names no {key} set")
    for name, arm in arms.items():
        if not isinstance(arm, dict) or "arm" not in arm or "reading" not in arm:
            found.append(f"arm {name!r} does not say what its payloads record (arm, reading)")
    pairs = [(arm.get("arm"), arm.get("reading")) for arm in arms.values() if isinstance(arm, dict)]
    if len(set(pairs)) != len(pairs):
        found.append("two arms record the same instruction and reading")
    for name, test in (config.get("tests") or {}).items():
        for side in ("a", "b"):
            if test.get(side) not in arms:
                found.append(f"{name} compares an arm the protocol has not: {test.get(side)!r}")
        if test.get("measure") not in TEST_MEASURES or test.get("also", "tokens_total") not in TEST_MEASURES:
            found.append(f"{name} measures what this analysis does not: {test.get('measure')!r}")
        if test.get("on") not in sets:
            found.append(f"{name} is on a set the protocol does not name: {test.get('on')!r}")
        if test.get("strata") not in ("question", "template"):
            found.append(f"{name} is stratified by {test.get('strata')!r}, not by question or template")
        if test.get("strata") == "template" and test.get("on") != "held_out":
            found.append(f"{name} is stratified by template, which only the held-out rewordings have")
    if len(config.get("tests") or {}) < 1:
        found.append("the protocol names no primary test")
    for arm, groups in ((config.get("design") or {}).get("asks") or {}).items():
        if arm not in arms:
            found.append(f"the design has an arm the protocol has not ask questions: {arm!r}")
        for group in groups:
            if group != "templates" and group not in sets:
                found.append(f"the design has {arm} ask a set the protocol does not name: {group!r}")
    against = config.get("against_open_everything") or {}
    if against and (against.get("a") not in arms or against.get("b") not in arms or against.get("on") not in sets):
        found.append("the comparison with open everything names an arm or set the protocol has not")
    for name in config.get("sensitivity") or []:
        if name not in SENSITIVITIES:
            found.append(f"no sensitivity this analysis can run is called {name!r}")
    for key in config.get("require") or {}:
        if key not in PROTOCOL_CONDITIONS:
            found.append(f"the protocol requires {key!r}, which no run records")
    # Since protocol analysis v2 (23 October 2026): each model's role, the splits of a test,
    # and the shipped arm's failure codes, every one named before any run.
    roles = config.get("roles") or {}
    if roles:
        if sorted(roles) != sorted(config.get("models") or []):
            found.append("the roles are not the protocol's models, one each")
        if any(role not in ROLES for role in roles.values()):
            found.append(f"a model's role is not one of {', '.join(ROLES)}")
        if list(roles.values()).count("primary") != 1:
            found.append("the roles name other than one primary model")
    for name, splits in (config.get("splits") or {}).items():
        if name not in (config.get("tests") or {}):
            found.append(f"the splits are of a test the protocol has not: {name!r}")
        for label, parts in splits.items():
            if len(parts) != 2 or any(part not in sets for part in parts):
                found.append(f"the split {label!r} of {name} is not two sets the protocol names")
    breakdown = config.get("failure_breakdown") or {}
    if breakdown:
        if breakdown.get("arm") not in arms or breakdown.get("on") not in sets:
            found.append("the failure breakdown names an arm or set the protocol has not")
        if tuple(code.get("code") for code in breakdown.get("codes") or []) != FAILURE_CODES:
            found.append(f"the failure breakdown's codes are not this analysis's, in order: "
                         f"{', '.join(FAILURE_CODES)}")
        if not isinstance(breakdown.get("page_size"), int):
            found.append("the failure breakdown names no page size")
    return found


def resolve_protocol(path: pathlib.Path, config: dict, spec: dict) -> Protocol:
    """The protocol file's sets as question ids of the claim's task file `spec`. The held-out
    rewordings are its tasks with a template, read by id and template only. Every id a set
    names must be a task of the file, or this refuses."""
    tasks = {task["id"]: task for task in spec["tasks"]}
    sets = {}
    for key, value in config["sets"].items():
        if key == "held_out":
            sets[key] = tuple(task_id for task_id, task in tasks.items() if task.get(value))
        elif isinstance(value, str):
            sets[key] = value
        else:
            sets[key] = tuple(value)
    named = {q for key, value in sets.items() if not isinstance(value, str) for q in value}
    named |= {value for value in sets.values() if isinstance(value, str)}
    stray = sorted(named - set(tasks))
    if stray:
        raise SystemExit(f"the protocol's sets name questions {spec.get('fixture') or 'the task file'} "
                         f"does not hold: {stray}")
    templates_of = {task_id: tasks[task_id]["template"] for task_id in sets["held_out"]}
    templates = tuple(task_id for task_id, task in tasks.items() if not task.get("template"))
    design = {}
    for arm, groups in config["design"]["asks"].items():
        design[arm] = tuple(dict.fromkeys(q for group in groups
                                          for q in (templates if group == "templates" else sets[group])))
    keyed = frozenset(task_id for task_id, task in tasks.items() if task["expect"].get("kind") != "none")
    protocol = Protocol(path=path, config=config,
                        names={(arm["arm"], arm["reading"]): name for name, arm in config["arms"].items()},
                        arms=tuple(config["arms"]), sets=sets, templates_of=templates_of, keyed=keyed,
                        design=design, rounds=tuple(config["design"]["rounds"]), tests=config["tests"],
                        require=config.get("require") or {}, models=tuple(config.get("models") or ()),
                        roles=dict(config.get("roles") or {}),
                        splits={name: {label: tuple(parts) for label, parts in splits.items()}
                                for name, splits in (config.get("splits") or {}).items()},
                        breakdown=dict(config.get("failure_breakdown") or {}))
    # A split is of the strata its test is on, the two parts disjoint and every stratum in
    # one: for H4, the thirteen keyed templates the rewordings reword.
    for name, splits in protocol.splits.items():
        universe = strata_of(protocol.tests[name], protocol)
        for label, parts in splits.items():
            first, second = (set(sets[part]) for part in parts)
            if first & second or first | second != set(universe):
                raise SystemExit(f"the split {label!r} of {name} does not divide its {len(universe)} "
                                 f"strata in two: {sorted(set(universe) ^ (first | second))} "
                                 f"{'and the parts overlap' if first & second else ''}".strip())
    return protocol


def answered_correct(run: dict) -> bool:
    """Correct under the key for the reading the run was answered under (score v4)."""
    return run.get("verdict") == "correct"


def scored(runs: list[dict]) -> list[dict]:
    """The runs a key judged. A run with no key for the reading it answered is unscored and
    is never counted as wrong (LESSONS 34): a test of correct leaves it out, and the analysis
    lists it as a problem, since suite.py refuses a batch that could produce one."""
    return [run for run in runs if run.get("verdict") != "unscored"]


def questions_of(spec: dict, protocol: Protocol, drop: frozenset = frozenset()) -> list[str]:
    """The questions a test reads: its set's, less `drop` and the rewordings of a dropped
    template, and for a test of correct only those with a key."""
    return [q for q in protocol.sets[spec["on"]] if q not in drop
            and protocol.templates_of.get(q) not in drop
            and (spec["measure"] != "correct" or q in protocol.keyed)]


def strata_of(spec: dict, protocol: Protocol, drop: frozenset = frozenset()) -> list[str]:
    """A test's strata: its questions, or for a test by template the templates they reword."""
    questions = questions_of(spec, protocol, drop)
    if spec["strata"] == "template":
        return list(dict.fromkeys(protocol.templates_of[q] for q in questions))
    return questions


def by_rewording(runs: list[dict], templates_of: dict) -> list[dict]:
    """One unit a held-out rewording, for H4 at the level its parsers act on (23 October 2026):
    both parsers are deterministic, so the box makes one plan of each rewording whatever the
    round, and the rounds repeat the agent, not the parse. A unit is the share of the
    rewording's runs that a key judged and that were correct, under its template."""
    groups = collections.defaultdict(list)
    for run in scored(runs):
        groups[run["task"]].append(answered_correct(run))
    return [{"task": templates_of[rewording], "rewording": rewording, "share": sum(got) / len(got)}
            for rewording, got in groups.items()]


def one_test(spec: dict, arms: dict[str, list[dict]], protocol: Protocol, drop: frozenset = frozenset(),
             closed_in: bool = False, rewordings: bool = False) -> dict:
    """One of the protocol's tests, two-sided and unadjusted. A test of correct counts only
    the questions with a key, and a test stratified by template sets each held-out
    rewording's runs under its template's stratum.

    A test of what a run opened or cost counts only the slots where the agent ran (protocol
    analysis v2, 23 October 2026, from the verifier's audit). A slot the box closes, an ask
    no reply answered or a decline, runs no agent: it entered H2 and H3 as 0 listings and the
    parse's cost, and only the model arm closes slots on the gated questions, so it could
    only favour the model. The closed slots are left out and listed by question and arm;
    `closed_in` puts them back, for the sensitivity. `rewordings` takes a test by template at
    one unit a rewording (`by_rewording`), for the sensitivity."""
    questions = questions_of(spec, protocol, drop)
    a, b = arms.get(spec["a"], []), arms.get(spec["b"], [])
    if spec["strata"] == "template":
        strata = strata_of(spec, protocol, drop)
        if rewordings:
            a = by_rewording([run for run in a if run["task"] in questions], protocol.templates_of)
            b = by_rewording([run for run in b if run["task"] in questions], protocol.templates_of)
        else:
            a = [{**run, "task": protocol.templates_of[run["task"]]} for run in a if run["task"] in questions]
            b = [{**run, "task": protocol.templates_of[run["task"]]} for run in b if run["task"] in questions]
    else:
        strata = questions
    closed = []
    if spec["measure"] != "correct":
        for q in strata:
            shut = {side: sum(1 for run in runs if run["task"] == q and run.get("outcome") == voids.CLOSED)
                    for side, runs in (("a", a), ("b", b))}
            if shut["a"] or shut["b"]:
                closed.append({"task": q, **shut})
        if not closed_in:
            a = [run for run in a if run.get("outcome") != voids.CLOSED]
            b = [run for run in b if run.get("outcome") != voids.CLOSED]
    if spec["measure"] == "correct" and rewordings and spec["strata"] == "template":
        result = compare_ranks(a, b, strata, "share")
        result["test"] = ("stratified exact rank test by template on each rewording's share of its runs "
                          "correct (van Elteren, equal weights, mid-ranks)")
        result["unit"] = "rewording"
    elif spec["measure"] == "correct":
        result = compare_correct(scored(a), scored(b), strata, answered_correct)
        if spec["strata"] == "template":
            result["test"] = "stratified exact test by template (compare_cells.stratified_exact)"
    else:
        result = compare_ranks(a, b, strata, spec["measure"])
    result.update({"a": spec["a"], "b": spec["b"], "on": spec["on"], "strata": spec["strata"],
                   "questions": strata})
    if spec["measure"] != "correct":
        result["closed"] = closed
        result["closed_rule"] = "in" if closed_in else "left out"
    if spec.get("also"):
        result["also"] = {**compare_ranks(a, b, strata, spec["also"]), "a": spec["a"], "b": spec["b"]}
    return result


def protocol_tests(arms: dict[str, list[dict]], protocol: Protocol, drop: frozenset = frozenset(),
                   closed_in: bool = False, rewordings: bool = False) -> dict:
    """The protocol's primary tests, two-sided, with Holm over all of them (`one_test`). `drop`
    leaves questions out, and a rewording of a dropped template with them, for a
    sensitivity, as `closed_in` and `rewordings` do in their way."""
    tests = {name: one_test(spec, arms, protocol, drop, closed_in, rewordings)
             for name, spec in protocol.tests.items()}
    adjusted = holm({name: test["p"] for name, test in tests.items()})
    for name, test in tests.items():
        test["p_holm"] = adjusted[name]
        test["rejected"] = adjusted[name] <= ALPHA
    return tests


def split_tests(arms: dict[str, list[dict]], protocol: Protocol) -> dict:
    """Each test the protocol splits, on each part of each split it names, unadjusted: a
    secondary reading of where the effect is, fixed before the run (protocol analysis v2,
    23 October 2026). For H4, the first claim's six templates against the seven added for
    the second, and the tee's against the water's."""
    out = {}
    for name, splits in protocol.splits.items():
        spec = protocol.tests[name]
        universe = strata_of(spec, protocol)
        out[name] = []
        for label, parts in splits.items():
            got = []
            for part in parts:
                keep = set(protocol.sets[part])
                result = one_test(spec, arms, protocol, frozenset(s for s in universe if s not in keep))
                got.append({"set": part, **result})
            out[name].append({"split": label, "parts": got})
    return out


def protocol_against(arms: dict[str, list[dict]], protocol: Protocol) -> dict | None:
    """Correct, the protocol's block against open everything, by question and pooled, as
    counts and Newcombe intervals for the difference. Never a test of equivalence."""
    spec = protocol.config.get("against_open_everything")
    if not spec:
        return None
    a, b = scored(arms.get(spec["a"], [])), scored(arms.get(spec["b"], []))
    rows = []
    for q in protocol.sets[spec["on"]]:
        ra = [run for run in a if run["task"] == q]
        rb = [run for run in b if run["task"] == q]
        if ra and rb:
            rows.append(difference(q, sum(map(answered_correct, ra)), len(ra),
                                   sum(map(answered_correct, rb)), len(rb)))
    pooled = difference("pooled", sum(r["a"][0] for r in rows), sum(r["a"][1] for r in rows),
                        sum(r["b"][0] for r in rows), sum(r["b"][1] for r in rows))
    return {"a": spec["a"], "b": spec["b"], "on": spec["on"], "per_question": rows, "pooled": pooled}


def declines(arms: dict[str, list[dict]], protocol: Protocol) -> dict:
    """What each arm did with the questions the block should not plan, the templates and
    their rewordings: refused, asked, planned, or sent to the agent without a plan."""
    wanted = set(protocol.sets["decline"])
    out = {}
    for arm in protocol.arms:
        runs = [run for run in arms.get(arm, []) if run["task"] in wanted
                or protocol.templates_of.get(run["task"]) in wanted]
        if not runs:
            continue
        closed = [run for run in runs if run["outcome"] == voids.CLOSED]
        out[arm] = {"runs": len(runs), "refused": sum(run["refused"] for run in closed),
                    "asked": sum(not run["refused"] for run in closed),
                    "planned": sum(run["planned"] for run in runs),
                    "answered without a plan": sum(1 for run in runs if run["outcome"] != voids.CLOSED
                                                   and not run["planned"])}
    return out


def held_out_table(arms: dict[str, list[dict]], protocol: Protocol) -> dict:
    """The held-out rewordings by template, each arm that asked them: correct under the key
    for the reading answered, of the runs, and how many the box asked about or refused."""
    out = {}
    for arm in protocol.arms:
        runs = [run for run in arms.get(arm, []) if run["task"] in protocol.templates_of]
        if not runs:
            continue
        rows = {}
        for template in dict.fromkeys(protocol.templates_of.values()):
            mine = [run for run in runs if protocol.templates_of[run["task"]] == template]
            if mine:
                rows[template] = {"runs": len(mine), "keyed": template in protocol.keyed,
                                  "scored": len(scored(mine)), "correct": sum(map(answered_correct, mine)),
                                  "asked": sum(run["asked"] for run in mine),
                                  "refused": sum(run["refused"] for run in mine),
                                  "opened_median": statistics.median(run["opened"] for run in mine)}
        out[arm] = rows
    return out


def sorted_or_resized(run: dict) -> bool:
    """Whether a run asked the shop to sort its results or change their page size
    (`toolbar.read`). A slot the box closed asked nothing."""
    reading = run.get("toolbar") or {}
    return bool(reading.get("sorted") or reading.get("resized"))


def toolbar_table(arms: dict[str, list[dict]], protocol: Protocol) -> dict:
    """The runs of each arm that sorted the results or changed their page size, counted from
    each run's log (protocol analysis v2, 23 October 2026, from the verifier's audit): the
    page rules hold for the shop's relevance order at 36 a page only, and at 60 a page every
    listing of the A+ market renders on one. Each such run is named with what it asked."""
    out = {}
    for arm in [a for a in protocol.arms if a in arms] + sorted(set(arms) - set(protocol.arms)):
        runs = [run for run in arms[arm] if run.get("toolbar") is not None]
        named = []
        for run in runs:
            reading = run["toolbar"]
            if reading["sorted"] or reading["resized"]:
                named.append({"run": f"{run['batch']}/{run['task']}-{run['repeat']}",
                              "sorted": reading["order"] + reading["direction"],
                              "page size": reading["limit"] + [m for m in reading["mode"] if m == "list"]})
        out[arm] = {"runs": len(runs), "sorted": sum(1 for r in runs if r["toolbar"]["sorted"]),
                    "resized": sum(1 for r in runs if r["toolbar"]["resized"]), "named": named}
    return out


def failure_code(run: dict, page_size: int) -> tuple[str, str]:
    """A run's failure code and its evidence, by the protocol file's written rules, tried in
    order (`FAILURE_CODES`), the first that holds decides:

      page 2 never reached            the log shows no results page numbered 2 or more and no
                                      page size above the shop's, so the run read the first
                                      results page alone (`toolbar.past_page_one`); on the A+
                                      market both products have listings on page 2
                                      (env/generate_aplus.py, rule `interleaved`)
      a card or sold-out price taken  the answer states a listing's advertised price, or the
                                      price of the question's variant at a listing where it
                                      is sold out, that the key does not hold as right
                                      (`prices_taken`)
      other                           anything else"""
    reading = run.get("toolbar") or {"results_pages": [], "results_limits": []}
    if not toolbar.past_page_one(reading, page_size):
        pages = reading["results_pages"]
        return FAILURE_CODES[0], (f"results pages seen: {pages}" if pages else "no results page numbered")
    taken = run.get("taken") or {}
    if taken.get("card") or taken.get("sold_out"):
        return FAILURE_CODES[1], "; ".join(f"{kind.replace('_', ' ')} {', '.join(f'${p:.2f}' for p in prices)}"
                                           for kind, prices in taken.items() if prices)
    return FAILURE_CODES[2], f"results pages {reading['results_pages']}, limits {reading['results_limits']}"


def failure_breakdown(arms: dict[str, list[dict]], protocol: Protocol) -> dict | None:
    """The protocol arm's runs that a key judged and found not correct, on its set, each coded
    by `failure_code` from its log and answer (protocol analysis v2, 23 October 2026): by
    question, pooled, and every run named with its code and evidence."""
    spec = protocol.breakdown
    if not spec:
        return None
    wanted = set(protocol.sets[spec["on"]])
    runs = [run for run in scored(arms.get(spec["arm"], [])) if run["task"] in wanted and not answered_correct(run)]
    coded = [(run, *failure_code(run, spec["page_size"])) for run in runs]
    by_question = {}
    for q in protocol.sets[spec["on"]]:
        mine = [code for run, code, _ in coded if run["task"] == q]
        if mine:
            by_question[q] = {code: mine.count(code) for code in FAILURE_CODES}
    return {"arm": spec["arm"], "on": spec["on"], "page_size": spec["page_size"],
            "failures": len(coded), "of": len([r for r in scored(arms.get(spec["arm"], [])) if r["task"] in wanted]),
            "pooled": {code: sum(1 for _, got, _ in coded if got == code) for code in FAILURE_CODES},
            "by_question": by_question,
            "runs": [{"run": f"{run['batch']}/{run['task']}-{run['repeat']}", "code": code, "evidence": why}
                     for run, code, why in coded]}


def protocol_sensitivity(arms: dict[str, list[dict]], voided: list[dict], protocol: Protocol) -> dict:
    """The primary tests again under each sensitivity the protocol names."""
    out = {}
    for name in protocol.config.get("sensitivity") or []:
        if name == "without the two-reading questions":
            out[name] = protocol_tests(arms, protocol, frozenset(protocol.sets["two_readings"]))
        elif name == "distinct runs only":
            out[name] = protocol_tests({arm: compare_cells.distinct(runs) for arm, runs in arms.items()}, protocol)
        elif name == "with the voids included":
            out[name] = protocol_tests({arm: runs + [s for s in voided if s["measured"] and s["arm"] == arm]
                                        for arm, runs in arms.items()}, protocol)
        elif name == "without the runs that saw a hidden price":
            out[name] = protocol_tests({arm: [run for run in runs if not run["leaks"]]
                                        for arm, runs in arms.items()}, protocol)
        elif name == "with the closed slots in H2 and H3":
            out[name] = protocol_tests(arms, protocol, closed_in=True)
        elif name == "without the runs that sorted or changed the page size":
            out[name] = protocol_tests({arm: [run for run in runs if not sorted_or_resized(run)]
                                        for arm, runs in arms.items()}, protocol)
        elif name == "H4 by rewording, not by run":
            out[name] = protocol_tests(arms, protocol, rewordings=True)
    return out


def protocol_model(model: str | None, population: dict, conditions: dict, protocol: Protocol) -> dict:
    """Everything for one model's arms under a protocol file. Two models are never pooled."""
    kept = [s for s in population["kept"] if s["model"] == model]
    present = {s["arm"] for s in kept}
    arms = {arm: [s for s in kept if s["arm"] == arm]
            for arm in [a for a in protocol.arms if a in present] + sorted(present - set(protocol.arms))}
    voided = [s for s in population["voided"] if s["model"] == model]
    mine = {arm: conditions[(arm, model)] for arm in arms if (arm, model) in conditions}
    held, differ = {}, {}
    for key in PROTOCOL_CONDITIONS:
        if key in PROTOCOL_ARM_CONDITIONS:
            continue
        seen = {arm: c[key] for arm, c in mine.items()}
        if len(set(map(str, seen.values()))) <= 1:
            held[key] = next(iter(seen.values()), None)
        else:
            differ[key] = seen
    if "draw" in differ:
        raise SystemExit(f"the arms under {model} ran on more than one market draw, so they are "
                         f"never set against each other: {differ['draw']}")
    by_arm = {arm: {key: c[key] for key in PROTOCOL_ARM_CONDITIONS} for arm, c in mine.items()}
    required = [f"{arm} ran with {key} {c[key]}, where the protocol requires {value}"
                for arm, c in mine.items() for key, value in protocol.require.items() if c[key] != value]
    filled = collections.Counter((s["arm"], s["task"], s["repeat"]) for s in kept)
    # A slot left empty by a void is excluded by rule and listed as such; one with no run at
    # all, void or not, the command never ran, which is a problem (22 October 2026).
    voided_slots = {(s["arm"], s["task"], s["repeat"]) for s in voided}
    design = {"slots": 0, "filled": 0, "missing": [], "never_run": [], "outside": []}
    for arm, questions in protocol.design.items():
        for task in questions:
            for repeat in protocol.rounds:
                design["slots"] += 1
                if filled[(arm, task, repeat)]:
                    design["filled"] += 1
                else:
                    design["missing"].append(f"{arm}, {task} repeat {repeat}")
                    if (arm, task, repeat) not in voided_slots:
                        design["never_run"].append(f"{arm}, {task} repeat {repeat}")
    design["outside"] = sorted(f"{arm}, {task} repeat {repeat}" for (arm, task, repeat) in filled
                               if task not in protocol.design.get(arm, ()) or repeat not in protocol.rounds)
    templates = [q for q in protocol.sets["control"] + protocol.sets["gated"] + protocol.sets["decline"]]
    tables_ = {}
    for arm, runs in arms.items():
        rows = {q: summary([run for run in runs if run["task"] == q], answered_correct)
                for q in templates if any(run["task"] == q for run in runs)}
        gated = [run for run in runs if run["task"] in protocol.sets["gated"]]
        if gated:
            rows["pooled, gated"] = summary(gated, answered_correct)
        for q, row in rows.items():
            asked = gated if q == "pooled, gated" else [run for run in runs if run["task"] == q]
            row["tokens_mean"] = mean([run["tokens_total"] for run in asked if run.get("tokens_total") is not None])
            # A question with no key (the declines) has no correct answer to count: "-", not 0.
            # A run unscored under the reading it answered is no wrong answer either.
            row["keyed"] = all(run["task"] in protocol.keyed for run in asked)
            row["scored"] = len(scored(asked))
        tables_[arm] = rows
    return {
        "named": model in protocol.models,
        # The model's role, the file's (v2): the primary's tests are the claim, a
        # replication's are its own family, each with Holm over its four.
        "role": protocol.roles.get(model) if model in protocol.models else None,
        "arms": {arm: {"batches": sorted({s["batch"] for s in runs}), "runs": len(runs),
                       "repeats": sorted({s["repeat"] for s in runs}),
                       "distinct": len(compare_cells.distinct(runs)), "conditions": mine.get(arm)}
                 for arm, runs in arms.items()},
        "conditions": {"held": held, "differ": differ, "by_arm": by_arm, "required": required},
        "exclusions": {"voids": [brief(s) for s in voided],
                       "replaced": [r for r in population["replaced"] if r["model"] == model],
                       "missing": [m for m in population["missing"] if m["model"] == model],
                       "not_correct": [brief(s) for s in kept if s["outcome"] == voids.NOT_CORRECT],
                       "design": design},
        "tables": tables_,
        "held_out": held_out_table(arms, protocol),
        "primary": protocol_tests(arms, protocol),
        "splits": split_tests(arms, protocol),
        "against_open_everything": protocol_against(arms, protocol),
        "secondary": {"count_two_readings": count_stocked(arms, protocol.sets["count_two_readings"], list(protocol.arms)),
                      "asks": asks(arms, list(protocol.arms)), "declines": declines(arms, protocol),
                      "answer_check": answer_check(arms, list(protocol.arms)),
                      "toolbar": toolbar_table(arms, protocol),
                      "failure_breakdown": failure_breakdown(arms, protocol)},
        "sensitivity": protocol_sensitivity(arms, voided, protocol),
        "runs": [{key: s.get(key) for key in ("arm", "batch", "task", "template", "repeat", "outcome", "reason",
                                              "own", "buyable", "verdict", "answered", "opened", "skus",
                                              "covered", "missed", "cost", "tokens_total", "calls", "actions",
                                              "asked", "refused", "agent_asks", "leaks", "outside", "toolbar",
                                              "taken", "answer")}
                 for s in kept],
    }


def analyse_protocol(lines: list[Line], manifest: Manifest | None, path: pathlib.Path) -> dict:
    """Every figure under a protocol file, as data: `render_protocol` prints it."""
    config = json.loads(path.read_text())
    broken = check_protocol(config)
    if broken:
        raise SystemExit(f"{path.name} cannot be analysed: " + "; ".join(broken))
    names = {(arm["arm"], arm["reading"]): name for name, arm in config["arms"].items()}
    problems = list(manifest.problems) if manifest else []
    if manifest is not None and (len(manifest.starts) != 1 or len(manifest.ends) != 1):
        problems.append(f"the manifest holds {len(manifest.starts)} start and {len(manifest.ends)} "
                        f"end lines, where one run of the command writes one of each")
    loaded = []
    for line in lines:
        if line.folder is None or not (line.folder / "suite.json").exists():
            problems.append(f"a {line.kind} line names no batch folder with a suite.json "
                            f"({line.folder}), so it is not read")
            continue
        payload, slots, found = load_folder(line.folder, names, PROTOCOL_CONDITIONS)
        problems += found
        if line.kind == "batch" and line.args:
            arm, reading, wanted = intended(line.args)
            recorded = payload.get("arm") or flagged_arm(payload)
            if recorded != arm or payload.get("reading") != reading:
                problems.append(f"{line.folder.name}: the manifest's arguments ask for arm {arm}, "
                                f"reading {reading}; its payload says {recorded}, "
                                f"{payload.get('reading')}. The payload's is used")
        loaded.append((line, payload, slots))
    files = sorted({payload["tasks_file"] for _, payload, _ in loaded})
    if len(files) != 1:
        raise SystemExit(f"the batches read {len(files)} task files ({', '.join(files)}), where the "
                         f"protocol's sets are one task file's ids")
    protocol = resolve_protocol(path, config, json.loads((paths.TASKS / files[0]).read_text()))
    population = assemble(loaded, manifest is not None)
    problems += population["problems"]
    every = [slot for _, _, slots in loaded for slot in slots]
    conditions = one_condition_each(population["kept"] + population["voided"], PROTOCOL_CONDITIONS)
    models = sorted({slot["model"] for slot in population["kept"]} | {m["model"] for m in population["missing"]},
                    key=str)
    # The primary model first, then its replications in the file's order, then any the file
    # does not name (v2): the report is read in that order.
    named = [m for m in protocol.models if protocol.roles.get(m) == "primary"] + \
        [m for m in protocol.models if protocol.roles.get(m) != "primary"]
    models = [m for m in named if m in models] + [m for m in models if m not in named]
    out = {"analysis_version": VERSION, "protocol_analysis_version": PROTOCOL_ANALYSIS_VERSION,
           "scorer_version": scoring.VERSION, "protocol": config["protocol"],
           "protocol_file": shown_path(path), "protocol_version": config.get("version"), "tasks_file": files[0],
           "sets": {key: list(value) if not isinstance(value, str) else value
                    for key, value in protocol.sets.items()},
           "design": {arm: len(questions) * len(protocol.rounds) for arm, questions in protocol.design.items()},
           "source": source(lines, manifest, every), "problems": problems, "models": {},
           "models_named": list(protocol.models), "roles": dict(protocol.roles)}
    for model in models:
        result = protocol_model(model, population, conditions, protocol)
        out["problems"] += [f"{model}: {text}" for text in result["conditions"]["required"]]
        # A condition that is no arm's own and differs between arms makes two experiments of
        # one (LESSONS 7, 10), and the design's slots are the protocol's, fixed before the run.
        out["problems"] += [f"{model}: {key} differs between the arms: "
                            + "; ".join(f"{arm} {value}" for arm, value in seen.items())
                            for key, seen in result["conditions"]["differ"].items()]
        design = result["exclusions"]["design"]
        out["problems"] += [f"{model}: the design's slot {label} has no run, void or not"
                            for label in design["never_run"]]
        out["problems"] += [f"{model}: {run['batch']}/{run['task']}-{run['repeat']} has no key for the reading "
                            f"it answered, {run['answered']}, so it is unscored and in no test of correct"
                            for run in result["runs"] if run["verdict"] == "unscored" and run["task"] in protocol.keyed]
        out["problems"] += [f"{model}: a run the design does not ask for, {label}" for label in design["outside"]]
        out["models"][str(model)] = result
    out["problems"] += [f"the protocol's model {model} has no run" for model in protocol.models
                        if model not in out["models"]]
    return out


def shown_path(path: pathlib.Path) -> str:
    """A file as the report names it: from the repository's root when it is in it."""
    try:
        return str(path.resolve().relative_to(paths.REPO))
    except ValueError:
        return str(path)


def render_protocol(result: dict) -> str:
    out = []
    say = out.append
    say(f"The claim analysis under {result['protocol_file']} (version {result['protocol_version']}), for "
        f"{result['protocol']}: claim.py v{result['analysis_version']}, protocol analysis "
        f"v{result['protocol_analysis_version']}, every answer scored again by score.py v{result['scorer_version']}")
    sets = result["sets"]
    say(f"Task file {result['tasks_file']}: {len(sets['control'])} control, {len(sets['gated'])} gated, "
        f"{len(sets['decline'])} the block should not plan, {len(sets['held_out'])} held-out rewordings; two "
        f"readings: {', '.join(sets['two_readings'])}; reading-independent: {len(sets['reading_independent'])}")
    say("The design, slots each model: " + "; ".join(f"{arm} {n}" for arm, n in result["design"].items())
        + f"; models named: {', '.join(result['models_named'])}")
    roles = result.get("roles") or {}
    if roles:
        say("The tests' families, fixed before the run: " + "; ".join(
            f"{model} {role}" for model, role in roles.items())
            + ". The primary model's four tests are the claim, with Holm over the four; each replication's "
              "four are its own family, with its own Holm, and never pooled with the primary's.")
    src = result["source"]
    kinds = collections.Counter(line["kind"] for line in src["lines"])
    say("Read " + ", ".join(f"{n} {kind}{'s' if n > 1 else ''}" if kind == "folder" else
                            f"{n} {kind} line{'s' if n > 1 else ''}" for kind, n in kinds.items())
        + f"; the provider's charges summed over every run in them, voids included: ${src['charges']:.4f}")
    if "starts" in src:
        start = src["starts"][0] if src["starts"] else {}
        end = src["ends"][-1] if src["ends"] else {}
        say(f"Started {start.get('at', '-')}, ended {end.get('at', '-')}; the account moved "
            + (f"${src['account_moved']:.4f}" if src["account_moved"] is not None else "(not read)")
            + f"; cap ${src['cap']}" + (f"; stops: {'; '.join(src['stops'])}" if src["stops"] else "; no stop"))
    say(f"\nProblems found: {len(result['problems'])}")
    for text in result["problems"]:
        say(f"  {text}")
    for model, m in result["models"].items():
        role = {"primary": ", the primary: its four tests are the claim, Holm over the four",
                "replication": ", a replication of the primary: its own Holm over its four"}.get(m.get("role"), "")
        say(f"\n{'=' * 100}\nModel {model}" + ("" if m["named"] else ", which the protocol does not name")
            + role + ". Each model is its own result and is never pooled with another.")
        render_protocol_model(m, say)
    return "\n".join(out)


def render_protocol_model(m: dict, say) -> None:
    say("\nArms, each from its batches' payloads:")
    for arm, a in m["arms"].items():
        say(f"  {arm:30} {a['runs']:>3} runs, {a['distinct']:>3} distinct, repeats "
            f"{', '.join(map(str, a['repeats']))}   batches {', '.join(a['batches'])}")
    say(held_line(m["conditions"]["held"]))
    for key, seen in m["conditions"]["differ"].items():
        say(f"  DIFFERS between arms, {key}: " + "; ".join(f"{arm} {value}" for arm, value in seen.items()))
    for arm, c in m["conditions"]["by_arm"].items():
        shown = "; ".join(f"{key} {value}" for key, value in c.items() if value is not None)
        say(f"  {arm:30} {shown or 'no arm-specific condition'}")
    for text in m["conditions"]["required"]:
        say(f"  NOT AS REQUIRED: {text}")

    e = m["exclusions"]
    say("\nExclusions, decided from the logs and the records before any answer was read:")
    say(f"  voids {len(e['voids'])}" + "".join(f"\n    {v['batch']}/{v['task']}-{v['repeat']} ({v['arm']}): "
                                               f"{v['reason']}, {v['evidence']}" for v in e["voids"]))
    for r in e["replaced"]:
        say(f"    replaced by its re-run in {r['by']}: {r['batch']}/{r['task']}-{r['repeat']}")
    say(f"  missing {len(e['missing'])}" + "".join(f"\n    {x['batch']}/{x['task']}-{x['repeat']} "
                                                   f"({x['arm']}): {x['why']}" for x in e["missing"]))
    reasons = collections.Counter(x["reason"] for x in e["not_correct"])
    say("  not correct, kept and reported apart: "
        + (", ".join(f"{reason} {n}" for reason, n in sorted(reasons.items())) or "none"))
    d = e["design"]
    say(f"  the protocol's design, {d['slots']} slots: {d['filled']} filled, {len(d['missing'])} empty"
        + (f": {'; '.join(d['missing'][:12])}" + (" ..." if len(d["missing"]) > 12 else "") if d["missing"] else "")
        + (f"; outside the design: {'; '.join(d['outside'])}" if d["outside"] else ""))

    say("\n1. Each arm by question, then pooled over the gated questions. The unit is a run.")
    say("   correct: under the key for the reading the run was answered under, of the runs a key judged; - for "
        "a question with no key. opened: the listings of the question's product opened, median [each run]. "
        "needs: opened what the answer needs.")
    say("   $/run: the provider's charge, the model parser's included. tokens: the agent's, thousands, mean; "
        "the model parser's are not recorded. actions: browser actions a run, "
        "all/results page/listings. asks: the box's and the agent's. step, clock, none, abst: not correct "
        "for the step budget, the clock, no answer, an abstention.")
    for arm, questions in m["tables"].items():
        say(f"  {arm}")
        say(f"    {'question':22} {'runs':>4} {'correct':>7}  {'opened':26} {'needs':>5} {'$/run':>6} "
            f"{'tokens':>7} {'actions':>15} {'asks':>4} {'step':>4} {'clock':>5} {'none':>4} {'abst':>4} {'leak':>4}")
        for q, s in questions.items():
            opened = (f"{s['opened_median']:g} " if s["opened_median"] is not None else "- ") + \
                (str(s["opened"]) if len(s["opened"]) <= 5 else "")
            actions = f"{number(s['actions'])}/{number(s['actions_results'])}/{number(s['actions_listings'])}"
            tokens = "-" if s["tokens_mean"] is None else f"{s['tokens_mean'] / 1000:.0f}k"
            correct = f"{s['correct']}/{s['scored']}" if s["keyed"] else "-"
            say(f"    {q:22} {s['runs']:>4} {correct:>7}  {opened:26} "
                f"{str(s['covered']) + '/' + str(s['runs']):>5} {money(s['cost_mean']):>6} {tokens:>7} {actions:>15} "
                f"{s['asks']:>4} {s['step']:>4} {s['clock']:>5} {s['no_answer']:>4} {s['abstention']:>4} "
                f"{s['leaks']:>4}")

    say(f"\n2. Primary tests, two-sided, with Holm's correction over the {len(m['primary'])}")
    for name, t in m["primary"].items():
        say(f"  {name} {t['measure']}, {t['a']} against {t['b']}, on {t['on']}, by {t['strata']}: "
            + ", ".join(t["questions"]))
        if not t["per_question"]:
            say("     not computed: an arm has no runs on these questions, so Holm counts it as p = 1")
            continue
        say("     " + render_test(t))
        say(f"     {t['test']}: " + (f"rank sum {number(t['observed'])} against {number(t['expected'])} "
                                      f"expected, " if t.get("observed") is not None else "")
            + f"p = {p_text(t['p'])}, Holm p = {p_text(t['p_holm'])}"
            + ("  rejected at 0.05" if t["rejected"] else "  not rejected at 0.05"))
        also = t.get("also")
        if also:
            label = "the agent's tokens" if also["measure"] == "tokens_total" else also["measure"]
            say(f"     and on {label}, outside Holm: "
                + (render_test(also) + f"; p = {p_text(also['p'])}" if also["per_question"] else "not computed"))
        if "closed" in t:
            say(f"     slots the box closed, no agent run, {t['closed_rule']} (a {t['a']}, b {t['b']}): "
                + (", ".join(f"{row['task']} {row['a']}/{row['b']}" for row in t["closed"]) or "none"))
    for name, splits in (m.get("splits") or {}).items():
        say(f"  {name} on the pre-specified splits, secondary and unadjusted, each part on its own:")
        for split in splits:
            say(f"     {split['split']}")
            for part in split["parts"]:
                if not part["per_question"]:
                    say(f"       {part['set']:24} not computed: an arm has no runs on these strata")
                    continue
                if part["measure"] == "correct":
                    pooled = part["pooled"]
                    shown = (f"{len(part['questions'])} strata, pooled {pooled['a'][0]}/{pooled['a'][1]} "
                             f"against {pooled['b'][0]}/{pooled['b'][1]}")
                else:
                    shown = render_test(part)
                say(f"       {part['set']:24} {shown}; p = {p_text(part['p'])}")

    o = m["against_open_everything"]
    if o:
        say(f"\n3. Correct, {o['a']} against {o['b']}, on {o['on']}: counts and Newcombe's 95% hybrid "
            "score interval for the difference. Never a test of equivalence.")
        for row in o["per_question"] + [o["pooled"]]:
            say(f"     {row['task']:22} {row['a'][0]}/{row['a'][1]} against {row['b'][0]}/{row['b'][1]}"
                + (f", difference {row['difference']:+.2f}, interval {row['interval'][0]:+.3f} to "
                   f"{row['interval'][1]:+.3f}" if row["interval"] else ", no interval: an arm has no runs"))

    say("\n4. The held-out rewordings, by template: correct of the runs a key judged, asked, refused, opened median")
    for arm, rows in m["held_out"].items():
        say(f"  {arm}")
        for template, r in rows.items():
            correct = f"{r['correct']}/{r['scored']}" if r["keyed"] else "-"
            say(f"     {template:22} {correct:>5}  asked {r['asked']}  refused {r['refused']}  "
                f"opened {r['opened_median']:g}" + ("" if r["keyed"] else "  (no key)"))

    s = m["secondary"]
    say("\n5. Secondary and exploratory")
    cs = s["count_two_readings"]
    say("  a. The count with two readings, arm by key. The box's ask is one user turn.")
    for arm, row in cs["table"].items():
        say(f"     {arm:30} {row['runs']} runs: correct under the menu key {row['menu_key']}, "
            f"under the buyable key {row['buyable_key']}; user turns {row['user_turns']}")
    say(f"     The answers, for their declared reading to be coded by hand without seeing the arm "
        f"({len(cs['sheet'])}; the arm of each id is in the JSON, coding_key):")
    for row in cs["sheet"]:
        say(f"       [{row['id']}] declared reading: ______  " + " ".join(row["answer"].split()))
    say("  b. Asks, the box's and the agent's own, on the clear and the two-reading questions")
    for arm, row in s["asks"].items():
        say(f"     {arm:30} clear {row['clear']['asks']} of {row['clear']['runs']} runs, two readings "
            f"{row['ambiguous']['asks']} of {row['ambiguous']['runs']}")
    say("  c. The questions the block should not plan, with their rewordings")
    for arm, row in s["declines"].items():
        say(f"     {arm:30} {row['runs']} runs: refused {row['refused']}, asked {row['asked']}, planned "
            f"{row['planned']}, sent without a plan {row['answered without a plan']}")
    say("  d. The answer check replayed from the logs (replay_box), each run judged under the reading it answered")
    for arm, row in s["answer_check"].items():
        if row is None:
            say(f"     {arm:30} no plan, so nothing to replay")
            continue
        say(f"     {arm:30} {row['runs']} of the {row['planned']} runs the box planned: wrong "
            f"{row['wrong']}, refused {len(row['wrong_refused'])}; correct {row['correct']}, refused "
            f"{len(row['correct_refused'])}; other {row['other']}, refused {len(row['other_refused'])}")
        for name in ("not_reproduced", "decided_differently", "not_replayed"):
            for text in row[name]:
                say(f"       {name.replace('_', ' ')}: {text}")
    say("  e. Runs that sorted the results or changed their page size, read from each log's navigations "
        "and reported pages (toolbar.py)")
    for arm, row in s["toolbar"].items():
        say(f"     {arm:30} of {row['runs']} runs with a log: sorted {row['sorted']}, page size changed "
            f"{row['resized']}")
        for named in row["named"]:
            say(f"       {named['run']}: sorted {', '.join(named['sorted']) or '-'}, page size "
                f"{', '.join(named['page size']) or '-'}")
    fb = s.get("failure_breakdown")
    if fb:
        say(f"  f. Why {fb['arm']} was not correct, coded from the log and the answer by the written rules, the "
            f"first that holds: {fb['failures']} of its {fb['of']} runs a key judged on {fb['on']}, at "
            f"{fb['page_size']} a page")
        say("     pooled: " + "; ".join(f"{code} {n}" for code, n in fb["pooled"].items()))
        for q, row in fb["by_question"].items():
            say(f"     {q:22} " + "; ".join(f"{code} {n}" for code, n in row.items() if n))

    names = list(m["primary"])
    say("\n6. Sensitivity: the primary tests again, p (Holm p)")
    say(f"     {'':54} " + " ".join(f"{name:>22}" for name in names))
    for name, tests in m["sensitivity"].items():
        say(f"     {name:54} " + " ".join(f"{p_text(t['p']) + ' (' + p_text(t['p_holm']) + ')':>22}"
                                          for t in tests.values()))


# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="+", type=pathlib.Path,
                        help="the claim command's manifest, or batch folders")
    parser.add_argument("--json", type=pathlib.Path,
                        help="write the figures here; by default next to a manifest, as "
                             "<name>.analysis.json, and nowhere for a list of folders")
    parser.add_argument("--sets", type=pathlib.Path,
                        help="a protocol's question sets, as JSON (see `apply_sets`), or a "
                             "task file holding them under claim_sets; the first claim's by "
                             "default")
    parser.add_argument("--protocol", type=pathlib.Path,
                        help="a protocol file naming its arms, sets, design and primary tests, "
                             "experiments/tasks/claim2_analysis.json for the second claim; the "
                             "first claim's analysis by default")
    args = parser.parse_args(argv)
    if args.sets and args.protocol:
        parser.error("--sets is the first claim's analysis under other question sets; a protocol "
                     "file names its own")
    if args.sets:
        apply_sets(read_sets(args.sets))
    manifest = None
    if len(args.sources) == 1 and args.sources[0].is_file():
        manifest = parse_manifest(args.sources[0].read_text())
        lines = manifest.lines
        target = args.json or args.sources[0].with_name(
            args.sources[0].name.removesuffix(".manifest") + ".analysis.json")
    else:
        lines = [Line("folder", resolve(str(path))) for path in args.sources]
        target = args.json
    if args.protocol:
        result = analyse_protocol(lines, manifest, args.protocol)
        print(render_protocol(result))
    else:
        result = analyse(lines, manifest)
        print(render(result))
    if target is not None:
        target.write_text(json.dumps(result, indent=2, default=str) + "\n")
        print(f"\nthe same figures as JSON: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
