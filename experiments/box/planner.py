#!/usr/bin/env python3
"""Turn a question into a retrieval plan, and check that the plan is sound.

`targeting.py` chooses one of four strategies from the question and appends its text. That
works for four questions and stops working past them: a strategy is a paragraph, the
paragraphs cannot be composed, and nothing checks that the instruction the agent receives
matches the rule that will later judge its answer. Both halves of the policy were written
by hand and kept in step by hand, which is the kind of agreement that quietly stops being
true.

This module makes the plan the object. A plan says what population the question ranges
over, what bound may be used to skip part of it, when the agent may stop, and what the
answer must be able to show. The instruction text is rendered from the plan, and the
sufficiency contract is read from the same plan, so the two cannot drift apart.

Three things follow from that, in order of how soon they matter.

**Nothing changes today.** `render` returns the frozen strategy text from `targeting.py`
verbatim, so a run planned here receives the same bytes it would have received before.
`--regression` asserts exactly that over every question in every task file. The twelve
Rivenhall and twelve Calderwood policy runs stay valid.

**A plan can be checked before it is used.** `verify` tests a plan against four properties
that have each already been paid for: enumerate before bounding, quarantine a bound from
the answer, refute with one counterexample rather than a survey, and do not name the best
of a market you have not covered. A plan that fails is not sent to the agent.

**A plan need not be written by hand.** When the strategy list outgrows four entries the
plan can come from the model, and `verify` is what makes that safe: a proposed plan is
executed only if it passes, and the frozen strategy is the fallback if it does not. That is
the next step and it is not taken here.

    python experiments/box/planner.py --regression
    python experiments/box/planner.py --show "Across all the listings, which seller is cheapest"
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import targeting

# Bumped when a plan's meaning changes, not when its wording does. Runs made under
# different versions are different policies and are not pooled, the same discipline the
# draw id applies to catalogues and `targeting.VERSION` applies to strategy text.
#
# v2, 8 October 2026: a question answerable from the results page has its own kind, so its
# plan says the evidence is on the results page and asks for no coverage of listing pages.
VERSION = 2

# What a quantifier costs to settle. This is the table the whole policy rests on, and it is
# a statement about logic rather than about this catalogue.
#
#   argmin       naming the best of a population needs every member of that population
#                either opened or ruled out by a bound
#   universal    proving one takes all of them, refuting one takes a single counterexample
#   existential  one witness settles it, absence of a witness settles nothing
#   enumerate    the question asks for the set itself, so there is nothing to skip
QUANTIFIERS = {
    "total_bound": "argmin",
    "rate_bound": "argmin",
    "availability_bound": "argmin",
    "refutation": "universal",
    "depth_search": "existential",
    "survey": "enumerate",
    "results_page": "argmin",
    # Box v2's kinds, 14 October 2026, whose text lives in `primitives.py` rather than in
    # `targeting.py`. They share these tables so one source states what each plan rests on.
    # `plan` never produces them, since `targeting.classify` cannot, so no v1 plan changed.
    "exists_price": "existential",
    "topk_price": "argmin",
    "named_lookup": "enumerate",
    "argmax_price": "argmin",
}

# Which bound may be used to skip a member of the population, and why it is valid. Since 20
# October 2026 each reason says the card is the cheapest option that can be bought, in the
# words strategy text v8 and v9 send the agent: a sold-out size can cost less than the card
# (igr-app-07, $15.04 against $18.33). Not sent to the agent, and the bounds themselves are
# unchanged, so the planner's version is not.
BOUNDS = {
    "total_bound": {
        "field": "advertised price",
        "valid_because": "the advertised price is the cheapest option in that listing that can "
                         "be bought, so nothing in it that can be bought costs less",
    },
    "rate_bound": {
        "field": "advertised price divided by the largest pack volume",
        "valid_because": f"no listing can beat its advertised price spread over "
                         f"{targeting.LARGEST_PACK_LITRES} litres",
    },
    "availability_bound": {
        "field": "advertised price",
        "valid_because": "the advertised price is the cheapest option in that listing that can "
                         "be bought, so nothing in it that can be bought costs less",
    },
    "refutation": None,
    # Reviews are reached by turning pages, and nothing on a page bounds what is on the
    # next one. A rating average is published and bounds nothing a shopper asks about.
    "depth_search": None,
    "survey": None,
    "results_page": None,
    "exists_price": {
        "field": "advertised price",
        "valid_because": "the advertised price is the cheapest option that listing can "
                         "sell, so a listing advertised above the limit cannot meet it",
    },
    "topk_price": {
        "field": "advertised price",
        "valid_because": "the advertised price is the cheapest option in that listing that can "
                         "be bought, so nothing in it that can be bought costs less",
    },
    "named_lookup": None,
    # The advertised price is a lower bound, and nothing a lower bound says rules a
    # listing out of being the dearest.
    "argmax_price": None,
}

# What the answer has to be able to show, in the same vocabulary the sufficiency rules use.
# Each entry names the rule that enforces it, so a plan and the check that judges it cannot
# be changed independently without the mismatch being visible here.
EVIDENCE = {
    "total_bound": {"min_listings_opened": "oracle_floor",
                    "counterexample": False,
                    "enforced_by": ["superlative_without_coverage", "understated_population"]},
    "rate_bound": {"min_listings_opened": "oracle_floor",
                   "counterexample": False,
                   "enforced_by": ["superlative_without_coverage", "understated_population"]},
    "refutation": {"min_listings_opened": 1,
                   "counterexample": True,
                   "enforced_by": ["unverified_universal", "refutation_without_evidence"]},
    "availability_bound": {"min_listings_opened": "oracle_floor",
                           "counterexample": False,
                           "enforced_by": ["superlative_without_coverage",
                                           "understated_population"]},
    # Existential, so the asymmetry is the opposite of a universal: one hit settles yes and
    # no amount of silence settles no. The evidence a yes must show is the hit itself.
    "depth_search": {"min_listings_opened": 1,
                     "counterexample": False,
                     "witness": True,
                     "enforced_by": ["claim_without_content", "unverified_universal"]},
    "survey": {"min_listings_opened": "population",
               "counterexample": False,
               "enforced_by": ["claim_without_content"]},
    # The advertised prices are all on the results page, so nothing has to be opened.
    "results_page": {"min_listings_opened": 0,
                     "counterexample": False,
                     "enforced_by": []},
    # Box v2's kinds are enforced by the primitive's own check (`primitives.check`).
    "exists_price": {"min_listings_opened": 1,
                     "counterexample": False,
                     "witness": True,
                     "enforced_by": ["primitives.Witness"]},
    "topk_price": {"min_listings_opened": "oracle_floor",
                   "counterexample": False,
                   "enforced_by": ["primitives.BoundPrune"]},
    "named_lookup": {"min_listings_opened": "population",
                     "counterexample": False,
                     "enforced_by": ["primitives.Lookup"]},
    "argmax_price": {"min_listings_opened": "population",
                     "counterexample": False,
                     "enforced_by": ["primitives.BoundPrune"]},
}

# A figure produced by a bound is a device for deciding what to skip. It is not a price, and
# reporting it as one is the failure the quarantine paragraph exists to prevent.
FORBIDDEN_WITH_BOUND = ["a figure derived from the bound, reported as a price",
                        "an advertised price paired with a pack size it was not shown for"]


def plan(question: str) -> dict:
    """The retrieval plan for one question.

    Classification reads the question text, never the task id, for the same reason
    `targeting.py` does: keying off the id would make the policy look like it works while
    doing nothing, since the id encodes the answer the experiment exists to test for.
    """
    kind = targeting.classify(question)
    return {
        "planner_version": VERSION,
        "strategy_version": targeting.VERSION,
        "kind": kind,
        "quantifier": QUANTIFIERS[kind],
        "population": "every listing in the search results, including later pages",
        # Where the attribute being compared actually lives. On the results page it can be
        # compared without opening anything, which is what makes the control question a
        # control. Everything the policy is measured on is gated behind a listing page.
        "evidence_source": "results page" if kind == "results_page" else "listing pages",
        "enumerate_first": True,
        "bound": BOUNDS[kind],
        "stop_rule": STOP_RULES[kind],
        "evidence_required": EVIDENCE[kind],
        "forbidden_claims": FORBIDDEN_WITH_BOUND if BOUNDS[kind] else [],
    }


STOP_RULES = {
    "total_bound": "when no unopened listing advertises below the best total found",
    "rate_bound": "when no unopened listing's best possible rate beats the best rate found",
    "availability_bound": "when no unopened listing advertises below the best total found "
                          "that can actually be supplied",
    "refutation": "at the first listing that lacks the option, which settles the question",
    "depth_search": "at the first review that mentions it, or not before the last page",
    "survey": "when every enumerated listing has been opened",
    "results_page": "once every listing on the results page has been read",
    # {within} is the limit's own comparison, "below" for "under $27" and "at or below" for
    # "at most $27" (form v9, 20 October 2026), filled in by `primitives.Witness` as {k} is
    # by the bound. A limit that is not strict renders the words this entry always held.
    "exists_price": "at the first listing whose option is available {within} the limit, "
                    "or when every listing advertised {within} the limit has been opened",
    "topk_price": "when the {k} cheapest available totals are held and no unopened listing "
                  "advertises below the dearest of them",
    "named_lookup": "when every named listing has been opened",
    "argmax_price": "when every listing has been opened, since the advertised price bounds "
                    "nothing from above",
}


def verify(plan_obj: dict) -> list[str]:
    """Why this plan must not be executed, empty when it may be.

    Four properties, each one already paid for in a measured failure. They are what a plan
    from a model would have to satisfy before it is allowed to reach the agent, and what a
    hand-written plan is held to in the meantime.

    Two of the four were stated too broadly when first written, and `plan_probe.py` found
    both on its first run by asking the model for plans the strategy table has no entry for.
    Enumeration was demanded of every plan, which is wrong for an existential question: one
    seller under $20 settles "is anyone under $20", and finding it needs no list of the
    others. And coverage was demanded of every superlative, which is wrong when the attribute
    being compared is on the results page, as it is for the control question. Both are now
    conditional, and both conditions are stated in the plan rather than inferred.
    """
    kind = plan_obj.get("kind")
    if kind not in targeting.STRATEGIES:
        return [f"no strategy text exists for kind {kind!r}"]
    return properties(plan_obj)


def properties(plan_obj: dict) -> list[str]:
    """The four soundness properties alone, for a plan whose text comes from somewhere other
    than `targeting.py`: box v2 composes its text from `primitives.py` and holds the plan to
    these through `form.verify` (14 October 2026). `verify` is these plus the check that v1
    text exists, so nothing a v1 caller sees has changed."""
    problems = []
    evidence = plan_obj.get("evidence_required") or {}
    quantifier = plan_obj.get("quantifier")
    gated = plan_obj.get("evidence_source", "listing pages") == "listing pages"

    # A bound rules out candidates. It cannot rule out candidates that were never
    # enumerated, which is how the first targeting arm read four listings of fifteen and
    # called it pruning. Required only where something is actually skipped.
    if (plan_obj.get("bound") or quantifier == "argmin") and not plan_obj.get("enumerate_first"):
        problems.append("the population is bounded over without being enumerated first")

    # A bound that may appear in the answer is how $6.82 became a per-litre rate for a pack
    # that costs $8.30.
    if plan_obj.get("bound") and not plan_obj.get("forbidden_claims"):
        problems.append("a bound is used but nothing forbids reporting the figure it "
                        "produces as a price")

    # Refuting a universal takes one counterexample. A plan that surveys instead is sound
    # and wasteful, and a plan that answers without a witness is neither.
    if quantifier == "universal" and not evidence.get("counterexample"):
        problems.append("a universal claim is answered without requiring a counterexample")

    # Naming the best of a population that was never covered is the failure the coverage
    # rule catches after the fact. A plan should not propose it in the first place. It does
    # not apply when the attribute compared is published on the results page, since then
    # nothing has to be opened to compare it.
    if (quantifier == "argmin" and gated
            and evidence.get("min_listings_opened") not in ("oracle_floor", "population")):
        problems.append("the best of a population is claimed without requiring coverage "
                        "of that population")
    return problems


def render(plan_obj: dict) -> str:
    """The instruction the agent receives.

    Returns the frozen strategy text for the plan's kind, unchanged. The plan is the source
    of truth for what the policy intends; this is the source of truth for what the agent was
    told, and keeping the second one byte-stable is what lets the runs already recorded
    stand while the first one grows.
    """
    return targeting.STRATEGIES[plan_obj["kind"]]


def planned_query(question: str) -> tuple[str, str]:
    """The question with its plan attached, and the plan's kind.

    Signature matches `targeting.targeting_query` so a caller can swap one for the other.
    """
    plan_obj = plan(question)
    problems = verify(plan_obj)
    if problems:
        raise ValueError("refusing to execute an unsound plan: " + "; ".join(problems))
    return f"{question}\n\n{render(plan_obj)}", plan_obj["kind"]


def questions() -> list[tuple[str, str]]:
    """Every question the project asks, as (task file, query)."""
    found = []
    for name in ("tasks.json", "tasks_scaled.json", "tasks_heldout.json",
                 "tasks_apparel.json", "tasks_reviews.json"):
        path = paths.TASKS / name
        if not path.exists():
            continue
        spec = json.loads(path.read_text())
        for task in spec["tasks"]:
            found.append((name, task["query"].format(base="http://localhost:7770")))
    return found


def regression() -> int:
    """Assert the planner changes nothing the agent can see.

    A refactor of a policy that has already been measured is only free if the bytes are
    identical. This checks that over every question in every task file rather than over the
    four that happened to be in mind.
    """
    failures = 0

    # Every strategy needs a planner entry, and on 18 Sep 2026 two did not. Two strategies
    # were added to `targeting.py` by hand and the planner's tables were not touched, so
    # `plan()` raised KeyError on fifteen questions and nothing noticed, because no run goes
    # through the planner yet. Checked first here so the next hand-written strategy fails
    # loudly instead of quietly.
    orphans = sorted(k for k in targeting.STRATEGIES if k not in QUANTIFIERS)
    if orphans:
        failures += len(orphans)
        for kind in orphans:
            print(f"FAIL {'strategy table':20} {kind:12} has no plan, quantifier or evidence")

    for name, query in questions():
        want, want_kind = targeting.targeting_query(query)
        got, got_kind = planned_query(query)
        same = want == got and want_kind == got_kind
        problems = verify(plan(query))
        if not same:
            failures += 1
        if problems:
            failures += 1
        mark = "ok  " if same and not problems else "FAIL"
        print(f"{mark} {name:20} {got_kind:12} {query.split('. ', 1)[-1][:58]}")
        if not same:
            print(f"     rendered text differs from targeting.py v{targeting.VERSION}")
        for problem in problems:
            print(f"     unsound plan: {problem}")

    print(f"\n{len(questions())} questions, {failures} failures")
    print(f"planner v{VERSION}, strategies v{targeting.VERSION}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--regression", action="store_true",
                        help="check that every question plans to the frozen strategy text")
    parser.add_argument("--show", help="print the plan for one question")
    args = parser.parse_args()

    if args.show:
        plan_obj = plan(args.show)
        print(json.dumps(plan_obj, indent=2))
        problems = verify(plan_obj)
        print("\nverify:", "sound" if not problems else "; ".join(problems))
        print("\n--- rendered ---\n" + render(plan_obj))
        return 0
    return regression()


if __name__ == "__main__":
    raise SystemExit(main())
