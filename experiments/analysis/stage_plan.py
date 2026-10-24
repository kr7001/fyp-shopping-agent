#!/usr/bin/env python3
"""The second claim run's stage plan and its cost table (24 October 2026, the tee-only design).

Shared by the stage command generator (tools/claim2_stage_command.py), which emits the two
paid commands of the morning from it, and the pilot check (pilot_check.py), which prices
stage 1 from the pilot's records against the same plan. One module, so the command that runs
and the check that judges it cannot disagree about which arm asks which question in which
round.

**The plan** comes from the analysis file, experiments/tasks/claim2_analysis.json, and the
market's task file, never from a task's own flags: `design[model].asks` names, for each arm,
the question sets it asks and the rounds it asks them in; `sets` holds each set's ids, and two
names are the task file's: "templates", every task without a `template` field (the market's
questions), and "held_out", every task with one (the held-out rewordings, v2 and v3 alike).
Open everything asks the file's `gated` set, which the verifier fixed on 24 October without
tee-promo-check, although that task's `gated` flag is true: a task flag is never read here.
The arms run in the file's order, rotated by one each round, as the protocol says.

**Invocations are small** (LESSONS 41: a 27-slot invocation cost $4.74 against a $2.80 high):
one question each for shipped and open everything; for a block arm, at most `chunk` questions
of one set in one round.

**The pilot's plan** (handover section 6, command 1) is fixed here by the suite's own arm
names: twelve runs on the development market, one question each.

**The cost table prices stage 1 before the pilot runs**, from the one measured batch on a
two-page market, the 23 October pilot on Larchmere (`PILOT_23_OCT`, the block with the model,
every template once), divided by what OpenRouter's routing cost that day over list price
(`PILOT_PRICE_FACTOR`), and scaled for a market of more listings where a question's work grows
with them (`scale_for`). The rules, each a line of `estimate`:

  - a block arm's question costs what its template cost in that batch; a template the batch
    did not run costs what its stand-in did (`STAND_IN`: tee-xs-price is tee-target-price
    with another size, tee-promo-check is a single-listing lookup priced as the results-page
    read tee-headline, the new declines are a parse alone, as decline-delivery was);
  - a bound or a count question grows with the listings (`GROWS`), the others do not: a
    headline or a lookup reads one page or one listing, a decline runs no agent;
  - open everything costs 1.3 times the dearer of the question's block cost and the count
    question's, and always grows with the listings (unmeasured on two pages, as the A+ draft
    priced it);
  - shipped costs the verifier's $0.33 at the pilot's prices, whatever the question, and does
    not grow: it stops early by nature;
  - a held-out rewording costs what its template does.

The scaling is linear in the listings. The context an agent re-sends grows with every
listing it opens, so the true growth may be steeper; the pilot of the morning measures the
new shape (its check re-prices stage 1 from it), which is why it runs first.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402

VERSION = 1

# Each template's kind, the per-kind rules of the pilot check and the cost table (24 October
# 2026). A decline the table does not name is a decline by its prefix; any other unknown
# template is refused, since no measured cost stands for it.
KINDS = {
    "tee-headline": "headline",
    "tee-target-price": "bound", "tee-cheapest-target": "bound", "tee-xs-price": "bound",
    "tee-exists-under": "bound", "tee-top-3": "bound",
    "tee-all-stocked": "count", "tee-count-stocked": "count", "tee-count-buyable": "count",
    "tee-promo-check": "lookup",
    "decline-delivery": "decline", "decline-fit": "decline", "decline-scarcity": "decline",
}
GROWS = {"bound", "count"}               # the kinds whose work grows with the listings
TEMPLATES, HELD_OUT = "templates", "held_out"   # the two set names the task file resolves
# The suite's arm names (`suite.arm_of`) of the block arms, which get chunked invocations.
BLOCK_ARMS = ("box", "box-model")

# The 23 October pilot's block batch on Larchmere, DeepSeek with the model parser, every
# template once (experiments/results/pilot-20261023.manifest), and what its charges were over
# list price: 2.16, the verifier's figure from the logs (README.md, 23 October; the handover
# rounds it to 2.17). Dividing by the smaller figure estimates a little high, never low.
PILOT_23_OCT = "20261023T112840"
PILOT_PRICE_FACTOR = 2.16
# The 23 October probes on the 30 development rewordings, one call each, which price a parse
# probe's call: the DeepSeek one the routing gate and DeepSeek's reading tests, the Haiku one
# Haiku's reading tests. Both are committed result files.
DEEPSEEK_PROBE = "parse-probe-paraphrases_v1-20261023T112717.json"
HAIKU_PROBE = "parse-probe-paraphrases_v1-20261023T112838.json"
GATE_PROBE_CALLS = 30                    # the routing gate parses the 30 v1 rewordings
LARCHMERE = "aplus_dev.json"             # the measured market's fixture: 21 tee listings
STAND_IN = {"tee-xs-price": "tee-target-price", "tee-promo-check": "tee-headline",
            "decline-fit": "decline-delivery", "decline-scarcity": "decline-delivery"}
OPEN_EVERYTHING_FACTOR = 1.3
COUNT_QUESTION = "tee-count-buyable"
SHIPPED_PILOT_PRICE = 0.33               # the verifier's figure at the pilot's prices
HIGH = 2.0                               # an invocation's high is twice its estimate

# The pilot of the morning (handover section 6, command 1), by the suite's arm names, in the
# order the chain runs them; `pilot_invocations` puts them in the analysis file's arm order.
PILOT_PLAN = {
    "box-model": ["tee-xs-price", "tee-promo-check", "tee-count-buyable", "tee-cheapest-target",
                  "tee-count-stocked", "decline-fit"],
    "box": ["tee-xs-price", "tee-promo-check"],
    "exhaustive-product": ["tee-count-buyable", "tee-xs-price"],
    "none": ["tee-xs-price", "tee-promo-check"],
}


@dataclasses.dataclass(frozen=True)
class Invocation:
    round: int
    arm: str                      # the protocol's arm name, a key of the analysis file's arms
    questions: tuple[str, ...]    # task ids, the suite's --only


def kind_of(template: str) -> str:
    """A template's kind (`KINDS`); a decline by its prefix; anything else refused."""
    if template in KINDS:
        return KINDS[template]
    if template.startswith("decline-"):
        return "decline"
    raise ValueError(f"no kind is fixed for the template {template!r}, so nothing prices it")


