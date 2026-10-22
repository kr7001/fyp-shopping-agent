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
For the seven kinds v1 had, the text is the strategy body under the box's own account of
the market, which `tests/test_box.py` pins against a fixture frozen from v1. Until box v10
it was v1's bytes exactly, so the pilot measured under v1 was a measurement of what v2
sent; since strategy texts v8 and v9 (20 October 2026) it differs from them in the five
sentences those made true of the gated shop, and in nothing else, which the fixture's
dated amendment records.

Since box v13 (22 October 2026) a model may read the question instead of the rules
(`decide(parser="model", call=...)`), and the rules still verify, plan, stop and check: the
model's form is normalised and checked (`normalise.py`), the rules' form is used whenever it
fails, and every decision records who read the question, both forms and why. The rules
remain the default, and every text they render is the same.
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
import normalise
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
#   8  20 October 2026, the verifier's fixes to 7. A bare No is supported only by a
#      complete observed menu; an excerpt cut inside the menu shows presence alone
#      (`sufficiency.MenuReading`). A refusal comes before the ambiguity ask too, so no
#      user turn is spent on a question that needs what the shop does not show. The
#      graded-word rule reads "availability", a range of sizes and "the top" (form v6)
#   9  20 October 2026. A snapshot's combobox printed as a leaf (a depth cut) gives no
#      menu reading. An ambiguous question with one reading property 5 refuses is read
#      the other way without asking, and the record says the box chose it
#      (`Decision.reading_by`): a price question asked with "has size M" has a price only
#      for a size that can be sold. "best price" is the cheapest (form v7)
#   10 20 October 2026, the verifier's audit of the claim plan. "under $27" is a strict
#      limit (form v9, primitives v6), and so is the threshold ask's example. Four
#      sentences the box sends are made true of the gated shop under both readings
#      (strategy text v8). And the box can plan without its stop rule, every listing on
#      the page opened, for the arm that isolates the stop rule (`decide(exhaust=True)`,
#      recorded as `exhaust` in the decision and the plan)
#   11 20 October 2026. A fifth sentence made true (strategy text v9, primitives v7): a
#      sold-out size cannot be chosen from the menu, where a script can still force it
#   12 20 October 2026. The box without its stop rule no longer opens its quarantine by
#      saying the bound decides what to skip, since it skips nothing; it says what the
#      advertised price is (primitives v8). The box's own text is unchanged
#   13 22 October 2026, the model's front door. `decide(parser="model", call=...)`: a model
#      reads the question (form prompt v2), its form is normalised and checked
#      (`normalise.py`), and the rules' form is used instead, with the reason recorded,
#      when the call fails, the reply is not a form or the form fails a check. A word the
#      model reads two ways is asked about: the "offer" ask when it is the shop's own
#      ambiguity, the threshold ask for a price word with no figure, and a template quoting
#      the model's readings otherwise. A negated universal is planned (primitives v9).
#      Every decision records who read the question and both forms (`Parse`). With the
#      rules, the default, every text is the same as under box v12
VERSION = 13

# Who may read the question for the box: the rules, the default, or a model through a call
# the caller injects.
PARSERS = ("rules", "model")

