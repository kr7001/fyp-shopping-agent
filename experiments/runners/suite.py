#!/usr/bin/env python3
"""Run the RQ2 baseline suite: every task, several times, scored.

One run per task is not enough. The same model on the same page has been observed
answering correctly twice and fabricating a price on the third attempt, so a single
sample would have recorded that task as solved. This runs each task `--repeats`
times and reports the distribution.

    python experiments/runners/suite.py --repeats 5
    python experiments/runners/suite.py --repeats 1 --only water-a-9l5-price
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import box as box_module
import form as form_module
import page as page_module
import policy as policy_module
import primitives as primitives_module
import sufficiency
import score as scoring
import planner as planner_module
import targeting as targeting_module
import trace_stats
from page import GATED_UA  # one definition, shared with the box's own fetch

HERE = pathlib.Path(__file__).resolve().parent
REPO = paths.REPO
AGENT_CORE = paths.AGENT_CORE
RUNNER = HERE / "run_browser_task.py"
NAIVE_RUNNER = HERE / "naive_agent.py"
RESULTS = paths.RESULTS

# Which shop a run sees is decided by the browser's user agent, because `env/install_gated_theme.py`
# selects the price-suppressing theme that way. Nothing in a run record used to say which one it
# got, so a run launched without this looked identical to one launched with it while measuring a
# different shop. It is a default rather than a flag for the same reason: the leaky shop should
# have to be asked for. The user agent itself lives in `box/page.py`, because the box fetches
# the results page with it too.
#
# The browser tool is pinned. It was fetched as "latest" on every run until 14 October 2026
# (LESSONS 12), when npm's latest `@playwright/mcp` was 0.0.83 and every clothing cell had run
# on 0.0.83, so the pin changes nothing now and stops a release changing the tool between the
# box's runs and the cells they are compared with. Recorded in every suite payload as
# `browser_tool`.
BROWSER_TOOL = "0.0.83"
# The browser may request the shop and nothing else. A bypassed question names no shop
# page, so without this an agent could take the browser onto a live site, which the project
# never does. From `npx -y @playwright/mcp@0.0.83 --help`, read on 14 October 2026:
#
#   --allowed-origins <origins>           semicolon-separated list of TRUSTED
#                                         origins to allow the browser to request.
#                                         Default is to allow all.
#                                         Important: *does not* serve as a
#                                         security boundary and *does not* affect
#                                         redirects.
#
# So a redirect off the shop is not stopped by it, and reading every log's URLs stays the
# check that no run left the shop. A recorded condition (`browser_origins` in every suite
# payload) that differs from cells 1 to 5, which ran without it: no run of those cells left
# localhost, since the listing counter and the verifier's checks saw only shop URLs. The
# default shop sets no MCP arguments of its own (openJiuwen's apply), so it is not confined
# and its payload says None. The agent splits the string with `shlex`, so the flag and its
# value are two words, as the quoted user agent before them is one.
#
# Beside it, from the same `--help`, read again on 20 October 2026:
#
#   --block-service-workers               block service workers
#
# A service worker is a script a page may register that answers the page's later requests
# itself, from its own cache, so with one in place what the browser shows is not only what
# the shop sent. Blocking them keeps every page the agent reads a page the shop served
# (verifier finding, 20 October 2026). The three batches of 14 October (20261014T213118,
# 20261014T220116, 20261014T222007) ran without it, which their payloads show by having no
# `browser_flags`. `--allowed-origins` confines network requests and nothing else: in
# 20261014T220116 the bypassed poem run wrote its poem into a `data:text/html,...` URL and
# navigated to it, which makes no network request, so no breach, recorded here.
#
# And from the same `--help`, read again on 20 October 2026:
#
#   --isolated                            keep the browser profile in memory, do
#                                         not save it to disk.
#
# Without it the tool keeps one profile on disk and reuses it. Every openJiuwen run since
# 8 September 2026 shared the one at ~/Library/Caches/ms-playwright-mcp/mcp-chrome-b6e84f7,
# created at 21:48 that evening by the first run (experiments/runs/20260908T214912), and
# last written at 22:28 on 14 October by the last box batch. Read on 20 October, by cookie
# name and date and never by value, it holds Magento's PHPSESSID, created on 8 September
# and renewed to a year ahead on every visit, Magento's recently-viewed and
# recently-compared cookies, a browsing history and local storage. So whatever one run did
# to the shop's session, a product added to the compare list for one, was there for every
# later run of every arm: a state that outlives the run (LESSONS 11). With the flag each
# run starts from an empty profile and writes nothing. Every batch before 20 October ran on
# the shared profile, which their payloads show by a `browser_flags` without it (verifier
# finding, 20 October 2026).
ALLOWED_ORIGINS = "http://localhost:7770"
BROWSER_FLAGS = "--block-service-workers --isolated"
MCP_ARGS_GATED = (f'-y @playwright/mcp@{BROWSER_TOOL} --user-agent "{GATED_UA}" '
                  f'--allowed-origins {ALLOWED_ORIGINS} {BROWSER_FLAGS}')


def browser_conditions(scaffold: str, shop: str) -> dict:
    """The pinned browser tool, the origins it may request and the flags it runs with,
    recorded in every suite payload and printed in the dry run's header. Only openJiuwen
    on the gated shop gets them: the naive loop drives its own browser, and the default
    shop leaves openJiuwen's own "latest" in place."""
    pinned = scaffold == "openjiuwen" and shop == "gated"
    return {"browser_tool": BROWSER_TOOL if pinned else None,
            "browser_origins": ALLOWED_ORIGINS if pinned else None,
            "browser_flags": BROWSER_FLAGS if pinned else None}


