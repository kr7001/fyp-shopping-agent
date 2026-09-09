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