# Every wording of what the box sends that was changed on purpose since the box v2 batches
# of 14 October 2026 (box v6), as (the box version that changed it, the words before, the
# words since), in the order they were made. The one place they are listed: today's text
# with every change made after a run's own box version swapped back is the text that run
# was sent (`as_sent_by`), which is how `replay_box` checks a stored plan byte for byte and
# `test_claim_arms.V1Amendment` checks the fixture frozen from v1 against v1. The strict
# "under" of form v9 (box v10) changed what a question parses to rather than a sentence, and
# a stored form keeps the operator it had, so a stored plan recomposed from its form needs
# no entry for it; deciding a question again today is another matter (`replay_box`). The
# quarantine's first sentence under the box without its stop rule (box v12) has none either:
# it changed in that arm alone, the box's own text keeps the old one, and no run of that arm
# was made before it changed.
REWORDED = (
    (10, "That price is the cheapest option in that listing, so nothing inside it can cost less.",
     "That price is the cheapest option in that listing that can be bought, so nothing in it "
     "that can be bought costs less."),
    (10, "The price a listing shows before you choose is its cheapest option, not the one asked "
         "about, and the reply to choosing an option does not show the new price.",
     "The price a listing shows before you choose is its cheapest option that can be bought, "
     "not necessarily the one asked about, and the reply to choosing an option does not show "
     "the new price."),
    (10, "It is not a real price and must never appear in your answer.",
     "It is not a price read for the option asked about, and must never appear in your answer "
     "as one."),
    (10, "Stopping after one or two openings is the correct outcome here, not a sign that you did "
         "too little.",
     "Stopping after one or two openings, once a counterexample is found, is the correct "
     "outcome here, not a sign that you did too little."),
    (10, "Stopping after one opening is the correct outcome here, not a sign that you did too "
         "little.",
     "Stopping after one opening, when that listing meets the condition, is the correct outcome "
     "here, not a sign that you did too little."),
    (10, "is each listing's cheapest option, so it bounds a price from below",
     "is each listing's cheapest option that can be bought, so it bounds a price from below"),
    (10, "and only listings at or below it will count.", "and only listings below it will count."),
    (11, "is shown as disabled or greyed out and cannot be chosen, so it has no price you can use.",
     "is shown as disabled or greyed out and cannot be chosen from the menu, so it has no price "
     "you can use."),
)


def as_sent_by(text: str | None, version: int | None) -> str | None:
    """The text as box `version` sent it: today's words with every rewording made after that
    version swapped back, the latest first (REWORDED). A record with no version is taken to
    be from before all of them; a text from the current version comes back unchanged."""
    if text is None:
        return None
    for since, before, after in reversed(REWORDED):
        if since > (version or 0):
            text = text.replace(after, before)
    return text


# The results page the question sends the agent to: the first URL in it.
URL = re.compile(r"https?://\S+")

# Why a question went to the agent unchanged. The one reason there is: the rules found no
# shape and no sign that the question is about the shop (`form.shopping_signal`).
BYPASS_REASON = "no shopping shape recognised"

# The account of the market the box puts in front of every plan. It lives beside the
# primitives that follow it, and keeps this name because the suite and the tests call it.
preamble = primitives.preamble


@dataclasses.dataclass(frozen=True)
class Parse:
    """Who read the question for a decision, and what each reader made of it (box v13, 22
    October 2026). Under the rules, the default, there is one reader and nothing else to
    say. Under the model, the rules' form of the question as decided and the model's beside
    it, the form as the model wrote it and each change normalisation made, the reply itself,
    so a replay can decide again without a call, and which of the two forms the decision
    used, with the reason when it was the rules'."""
    parser: str = "rules"
    used: str = "rules"
    fallback_reason: str | None = None   # why the model's form was not used
    prompt_version: int | None = None    # the prompt sent, None when none was
    rules_form: form_module.Form | None = None
    model_form: form_module.Form | None = None   # normalised, under the reading decided
    model_raw: form_module.Form | None = None    # as the model wrote it
    changes: tuple[str, ...] = ()
    reply: str | None = None

    def record(self) -> dict:
        def form(value: form_module.Form | None) -> dict | None:
            return value.record() if value is not None else None
        return {"parser": self.parser, "used": self.used, "fallback_reason": self.fallback_reason,
                "prompt_version": self.prompt_version,
                "normalise_version": normalise.VERSION if self.parser == "model" else None,
                "rules_form": form(self.rules_form), "model_form": form(self.model_form),
                "model_raw": form(self.model_raw), "changes": list(self.changes),
                "reply": self.reply}


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
    reading_by: str | None = None   # who chose the reading: "user" by a reply, "box" when the other reading was refused
    exhaust: bool = False       # decided for the arm without the stop rule, `--box-exhaust`
    parse: Parse | None = None  # who read the question, see `Parse`; None is the rules alone

    def record(self) -> dict:
        return {"box_version": VERSION, "form_version": form_module.VERSION,
                "primitives_version": primitives.VERSION,
                "kind": self.kind, "page": self.page.record() if self.page else None,
                "asked": self.ask is not None, "ask": self.ask.text if self.ask else None,
                "reading": self.reading, "reading_by": self.reading_by, "query": self.query,
                "form": self.form.record() if self.form else None, "refuse": self.refuse,
                "bypassed": self.bypass, "bypass_reason": BYPASS_REASON if self.bypass else None,
                "fallback": bool(self.form and self.form.fallback),
                "plan": self.plan.record() if self.plan else None,
                "exhaust": self.exhaust,
                "parse": (self.parse or Parse()).record()}


