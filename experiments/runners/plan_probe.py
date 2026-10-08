#!/usr/bin/env python3
"""Ask the model to write its own retrieval plan, and check whether the plan is sound.

`planner.py` builds a plan from four hand-written strategies. That works for the questions
in hand and does not scale: a new kind of question needs a new paragraph, written by me,
frozen by me, and kept in step with the rule that judges its answer.

The alternative is to let the model write the plan and to execute it only if it passes
`planner.verify`. Whether that is worth building depends on a number nobody has: how often
an unaided model proposes a plan that is actually sound. This measures it, with no browser
and therefore almost no money, before any of it is built.

Two conditions, because they answer different questions.

**blind.** The model is given the schema and the question, and nothing about what makes a
plan sound. This is the honest test of whether the soundness conditions have to be supplied.

**guided.** The model is also given the four properties the verifier checks. If blind fails
and guided passes, the properties belong in the prompt, which is a cheap finding. If guided
fails too, a model-written plan is not yet safe to execute and the frozen strategies stay.

Eight questions. Five are the ones already measured, so the model's choice can be compared
against the deterministic classifier. Three are kinds the strategy table does not cover,
which is the case the whole idea exists for.

    python experiments/runners/plan_probe.py --dry-run
    python experiments/runners/plan_probe.py
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import planner
import targeting

REPO = paths.REPO
RESULTS = paths.RESULTS
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
USAGE = "https://openrouter.ai/api/v1/key"

# The five already measured, so the model's classification can be checked against the
# deterministic one, plus three the strategy table has no entry for. The last three are the
# point: a threshold question can stop at the first listing under the threshold, a count
# cannot stop early at all, and the fourth asks for something the shop does not publish, so
# the only correct plan is to refuse.
QUESTIONS = [
    ("cheapest-target", "Across all the Rivenhall listings, which seller is cheapest for "
                        "the 2 x 9.5L pack, and what is that price?"),
    ("target-price", "What is the lowest price anyone charges for the 2 x 9.5L pack of "
                     "Rivenhall water?"),
    ("all-stocked", "Does every Rivenhall listing stock the 2 x 9.5L pack? Answer yes or no."),
    ("best-per-litre", "Across all the Rivenhall listings and all their pack sizes, which "
                       "seller offers the lowest price per litre?"),
    ("headline", "Of the Rivenhall water listings shown, which one advertises the lowest "
                 "price on the results page, and what is that price?"),
    ("threshold", "Is any Rivenhall seller under $20 for the 2 x 9.5L pack?"),
    ("count", "How many of the Rivenhall listings stock the 2 x 9.5L pack?"),
    ("unanswerable", "Which Rivenhall seller delivers fastest?"),
]

SCHEMA = """Return one JSON object and nothing else, with exactly these fields:

{
  "kind": a short name for the retrieval strategy,
  "quantifier": one of "argmin", "universal", "existential", "enumerate",
  "population": what set of things the question ranges over,
  "evidence_source": "results page" if the attribute being compared is published in the
                     search results, otherwise "listing pages",
  "enumerate_first": true or false, whether the whole population is listed before any of
                     it is skipped,
  "bound": null, or {"field": what is compared, "valid_because": why that comparison can
           rule a candidate out},
  "stop_rule": when the agent may stop retrieving,
  "evidence_required": {"min_listings_opened": a number, or "oracle_floor", or
                        "population"; "counterexample": true or false},
  "forbidden_claims": a list of things the answer must not say
}"""

CONTEXT = """You are planning how a web agent should retrieve information from an online
shop before answering a question.

The shop's search results hold 15 competing listings for the same product, across two
pages. Each listing shows one advertised price, which is its cheapest option. A listing
sells the product in several pack sizes, and the price of a given pack size is visible
only after opening that listing. Some listings do not stock every pack size."""

PROPERTIES = """A plan is sound only if all four of these hold:

1. The population is enumerated before any of it is skipped. A bound cannot rule out a
   candidate that was never known to exist.
2. If the plan uses a bound to skip candidates, it forbids the answer from reporting any
   figure the bound produced. A bound is a device for deciding what not to open, not a
   price.
3. A question about every member of a population requires a counterexample to answer in
   the negative, and the whole population to answer in the affirmative.