def browser_env(shop: str, probe: str = "viewport",
                cache_dir: pathlib.Path | None = None) -> dict:
    """The environment a runner needs to see the shop this suite says it is measuring."""
    env = dict(os.environ)
    # A fresh selector cache per run. openJiuwen remembers which CSS selectors found cards
    # on a route and reuses them next time, in a file under the home directory that outlives
    # every run. That makes run 18 of a batch a different experiment from run 1, through no
    # property of the question. Observed on 7 Oct 2026: one run's probe reported
    # `cache_candidate_count: 0` and `selector_source: 'generic'` where a cold probe on the
    # same page finds eleven candidates. Each run now starts from nothing, which is the only
    # state that is the same for every run.
    if cache_dir is not None:
        env["OPENJIUWEN_BROWSER_SELECTOR_CACHE"] = str(cache_dir / "selector_cache.json")
    if shop == "gated":
        env["PLAYWRIGHT_MCP_ARGS"] = MCP_ARGS_GATED
    else:
        env.pop("PLAYWRIGHT_MCP_ARGS", None)
    # The "see everything" arm. One setting, applied by `see_everything.py` inside the
    # runner, with the prompt and every other setting held constant.
    if probe == "whole-page":
        env["IGR_SEE_EVERYTHING"] = "1"
    else:
        env.pop("IGR_SEE_EVERYTHING", None)
    return env


def run_once(task: dict, base_url: str, out_dir: pathlib.Path, tag: str,
             query: str | None = None, scaffold: str = "openjiuwen",
             shop: str = "gated", probe: str = "viewport") -> dict:
    """Execute one task once and return its record, enriched with trace counts.

    `query` overrides the task text, which is how a policy retry re-asks the same task
    with the reason its first answer was rejected.
    """
    query = query if query is not None else task["query"].format(base=base_url)
    (out_dir / "caches" / tag).mkdir(parents=True, exist_ok=True)
    record_path = out_dir / f"{tag}.json"
    log_path = out_dir / f"{tag}.log"

    # The naive loop is a second scaffold rather than a second setting, so it runs from its
    # own interpreter with its own browser. Everything after this point is shared: the same
    # scoring, the same gate, the same draw id, the same records on disk.
    if scaffold == "naive":
        command = [str(REPO / ".venv-naive" / "bin" / "python"), str(NAIVE_RUNNER),
                   query, "--out", str(record_path)]
        if shop == "gated":
            command += ["--user-agent", GATED_UA]
        cwd = REPO
    else:
        command = ["uv", "run", "python", str(RUNNER), query, "--out", str(record_path)]
        cwd = AGENT_CORE

    with log_path.open("w") as log:
        subprocess.run(command, cwd=cwd,
                       env=browser_env(shop, probe, cache_dir=out_dir / "caches" / tag),
                       stdout=log, stderr=subprocess.STDOUT, check=False)

    if not record_path.exists():
        return {"error": "runner wrote no record", "log": log_path.name}

    # The counts are written back into the run record, not just carried in memory.
    # A per-run file that lacks them is not self-describing, and the whole point of
    # keeping every record is that a result can be re-examined later on its own.
    record = json.loads(record_path.read_text())
    # The naive loop counts its own calls as it makes them, in the same vocabulary. Only
    # openJiuwen's trace has to be recovered from its log.
    if not record.get("trace"):
        record["trace"] = trace_stats.stats(log_path)
    # openJiuwen's runner has no per call figure of its own, so take the one the provider
    # printed into the log. The account delta it records lags and bills a run for the
    # previous run's settling spend, which on 7 Oct 2026 was a factor of 32 on one run.
    reported = (record["trace"] or {}).get("cost_reported_usd")
    if reported:
        record["spend_delta_usd"] = record.get("cost_usd")
        record["cost_usd"] = reported
    record["log"] = log_path.name
    # Which shop this run saw. A record without it predates the theme and was measured
    # against a page that published every variant price on load.
    record["shop"] = shop
    # Which card probe setting this run met. A record without it predates the arm.
    record["probe"] = probe
    # The naive loop stamps its own scaffold, openJiuwen's runner does not, so a mixed
    # directory had records where the field was simply absent. Stamped here for both, since
    # a record that cannot say which agent produced it is how four arms got pooled once.
    record.setdefault("scaffold", scaffold)
    record_path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return record


def model_from_records(out_dir: pathlib.Path) -> str | None:
    """The model the runner actually used, read back from the first run it wrote.

    `MODEL_NAME` in the environment is the usual way the model is chosen, but it can also
    come from the repo's .env, in which case the environment says nothing. Reading it back
    from a record means the suite reports what ran rather than what was requested.
    """
    for record in sorted(out_dir.glob("*.json")):
        if record.name == "suite.json":
            continue
        try:
            model = json.loads(record.read_text()).get("model")
        except (OSError, json.JSONDecodeError):
            continue
        if model:
            return model
    return None


