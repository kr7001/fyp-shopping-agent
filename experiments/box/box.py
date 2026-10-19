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
#   3  14 October 2026. The check changes, the text does not: the floor from the page
#      counts a tie at the answer's price once (`policy.bound_floor`), and the witness
#      and counterexample checks refuse an answer with neither yes nor no (primitives
#      v2). On Thornwood every stored floor is the same, so the pilot stands
#   4  14 October 2026. A question with no shopping shape and no shopping signal bypasses
#      the box: the agent gets it unchanged and the record says so. A shopping question
#      the rules can only survey keeps running and records that it was a fallback
#   5  14 October 2026. The checks change, the text does not (primitives v3): a denial is
#      read however it starts, an existence answer with neither yes nor no owes what a no
#      owes, the floor's extra one is for the answer's own listing only, and a seller is
#      named only as a whole word. "sell" and its forms are market words (form v4), so
#      "Who sells the softest tee?" is a fallback rather than a bypass
#   6  14 October 2026. The check changes, the text does not: the figures the question
#      states include every price limit the form parsed from it, written as the plan
#      writes it, so a question that says "under $20" exempts the "$20.00" the witness
#      text sends and an answer quoting it back is not refused (`stated_figures`)
#   7  20 October 2026. Two changes to what is refused before the agent runs, and two to
#      the check. A superlative or comparative on an attribute the shop does not show is
#      refused whatever the word (form v5), and a refusal comes before an ask for a price
#      limit. The check counts as opened only the listings on the page the box read, and
#      a bare No to a universal is supported by an opened listing whose observed size
#      menu lacks the size (primitives v4, `sufficiency.size_menus`). On the three box
#      v2 batches of 14 October no text changes; one question, "Who sells the softest
#      Thornwood tee?", is refused instead of planned by the fallback
VERSION = 7

# The results page the question sends the agent to: the first URL in it.
URL = re.compile(r"https?://\S+")

# Why a question went to the agent unchanged. The one reason there is: the rules found no
# shape and no sign that the question is about the shop (`form.shopping_signal`).
BYPASS_REASON = "no shopping shape recognised"

# The account of the market the box puts in front of every plan. It lives beside the
# primitives that follow it, and keeps this name because the suite and the tests call it.
preamble = primitives.preamble


@dataclasses.dataclass(frozen=True)
class Decision:
    question: str               # the question as planned, with any reading written in
    kind: str | None            # the plan's kind, None when the box asked, refused or bypassed
    ask: ambiguity.Ask | None   # the question put to the user, when there was one
    reading: str | None         # the reading the user's reply chose
    query: str | None           # the exact text the agent receives, None when not running
    plan: primitives.Plan | None
    page: page_module.Page | None   # what the box read, None when the question names no page
    form: form_module.Form | None = None    # what the box parsed, None when it asked first
    refuse: str | None = None   # why no plan was made: what the shop does not show
    bypass: bool = False        # the agent gets the question unchanged, see BYPASS_REASON

    def record(self) -> dict:
        return {"box_version": VERSION, "form_version": form_module.VERSION,
                "primitives_version": primitives.VERSION,
                "kind": self.kind, "page": self.page.record() if self.page else None,
                "asked": self.ask is not None, "ask": self.ask.text if self.ask else None,
                "reading": self.reading, "query": self.query,
                "form": self.form.record() if self.form else None, "refuse": self.refuse,
                "bypassed": self.bypass, "bypass_reason": BYPASS_REASON if self.bypass else None,
                "fallback": bool(self.form and self.form.fallback),
                "plan": self.plan.record() if self.plan else None}


def results_url(question: str, required: bool = True) -> str | None:
    """The first URL in the question. None when there is none and none is required, as
    for a question that may turn out to be about something other than the shop."""
    found = URL.search(question)
    if not found:
        if required:
            raise ValueError("the question names no results page to read")
        return None
    return found.group(0).rstrip(".,;:)")