def results_url(question: str, required: bool = True) -> str | None:
    """The first URL in the question. None when there is none and none is required, as
    for a question that may turn out to be about something other than the shop."""
    found = URL.search(question)
    if not found:
        if required:
            raise ValueError("the question names no results page to read")
        return None
    return found.group(0).rstrip(".,;:)")


def decide(question: str, page: page_module.Page | None, reply: str | None = None,
           exhaust: bool = False, parser: str = "rules", call=None) -> Decision:
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
    the shop does not show cannot be answered whatever reading or limit the user would
    give, so it is refused before the user is asked anything, and no turn of theirs is
    spent on it. The form read without a reading carries no availability filter, so the
    one refusal that depends on the reading (the price of a sold-out size) is never raised
    here, and such a question is still asked. The one ask the form raises on its own is
    for a price limit.

    A reading property 5 refuses is no reading at all, so when one of the two is refused
    the question is read the other way without asking, and the record says the box chose
    it (`reading_by` "box"; "user" when a reply did). "Which seller has the best price for
    size M?" has a price only for a size that can be sold, so it is read as buyable rather
    than asked and then refused after the reply (verifier finding, 20 October 2026). When
    both readings can be answered, as for "does every listing offer size M", the box asks.
    The box decides whether it would ask before it looks at any reply, so a reply given to
    a question it does not put, the scripted user's `--reading` included, is ignored, as a
    reply to a clear question is.

    With `exhaust` (20 October 2026) everything above is decided the same way, and a plan
    is composed without its stop rule: every listing on the page is opened before the
    answer (`primitives.exhaust_swaps`). The decision says which, whatever its outcome.

    With `parser` "model" (box v13, 22 October 2026) a model reads the question, through
    `call(prompt) -> str`, and the rules still verify, plan, stop and check: see
    `decide_by_model`. The rules, the default, decide as every box before v13 did.
    """
    if parser == "rules":
        return decide_by_rules(question, page, reply, exhaust)
    if parser != "model":
        raise ValueError(f"parser {parser!r} is not one of {PARSERS}")
    return decide_by_model(question, page, reply, exhaust, call)


def decide_by_rules(question: str, page: page_module.Page | None, reply: str | None = None,
                    exhaust: bool = False) -> Decision:
    """`decide` with the rules reading the question. The body is box v12's own, unchanged,
    so every text the rules render is the same bytes; `tests/test_box.py` pins them."""
    asked = ambiguity.ask(question)
    reading_by = None
    if asked is not None:
        form = form_module.from_rules(question, page)
        missing = form_module.not_shown(form, page) if page is not None else []
        if form.quantifier != "unknown" and missing:
            return Decision(question=question, kind=None, ask=None, reading=None, query=None,
                            plan=None, page=page, form=form, refuse=form_module.refusal(missing),
                            exhaust=exhaust)
        answerable = [key for key in asked.readings if not form_module.not_shown(
            form_module.from_rules(ambiguity.with_reading(question, asked, key), page), page)]
        if page is not None and len(answerable) == 1 and len(asked.readings) == 2:
            reply, reading_by = answerable[0], "box"
        elif reply is None:
            return Decision(question=question, kind=None, ask=asked, reading=None, query=None,
                            plan=None, page=page, exhaust=exhaust)
    reading = None
    if asked is not None:
        if reply not in asked.readings:
            raise ValueError(f"reply {reply!r} is not one of the readings offered: "
                             f"{sorted(asked.readings)}")
        question = ambiguity.with_reading(question, asked, reply)
        reading, reading_by = reply, reading_by or "user"
    # The ask recorded is the one put to the user; a reading the box chose was never asked.
    asked = None if reading_by == "box" else asked
    form = form_module.from_rules(question, page)
    if form.quantifier == "unknown":
        return Decision(question=question, kind=None, ask=asked, reading=reading,
                        query=question, plan=None, page=page, form=form, bypass=True,
                        reading_by=reading_by, exhaust=exhaust)
    if page is None:
        raise ValueError("the question names no results page to read")
    missing = form_module.not_shown(form, page)
    if missing:
        return Decision(question=question, kind=None, ask=asked, reading=reading, query=None,
                        plan=None, page=page, form=form, refuse=form_module.refusal(missing),
                        reading_by=reading_by, exhaust=exhaust)
    if "price limit" in form.unknowns:
        return Decision(question=question, kind=None,
                        ask=ambiguity.threshold_ask(form.evidence["unknowns"]),
                        reading=reading, query=None, plan=None, page=page, form=form,
                        reading_by=reading_by, exhaust=exhaust)
    problems = form_module.verify(form, page)
    if problems:
        # The refusal `planner.planned_query` makes, for the same reason: paying a model to
        # execute a plan already known to be unsound buys nothing.
        raise ValueError("refusing to execute an unsound plan: " + "; ".join(problems))
    plan = primitives.compose(form, page, exhaust=exhaust)
    return Decision(question=question, kind=form.kind(), ask=asked, reading=reading,
                    query=f"{question}\n\n{plan.text}", plan=plan, page=page, form=form,
                    reading_by=reading_by, exhaust=exhaust)


def decide_by_model(question: str, page: page_module.Page | None, reply: str | None,
                    exhaust: bool, call) -> Decision:
    """`decide` with a model reading the question and the rules doing the rest (box v13,
    22 October 2026).

    Before any call, a question the rules bypass, or one that names no page, is decided by
    the rules alone, with no call, since there is no page to plan from; the record says so.
    Then one call (`normalise.read`): the reply parsed, normalised to the page's own words
    and checked. When the call fails, the reply is not a form or the form fails a check,
    the rules decide, and the record keeps the model's form and the reason. A model's reading
    of the question never refuses it: a form that needs what the shop does not show fails a
    check, and the rules' form decides whether the question is refused. The one refusal made
    on a model's form is the one a reading brings, below.

    With the model's form the box asks as the rules do, in their order. The shop's own
    ambiguity, a size listed or buyable, is asked with the "offer" template when the lexicon
    finds it (`ambiguity.ask`), or the model flags it and the question does not settle it in
    the lexicon's words, and is answered as the rules' is: by the reply, or by the box when
    the shop cannot answer one reading. The reading is applied to the model's form in code
    (`normalise.with_reading`), so a reply costs no second call, and the refusal that
    depends on it, the price of a sold-out size, is the rules' own. Then any other word the
    model reads two ways is asked about with a template quoting its readings, and a missing
    price limit with the threshold ask; neither offers a reading a scripted reply could
    choose, so either ends the run as asked. Last, the form under its reading is held to the
    five properties and the plan's checks again (`normalise.plan_problems`), and the rules
    decide if it fails.
    """
    if call is None:
        raise ValueError("the model parser needs a call to send its prompt through")
    if page is None or form_module.from_rules(question, page).quantifier == "unknown":
        decision = decide_by_rules(question, page, reply, exhaust)
        why = ("the question names no results page, so the box has nothing to plan from and "
               "the model was not called" if page is None
               else "the rules found no shopping question, so the model was not called")
        return dataclasses.replace(decision, parse=Parse(
            parser="model", used="rules", fallback_reason=why,
            rules_form=form_module.from_rules(decision.question, page)))
    read = normalise.read(question, page, call)
    asked_question, asked_reply = question, reply
    changes = list(read.changes)

    def by_rules(reason: str, model_form: form_module.Form | None) -> Decision:
        decision = decide_by_rules(asked_question, page, asked_reply, exhaust)
        return dataclasses.replace(decision, parse=Parse(
            parser="model", used="rules", fallback_reason=reason,
            prompt_version=form_module.PROMPT_VERSION,
            rules_form=form_module.from_rules(decision.question, page), model_form=model_form,
            model_raw=read.raw, changes=tuple(changes), reply=read.reply))

    def decided(model_form: form_module.Form, **fields) -> Decision:
        decision = Decision(page=page, exhaust=exhaust, **fields)
        return dataclasses.replace(decision, parse=Parse(
            parser="model", used="model", prompt_version=form_module.PROMPT_VERSION,
            rules_form=form_module.from_rules(decision.question, page), model_form=model_form,
            model_raw=read.raw, changes=tuple(changes), reply=read.reply))

    if read.failure is not None:
        return by_rules(read.failure, read.form)
    form = read.form
    asked = ambiguity.ask(question)
    flagged = normalise.availability_ambiguity(form)
    if asked is None and flagged is not None:
        settled = ambiguity.CLEAR.search(question)
        if settled is not None:
            line = (f"ambiguity {flagged.word!r} dropped: the question settles it, "
                    f"{settled.group(0)!r}")
            evidence = dict(form.evidence)
            normalise.note(evidence, "ambiguities", line)
            form = dataclasses.replace(normalise.without_availability(form), evidence=evidence)
            changes.append(line)
        else:
            asked = ambiguity.availability_ask(flagged.word)
    reading_by = None
    if asked is not None:
        answerable = [key for key in asked.readings
                      if not form_module.not_shown(normalise.with_reading(form, key), page)]
        if len(answerable) == 1 and len(asked.readings) == 2:
            reply, reading_by = answerable[0], "box"
        elif reply is None:
            return decided(form, question=question, kind=None, ask=asked, reading=None,
                           query=None, plan=None)
    reading = None
    if asked is not None:
        if reply not in asked.readings:
            raise ValueError(f"reply {reply!r} is not one of the readings offered: "
                             f"{sorted(asked.readings)}")
        question = ambiguity.with_reading(question, asked, reply)
        form = normalise.with_reading(form, reply)
        reading, reading_by = reply, reading_by or "user"
    asked = None if reading_by == "box" else asked
    closed = dict(question=question, kind=None, reading=reading, query=None, plan=None,
                  form=form, reading_by=reading_by)
    missing = form_module.not_shown(form, page)
    if missing:
        return decided(form, ask=asked, refuse=form_module.refusal(missing), **closed)
    other = [entry for entry in form.ambiguities if not normalise.reads_availability(entry)]
    if other:
        return decided(form, ask=ambiguity.generic_ask(other[0].word, other[0].readings), **closed)
    if "price limit" in form.unknowns:
        return decided(form, ask=ambiguity.threshold_ask(form.evidence["unknowns"]), **closed)
    found = normalise.plan_problems(form, page)
    if found:
        return by_rules("; ".join(dict.fromkeys(found)), form)
    # A sound form can still have no text under the arm without its stop rule: a review
    # question turns pages, and `primitives.compose` refuses it there. That is the model's
    # form failing too, so the rules decide, and refuse it the same way if they read it so.
    try:
        plan = primitives.compose(form, page, exhaust=exhaust)
    except ValueError as fault:
        return by_rules(f"no plan can be composed from it: {fault}", form)
    return decided(form, question=question, kind=form.kind(), ask=asked, reading=reading,
                   query=f"{question}\n\n{plan.text}", plan=plan, form=form,
                   reading_by=reading_by)


def stated_figures(decision: Decision) -> set[int]:
    """The figures the question itself states, in cents, so an answer that quotes a limit
    back is not refused for inventing it: the decimals written in the question, and every
    price limit the form parsed from it, written as the plan text writes it.

    A question that says "under $20" writes no decimal, so `sufficiency.prices_in` read
    nothing from it, while the witness text put "$20.00" in front of the agent and an
    answer echoing that was refused as unsupported (verifier finding, 14 October 2026).
    The form's limit is the same figure however the question wrote it. A limit parsed by
    the rules is a float; one a model proposed is whatever its JSON held, and only a number
    is read. Strict or not, "under $27" or "at most $27" (form v9), the plan writes the
    figure as "$27.00", so the operator is not read here and both are exempted.
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