def agent_code_identity(git: str = "git", where: pathlib.Path = AGENT_CORE) -> dict:
    """Which openJiuwen code a batch runs: the submodule's commit, and a digest of the
    uncommitted patch on top of it.

    The agent is `agent/agent-core`, pinned at a commit but carrying the local patch
    `agent/openjiuwen-local.patch` (see `agent/README.md`). The spend guard's CODE_PATHS
    leave `agent/` out, so an edit there would reach a paid run unverified, and until
    14 Oct 2026 no batch record said which agent code ran. The verifier found the patch
    present in every clothing cell: a held-constant condition that no record named
    (LESSONS 10, 12). `agent_core_patch` is the sha1 of the bytes `git diff --full-index`
    prints, so an empty diff gives the sha1 of nothing, and the committed
    `agent/openjiuwen-local.patch`, written with the same flag, has that sha1 itself. Full
    blob ids because a plain `git diff` abbreviates them by the machine's setting, so the
    figure depended on the machine (verifier finding, 20 October 2026): the four October
    batches (20261014T084322, 20261014T213118, 20261014T220116, 20261014T222007) recorded
    the abbreviated form, ae20d54335978d01c3cd040b153585a8324831cc, for the same content
    that now records as the full-index digest. Git being unavailable never fails a batch:
    both fields read "unknown" and a warning is printed. `git` and `where` are parameters
    so a test can take both paths.
    """
    try:
        # `--show-toplevel` with HEAD, because git answers for the nearest enclosing
        # repository: an empty, uninitialised submodule folder would otherwise be recorded
        # as this repository's own commit without a word.
        toplevel, commit = _git(git, where, "rev-parse", "--show-toplevel", "HEAD").decode().split()
        if pathlib.Path(toplevel).resolve() != where.resolve():
            raise LookupError(f"{where} is not its own repository, git answered for {toplevel}")
        patch = hashlib.sha1(_git(git, where, "diff", "--full-index")).hexdigest()
    except (OSError, subprocess.CalledProcessError, LookupError) as error:
        print(f"warning: the agent code's identity could not be read, recording it as "
              f"unknown: {error}", file=sys.stderr)
        commit = patch = "unknown"
    return {"agent_core_commit": commit, "agent_core_patch": patch}


def _git(git: str, where: pathlib.Path, *args: str) -> bytes:
    """What git prints for `args` inside `where`, as bytes. Raises when git fails."""
    return subprocess.run([git, "-C", str(where), *args], capture_output=True,
                          check=True).stdout


def draw_id(spec: dict) -> str:
    """Which catalogue, in which state, a task file's answers belong to.

    Runs scored against different answer keys are different measurements, and pooling
    them has produced a wrong figure six times now. The id is a hash of the answer key
    itself, so a regenerated market gets a new one without anyone remembering to bump a
    number. `_environment` is for the one change a hash of the answers cannot see: the page
    changing while the answers stay the same, as when the authoring notes were removed
    from the small fixture's product descriptions on 13 Sep 2026.
    """
    market = spec.get("brand") or ("Rivenhall" if spec.get("_instance") else "small")
    key = {"answers": spec.get("_instance")
           or [[t["id"], t["expect"]] for t in spec["tasks"]],
           "environment": spec.get("_environment")}
    digest = hashlib.sha1(json.dumps(key, sort_keys=True).encode()).hexdigest()[:10]
    return f"{market}:{digest}"