def decide(question: str, page: page_module.Page | None, reply: str | None = None) -> Decision:
    """An ask, a refusal or a plan for one question.

    With no reply, an ambiguous question comes back as an ask and nothing is planned. A
    reply must be one of the readings the ask offered, and the question is then planned
    with that reading written into it, so the agent sees no ambiguity. A reply to a
    question that was never ambiguous is ignored.

    The ask on a price word with no figure offers no readings, so a reply cannot answer it
    and the ask stands as the outcome. The design's third rule, not asking when the two
    readings agree on this page, waits: it needs to know whether any listing is sold out
    in the size asked about, and the results page shows no stock, so it is not faked here.

    A question the rules find no shape and no shopping signal in is a bypass: the agent
    gets it unchanged, with no preamble and no plan, and the record says so. The page may
    be None then, since such a question names none. Every other outcome needs the page.

    A refusal comes before an ask (20 October 2026): a question that needs an attribute
    the shop does not show cannot be answered whatever limit the user would give, so it is
    refused rather than asked. The one ask the form raises on its own is for a price limit.
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
    if form.quantifier == "unknown":
        return Decision(question=question, kind=None, ask=asked, reading=reading,
                        query=question, plan=None, page=page, form=form, bypass=True)
    if page is None:
        raise ValueError("the question names no results page to read")
    missing = form_module.not_shown(form, page)
    if missing:
        return Decision(question=question, kind=None, ask=asked, reading=reading, query=None,
                        plan=None, page=page, form=form, refuse=form_module.refusal(missing))
    if "price limit" in form.unknowns:
        return Decision(question=question, kind=None,
                        ask=ambiguity.threshold_ask(form.evidence["unknowns"]),
                        reading=reading, query=None, plan=None, page=page, form=form)
    problems = form_module.verify(form, page)
    if problems:
        # The refusal `planner.planned_query` makes, for the same reason: paying a model to
        # execute a plan already known to be unsound buys nothing.
        raise ValueError("refusing to execute an unsound plan: " + "; ".join(problems))
    plan = primitives.compose(form, page)
    return Decision(question=question, kind=form.kind(), ask=asked, reading=reading,
                    query=f"{question}\n\n{plan.text}", plan=plan, page=page, form=form)


def stated_figures(decision: Decision) -> set[int]:
    """The figures the question itself states, in cents, so an answer that quotes a limit
    back is not refused for inventing it: the decimals written in the question, and every
    price limit the form parsed from it, written as the plan text writes it.

    A question that says "under $20" writes no decimal, so `sufficiency.prices_in` read
    nothing from it, while the witness text put "$20.00" in front of the agent and an
    answer echoing that was refused as unsupported (verifier finding, 14 October 2026).
    The form's limit is the same figure however the question wrote it. A limit parsed by
    the rules is a float; one a model proposed is whatever its JSON held, and only a number
    is read.
    """
    stated = set(sufficiency.prices_in(decision.question))
    filters = decision.form.filters if decision.form is not None else ()
    for condition in filters:
        if condition.attribute == "price" and isinstance(condition.value, (int, float)):
            stated.update(sufficiency.prices_in(f"${condition.value:.2f}"))
    return stated


def check(decision: Decision, answer: str, log_path: pathlib.Path) -> dict:
    """The refusal check for a run the box planned, from the page and the plan alone.

    A v1 kind gets v1's page-derived check unchanged, so the pilot's verdicts stay
    comparable. A kind v1 did not have gets the figure rules alone, with the figures the
    question itself states exempted (a limit the answer quotes back is not an invented
    price, `stated_figures`), since the coverage rules are written for v1's question
    shapes. So does a bypassed question, which has no plan and usually no page: the figure
    rules need neither. Either way, a verdict that passes is then held to the plan's own
    check, when there is a plan: did the run open what the primitive's stop rule required.

    What counts as opened is a listing of the market the box read, the page's own URLs
    (20 October 2026); a bypassed run has no page, so the counter's own rule applies. The
    size menus the run saw are read from its log for the counterexample check.
    """
    text = sufficiency.observed_text(log_path)
    market = [item.url for item in decision.page.listings] if decision.page else None
    if decision.kind in targeting.BODIES:
        verdict = policy.gate_from_page(decision.question, decision.page, answer, log_path)
    else:
        seen = sufficiency.evidence(text)
        stated = stated_figures(decision)
        seen = {"deltas": seen["deltas"], "absolutes": seen["absolutes"] | stated,
                "any": seen["any"] | stated}
        verdict = {**sufficiency.check(answer, seen),
                   "opened": len(sufficiency.listings_opened(text, market)),
                   "population": len(decision.page.listings) if decision.page else None,
                   "floor": None, "floor_from": "page" if decision.page else None}
    if verdict["ok"] and decision.plan is not None:
        own = primitives.check(decision.form, decision.page, answer, text,
                               menus=sufficiency.size_menus(log_path))
        verdict = {**verdict, "ok": own["ok"], "flag": own["flag"], "why": own["why"],
                   "primitive": own["primitive"]}
    return verdict