4. Naming the best member of a population requires the evidence to cover that population,
   so the required coverage is the whole population or the fewest members any correct
   method could open. This does not apply when the attribute compared is already published
   in the search results."""


def load_key() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    return os.getenv("OPENROUTER_API_KEY", "")


def model_name() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith("MODEL_NAME="):
            return line.split("=", 1)[1].strip()
    return "anthropic/claude-haiku-4.5"


def usage(key: str) -> float | None:
    try:
        got = requests.get(USAGE, headers={"Authorization": f"Bearer {key}"}, timeout=20)
        return float(got.json()["data"]["usage"])
    except Exception:
        return None


def ask(key: str, model: str, question: str, guided: bool) -> tuple[dict | None, str]:
    parts = [CONTEXT, PROPERTIES if guided else "", SCHEMA,
             f"The question the agent must answer:\n{question}"]
    prompt = "\n\n".join(p for p in parts if p)
    reply = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "temperature": 0,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    reply.raise_for_status()
    text = reply.json()["choices"][0]["message"]["content"]
    block = re.search(r"\{.*\}", text, re.DOTALL)
    if not block:
        return None, text
    try:
        return json.loads(block.group(0)), text
    except json.JSONDecodeError:
        return None, text


def verify_proposed(proposal: dict) -> list[str]:
    """Check a model-written plan with the same verifier a hand-written plan faces.

    `planner.verify` expects a kind that has strategy text, which a model-written plan will
    not have, so that one check is replaced by the equivalent structural question: does the
    plan name a quantifier the verifier knows how to reason about. Everything else is the
    same code path, deliberately, because a verifier that is lenient for proposals is not a
    verifier.
    """
    problems = []
    quantifier = proposal.get("quantifier")
    evidence = proposal.get("evidence_required") or {}
    gated = proposal.get("evidence_source", "listing pages") != "results page"
    if quantifier not in ("argmin", "universal", "existential", "enumerate"):
        problems.append(f"unknown quantifier {quantifier!r}")

    if (proposal.get("bound") or quantifier == "argmin") and not proposal.get("enumerate_first"):
        problems.append("the population is bounded over without being enumerated first")
    if proposal.get("bound") and not proposal.get("forbidden_claims"):
        problems.append("a bound is used but nothing forbids reporting its figure as a price")
    if quantifier == "universal" and not evidence.get("counterexample"):
        problems.append("a universal claim is answered without requiring a counterexample")
    if (quantifier == "argmin" and gated
            and evidence.get("min_listings_opened") not in ("oracle_floor", "population", 11, 15)):
        problems.append("the best of a population is claimed without requiring coverage")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    model = args.model or model_name()
    if args.dry_run:
        for name, question in QUESTIONS:
            print(f"{name:14} deterministic={targeting.classify(question):12} {question[:60]}")
        print(f"\n{len(QUESTIONS) * 2} calls to {model}, text only, no browser")
        return 0

    key = load_key()
    if not key:
        print("no OPENROUTER_API_KEY")
        return 1
    before = usage(key)

    rows = []
    for guided in (False, True):
        for name, question in QUESTIONS:
            proposal, raw = ask(key, model, question, guided)
            problems = ["no JSON object in the reply"] if proposal is None \
                else verify_proposed(proposal)
            rows.append({"condition": "guided" if guided else "blind", "task": name,
                         "question": question,
                         "deterministic_kind": targeting.classify(question),
                         "proposed_kind": (proposal or {}).get("kind"),
                         "quantifier": (proposal or {}).get("quantifier"),
                         "sound": not problems, "problems": problems,
                         "plan": proposal, "raw": raw[:2000]})
            mark = "ok  " if not problems else "FAIL"
            print(f"{mark} {rows[-1]['condition']:7} {name:14} "
                  f"{str(rows[-1]['proposed_kind'])[:22]:22} {'; '.join(problems)[:60]}")

    after = usage(key)
    spent = round(after - before, 4) if (before is not None and after is not None) else None

    for condition in ("blind", "guided"):
        part = [r for r in rows if r["condition"] == condition]
        print(f"\n{condition}: {sum(r['sound'] for r in part)} of {len(part)} plans sound")
    known = [r for r in rows if r["task"] in
             ("cheapest-target", "target-price", "all-stocked", "best-per-litre", "headline")]
    print(f"agreement with the deterministic classifier is reported per row above, on the "
          f"{len(known) // 2} questions it has a strategy for")
    print(f"spend: {('$%.4f' % spent) if spent is not None else 'unknown'}")

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out = RESULTS / f"plan-probe-{stamp}.json"
    out.write_text(json.dumps({"ran_at": stamp, "model": model, "spend_usd": spent,
                               "planner_version": planner.VERSION,
                               "rows": rows}, indent=2) + "\n")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