def add(*values) -> float | int | None:
    """Sum what is present. A missing cost is unknown, not zero."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


# The results page the box reads, fetched once per batch and reused by every task and
# repeat, so one page record describes what the whole batch planned from.
PAGES: dict[str, page_module.Page] = {}


def results_page(url: str) -> page_module.Page:
    if url not in PAGES:
        PAGES[url] = page_module.fetch(url)
    return PAGES[url]


def build_query(task: dict, spec: dict, args) -> tuple[str | None, dict]:
    """The exact text the agent receives, and what produced it.

    One function for the dry run and the paid loop, so the text the verifier reads is the
    text the agent gets (LESSONS 17). Applied in order: the box, or the box without its stop
    rule under `--box-exhaust`, targeting, the exhaustive instruction, the confidence
    prompt. The text is None when the box asked and no `--reading` answered it, or when it
    refused. A question the box bypasses comes back as its own text, which is what the
    agent then gets. The dict holds the strategy kind, the box's record, the page it read
    and its decision, each None when not used.
    """
    query = task["query"].format(base=spec["base_url"])
    applied = {"strategy": None, "box": None, "page": None, "decision": None}
    # Read with a default: a caller that builds its own namespace, as the tests do, may
    # predate the flag (20 October 2026).
    exhaust = getattr(args, "box_exhaust", False)
    if args.box or exhaust:
        # A question with no URL names no page to read. The box decides whether that is
        # because it is not about the shop (a bypass) or an error.
        url = box_module.results_url(query, required=False)
        page = results_page(url) if url else None
        decision = box_module.decide(query, page, reply=args.reading, exhaust=exhaust)
        applied.update(strategy=decision.kind, box=decision.record(), page=page,
                       decision=decision)
        if decision.query is None:
            return None, applied
        query = decision.query
    if args.targeting:
        # Through the planner rather than straight to the strategy table. The plan is
        # checked for soundness before the agent ever sees it, and `render` returns the
        # frozen strategy text unchanged, so a run planned this way receives the same
        # bytes it would have received before. Verified over every question by
        # `planner.py --regression`. A plan that fails verification raises rather than
        # running, because paying a model to execute a plan already known to be unsound
        # buys nothing.
        query, applied["strategy"] = planner_module.planned_query(query)
    if args.exhaustive:
        query = policy_module.exhaustive_query(query)
    if args.confidence != "off":
        query = policy_module.confidence_query(query, args.confidence)
    return query, applied


def arm_of(args) -> str:
    """Which retrieval instruction the batch adds to every question, the arm's name in its
    payload (20 October 2026): the box, the box without its stop rule, the targeting
    strategies, the open-everything instruction, the last two together, or none. The
    other conditions of an arm (probe, scaffold, shop, model) have their own fields."""
    if getattr(args, "box_exhaust", False):
        return "box-exhaust"
    if args.box:
        return "box"
    named = [name for name, on in (("targeting", args.targeting),
                                   ("exhaustive", args.exhaustive)) if on]
    return "+".join(named) or "none"


def asked_row(task: dict, repeat: int, box_record: dict) -> dict:
    """A run slot the box closed without running the agent: it asked the user, or (box v2)
    it refused because the shop does not show what the question needs. Nothing was spent,
    so the cost is zero rather than unknown."""
    refused = box_record.get("refuse")
    return {"task": task["id"], "family": task["family"], "gated": task["gated"],
            "repeat": repeat, "verdict": "refused" if refused else "asked",
            "why": ("the box refused: the shop does not show what the question needs"
                    if refused else "the box asked the user and no --reading answered it"),
            "answer": (refused or box_record["ask"])[:300],
            "tool_calls": None, "actions": None, "observations": None,
            "cost_usd": 0, "elapsed_s": 0, "error": None, "log": None,
            "box": box_record, "reading": None}


def box_fields(box_record: dict) -> dict:
    """What a run under the box records about it: the box's own record, the reading the
    question was answered under, and who chose it.

    The reading is the box record's: the scripted user's reply where the box asked, the
    box's own choice where one reading had no answer on this shop (`box.decide`,
    `reading_by` "box"), and None on a question the box never asked, where no reading is
    a condition of the run. Until 14 Oct 2026 every row under `--reading menu` said
    `reading: "menu"`, the clear questions included; until 20 Oct a row the box read as
    buyable said None, and the run was scored under the menu key (verifier findings)."""
    return {"box": box_record, "reading": box_record.get("reading"),
            "reading_by": box_record.get("reading_by")}


def reading_answered(box_record: dict | None, flag: str | None) -> str | None:
    """The reading a run answered under, which its scoring key follows: the box record's
    when the box ran, a reply or the box's own choice, else the `--reading` flag, which
    without the box is None."""
    return box_record.get("reading") if box_record else flag


def print_dry_task(task: dict, query: str | None, applied: dict) -> None:
    """One task of the dry run: the exact text, through the same function the paid loop
    uses, so what is read here is what the agent gets (LESSONS 17). An ask is printed as
    the box's question, a refusal as what the box said was missing, a reading the box took
    on its own as a line before the text."""
    print(f"  {task['id']:26} gated={task['gated']}  {task['expect']['kind']}")
    record = applied["box"]
    if query is not None and record and record["bypassed"]:
        print(f"BYPASS: {query}")
    elif query is not None:
        if record and record.get("reading_by") == "box":
            print(f"reading taken by the box: {record['reading']}")
        print(query)
    elif record["refuse"]:
        print(f"REFUSES: {record['refuse']}")
    else:
        print(f"ASKS: {record['ask']}")
    print()


def gate_for(task: dict, spec: dict, answer: str, log_path: pathlib.Path,
             page: page_module.Page | None,
             decision: box_module.Decision | None = None) -> dict:
    """The refusal check. Under box v2 it is the box's own: v1's page-derived rules, then
    the plan's primitive check, and for a bypassed question the figure rules alone, since
    the box read no page and made no plan to hold the answer to. Under v1 it read the
    market size and the floor from the page the box fetched. Without the box it is the
    evaluation tool it was, reading both from the answer key."""
    if decision is not None and (decision.plan is not None or decision.bypass):
        return box_module.check(decision, answer, log_path)
    if page is not None:
        question = task["query"].format(base=spec["base_url"])
        return policy_module.gate_from_page(question, page, answer, log_path)
    return policy_module.gate(task, spec, answer, log_path)


def apply_policy(mode: str, task: dict, spec: dict, answer: str, record: dict,
                 out_dir: pathlib.Path, tag: str, confidence: str = "off",
                 reason: str | None = None, scaffold: str = "openjiuwen",
                 shop: str = "gated", probe: str = "viewport",
                 page: page_module.Page | None = None,
                 decision: box_module.Decision | None = None) -> tuple:
    """Run the sufficiency check and act on it.

    Cost and interaction counts are reported for the arm as a whole, both attempts
    included. A policy that buys accuracy with a second full run has to be charged for
    it, or the comparison against the baseline is not a comparison.

    `page` is the results page the box read, when it ran, and makes the check read the
    market from the page rather than from the answer key. `decision` is the box's plan,
    and makes the check the plan's own.
    """
    result = record.get("result") or {}
    trace = record.get("trace") or {}
    check = gate_for(task, spec, answer, out_dir / f"{tag}.log", page, decision)

    if check["ok"] or mode == "gate":
        if not check["ok"]:
            answer = policy_module.abstention_for(check)
        return answer, record, result, trace, check

    build = (policy_module.investigate_query if mode == "investigate"
             else policy_module.retry_query)
    query = build(task["query"].format(base=spec["base_url"]), check, reason=reason)
    if confidence != "off":
        query = policy_module.confidence_query(query, confidence)
    tag2 = f"{tag}-{mode}"
    # The retry is the same arm and must meet the same shop with the same agent. Before
    # this it always ran openJiuwen against the default theme, whatever the first attempt
    # had been, so a naive policy run silently changed both halfway through.
    second = run_once(task, spec["base_url"], out_dir, tag2, query=query,
                      scaffold=scaffold, shop=shop, probe=probe)
    result2 = second.get("result") or {}
    answer2 = str(result2.get("final") or "")
    trace2 = second.get("trace") or {}
    check2 = gate_for(task, spec, answer2, out_dir / f"{tag2}.log", page, decision)

    # Still unverified after being told why: abstain rather than emit it a second time.
    final_answer = answer2 if check2["ok"] else policy_module.abstention_for(check2)
    merged = {**second,
              "cost_usd": add(record.get("cost_usd"), second.get("cost_usd")),
              "elapsed_s": add(record.get("elapsed_s"), second.get("elapsed_s"))}
    merged_trace = {key: add(trace.get(key), trace2.get(key))
                    for key in ("tool_calls_total", "actions", "observations")}
    return final_answer, merged, result2, merged_trace, {
        **check2, "retried": True, "first_flag": check["flag"],
        "first_why": check["why"], "first_answer": answer[:300]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repeats", type=int, default=5)
    # The claim runs each arm as three rounds of `--repeats 1` with the arm order rotated,
    # so a round's runs must say which round they are: repeat N, N+1 and so on, in the
    # run's file names, its log and its suite.json row (20 October 2026).
    parser.add_argument("--repeat-start", type=int, default=1, metavar="N",
                        help="number the repeats from N, so a batch run as one round of "
                             "several carries that round's repeat numbers. Default 1")
    parser.add_argument("--tasks", type=pathlib.Path, default=paths.TASKS / "tasks.json")
    parser.add_argument("--only", nargs="*", help="task ids to run, default all")
    parser.add_argument("--targeting", action="store_true",
                        help="choose a retrieval strategy from the question before "
                             "opening anything. The second half of RQ3")
    parser.add_argument("--exhaustive", action="store_true",
                        help="instruct the agent to open every listing. The upper bound "
                             "on cost, correct and expensive, that a targeting policy has "
                             "to beat")
    parser.add_argument("--confidence", choices=("off", "plain", "retrieval"), default="off",
                        help="ask the agent to state a confidence with its answer. This is "
                             "the verbalised-confidence baseline, not part of the "
                             "contribution, and is measured to answer the obvious "
                             "objection rather than to be used")
    parser.add_argument("--policy", choices=("off", "gate", "retry", "investigate"),
                        default="off",
                        help="off is the unmodified baseline; gate abstains on a failed "
                             "sufficiency check; retry re-asks the whole task with the "
                             "reason; investigate asks the agent to diagnose its own "
                             "error and retrieve only what settles it")
    parser.add_argument("--scaffold", choices=("openjiuwen", "naive"), default="openjiuwen",
                        help="which agent answers. naive is the from-scratch loop with no "
                             "card probe, the control for whether the failure belongs to "
                             "the agent or to one agent's default")
    parser.add_argument("--shop", choices=("gated", "default"), default="gated",
                        help="gated suppresses the variant prices the stock theme puts in\n"
                             "the page, which is what the live marketplace does. default is\n"
                             "the leaky shop every run before 18 Sep 2026 was measured on")
    parser.add_argument("--probe", choices=("viewport", "whole-page"), default="viewport",
                        help="viewport is openJiuwen's shipped card probe, which reports "
                             "only what is on screen. whole-page flips that one setting and "
                             "changes nothing else, which is the arm that separates the tool "
                             "from the model as the cause of stopping at four listings")
    parser.add_argument("--box", action="store_true",
                        help="run the box first: it reads the results page, asks back on an "
                             "ambiguous question, and otherwise plans the retrieval. The "
                             "contribution. Excludes --targeting, --exhaustive and, until "
                             "its browser is confined to the shop, --scaffold naive")
    parser.add_argument("--box-exhaust", action="store_true",
                        help="the box without its stop rule: the same text as --box for every "
                             "question, except that every gated plan opens every listing on "
                             "the page before answering. The arm that isolates the stop rule "
                             "for research question 3. Excludes --box, --targeting and "
                             "--exhaustive, and everything --box excludes")
    parser.add_argument("--reading", choices=("menu", "buyable"),
                        help="the scripted user's reply when the box asks. menu: a size in "
                             "the listing's menu counts, sold out or not, which is the "
                             "task's own key. buyable: only a size that can be sold now, "
                             "the key in tasks/readings_<market>.json. Without it a box "
                             "that asks records the ask, runs no agent and spends nothing")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the exact text each task would send, and run nothing")
    args = parser.parse_args()

    # The box plans the retrieval itself, so a second strategy on top of it would measure
    # a mixture. A reading is a reply to the box's question, so it means nothing without
    # the box. The retry arms rebuild the query from the task text, without the box's
    # plan, so under the box only the gate is supported in v1.
    if args.box and (args.targeting or args.exhaustive):
        parser.error("--box cannot be combined with --targeting or --exhaustive: the box "
                     "plans the retrieval itself")
    # The arm without the stop rule is its own arm (20 October 2026): with --box it would
    # be two arms in one batch, and with --targeting or --exhaustive a mixture of plans.
    if args.box_exhaust and (args.box or args.targeting or args.exhaustive):
        parser.error("--box-exhaust cannot be combined with --box, --targeting or "
                     "--exhaustive: it is an arm of its own")
    # From here on --box-exhaust is the box as far as every rule about the box goes.
    boxed = args.box or args.box_exhaust
    if args.reading and not boxed:
        parser.error("--reading is the scripted reply to the box's question, so it needs "
                     "--box or --box-exhaust")
    if args.repeat_start < 1:
        parser.error("--repeat-start numbers the first repeat, so it is 1 or more")
    if boxed and args.policy in ("retry", "investigate"):
        parser.error("--box supports --policy off or gate only in v1: the retry arms "
                     "rebuild the query without the box's plan")
    # The naive loop launches its own browser with a user agent and nothing else
    # (`naive_agent.py`, `driver.chromium.launch()` and `browser.new_context`), so
    # `browser_conditions` records it as not confined to the shop, where openJiuwen on the
    # gated shop gets --allowed-origins. A question the box bypasses names no shop page, so
    # under the box that browser could be sent to a live site, which this project never
    # does. Refused until the second agent's browser is confined too (14 October 2026,
    # verifier finding).
    if boxed and args.scaffold == "naive":
        parser.error("--box cannot be combined with --scaffold naive: the second agent's "
                     "browser is not confined to the shop, since it launches its own without "
                     "--allowed-origins, and a question the box bypasses could take it off "
                     "localhost. Refused until it is confined")

    # Task files moved into experiments/tasks/ on 8 Oct 2026. Commands in the decision log
    # still name the old place, so a missing path falls back to the same file name there.
    if not args.tasks.exists() and (paths.TASKS / args.tasks.name).exists():
        print(f"note: {args.tasks} has moved, reading {paths.TASKS / args.tasks.name}")
        args.tasks = paths.TASKS / args.tasks.name
    spec = json.loads(args.tasks.read_text())
    # An id that names no task is an error, by name. Until 14 Oct 2026 it was dropped
    # without a word, so a misspelt --only ran the rest as if nothing were missing
    # (verifier finding at 7d2ec2e).
    known = {t["id"] for t in spec["tasks"]}
    unknown = [task_id for task_id in args.only or [] if task_id not in known]
    if unknown:
        parser.error(f"--only names a task that is not in {args.tasks.name}: {', '.join(unknown)}")
    tasks = [t for t in spec["tasks"] if not args.only or t["id"] in args.only]
    if not tasks:
        print("no matching tasks")
        return 1
    # The scripted user's other readings of the ambiguous questions, for scoring under
    # `--reading`. Empty when the task file has no sidecar.
    readings = scoring.readings_for(args.tasks)

    # Which agent code answers, read once before anything runs and printed in the header
    # so the dry run shows it too. Only openJiuwen lives in the submodule.
    agent_code = (agent_code_identity() if args.scaffold == "openjiuwen"
                  else {"agent_core_commit": None, "agent_core_patch": None})
    browser = browser_conditions(args.scaffold, args.shop)

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir = RESULTS / stamp
    total = len(tasks) * args.repeats
    # The repeat numbers the runs carry (`--repeat-start`). The header names them only when
    # they do not start at 1, so a default batch prints what it always printed.
    repeats = range(args.repeat_start, args.repeat_start + args.repeats)
    numbered = (f", repeats {repeats[0]} to {repeats[-1]}"
                if args.repeat_start != 1 and args.repeats > 0 else "")
    print(f"{len(tasks)} tasks x {args.repeats} repeats = {total} runs{numbered} -> {out_dir}")
    print("agent code: " + " ".join(f"{key}={value}" for key, value in agent_code.items()))
    # The browser's conditions in the header too, so the dry run shows what a paid run
    # under the same flags would record.
    print("browser: " + " ".join(f"{key}={value}" for key, value in browser.items()))
    # The arm, so a dry run of the box and of the box without its stop rule say which.
    print(f"arm: {arm_of(args)}")

    if args.dry_run:
        # The exact text, through the same function the paid loop uses, so what is read
        # here is what the agent gets (LESSONS 17). An ask is printed as the box's question,
        # a refusal as what the box said was missing. Under the box, the counts the batch
        # would record and how many of its slots would reach the agent come last.
        records = []
        for task in tasks:
            query, applied = build_query(task, spec, args)
            records.append(applied["box"])
            print_dry_task(task, query, applied)
        summary = dry_summary(records, args.repeats)
        if summary:
            print(summary)
        return 0

    out_dir.mkdir(parents=True, exist_ok=True)
    rows, done = [], 0
    for task in tasks:
        for repeat in repeats:
            done += 1
            tag = f"{task['id']}-{repeat}"
            query, applied = build_query(task, spec, args)
            strategy = applied["strategy"]
            if query is None:
                # The box asked and no scripted reply was given, or it refused. Either is
                # the outcome: no agent runs and nothing is spent.
                row = asked_row(task, repeat, applied["box"])
                rows.append(row)
                print(f"[{done}/{total}] {tag:32} {row['verdict']:10} the box {row['verdict']}")
                continue
            record = run_once(task, spec["base_url"], out_dir, tag, query=query,
                              scaffold=args.scaffold, shop=args.shop, probe=args.probe)
            result = record.get("result") or {}
            answer = str(result.get("final") or "")
            trace = record.get("trace") or {}

            # Read the stated confidence, then take it out of the answer. The scorer looks
            # for money and a two-digit percentage sitting in the text can be read as one.
            confidence, reason = None, None
            if args.confidence != "off":
                confidence = policy_module.parse_confidence(answer)
                reason = policy_module.parse_reason(answer)
                answer = policy_module.strip_confidence(answer)

            check = None
            if args.policy != "off":
                answer, record, result, trace, check = apply_policy(
                    args.policy, task, spec, answer, record, out_dir, tag,
                    confidence=args.confidence, reason=reason,
                    scaffold=args.scaffold, shop=args.shop, probe=args.probe,
                    page=applied["page"], decision=applied["decision"])

            # Scored against the key for the reading the run answered under, the user's
            # reply or the box's own choice, when the sidecar has one for this task, and
            # against the task's own key otherwise.
            answered = reading_answered(applied["box"], args.reading)
            verdict = scoring.score(scoring.under_reading(task, answered, readings),
                                    answer, bool(result.get("ok")))
            row = {
                "task": task["id"], "family": task["family"], "gated": task["gated"],
                "repeat": repeat,
                "verdict": verdict["verdict"], "why": verdict["why"],
                "answer": answer[:300],
                "tool_calls": trace.get("tool_calls_total"),
                "actions": trace.get("actions"),
                "observations": trace.get("observations"),
                "cost_usd": record.get("cost_usd"),
                "elapsed_s": record.get("elapsed_s"),
                "error": record.get("error") or result.get("error"),
                "log": record.get("log"),
            }
            if strategy:
                row["strategy"] = strategy
            if boxed:
                # The page the box read, whether it asked, the reading answered under and
                # who chose it, and the exact query, so a run under the box says what
                # produced it.
                row.update(box_fields(applied["box"]))
            if args.confidence != "off":
                row["confidence"] = confidence
                row["confidence_reason"] = reason
                row["confidence_wording"] = args.confidence
            if check is not None:
                row.update({"policy": args.policy, "flag": check.get("flag"),
                            "flag_why": check.get("why"),
                            "opened": check.get("opened"),
                            # The market size and floor the check used, and where they
                            # came from: the page under the box, the answer key otherwise.
                            "population": check.get("population"),
                            "floor": check.get("floor"),
                            "floor_from": check.get("floor_from", "answer key"),
                            "retried": bool(check.get("retried")),
                            "first_flag": check.get("first_flag"),
                            "first_why": check.get("first_why"),
                            "first_answer": check.get("first_answer")})
            rows.append(row)
            conf = f" conf={row.get('confidence')}" if args.confidence != "off" else ""
            conf += f" [{strategy}]" if strategy else ""
            conf += " [bypass]" if boxed and applied["box"]["bypassed"] else ""
            if boxed and applied["box"].get("reading_by") == "box":
                conf += f" [reading taken by the box: {applied['box']['reading']}]"
            print(f"[{done}/{total}] {tag:32} {row['verdict']:10} "
                  f"calls={row['tool_calls']} act={row['actions']}{conf} "
                  f"${row['cost_usd']} {row['elapsed_s']}s")

    summary = summarise(rows)
    payload = {"ran_at": dt.datetime.now().isoformat(timespec="seconds"),
               "repeats": args.repeats,
               # The first repeat's number, see `--repeat-start`. Absent before 20 Oct
               # 2026, when every batch numbered its repeats from 1.
               "repeat_start": args.repeat_start,
               "policy": args.policy,
               "confidence": args.confidence,
               "exhaustive": args.exhaustive,
               "targeting": args.targeting,
               # The box plans through the same classifier and planner, so both versions
               # are recorded under it too.
               "targeting_version": (targeting_module.VERSION
                                     if args.targeting or boxed else None),
               "planner_version": (planner_module.VERSION
                                   if args.targeting or boxed else None),
               # `box` is --box alone. The box without its stop rule is its own arm, so a
               # reader that selects box batches by this field never pools it with them
               # (LESSONS 7); `arm` names every arm (20 October 2026).
               "box": args.box,
               "box_exhaust": args.box_exhaust,
               "arm": arm_of(args),
               "box_version": box_module.VERSION if boxed else None,
               # Box v2 parses through form.py and plans through primitives.py, each
               # versioned on its own, so a run says which of each produced it.
               "form_version": form_module.VERSION if boxed else None,
               "primitives_version": primitives_module.VERSION if boxed else None,
               "reading": args.reading,
               # The pinned browser tool, the origins the browser may request and the
               # flags it runs with, see `browser_conditions`: `browser_tool`,
               # `browser_origins` and `browser_flags`.
               **browser,
               # Which scorer judged the rows (LESSONS 10). Absent before 14 Oct 2026,
               # when every batch was scored by version 1.
               "scorer_version": scoring.VERSION,
               # Which sufficiency rules judged this suite. A verdict that does not say
               # what judged it cannot be compared with one scored under different rules,
               # and the rules have now changed once.
               "rules_version": sufficiency.RULES_VERSION if args.policy != "off" else None,
               # Which model answered. Until now this lived only in the per-run records,
               # which was enough while every run used the same one. A second model is a
               # second arm, and an arm whose suite does not say what produced it cannot be
               # compared with anything.
               "model": os.environ.get("MODEL_NAME") or model_from_records(out_dir),
               "scaffold": args.scaffold,
               # Which openJiuwen code answered: the submodule's commit and the sha1 of
               # its uncommitted patch, see `agent_code_identity`. None for the naive loop.
               "agent_core_commit": agent_code["agent_core_commit"],
               "agent_core_patch": agent_code["agent_core_patch"],
               "tasks_file": args.tasks.name,
               "draw": draw_id(spec),
               # The ground truth this suite was scored against. The catalogue is
               # regenerated between rounds, so without it an old result cannot be told
               # apart from a wrong one.
               "instance": spec.get("_instance"),
               "summary": summary, "rows": rows}
    (out_dir / "suite.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")

    print_summary(summary, rows)
    print(f"\nfull results: {out_dir / 'suite.json'}")
    return 0


def summarise(rows: list[dict]) -> dict:
    by_task: dict[str, dict] = {}
    for row in rows:
        entry = by_task.setdefault(row["task"], {
            "gated": row["gated"], "verdicts": collections.Counter(),
            "actions": [], "tool_calls": [], "cost": []})
        entry["verdicts"][row["verdict"]] += 1
        for key, field in (("actions", "actions"), ("tool_calls", "tool_calls"),
                           ("cost", "cost_usd")):
            if row[field] is not None:
                entry[key].append(row[field])

    for entry in by_task.values():
        entry["verdicts"] = dict(entry["verdicts"])
        entry["mean_actions"] = mean(entry["actions"])
        entry["mean_tool_calls"] = mean(entry["tool_calls"])
        entry["total_cost"] = round(sum(entry["cost"]), 4) if entry["cost"] else None

    overall = collections.Counter(row["verdict"] for row in rows)
    return {"by_task": by_task, "overall": dict(overall),
            "total_cost": round(sum(r["cost_usd"] for r in rows if r["cost_usd"]), 4),
            "box": box_counts(rows)}


def box_counts(rows: list[dict]) -> dict | None:
    """How many rows the box asked on, refused, bypassed and planned by its fallback, so
    the rate at which questions get past it is a figure of the batch (14 Oct 2026). Asked
    counts every row the box put its question on, whether or not a `--reading` answered
    it: the verdicts say which. Fallback counts a row the fallback planned and the agent
    ran, so a fallback the box then refused, or asked on with no reading to answer it, is
    counted under refused or asked alone. Until 14 Oct 2026 a refused fallback was counted
    twice (verifier finding). None when no row went through the box."""
    records = [row["box"] for row in rows if row.get("box")]
    if not records:
        return None
    return {"asked": sum(1 for r in records if r.get("asked")),
            "refused": sum(1 for r in records if r.get("refuse")),
            "bypassed": sum(1 for r in records if r.get("bypassed")),
            "fallback": sum(1 for r in records if r.get("fallback") and r.get("query") is not None)}


def dry_summary(records: list[dict | None], repeats: int) -> str | None:
    """What a batch under the box would count, from the dry run's one decision per task:
    `box_counts` over the rows the paid loop would write, and how many of its slots reach
    the agent, since an asked or refused slot runs nothing. None without the box. Added
    14 Oct 2026 so the v2 task file's expectations can be checked before anything is spent."""
    rows = [{"box": record} for record in records if record] * repeats
    counts = box_counts(rows)
    if counts is None:
        return None
    reach = sum(1 for record in records if record and record["query"] is not None) * repeats
    return (f"box: asked {counts['asked']}, refused {counts['refused']}, bypassed "
            f"{counts['bypassed']}, fallback {counts['fallback']}; {reach} of "
            f"{len(records) * repeats} runs would reach the agent")