def load(path: pathlib.Path) -> dict:
    return json.loads(pathlib.Path(path).read_text())


def templates_of(spec: dict) -> list[str]:
    """The market's own questions: every task without a `template` field, in file order."""
    return [task["id"] for task in spec["tasks"] if not task.get("template")]


def held_out_of(spec: dict) -> dict[str, str]:
    """Each held-out task, by id, with the template it rewords, in file order."""
    return {task["id"]: task["template"] for task in spec["tasks"] if task.get("template")}


def template_of(spec: dict, task_id: str) -> str:
    """The template a task is priced by: its own id, or for a held-out task the one it rewords."""
    return held_out_of(spec).get(task_id, task_id)


def keyless_of(spec: dict) -> set[str]:
    """The tasks no key can judge, by the scorer's own rule: no `expect`, or one of kind none."""
    return {task["id"] for task in spec["tasks"]
            if not task.get("expect") or task["expect"].get("kind") == "none"}


def resolve_set(name: str, analysis: dict, spec: dict) -> list[str]:
    """A set's task ids: the task file's for "templates" and "held_out", the analysis file's
    `sets` for any other name. A set that names a task the file lacks is refused."""
    if name == TEMPLATES:
        ids = templates_of(spec)
    elif name == HELD_OUT:
        ids = list(held_out_of(spec))
    else:
        if name not in (analysis.get("sets") or {}):
            raise ValueError(f"the analysis file has no set {name!r}")
        ids = list(analysis["sets"][name])
    known = {task["id"] for task in spec["tasks"]}
    missing = [i for i in ids if i not in known]
    if missing:
        raise ValueError(f"the set {name!r} names tasks the task file lacks: {', '.join(missing)}")
    return ids


def arms_by_suite_name(analysis: dict) -> dict[str, str]:
    """The protocol's arm name for each suite arm name ("box-model" and so on)."""
    return {arm["arm"]: name for name, arm in analysis["arms"].items()}


