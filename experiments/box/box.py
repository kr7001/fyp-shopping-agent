#!/usr/bin/env python3
"""The box: what openJiuwen must retrieve, decided from the question and the results page.

It runs before the agent and does one of three things. It hands the agent a plan: how many
listings there are, which to open and in what order, when to stop and what counts as
evidence. It asks the user back, when the question has two reasonable readings and the
readings give different answers, or names a price with no figure. Or it refuses, when the
question needs an attribute this shop does not show, and says what is missing instead.

It may use only what the agent itself could see: the question, the first results page as
`page.py` read it, and the user's reply to its own question. Never a task file's answers,
a market's instance record or a generated catalogue. `tests/test_box.py` checks that.

Version 2 parses the question into a logical form (`form.py`), holds the form to five
soundness properties, and composes the plan from a retrieval primitive (`primitives.py`).
For the seven kinds v1 had, the text is the same bytes v1 sent, the frozen v7 strategy body
under the box's own account of the market, which `tests/test_box.py` pins against a fixture
frozen from v1. So the pilot measured under v1 stays a measurement of what v2 sends.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401  (puts box/, runners/, analysis/, water/ on the path)
import ambiguity
import form as form_module
import page as page_module
import policy
import primitives
import sufficiency
import targeting

# Bumped when the box's behaviour changes: what it asks, what it reads, or the text it
# renders. Runs made under different versions are different boxes and are never pooled.
#
#   1  14 October 2026. Reads the first results page, asks on an ambiguous variant
#      question, and renders the listings by advertised price above the v7 strategy body
#   2  14 October 2026. Parses the question into a form, verifies five properties, asks for
#      a missing price limit, refuses an attribute the shop does not show, composes the
#      plan from a primitive, and checks the answer by the plan. The six clothing
#      questions render the same bytes as v1
VERSION = 2

# The results page the question sends the agent to: the first URL in it.
URL = re.compile(r"https?://\S+")

# The account of the market the box puts in front of every plan. It lives beside the
# primitives that follow it, and keeps this name because the suite and the tests call it.
preamble = primitives.preamble


@dataclasses.dataclass(frozen=True)
class Decision:
    question: str               # the question as planned, with any reading written in
    kind: str | None            # the plan's kind, None when the box asked or refused
    ask: ambiguity.Ask | None   # the question put to the user, when there was one
    reading: str | None         # the reading the user's reply chose
    query: str | None           # the exact text the agent receives, None when not running
    plan: primitives.Plan | None
    page: page_module.Page      # what the box read
    form: form_module.Form | None = None    # what the box parsed, None when it asked first
    refuse: str | None = None   # why no plan was made: what the shop does not show

    def record(self) -> dict:
        return {"box_version": VERSION, "form_version": form_module.VERSION,
                "primitives_version": primitives.VERSION,
                "kind": self.kind, "page": self.page.record(),
                "asked": self.ask is not None, "ask": self.ask.text if self.ask else None,
                "reading": self.reading, "query": self.query,
                "form": self.form.record() if self.form else None, "refuse": self.refuse,
                "plan": self.plan.record() if self.plan else None}


def results_url(question: str) -> str:
    found = URL.search(question)
    if not found:
        raise ValueError("the question names no results page to read")
    return found.group(0).rstrip(".,;:)")


def decide(question: str, page: page_module.Page, reply: str | None = None) -> Decision:
    """An ask, a refusal or a plan for one question.

    With no reply, an ambiguous question comes back as an ask and nothing is planned. A
    reply must be one of the readings the ask offered, and the question is then planned
    with that reading written into it, so the agent sees no ambiguity. A reply to a
    question that was never ambiguous is ignored.

    The ask on a price word with no figure offers no readings, so a reply cannot answer it
    and the ask stands as the outcome. The design's third rule, not asking when the two
    readings agree on this page, waits: it needs to know whether any listing is sold out
    in the size asked about, and the results page shows no stock, so it is not faked here.
    """
    asked = ambiguity.ask(question)
    if asked is not None and reply is None:
        return Decision(question=question, kind=None, ask=asked, reading=None, query=None,
                        plan=None, page=page)
    reading = None
    if asked is not None:
        if reply not in asked.readings:
            raise ValueError(f"reply {reply!r} is not one of the readings offered: "
                             f"{sorted(asked.readings)}")
        question = ambiguity.with_reading(question, asked, reply)
        reading = reply
    form = form_module.from_rules(question, page)
    if form.unknowns:
        return Decision(question=question, kind=None,
                        ask=ambiguity.threshold_ask(form.evidence["unknowns"]),
                        reading=reading, query=None, plan=None, page=page, form=form)
    missing = form_module.not_shown(form, page)
    if missing:
        return Decision(question=question, kind=None, ask=asked, reading=reading, query=None,
                        plan=None, page=page, form=form, refuse=form_module.refusal(missing))
    problems = form_module.verify(form, page)
    if problems:
        # The refusal `planner.planned_query` makes, for the same reason: paying a model to
        # execute a plan already known to be unsound buys nothing.
        raise ValueError("refusing to execute an unsound plan: " + "; ".join(problems))
    plan = primitives.compose(form, page)
    return Decision(question=question, kind=form.kind(), ask=asked, reading=reading,
                    query=f"{question}\n\n{plan.text}", plan=plan, page=page, form=form)


def check(decision: Decision, answer: str, log_path: pathlib.Path) -> dict:
    """The refusal check for a run the box planned, from the page and the plan alone.

    A v1 kind gets v1's page-derived check unchanged, so the pilot's verdicts stay
    comparable. A kind v1 did not have gets the figure rules alone, with the figures the
    question itself states exempted (a limit the answer quotes back is not an invented
    price), since the coverage rules are written for v1's question shapes. Either way, a
    verdict that passes is then held to the plan's own check: did the run open what the
    primitive's stop rule required.
    """
    text = sufficiency.observed_text(log_path)
    if decision.kind in targeting.BODIES:
        verdict = policy.gate_from_page(decision.question, decision.page, answer, log_path)
    else:
        seen = sufficiency.evidence(text)
        stated = set(sufficiency.prices_in(decision.question))
        seen = {"deltas": seen["deltas"], "absolutes": seen["absolutes"] | stated,
                "any": seen["any"] | stated}
        verdict = {**sufficiency.check(answer, seen),
                   "opened": len(sufficiency.listings_opened(text)),
                   "population": len(decision.page.listings), "floor": None,
                   "floor_from": "page"}
    if verdict["ok"] and decision.plan is not None:
        own = primitives.check(decision.form, decision.page, answer, text)
        verdict = {**verdict, "ok": own["ok"], "flag": own["flag"], "why": own["why"],
                   "primitive": own["primitive"]}
    return verdict