def mean(values: list) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def print_summary(summary: dict, rows: list[dict]) -> None:
    print("\n" + "=" * 78)
    print(f"{'task':28} {'gated':5} {'verdicts':28} {'acts':>5} {'calls':>6}")
    print("-" * 78)
    for task_id, entry in summary["by_task"].items():
        verdicts = " ".join(f"{k}:{v}" for k, v in sorted(entry["verdicts"].items()))
        print(f"{task_id:28} {str(entry['gated']):5} {verdicts:28} "
              f"{str(entry['mean_actions']):>5} {str(entry['mean_tool_calls']):>6}")
    print("-" * 78)
    print("overall:", summary["overall"])
    if summary.get("box"):
        counts = summary["box"]
        print(f"box: asked {counts['asked']}, refused {counts['refused']}, "
              f"bypassed {counts['bypassed']}, fallback {counts['fallback']}")
    print("total cost: $", summary["total_cost"])

    gated = [r for r in rows if r["gated"] and r["actions"] is not None]
    correct = [r["actions"] for r in gated if r["verdict"] == "correct"]
    wrong = [r["actions"] for r in gated if r["verdict"] == "wrong"]
    if correct and wrong:
        print(f"\ngated tasks, mean actions: correct {mean(correct)}, wrong {mean(wrong)}")


if __name__ == "__main__":
    raise SystemExit(main())
