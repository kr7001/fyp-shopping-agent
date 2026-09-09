#!/usr/bin/env python3
"""Turn the sufficiency rules into a policy the agent actually runs under.

`sufficiency.py` decides whether an answer is supported by what the run observed. That
is a judgement, not a behaviour. This module is the behaviour: what the system does with
a run whose answer fails the check.

Two arms, because they answer different questions.

**gate.** A flagged answer is replaced by an abstention naming what could not be
verified. Nothing is re-run, so the arm costs nothing beyond the baseline and isolates
one effect: what happens to accuracy when the agent is allowed to say it does not know.
The expected result is that wrong answers become abstentions and correct answers survive.

**retry.** A flagged answer is sent back with the reason, and the task is attempted
again. This is the arm that can turn a failure into a correct answer rather than merely a
refusal, and it is the one that costs money. It mirrors the goal mode openJiuwen already
has, where a step reports `blocked` and the loop re-plans, except the block is raised by
evidence rather than by a tool error.

The second attempt runs in a fresh browser, because each run is its own process and the
runtime shuts the browser down on exit. So the retry inherits the reason but not the page
state, which makes it a strictly harder test than an in-loop block would be, and makes
its cost a full second run rather than a few extra steps. Worth stating plainly rather
than implying an in-loop integration that is not what this measures.

The check runs against the run log the runner already wrote, using the same parser the
offline evaluation used. That is deliberate: if the live input and the offline input are
the same bytes through the same code, the offline precision and recall figures transfer
to the live arm instead of having to be re-established.
"""

from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import sufficiency

# Wording matters here in a way it usually does not. The scorer classifies an answer as
# an abstention by looking for a hedge, and a policy that refuses without using one would
# be scored as a wrong answer, which would hide the very effect this arm measures. So the
# abstention says "could not determine" explicitly, and the reason follows it.
ABSTENTION = ("I could not determine this reliably. {why}. "
              "The figure above is not confirmed by what I retrieved.")

# What to tell the agent when it is sent back. A bare "try again" wastes the attempt: the
# baseline shows the agent is not short of effort, it is wrong about what it has. Each
# hint names the specific misreading so the second attempt is aimed.
HINTS = {
    "delta_as_absolute": (
        "Your answer reported a figure that the page showed only as a surcharge. A "
        "variant option labelled '+$X' states the amount added to the base price, not "
        "the price of that variant. Add it to the base price and report the total."),
    "unsupported_number": (
        "Your answer stated an amount that does not appear on any page you opened. "
        "Re-read the relevant page and quote only figures shown there."),
    "claim_without_content": (
        "Your answer said the work was done but contained none of the figures asked "
        "for. Report each item with its price."),
    "unverified_universal": (
        "You answered yes to a question about every listing, having opened only some of "
        "them. Either open the rest, or say which ones you did not check."),
}


def instance(spec: dict) -> dict:
    return spec.get("_instance") or {}


def gate(task: dict, spec: dict, answer: str, log_path: pathlib.Path) -> dict:
    """Run the sufficiency check over one finished run.

    Returns the raw verdict from `sufficiency.check`, plus the coverage figures it was
    given, so a result file records why a run was blocked and not only that it was.
    """
    text = sufficiency.observed_text(log_path)
    inst = instance(spec)
    opened = sufficiency.listings_opened(text)
    verdict = sufficiency.check(
        answer,
        sufficiency.evidence(text),
        question=task.get("query", ""),
        population=inst.get("listings"),
        opened=len(opened),
    )
    return {**verdict, "opened": len(opened), "population": inst.get("listings")}


def abstention_for(verdict: dict) -> str:
    return ABSTENTION.format(why=verdict["why"])


def hint_for(verdict: dict) -> str:
    """The instruction appended to a second attempt."""
    return HINTS.get(verdict["flag"], "Your previous answer could not be verified "
                                      "against what you retrieved. Check it again.")


def retry_query(query: str, verdict: dict) -> str:
    return (f"{query}\n\n"
            "Your previous attempt in this browser session produced an answer that "
            f"failed a verification check: {verdict['why']}.\n"
            f"{hint_for(verdict)}\n"
            "Answer again from the start, and if you still cannot confirm the figure, "
            "say so rather than guessing.")

# ---------------------------------------------------------------------------
# The verbalised-confidence baseline.
#
# The obvious objection to this project is "why not just ask the agent how confident it
# is, and abstain below a threshold". It has to be answered with a measurement rather than
# a citation, so it is implemented here as a fourth arm.
#
# Two wordings, because they test different things and only one of them is the standard
# baseline.
#
# `plain` is the formulation the calibration literature uses: confidence that the answer
# is correct. This is the fair comparison.
#
# `retrieval` names the dimension this project cares about, asking the agent to consider
# whether it gathered everything needed. It is a deliberately *stronger* baseline, and
# close to a cheap version of the contribution. If it works, that is a real finding and a
# far simpler fix than five rules, so it deserves a fair test rather than a strawman.
#
# The prediction, recorded before running: neither separates right from wrong, because the
# agent is not uncertain. On a gated listing its context is internally consistent, it saw
# one price and read it correctly, so high confidence is the calibrated response. If that
# holds, confidence cannot be the signal, and an evidence-grounded check is necessary
# rather than merely one option among several.
CONFIDENCE_PROMPTS = {
    # The agent's own contract is a JSON object whose `final` key holds the answer text, so
    # the request has to name that field. A first attempt asked for a trailing line and was
    # simply not complied with, which is a prompt-format problem rather than a result and
    # would have quietly turned this baseline into a strawman.
    "plain": (
        "\n\nIn your final answer text, after the answer itself, end the `final` string "
        "with how confident you are that the answer is correct, in exactly this format:\n"
        "CONFIDENCE: <number from 0 to 100>\n"
        "Include it every time, even when you are certain."),
    "retrieval": (
        "\n\nIn your final answer text, after the answer itself, end the `final` string "
        "with how confident you are that the answer is correct, taking into account "
        "whether you gathered all the information the question needed, in exactly this "
        "format:\nCONFIDENCE: <number from 0 to 100>\n"
        "Include it every time, even when you are certain."),
}

CONFIDENCE_RE = re.compile(r"CONFIDENCE\s*[:=]\s*(\d{1,3})", re.IGNORECASE)


def confidence_query(query: str, wording: str) -> str:
    return query + CONFIDENCE_PROMPTS[wording]


def parse_confidence(answer: str) -> int | None:
    """The confidence the agent stated, or None if it did not state one.

    A missing figure is recorded as missing rather than defaulted. Treating an absent
    confidence as 100 would manufacture the very overconfidence this arm tests for.
    """
    found = CONFIDENCE_RE.findall(answer or "")
    if not found:
        return None
    value = int(found[-1])
    return value if 0 <= value <= 100 else None


def strip_confidence(answer: str) -> str:
    """The answer without its confidence line, so scoring sees what it would have seen.

    The stated number is a percentage and the scorer looks for money, so leaving it in
    risks a two-digit confidence being read as part of a price.
    """
    return CONFIDENCE_RE.sub("", answer or "").strip()
