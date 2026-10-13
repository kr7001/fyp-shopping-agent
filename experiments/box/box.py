#!/usr/bin/env python3
"""The box: what openJiuwen must retrieve, decided from the question and the results page.

It runs before the agent and does one of two things. It hands the agent a plan: how many
listings there are, which to open and in what order, when to stop and what counts as
evidence. Or it asks the user back, when the question has two reasonable readings and the
readings give different answers.

It may use only what the agent itself could see: the question, the first results page as
`page.py` read it, and the user's reply to its own question. Never a task file's answers,
a market's instance record or a generated catalogue. `tests/test_box.py` checks that.

Written rules, not a model, decide the plan: `targeting.classify` chooses the kind of
answer the question needs and `planner.plan` builds and checks the plan. The strategy text
the agent receives is the frozen v7 text minus its "enumerate first" step, because the box
has done the enumeration itself and puts the listings it read in front of the strategy.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401  (puts box/, runners/, analysis/, water/ on the path)
import ambiguity
import page as page_module
import planner
import targeting

# Bumped when the box's behaviour changes: what it asks, what it reads, or the text it
# renders. Runs made under different versions are different boxes and are never pooled.
#
#   1  14 October 2026. Reads the first results page, asks on an ambiguous variant
#      question, and renders the listings by advertised price above the v7 strategy body
VERSION = 1

# The results page the question sends the agent to: the first URL in it.
URL = re.compile(r"https?://\S+")


@dataclasses.dataclass(frozen=True)
class Decision:
    kind: str | None            # the question's kind, None when the box asked instead
    ask: ambiguity.Ask | None   # the question put to the user, when there was one
    reading: str | None         # the reading the user's reply chose
    query: str | None           # the exact text the agent receives, None when asking
    plan: dict | None           # the planner's plan, None when asking
    page: page_module.Page      # what the box read

    def record(self) -> dict:
        return {"box_version": VERSION, "kind": self.kind, "page": self.page.record(),
                "asked": self.ask is not None, "ask": self.ask.text if self.ask else None,
                "reading": self.reading, "query": self.query}


def results_url(question: str) -> str:
    found = URL.search(question)
    if not found:
        raise ValueError("the question names no results page to read")
    return found.group(0).rstrip(".,;:)")


def preamble(page: page_module.Page) -> str:
    """What the box read from the results page, in the words the agent receives.

    The listings come sorted by advertised price because every bound strategy opens them
    in that order, and their URLs come with them. Finding those was the box's work: the
    cells it is compared with had to find them, and that is stated as a difference rather
    than hidden.
    """
    pager = ("there is a next page, open it too before deciding." if page.next_page
             else "there is no next page.")
    lines = [f"The results page lists {len(page.listings)} listings on one page; {pager}",
             "Listings by advertised price, read from the results page:"]
    lines += [f"{n}. {item.seller}, advertised ${item.advertised:.2f}, {item.url}"
              for n, item in enumerate(page.by_price(), 1)]
    return "\n".join(lines)


def decide(question: str, page: page_module.Page, reply: str | None = None) -> Decision:
    """An ask or a plan for one question.

    With no reply, an ambiguous question comes back as an ask and nothing is planned. A
    reply must be one of the readings the ask offered, and the question is then planned
    with that reading written into it, so the agent sees no ambiguity. A reply to a
    question that was never ambiguous is ignored.
    """
    asked = ambiguity.ask(question)
    if asked is not None and reply is None:
        return Decision(kind=None, ask=asked, reading=None, query=None, plan=None, page=page)
    reading = None
    if asked is not None:
        if reply not in asked.readings:
            raise ValueError(f"reply {reply!r} is not one of the readings offered: "
                             f"{sorted(asked.readings)}")
        question = ambiguity.with_reading(question, asked, reply)
        reading = reply
    kind = targeting.classify(question)
    plan = planner.plan(question)
    problems = planner.verify(plan)
    if problems:
        # The refusal `planner.planned_query` makes, for the same reason: paying a model to
        # execute a plan already known to be unsound buys nothing.
        raise ValueError("refusing to execute an unsound plan: " + "; ".join(problems))
    query = f"{question}\n\n{preamble(page)}\n\n{targeting.BODIES[kind]}"
    return Decision(kind=kind, ask=asked, reading=reading, query=query, plan=plan, page=page)
