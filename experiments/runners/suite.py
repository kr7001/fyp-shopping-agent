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
import normalise as normalise_module
import page as page_module
import parse_probe  # the one call to the provider a parse makes, and its charge
import plan_probe  # the key and the agent's model, read the same way
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


# The agent's step and clock limits (22 October 2026, for the second claim run, which raises
# both for every arm alike, to 300 steps and 1800 s, since browsing two results pages whole
# runs past these). The defaults are openJiuwen's own, which every batch before ran under:
# its guardrail's DEFAULT_GUARDRAIL_MAX_STEPS (agent-core, harness/tools/browser_move/utils/
# env.py), passed as BROWSER_GUARDRAIL_MAX_STEPS, and the runner's --timeout
# (run_browser_task.py), its run's deadline; `tests/test_claim_arms.py` holds both to the
# source. The naive loop has a step limit of its own, NAIVE_STEP_LIMIT (`naive_agent.py`),
# and no clock, so neither flag reaches it.
DEFAULT_MAX_STEPS = 100
DEFAULT_CLOCK_S = 600
NAIVE_STEP_LIMIT = 100


def limits(scaffold: str, max_steps: int | None = None, clock_s: int | None = None) -> dict:
    """The step and clock limits a run of this scaffold runs under: the flags' for
    openJiuwen, the defaults when none is given, and the naive loop's own."""
    if scaffold == "naive":
        return {"max_steps": NAIVE_STEP_LIMIT, "clock_s": None}
    return {"max_steps": max_steps or DEFAULT_MAX_STEPS, "clock_s": clock_s or DEFAULT_CLOCK_S}


# The model parser (box v13, 22 October 2026). It reads each run's question through one call
# at temperature 0, the setting of every parse probe, with no retry. Its model is the
# agent's own unless `--parser-model` names another, read the way the agent reads it
# (`run_browser_task.py`): MODEL_NAME in the environment, then in the repository's .env,
# then this default.
PARSER_TEMPERATURE = 0
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"


def agent_model() -> str:
    """The model the agent will run, as the agent reads it."""
    if os.environ.get("MODEL_NAME"):
        return os.environ["MODEL_NAME"]
    if (REPO / ".env").exists():
        return plan_probe.model_name()
    return DEFAULT_MODEL


def parser_call(model: str, key: str, charges: list, tokens: list | None = None):
    """The model parser's call for one run: one request to `model` through
    `parse_probe.call_model` (temperature 0, no retry), the provider's charge for it
    appended to `charges`. A reply that is no completion raises as a failed call with the
    charge its body states, if any. A request that fails otherwise, a timeout, an HTTP error
    or a body that is not JSON, may or may not have been charged, and nothing says which, so
    its charge is unknown, None, never $0 (verifier finding, 22 October 2026). Either way
    the box then uses the rules' form and says why. The call's tokens go to `tokens` the
    same way (23 October 2026): the provider's count, or None where it gave none."""
    def call(prompt: str) -> str:
        try:
            text, cost, used = parse_probe.call_model(key, model, prompt)
        except parse_probe.UnexpectedReply as fault:
            charges.append(fault.cost)
            if tokens is not None:
                tokens.append(fault.tokens)
            raise
        except Exception:
            charges.append(None)
            if tokens is not None:
                tokens.append(None)
            raise
        charges.append(cost)
        if tokens is not None:
            tokens.append(used)
        return text
    return call


def parse_cost(charges: list) -> float | None:
    """What a run's parse cost: its charges summed, 0 when no call was made, and None when
    the provider did not say what a call cost, since a missing cost is unknown, not zero."""
    if any(charge is None for charge in charges):
        return None
    return round(sum(charges), 6)