def suite_arm(analysis: dict, name: str) -> str:
    return analysis["arms"][name]["arm"]


def design_of(analysis: dict, model: str) -> dict:
    """What the model's design asks of each arm: {arm: {set name: [rounds]}}."""
    design = (analysis.get("design") or {}).get(model)
    if design is None:
        raise ValueError(f"the analysis file has no design for {model}")
    return design["asks"]


def chunked(ids: list[str], size: int) -> list[tuple[str, ...]]:
    return [tuple(ids[i:i + size]) for i in range(0, len(ids), size)]


def stage1_invocations(analysis: dict, spec: dict, model: str, chunk: int = 8) -> list[Invocation]:
    """Stage 1's invocations in the order the chain runs them: every round the model's design
    names, the arms in the analysis file's order rotated by one each round, and within an arm
    each set it asks in that round, in the design's order; one question per invocation for
    shipped and open everything, up to `chunk` for a block arm."""
    asks = design_of(analysis, model)
    arms = [name for name in analysis["arms"] if name in asks]
    rounds = sorted({r for sets in asks.values() for rs in sets.values() for r in rs})
    out = []
    for r in rounds:
        shift = (r - 1) % len(arms)
        for arm in arms[shift:] + arms[:shift]:
            for name, in_rounds in asks[arm].items():
                if r not in in_rounds:
                    continue
                ids = resolve_set(name, analysis, spec)
                size = chunk if suite_arm(analysis, arm) in BLOCK_ARMS else 1
                out += [Invocation(r, arm, qs) for qs in chunked(ids, size)]
    return out


def pilot_invocations(analysis: dict, spec: dict) -> list[Invocation]:
    """The pilot's twelve runs (`PILOT_PLAN`), round 1, one question each, the arms in the
    analysis file's order. A question the task file lacks is refused, by name."""
    by_suite = arms_by_suite_name(analysis)
    missing = [a for a in PILOT_PLAN if a not in by_suite]
    if missing:
        raise ValueError(f"the analysis file has no arm recorded as {', '.join(missing)}")
    known = {task["id"] for task in spec["tasks"]}
    out = []
    for name in analysis["arms"]:
        for question in PILOT_PLAN.get(suite_arm(analysis, name), []):
            if question not in known:
                raise ValueError(f"the pilot asks {question}, which the task file lacks")
            out.append(Invocation(1, name, (question,)))
    return out


# ---------------------------------------------------------------------------
# The cost table


def measured_block_costs(results: pathlib.Path | None = None) -> dict[str, float]:
    """Each template's cost in the 23 October pilot's block batch, at that day's prices, the
    parse's charge included (its rows' cost_usd), read from the stored suite.json."""
    payload = load((results or paths.RESULTS) / PILOT_23_OCT / "suite.json")
    found: dict[str, float] = {}
    for row in payload["rows"]:
        if row.get("cost_usd") is not None and row["task"] not in found:
            found[row["task"]] = float(row["cost_usd"])
    return found


def listings_of(fixture_path: pathlib.Path) -> int:
    """How many tee listings a fixture seeds: its families of product tee, or all of them for
    a fixture whose families name no product."""
    families = load(fixture_path)["families"]
    tees = [f for f in families if f.get("product", "tee") == "tee"]
    return len(tees)


def scale_for(fixture_path: pathlib.Path, fixtures: pathlib.Path | None = None, growth: float = 1.0) -> float:
    """How many times a growing question's cost is scaled for this market: its tee listings
    over the measured market's, Larchmere's, to the power `growth`. 1, linear, is the table's
    rule; 2 is the steeper case where the context an agent re-sends grows with every listing
    it opens, offered beside it so the stage total can be read both ways."""
    return (listings_of(fixture_path) / listings_of((fixtures or paths.FIXTURES) / LARCHMERE)) ** growth