def stubbed_replies(path: pathlib.Path) -> dict[str, str]:
    """Recorded or stubbed model replies for a dry run under the model parser, by task id,
    from a JSON file {"replies": {task id: reply text}}, so the dry run can show the plan a
    reply gives while sending nothing. A paid run never reads one (`main` refuses it)."""
    data = json.loads(path.read_text())
    replies = data.get("replies") if isinstance(data, dict) else None
    if not isinstance(replies, dict) or not all(isinstance(text, str) for text in replies.values()):
        raise ValueError(f'{path} must hold {{"replies": {{task id: reply text}}}}')
    return replies


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
             shop: str = "gated", probe: str = "viewport",
             max_steps: int | None = None, clock_s: int | None = None) -> dict:
    """Execute one task once and return its record, enriched with trace counts.

    `query` overrides the task text, which is how a policy retry re-asks the same task
    with the reason its first answer was rejected. `max_steps` and `clock_s` are the
    agent's limits (`limits`), the defaults when None, recorded in the record.
    """
    bounds = limits(scaffold, max_steps, clock_s)
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
        command = ["uv", "run", "python", str(RUNNER), query, "--out", str(record_path),
                   "--timeout", str(bounds["clock_s"])]
        cwd = AGENT_CORE
    env = browser_env(shop, probe, cache_dir=out_dir / "caches" / tag)
    # Set always, so the limit is the suite's and never one left in the shell.
    if scaffold != "naive":
        env["BROWSER_GUARDRAIL_MAX_STEPS"] = str(bounds["max_steps"])

    with log_path.open("w") as log:
        subprocess.run(command, cwd=cwd, env=env,
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
    # The step and clock limits it ran under (22 October 2026). A record without them ran
    # under openJiuwen's defaults, 100 steps and 600 s, or the naive loop's 100 steps.
    record.update(bounds)
    # The naive loop stamps its own scaffold, openJiuwen's runner does not, so a mixed
    # directory had records where the field was simply absent. Stamped here for both, since
    # a record that cannot say which agent produced it is how four arms got pooled once.
    record.setdefault("scaffold", scaffold)
    record_path.write_text(json.dumps(record, indent=2, default=str) + "\n")
    return record


def parse_tokens(counts: list) -> dict | None:
    """What a run's parse used (23 October 2026): each call's prompt and completion tokens
    summed, with the number of calls; zeros when no call was made, and None when a call's
    count is unknown, since a missing count is unknown, not zero."""
    if any(count is None for count in counts):
        return None
    prompt = sum(count["prompt"] for count in counts)
    completion = sum(count["completion"] for count in counts)
    return {"prompt": prompt, "completion": completion, "total": prompt + completion,
            "calls": len(counts)}


def run_tokens(agent: dict | None, parse: dict | None) -> dict | None:
    """A run's tokens, the agent's and its parse's together, or None when either is
    unknown (23 October 2026)."""
    if not agent or parse is None:
        return None
    prompt = (agent.get("prompt") or 0) + parse["prompt"]
    completion = (agent.get("completion") or 0) + parse["completion"]
    return {"prompt": prompt, "completion": completion, "total": prompt + completion}


def charge_parse(record: dict, parsed: float | None, record_path: pathlib.Path,
                 parsed_tokens: dict | None = None) -> dict:
    """A run's record with its parse charged to it (22 October 2026): `cost_usd` becomes
    what the run cost, the agent's charges and the parse's, beside `agent_cost_usd`, which
    the log's own charges re-sum to (`verify_cells`), and `parse_cost_usd`. None when either
    part is unknown, since a missing cost is unknown, not zero. Its tokens the same way since
    23 October 2026: `tokens`, the run's, beside `agent_tokens`, the log's own count, and
    `parse_tokens` (`parse_tokens`); the agent's `trace` is left as the log gives it. Written
    back into the run's record file when the runner wrote one, so the file says what its
    run cost."""
    agent = record.get("cost_usd")
    agent_tokens = (record.get("trace") or {}).get("tokens")
    record = {**record, "agent_cost_usd": agent, "parse_cost_usd": parsed,
              "cost_usd": None if agent is None or parsed is None else round(agent + parsed, 6),
              "agent_tokens": agent_tokens, "parse_tokens": parsed_tokens,
              "tokens": run_tokens(agent_tokens, parsed_tokens)}
    if record_path.exists():
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


def tasks_file_name(path: pathlib.Path) -> str:
    """The task file as a batch records it (`tasks_file`), which every reader opens again as
    `paths.TASKS / tasks_file`: verify_cells, claim, replay_box, voids, rescore, leaks and
    the layout test. Its path under experiments/tasks/, so a pilot's file in
    experiments/tasks/pilot/ is found again (23 October 2026); for a file directly there that
    is its name, as every batch before recorded. A file outside, a test's, keeps its name, and
    so does a link to one of ours there: only the folder is resolved, never the file."""
    try:
        folder = path.absolute().parent.resolve().relative_to(paths.TASKS.resolve())
    except ValueError:
        return path.name
    return (folder / path.name).as_posix()


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


def results_page(url: str, reader: str = page_module.READERS[0]) -> page_module.Page:
    """Every results page of the search, read once per batch by the batch's reader
    (`--page-reader`, box v16): one batch, one reader, so the cache is by address alone."""
    if url not in PAGES:
        PAGES[url] = page_module.read(url, reader)
    return PAGES[url]


def build_query(task: dict, spec: dict, args, call=None) -> tuple[str | None, dict]:
    """The exact text the agent receives, and what produced it.

    One function for the dry run and the paid loop, so the text the verifier reads is the
    text the agent gets (LESSONS 17). Applied in order: the box, or the box without its stop
    rule under `--box-exhaust`, targeting, the exhaustive instruction, the confidence
    prompt. The text is None when the box asked and no `--reading` answered it, or when it
    refused. A question the box bypasses comes back as its own text, which is what the
    agent then gets. The dict holds the strategy kind, the box's record, the page it read
    and its decision, each None when not used.

    Under `--parser model` the box reads the question through `call`, which the paid loop
    makes with `parser_call` for each run and a dry run makes from a replies file, so a
    dry run sends nothing (22 October 2026).
    """
    query = task["query"].format(base=spec["base_url"])
    applied = {"strategy": None, "box": None, "page": None, "decision": None}
    # Read with a default: a caller that builds its own namespace, as the tests do, may
    # predate the flag (20 October 2026), or the parser's (22 October 2026).
    exhaust = getattr(args, "box_exhaust", False)
    if args.box or exhaust:
        # A question with no URL names no page to read. The box decides whether that is
        # because it is not about the shop (a bypass) or an error.
        url = box_module.results_url(query, required=False)
        # Every results page, by the batch's reader (box v16). A namespace a test builds may
        # predate the flag, and reads by the default.
        reader = getattr(args, "page_reader", None) or page_module.READERS[0]
        page = results_page(url, reader) if url else None
        # Anything but the word "model" is the rules: a namespace a test builds, a mock
        # among them, may have no parser of its own. The command line allows only the two.
        parser = "model" if getattr(args, "parser", "rules") == "model" else "rules"
        # How a rate question is planned (box v18). Anything but the word "every" is the bound,
        # the default, as for the parser: a namespace a test builds, a mock among them, may
        # have no rate plan of its own.
        rate = "every" if getattr(args, "rate_plan", None) == "every" else "bound"
        # The scripted user's reply for this question, its own reading under "own" (23
        # October 2026); a namespace a test builds may have no `two_readings`.
        reply = scripted_reply(task, args.reading, getattr(args, "two_readings", None))
        decision = box_module.decide(query, page, reply=reply, exhaust=exhaust,
                                     parser=parser, call=call, rate=rate)
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
        # Every listing, the default, or every listing of the task's product (22 October 2026).
        wording = getattr(args, "exhaustive_wording", None) or "every"
        query = policy_module.exhaustive_query(query, task["product"] if wording == "product" else None)
    if args.confidence != "off":
        query = policy_module.confidence_query(query, args.confidence)
    return query, applied


def arm_of(args) -> str:
    """Which retrieval instruction the batch adds to every question, the arm's name in its
    payload (20 October 2026): the box, the box without its stop rule, the targeting
    strategies, the open-everything instruction, the last two together, or none. The
    other conditions of an arm (probe, scaffold, shop, model) have their own fields.

    The box read by the model parser is another arm, "box-model" or "box-exhaust-model"
    (22 October 2026), so a reader that selects box batches by their arm never pools the
    two parsers (LESSONS 7). A namespace without the flag is the rules'."""
    model = getattr(args, "parser", "rules") == "model"
    if getattr(args, "box_exhaust", False):
        return "box-exhaust-model" if model else "box-exhaust"
    if args.box:
        return "box-model" if model else "box"
    # Open everything naming the question's product is an arm of its own (22 October 2026).
    product = getattr(args, "exhaustive_wording", None) == "product"
    named = [name for name, on in (("targeting", args.targeting),
                                   ("exhaustive-product" if product else "exhaustive", args.exhaustive)) if on]
    return "+".join(named) or "none"


def asked_row(task: dict, repeat: int, box_record: dict, cost: float | None = 0) -> dict:
    """A run slot the box closed without running the agent: it asked the user, or (box v2)
    it refused because the shop does not show what the question needs. No agent ran, so
    under the rules nothing was spent and the cost is zero rather than unknown. Under the
    model parser the parse was paid for, and `cost` is what it cost (22 October 2026)."""
    refused = box_record.get("refuse")
    return {"task": task["id"], "family": task["family"], "gated": task["gated"],
            "repeat": repeat, "verdict": "refused" if refused else "asked",
            "why": ("the box refused: the shop does not show what the question needs"
                    if refused else "the box asked the user and no --reading answered it"),
            "answer": (refused or box_record["ask"])[:300],
            "tool_calls": None, "actions": None, "observations": None,
            "cost_usd": cost, "elapsed_s": 0, "error": None, "log": None,
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
    when the box ran, a reply or the box's own choice, else the scripted reply, the task's
    own (`scripted_reply`), which without the box is None."""
    return box_record.get("reading") if box_record else flag


# The scripted user's replies where the box asks (`--reading`). "menu" and "buyable" answer
# every question alike, as every batch before 23 October 2026 did, and stay for those
# batches. "own" answers each question with the reading its own key was written under (the
# verifier's FAIL at cce9ab0, blocker 1: pv1-15, "How many Larchmere listings can sell me a
# size M today?", was asked by the word list, told "whether or not it is sold out" by
# --reading menu, and would have been scored against its key, which counts what can be
# bought).
SCRIPTED_READINGS = ("menu", "buyable", "own")


def scripted_reply(task: dict, flag: str | None, two_readings: list[str] | None) -> str | None:
    """The scripted user's reply to the box's question on this task: the flag itself under
    "menu" or "buyable" or none. Under "own", the reading the task's own key was written
    under: "menu" for a question in its sidecar's `two_readings`, whose key counts a size in
    the menu sold out or not, and "buyable" for every other question with a key, whose key
    counts what can be bought. A file whose sidecar names no `two_readings` wrote every key
    under the menu reading (`score.two_readings_for`). A question with no key gets no reply,
    so an ask on it closes the slot, since nothing would judge its run."""
    if flag != "own":
        return flag
    if task["expect"].get("kind") == "none":
        return None
    if two_readings is None or task["id"] in two_readings:
        return scoring.OWN_READING
    return "buyable"


def score_run(task: dict, reading: str | None, readings: dict, two_readings: list[str] | None,
              answer: str, ok: bool) -> dict:
    """`score.score_under` with the task file's `two_readings` given to `under_reading`, so a
    run told the menu reading on a question whose key counts what can be bought is unscored,
    never scored against that key (23 October 2026). Kept here, not in score.py, until the
    scorer's v7 merges, which then takes the parameter in `score_under` too."""
    try:
        keyed = scoring.under_reading(task, reading, readings, two_readings)
    except scoring.NoKeyForReading as fault:
        return {"verdict": "unscored", "why": f"no answer key for this run: {fault}",
                "prices": scoring.prices_in(answer or "")}
    return scoring.score(keyed, answer, ok)


def unscorable(tasks: list[dict], spec: dict, args, readings: dict,
                two_readings: list[str] | None = None) -> list[str]:
    """The tasks a batch could not score, each with the reading its runs would be scored
    under: the `--reading` reply where the box asks, the box's own reading where it takes
    one, the task's own key otherwise (`reading_answered`), wherever `score.under_reading`
    has no key for it. A run answered under a reading with no key would be unscored, so the
    batch is refused before anything is spent rather than paying for runs nothing judges. A
    slot the box closes, an ask with no reply or a refusal, runs nothing and is scored by
    nothing.

    Under the model parser (22 October 2026) the decision waits on each run's reply, so it
    cannot be known before anything is spent. The rules' decision is checked as above,
    which costs nothing. And on every question the model reads, any question with a page
    that the rules do not bypass, the model can flag the in-the-menu-or-buyable ambiguity,
    asked and answered by `--reading`, or lead the box to take the buyable reading itself,
    whatever the word list makes of the question; so each such question with a key needs a
    key under every reading other than its own that the run could then be answered under
    (verifier finding, 22 October 2026: a model's ask was scored under the task's own key).

    `two_readings` are the questions the sidecar names as having two (23 October 2026, the
    verifier's FAIL at cce9ab0): the menu reading is the own reading of those alone
    (`score.under_reading`), so a scripted "menu" on any other question is a reading with no
    key. Under `--reading menu` that reports each such question the rules ask on, and under
    the model parser each such question the model reads, since it can ask on any. Under
    `--reading own` each question is answered with its own reading (`scripted_reply`)."""
    missing = []
    # The rules decide with the replies `two_readings` gives, as the paid loop does.
    rules = argparse.Namespace(**{**vars(args), "parser": "rules", "two_readings": two_readings})
    model = getattr(args, "parser", "rules") == "model"
    for task in tasks:
        query, applied = build_query(task, spec, rules)
        reply = scripted_reply(task, args.reading, two_readings)
        if query is not None:
            reading = reading_answered(applied["box"], reply)
            try:
                scoring.under_reading(task, reading, readings, two_readings)
            except scoring.NoKeyForReading:
                missing.append(f"{task['id']} under the {reading} reading")
        read_by_model = model and applied["page"] is not None and not (applied["box"] or {}).get("bypassed")
        if not read_by_model:
            continue
        # The buyable reading the box can take itself, and the scripted reply to an ask.
        for reading in sorted({"buyable", reply} - {None}):
            try:
                scoring.under_reading(task, reading, readings, two_readings)
            except scoring.NoKeyForReading:
                found = f"{task['id']} under the {reading} reading"
                if found not in missing:
                    # The buyable reading the box can take itself, whatever the reply; any
                    # other, the scripted reply to an ask the model can put on any question.
                    missing.append(f"{found}, which the model parser can lead any question it "
                                   f"reads to" if reading == "buyable" else
                                   f"{found}, the scripted reply if the model parser asks, as it "
                                   f"can on any question it reads")
    return missing


def dry_text(query: str | None, applied: dict) -> None:
    """What one decision sends, as the dry run prints it: the exact text, an ask as the
    box's question, a refusal as what the box said was missing, a reading the box took on
    its own as a line before the text."""
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


def scripted_line(record: dict | None, reply: str | None) -> str:
    """Under `--reading own`, the scripted user's reply for a task and whether it was given
    (23 October 2026), as its record's `reading_by` says: given where the box asked, not
    needed where the box took a reading itself, and not given where it asked nothing."""
    by = (record or {}).get("reading_by")
    given = ("given: the box asked" if by == "user" else
             f"not needed: the box took the {record['reading']} reading itself" if by == "box" else
             "not given: the box did not ask")
    return f"scripted reply under --reading own: {reply or 'none, since no key would judge it'}, {given}"


def print_dry_task(task: dict, query: str | None, applied: dict, own: bool = False,
                   scripted: str | None = None) -> None:
    """One task of the dry run: the exact text, through the same function the paid loop
    uses, so what is read here is what the agent gets (LESSONS 17). Under `--reading own`
    (`own`) the scripted reply, `scripted`, is printed first with whether it was given;
    otherwise the lines are what they always were."""
    print(f"  {task['id']:26} gated={task['gated']}  {task['expect']['kind']}")
    if own:
        print(scripted_line(applied["box"], scripted))
    dry_text(query, applied)
    print()


def print_dry_parsers(task: dict, spec: dict, args, replies: dict[str, str]) -> dict | None:
    """One task of a dry run under `--parser model` (22 October 2026): what the rules give,
    then what the model parser gives with the reply `replies` holds for the task, or a line
    saying there is none, since a dry run sends nothing. Each with the form it used and,
    for the model, every change normalisation made and why the rules' form was used, when
    it was. Returns the record the batch's counts take: the model's decision where a reply
    was given, the rules' otherwise, which is also what the box sends when the model's form
    fails."""
    print(f"  {task['id']:26} gated={task['gated']}  {task['expect']['kind']}")
    query, applied = build_query(task, spec, argparse.Namespace(**{**vars(args), "parser": "rules"}))
    # The form the decision used, or, where the box asked first and used none, the rules'
    # form of the question as asked.
    form = (applied["box"] or {}).get("form") or form_module.from_rules(
        task["query"].format(base=spec["base_url"]), applied["page"]).record()
    print(f"parser rules: {parse_probe.summary(form)}")
    own = args.reading == "own"
    scripted = scripted_reply(task, args.reading, getattr(args, "two_readings", None))
    if own:
        print(scripted_line(applied["box"], scripted))
    dry_text(query, applied)
    reply = replies.get(task["id"])
    version = f"prompt v{form_module.PROMPT_VERSION}, normalisation v{normalise_module.VERSION}"
    if reply is None:
        print(f"parser model ({version}): no reply, since a dry run sends nothing. Give one with "
              f"--parser-replies to see the plan it gives; if the model's form fails, the box "
              f"sends the rules' text above")
        print()
        return applied["box"]
    query, applied = build_query(task, spec, args, call=lambda prompt: reply)
    parse = applied["box"]["parse"]
    if parse["used"] == "rules":
        print(f"parser model ({version}), reply from {args.parser_replies.name}: the rules' form "
              f"is used: {parse['fallback_reason']}")
    else:
        print(f"parser model ({version}), reply from {args.parser_replies.name}: "
              f"{parse_probe.summary(parse['model_form'])}")
    for change in parse["changes"]:
        print(f"  normalised: {change}")
    if parse.get("declined"):
        print("  declined on the model's form: what it needs is not shown, by the rules' check "
              "of the page's attributes")
    if own:
        print(scripted_line(applied["box"], scripted))
    dry_text(query, applied)
    print()
    return applied["box"]


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
                 decision: box_module.Decision | None = None,
                 max_steps: int | None = None, clock_s: int | None = None) -> tuple:
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
                      scaffold=scaffold, shop=shop, probe=probe, max_steps=max_steps, clock_s=clock_s)
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
    parser.add_argument("--exhaustive-wording", choices=("every", "product"), default=None,
                        help="with --exhaustive: every, the default, tells the agent to open "
                             "every listing in the results, as every batch before 22 October "
                             "2026 did; product names the task's product (its task file's "
                             "`product`), for a search that holds another product too. An arm "
                             "of its own, exhaustive-product")
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
    parser.add_argument("--reading", choices=SCRIPTED_READINGS,
                        help="the scripted user's reply when the box asks. menu: a size in "
                             "the listing's menu counts, sold out or not. buyable: only a size "
                             "that can be sold now, the key in tasks/readings_<market>.json. "
                             "own: each question's own reading, menu for a question the "
                             "sidecar names under two_readings and buyable for any other with "
                             "a key (23 October 2026). Without it a box that asks records the "
                             "ask, runs no agent and spends nothing")
    parser.add_argument("--parser", choices=box_module.PARSERS, default="rules",
                        help="who reads the question for the box. rules, the default, as every "
                             "box batch before 22 October 2026. model: one call per run reads "
                             "it, and its form is normalised and held to the box's checks, "
                             "with the rules' form used instead, and the reason recorded, when "
                             "the call fails or the form fails a check. Needs --box or "
                             "--box-exhaust, and is an arm of its own")
    parser.add_argument("--parser-model", default=None,
                        help="the model --parser model calls, by default the agent's own "
                             "(MODEL_NAME, as the agent reads it)")
    parser.add_argument("--parser-replies", type=pathlib.Path, default=None,
                        help='with --parser model and --dry-run only: a JSON file {"replies": '
                             '{task id: reply text}} of recorded or stubbed model replies, so '
                             "the dry run shows the plan each gives while sending nothing")
    parser.add_argument("--page-reader", choices=page_module.READERS, default=None,
                        help="how the box reads the results pages, every one of them since "
                             "box v16. rendered, the default: in a headless browser with the "
                             "agent's user agent, run in the Playwright venv. fetch: each "
                             "page's HTML over HTTP, the box's reader until box v16, when it "
                             "read the first page alone. Needs --box or --box-exhaust")
    parser.add_argument("--rate-plan", choices=box_module.RATE_PLANS, default=None,
                        help="how the box plans a rate question, such as the best price per "
                             "litre: bound, the default, skips a listing whose advertised price "
                             "over the largest pack cannot win, as every box batch before 23 "
                             "October 2026; every opens every listing, with no bound, since the "
                             "largest pack is a figure the results pages do not show. Needs --box or "
                             "--box-exhaust")
    parser.add_argument("--max-steps", type=int, default=None, metavar="N",
                        help=f"openJiuwen's step limit, passed as BROWSER_GUARDRAIL_MAX_STEPS; "
                             f"{DEFAULT_MAX_STEPS} by default, its own, as every batch before 22 "
                             f"October 2026 ran under")
    parser.add_argument("--clock", type=int, default=None, metavar="S",
                        help=f"openJiuwen's wall clock limit for one run, in seconds, passed as "
                             f"the runner's --timeout; {DEFAULT_CLOCK_S} by default, as before")
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
    if args.exhaustive_wording and not args.exhaustive:
        parser.error("--exhaustive-wording words the open-everything instruction, so it needs "
                     "--exhaustive")
    args.exhaustive_wording = (args.exhaustive_wording or "every") if args.exhaustive else None
    # The limits are openJiuwen's (22 October 2026). The naive loop has its own step limit
    # and no clock, so either flag there would record a limit nobody applied.
    for flag, value in (("--max-steps", args.max_steps), ("--clock", args.clock)):
        if value is not None and value < 1:
            parser.error(f"{flag} is a limit, so it is 1 or more")
        if value is not None and args.scaffold == "naive":
            parser.error(f"{flag} is openJiuwen's limit; the naive loop has a step limit of its "
                         f"own ({NAIVE_STEP_LIMIT}) and no clock")
    bounds = limits(args.scaffold, args.max_steps, args.clock)
    args.max_steps, args.clock = bounds["max_steps"], bounds["clock_s"]
    # The reader is the box's (box v16), so with no box it would name a reading nobody made.
    if args.page_reader and not boxed:
        parser.error("--page-reader is how the box reads the results pages, so it needs --box "
                     "or --box-exhaust")
    args.page_reader = (args.page_reader or page_module.READERS[0]) if boxed else None
    # The rate plan is the box's (box v18), so with no box it would name a plan nobody made.
    if args.rate_plan and not boxed:
        parser.error("--rate-plan is how the box plans a rate question, so it needs --box or "
                     "--box-exhaust")
    args.rate_plan = (args.rate_plan or "bound") if boxed else None
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
    # The parser is the box's (22 October 2026). A stubbed reply is for a dry run alone: a
    # paid run reading one would measure a parse nobody made.
    model_parser = args.parser == "model"
    if model_parser and not boxed:
        parser.error("--parser model reads the question for the box, so it needs --box or "
                     "--box-exhaust")
    if args.parser_model and not model_parser:
        parser.error("--parser-model names the model of --parser model, so it needs it")
    if args.parser_replies and not (model_parser and args.dry_run):
        parser.error("--parser-replies stands in for the model's replies in a dry run, so it "
                     "needs --parser model and --dry-run")
    parser_model = (args.parser_model or agent_model()) if model_parser else None

    # Task files moved into experiments/tasks/ on 8 Oct 2026. Commands in the decision log
    # still name the old place, so a missing path falls back to the same file name there.
    if not args.tasks.exists() and (paths.TASKS / args.tasks.name).exists():
        print(f"note: {args.tasks} has moved, reading {paths.TASKS / args.tasks.name}")
        args.tasks = paths.TASKS / args.tasks.name
    spec = json.loads(args.tasks.read_text())
    # An id that names no task is an error, by name. Until 14 Oct 2026 it was dropped
    # without a word, so a misspelt --only ran the rest as if nothing were missing
    # (verifier finding at 39f15e9).
    known = {t["id"] for t in spec["tasks"]}
    unknown = [task_id for task_id in args.only or [] if task_id not in known]
    if unknown:
        parser.error(f"--only names a task that is not in {args.tasks.name}: {', '.join(unknown)}")
    tasks = [t for t in spec["tasks"] if not args.only or t["id"] in args.only]
    if not tasks:
        print("no matching tasks")
        return 1
    # The product wording names each task's product, so a task file must say it (22 October
    # 2026): refused by name rather than worded without one.
    unnamed = [t["id"] for t in tasks if args.exhaustive_wording == "product" and not t.get("product")]
    if unnamed:
        parser.error(f"--exhaustive-wording product names each task's product, and "
                     f"{args.tasks.name} names none for {', '.join(unnamed)}")
    # The scripted user's other readings of the ambiguous questions, for scoring under
    # `--reading`. Empty when the task file has no sidecar.
    readings = scoring.readings_for(args.tasks)
    # The questions its sidecar says have two readings, None where it names none (23 October
    # 2026): the scripted reply under "own" and the reading each key was written under.
    args.two_readings = scoring.two_readings_for(args.tasks)
    # Every key a run will be scored against, found before the first run and in the dry
    # run, so a missing one stops the batch before anything is spent (20 October 2026).
    missing = unscorable(tasks, spec, args, readings, args.two_readings)
    if missing:
        parser.error(f"{args.tasks.name} has no answer key for the reading these runs would "
                     f"be scored under, so nothing runs: {'; '.join(missing)}")

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
    # The agent's limits, every batch's conditions since 22 October 2026.
    print(f"limits: max steps {args.max_steps}, clock "
          + (f"{args.clock} s" if args.clock is not None else "none"))
    # The arm, so a dry run of the box and of the box without its stop rule say which.
    print(f"arm: {arm_of(args)}")
    # How the box reads the results pages (box v16), a condition of every box batch.
    if boxed:
        print(f"page reader: {args.page_reader}, every results page")
    # The rate plan when it is not the default (box v18), so a default header is unchanged.
    if boxed and args.rate_plan != "bound":
        print(f"rate plan: {args.rate_plan}, a rate question opens every listing, with no bound")
    # Under the model parser, who reads the question and with what. Not printed under the
    # rules, so a rules batch's header is what it always was.
    if model_parser:
        print(f"parser: model {parser_model}, temperature {PARSER_TEMPERATURE}, prompt "
              f"v{form_module.PROMPT_VERSION}, normalisation v{normalise_module.VERSION}")

    if args.dry_run:
        # The exact text, through the same function the paid loop uses, so what is read
        # here is what the agent gets (LESSONS 17). An ask is printed as the box's question,
        # a refusal as what the box said was missing. Under the box, the counts the batch
        # would record and how many of its slots would reach the agent come last. Under the
        # model parser each task shows what both parsers give, the model's from a replies
        # file when one is given, since a dry run sends nothing.
        replies = stubbed_replies(args.parser_replies) if args.parser_replies else {}
        records = []
        for task in tasks:
            if model_parser:
                records.append(print_dry_parsers(task, spec, args, replies))
                continue
            query, applied = build_query(task, spec, args)
            records.append(applied["box"])
            print_dry_task(task, query, applied, own=args.reading == "own",
                           scripted=scripted_reply(task, args.reading, args.two_readings))
        summary = dry_summary(records, args.repeats)
        if summary:
            if model_parser:
                given = len(set(replies) & {task["id"] for task in tasks})
                print(f"the counts take the model parser's decision on the {given} tasks a reply "
                      f"was given for, and the rules' on the rest")
            print(summary)
        return 0

    key = None
    if model_parser:
        key = plan_probe.load_key()
        if not key:
            print("no OPENROUTER_API_KEY for the model parser")
            return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, done = [], 0
    for task in tasks:
        for repeat in repeats:
            done += 1
            tag = f"{task['id']}-{repeat}"
            # Under the model parser each run's question is read by its own call, and what
            # it was charged is part of the run's cost (22 October 2026).
            charges: list = []
            counts: list = []
            call = parser_call(parser_model, key, charges, counts) if model_parser else None
            query, applied = build_query(task, spec, args, call=call)
            parsed = parse_cost(charges)
            parsed_tokens = parse_tokens(counts)
            strategy = applied["strategy"]
            if query is None:
                # The box asked and no scripted reply was given, or it refused. Either is
                # the outcome: no agent runs, and nothing is spent but the parse.
                row = asked_row(task, repeat, applied["box"], cost=parsed if model_parser else 0)
                if model_parser:
                    row["parse_cost_usd"] = parsed
                    row["parse_tokens"] = parsed_tokens
                rows.append(row)
                declined = ((applied["box"] or {}).get("parse") or {}).get("declined")
                print(f"[{done}/{total}] {tag:32} {row['verdict']:10} the box {row['verdict']}"
                      + (" on the model's form" if declined else ""))
                continue
            record = run_once(task, spec["base_url"], out_dir, tag, query=query,
                              scaffold=args.scaffold, shop=args.shop, probe=args.probe,
                              max_steps=args.max_steps, clock_s=args.clock)
            if model_parser:
                record = charge_parse(record, parsed, out_dir / f"{tag}.json", parsed_tokens)
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
                    page=applied["page"], decision=applied["decision"],
                    max_steps=args.max_steps, clock_s=args.clock)

            # Scored against the key for the reading the run answered under, the user's
            # reply or the box's own choice, the sidecar's when that reading is not the
            # task's own, and unscored, never the task's own key, when the sidecar has
            # none (score.py v4; `unscorable` refuses such a batch before it runs).
            answered = reading_answered(applied["box"], scripted_reply(task, args.reading, args.two_readings))
            verdict = score_run(task, answered, readings, args.two_readings, answer, bool(result.get("ok")))
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
            if model_parser:
                row["parse_cost_usd"] = parsed
                row["parse_tokens"] = parsed_tokens
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
            if model_parser:
                conf += f" [parsed by the {applied['box']['parse']['used']}, ${parsed}]"
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
               # Which open-everything instruction (22 October 2026): "every" listing, as every
               # batch before, or every listing of the task's "product"; None without it.
               "exhaustive_wording": args.exhaustive_wording,
               # The product wording's own version (23 October 2026); None under any other.
               "exhaustive_wording_version": (policy_module.EXHAUSTIVE_PRODUCT_VERSION
                                              if args.exhaustive_wording == "product" else None),
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
               # Who read the question for the box, and with what (22 October 2026). The
               # parser is part of the arm too (`arm_of`), so two parsers are never pooled
               # (LESSONS 7). The parse's charges are in every row's cost, and summed here.
               "parser": args.parser if boxed else None,
               "parser_model": parser_model,
               "parser_temperature": PARSER_TEMPERATURE if model_parser else None,
               "prompt_version": form_module.PROMPT_VERSION if model_parser else None,
               "normalise_version": normalise_module.VERSION if model_parser else None,
               "parse_charged_usd": (round(sum(row.get("parse_cost_usd") or 0 for row in rows), 6)
                                     if model_parser else None),
               "parse_charges_unknown": (sum(1 for row in rows if row.get("parse_cost_usd") is None)
                                         if model_parser else None),
               # The parse's tokens over the runs whose count is known, and how many are not
               # (23 October 2026); each run's own are in its row and its record.
               "parse_tokens": ({part: sum((row.get("parse_tokens") or {}).get(part, 0) for row in rows)
                                 for part in ("prompt", "completion", "total", "calls")}
                                if model_parser else None),
               "parse_tokens_unknown": (sum(1 for row in rows if row.get("parse_tokens") is None)
                                        if model_parser else None),
               "reading": args.reading,
               # Which reader read the results pages, every one of them (box v16, 22 October
               # 2026); None without the box. A box batch without the field read the first
               # page alone over HTTP.
               "page_reader": args.page_reader,
               # How the box planned a rate question (box v18): "bound" or "every"; None
               # without the box. A box batch without the field planned it with the bound.
               "rate_plan": args.rate_plan,
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
               # The step and clock limits every run ran under (22 October 2026), in every
               # run record too. A batch without them ran under openJiuwen's defaults, 100
               # steps and 600 s, or the naive loop's 100 steps and no clock.
               "max_steps": args.max_steps,
               "clock_s": args.clock,
               # Which openJiuwen code answered: the submodule's commit and the sha1 of
               # its uncommitted patch, see `agent_code_identity`. None for the naive loop.
               "agent_core_commit": agent_code["agent_core_commit"],
               "agent_core_patch": agent_code["agent_core_patch"],
               # Under experiments/tasks/, where every reader looks (`tasks_file_name`).
               "tasks_file": tasks_file_name(args.tasks),
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
    # The total is the known part. A run whose cost is unknown, a charge the provider did
    # not state, is counted beside it rather than dropped without a word (22 October 2026).
    return {"by_task": by_task, "overall": dict(overall),
            "total_cost": round(sum(r["cost_usd"] for r in rows if r["cost_usd"]), 4),
            "cost_unknown_runs": sum(1 for r in rows if r["cost_usd"] is None),
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
    unknown = summary.get("cost_unknown_runs")
    if unknown:
        print("total cost: $", summary["total_cost"],
              f"known; {unknown} runs whose cost is unknown are not in it")
    else:
        print("total cost: $", summary["total_cost"])

    gated = [r for r in rows if r["gated"] and r["actions"] is not None]
    correct = [r["actions"] for r in gated if r["verdict"] == "correct"]
    wrong = [r["actions"] for r in gated if r["verdict"] == "wrong"]
    if correct and wrong:
        print(f"\ngated tasks, mean actions: correct {mean(correct)}, wrong {mean(wrong)}")


if __name__ == "__main__":
    raise SystemExit(main())