@dataclasses.dataclass(frozen=True)
class Costs:
    """The 23 October costs at list price (`measured` is at the pilot's prices) and the
    listings scale of the market being priced."""
    measured: dict[str, float]
    scale: float

    def block(self, template: str) -> float:
        """A block arm's cost for a template at list price, scaled where its kind grows."""
        stood = STAND_IN.get(template, template)
        if stood not in self.measured:
            raise ValueError(f"the 23 October pilot measured no cost for {template} or a stand-in")
        base = self.measured[stood] / PILOT_PRICE_FACTOR
        return base * self.scale if kind_of(template) in GROWS else base

    def estimate(self, arm: str, template: str) -> float:
        """One run's estimate at list price for a suite arm name and a template."""
        if arm in BLOCK_ARMS:
            return self.block(template)
        if arm == "exhaustive-product":
            dearer = max(self.measured[STAND_IN.get(template, template)], self.measured[COUNT_QUESTION])
            return OPEN_EVERYTHING_FACTOR * dearer / PILOT_PRICE_FACTOR * self.scale
        if arm == "none":
            return SHIPPED_PILOT_PRICE / PILOT_PRICE_FACTOR
        raise ValueError(f"no estimate rule for the arm {arm!r}")


def costs_for(fixture_path: pathlib.Path, results: pathlib.Path | None = None,
              fixtures: pathlib.Path | None = None, growth: float = 1.0) -> Costs:
    return Costs(measured_block_costs(results), scale_for(fixture_path, fixtures, growth))


def invocation_estimate(invocation: Invocation, analysis: dict, spec: dict, costs: Costs) -> float:
    """An invocation's estimate: the sum over its questions, each by its template."""
    arm = suite_arm(analysis, invocation.arm)
    return sum(costs.estimate(arm, template_of(spec, q)) for q in invocation.questions)


def probe_charge_per_call(path: pathlib.Path) -> float | None:
    """What a stored parse probe charged per call, from its result file; None when the file
    cannot be read or holds no charged rows."""
    try:
        probe = json.loads(pathlib.Path(path).read_text())
        rows = probe.get("rows") or []
        return float(probe["charged_usd"]) / len(rows) if rows else None
    except (OSError, KeyError, TypeError, ValueError):
        return None


def reading_entries(files: list[pathlib.Path], templates: list[str]) -> int:
    """How many entries the reading tests parse from these paraphrase files: those whose
    template the market holds (`parse_probe --only-templates`), or that have none at all, the
    reading-test-only entries. Read by id and template, never a text."""
    count = 0
    for path in files:
        for entry in load(path)["paraphrases"]:
            if entry.get("template") is None or entry["template"] in templates:
                count += 1
    return count


def probe_estimates(model_calls: int, haiku_calls: int, results: pathlib.Path | None = None) -> dict[str, float]:
    """The text-only extras at the 23 October probes' charge per call: the routing gate's 30
    DeepSeek calls, and the reading tests' calls for DeepSeek and for Haiku."""
    results = results or paths.RESULTS
    deepseek = probe_charge_per_call(results / DEEPSEEK_PROBE) or 0.0
    haiku = probe_charge_per_call(results / HAIKU_PROBE) or 0.0
    return {"routing gate": GATE_PROBE_CALLS * deepseek,
            "reading tests, DeepSeek": model_calls * deepseek,
            "reading tests, Haiku": haiku_calls * haiku}


def main() -> int:
    """Print stage 1's plan and estimates for an analysis file, a task file and a fixture."""
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--analysis", type=pathlib.Path, default=paths.TASKS / "claim2_analysis.json")
    parser.add_argument("--tasks", type=pathlib.Path, required=True)
    parser.add_argument("--fixture", type=pathlib.Path, required=True)
    parser.add_argument("--model", default="deepseek/deepseek-v4-flash")
    parser.add_argument("--chunk", type=int, default=8)
    args = parser.parse_args()
    analysis, spec = load(args.analysis), load(args.tasks)
    costs = costs_for(args.fixture)
    total = 0.0
    print(f"listings scale {costs.scale:.3f} against Larchmere; prices at list, the pilot's over {PILOT_PRICE_FACTOR}")
    for inv in stage1_invocations(analysis, spec, args.model, args.chunk):
        est = invocation_estimate(inv, analysis, spec, costs)
        total += est
        print(f"round {inv.round}  {inv.arm:28} ${est:6.3f}  {' '.join(inv.questions)}")
    print(f"stage 1 estimate ${total:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
