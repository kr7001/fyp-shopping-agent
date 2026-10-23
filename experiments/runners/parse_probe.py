#!/usr/bin/env python3
"""Parse every census question with the model, and compare each form with the rules' form.

Box v2 has two parsers (`box/form.py`): written rules, which are free and deterministic,
and a model, which generalises further and varies. The design measures the second against
the first before either is trusted past the forms the rules know: the agreement rate, the
forms that fail verification, and the questions where the model is right and the rules
are not, which are the ones that extend the rules next.

This runs that comparison with no browser and therefore almost no money: one call per
question, text only. The cost of every call is the provider's own figure for that call,
and the account's usage is read before and after as the check on their sum (LESSONS 6).
The rules get the results page a question names, fetched once per URL as the suite does
for the box, so they can see the sellers a question names. A call that fails is recorded
on its row and the probe goes on, with no retry, and the result file is written whatever
stops the loop, so what was paid for is on disk (verifier findings, 14 October 2026).

With `--questions FILE` it probes a paraphrase file instead (20 October 2026): questions
reworded by someone who had not read the rules, each held against the rules' form of the
question it rewords, its template. The census asks whether the model agrees with the rules
on the questions the rules were written on; this asks which of the two still finds the
template's form when the words change. The rules read the results page as the box read it
in the stored batch the file names, so no shop is needed, and that half is free: the dry
run prints it, with what `box.decide` does with each question, the number of calls and an
estimate from the census's charge per call.

Since 22 October 2026 both modes measure what the box would use (box v13): the model's
reply to the current prompt (`form.PROMPT_VERSION`), normalised to the page's own words
(`normalise.normalise`), is the model's form, held to the box's own gate
(`normalise.problems`) for its problems. The form as the model wrote it is kept beside it,
with its tiers and each change, so what normalisation did can be read off every row. A
paraphrase row also says what `box.decide` does with the question under the model parser,
from the same reply, with no second call. A result file says which prompt and which
normalisation made it.

    python experiments/runners/parse_probe.py --dry-run     # prints the prompts, calls nothing
    python experiments/runners/parse_probe.py               # paid: one call per question
    python experiments/runners/parse_probe.py --questions experiments/tasks/paraphrases_v1.json --dry-run
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import box
import form
import normalise
import page as page_module
import plan_probe  # the key, the model name and the account usage, read the same way
import provider_routing  # the routing the agent's calls get, off unless IGR_PROVIDER_ROUTING is set
import planner
import primitives
import targeting

RESULTS = paths.RESULTS
ENDPOINT = plan_probe.ENDPOINT

# The results page each question names, fetched once per URL and shared by every question
# that names it, as `suite.PAGES` does for the box.
PAGES: dict[str, page_module.Page | None] = {}


def census() -> list[tuple[str, str]]:
    """Every question in the project's task files, with the file each came from."""
    return planner.questions()


def results_page(question: str) -> page_module.Page | None:
    """The results page the question sends the agent to, as the box reads it, or None when
    the question names none. A page the shop cannot serve is None too, with a warning, so
    the rules parse without its sellers rather than the probe stopping."""
    urls = [url.rstrip(".,;:)") for url in form.URL.findall(question)]
    url = next((url for url in urls if form.RESULTS_URL.search(url)), None)
    if url is None:
        return None
    if url not in PAGES:
        try:
            PAGES[url] = page_module.fetch(url)
        except (OSError, ValueError) as fault:
            print(f"warning: {url} could not be read, parsing without it: {fault}",
                  file=sys.stderr)
            PAGES[url] = None
    return PAGES[url]


def repository_commit() -> str:
    """Which code made the probe, for its result file. "unknown", with a warning, when git
    cannot say: that never stops a probe."""
    try:
        return subprocess.run(["git", "-C", str(paths.REPO), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as fault:
        print(f"warning: the repository commit could not be read, recording it as unknown: "
              f"{fault}", file=sys.stderr)
        return "unknown"


class UnexpectedReply(Exception):
    """A reply the provider served as a success whose body is not a chat completion: no
    `choices`, or no message content in the first. The provider may still have charged
    for it, so the charge comes with it when the body says one, and the row keeps it, and
    so do its tokens (`tokens_of`) since 23 October 2026. Until 14 October 2026 the
    KeyError stopped the loop and lost the row (verifier finding)."""

    def __init__(self, why: str, cost: float | None, tokens: dict | None = None,
                 served: str | None = None):
        super().__init__(why)
        self.cost = cost
        self.tokens = tokens
        self.served = served


def tokens_of(usage) -> dict | None:
    """The call's prompt and completion tokens as the provider counted them in its `usage`,
    or None when it gives either as no whole number (23 October 2026, so a run under the
    model parser can count its parse's tokens with the agent's)."""
    if not isinstance(usage, dict):
        return None
    prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in (prompt, completion)):
        return None
    return {"prompt": prompt, "completion": completion}


def call_model(key: str, model: str, prompt: str) -> tuple[str, float | None, dict | None, str | None]:
    """One call: its reply, what the provider charged for it, or None when it did not say,
    its tokens (`tokens_of`), or None when it did not count them, and the provider OpenRouter
    served it from, or None when the reply does not say. A 200 with a body that is not JSON
    raises requests' own `JSONDecodeError`, a request failure; a JSON body without the
    completion raises `UnexpectedReply`. The model's routing, when IGR_PROVIDER_ROUTING sets
    one, goes in the body as OpenRouter's "provider" object (`provider_routing`)."""
    body = {"model": model, "temperature": 0, "usage": {"include": True},
            "messages": [{"role": "user", "content": prompt}]}
    routing = provider_routing.routing_for(model)
    if routing is not None:
        body["provider"] = routing
    reply = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=body,
        timeout=120,
    )
    reply.raise_for_status()
    payload = reply.json()
    usage = payload.get("usage") if isinstance(payload, dict) else None
    cost = usage.get("cost") if isinstance(usage, dict) else None
    cost = float(cost) if cost is not None else None
    tokens = tokens_of(usage)
    served = payload.get("provider") if isinstance(payload, dict) else None
    served = served if isinstance(served, str) else None
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as fault:
        raise UnexpectedReply(f"the reply holds no choices[0].message.content "
                              f"({type(fault).__name__}: {fault}): {str(payload)[:200]!r}", cost, tokens,
                              served)
    # As text, the way `form.parse_reply` reads it (23 October 2026): a null content is
    # nothing and a list of parts its text parts. Content of any other type is a reply that
    # is no completion, with its charge and tokens kept, never a TypeError later.
    try:
        text = form.reply_text(content)
    except ValueError as fault:
        raise UnexpectedReply(f"the reply's content is not text: {fault}", cost, tokens, served)
    return text, cost, tokens, served


def summary(record: dict) -> str:
    """One line for a form's record: what it retrieves, over what, under which conditions."""
    filters = ", ".join(f"{f['attribute']} {f['op']} {f['value']}" for f in record["filters"]) or "none"
    k = f" k={record['k']}" if record["k"] else ""
    return f"{record['quantifier']} {record['objective']} over {record['population']}{k}, filters: {filters}"


def comparable(value):
    """A filter value as `agree` compares it: a number as a number, so the rules' 20.0 and
    a model's 20 are the same limit, a name as itself, and the values of an `in` filter as
    a set, so `seller in (A, B)` is `(B, A)` (verifier finding, 14 October 2026)."""
    if isinstance(value, tuple):
        return frozenset(comparable(v) for v in value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return str(value).strip()


def agree(rules: form.Form, model: form.Form) -> bool:
    """The same retrieval: quantifier, objective, population and k, and the same condition
    on every attribute the rules derived from the question's words.

    A rules filter is compared when its attribute has an entry in the rules' evidence,
    which `form.from_rules` writes for every filter the words chose. The one it writes no
    entry for is the silent default, availability = buyable on a witness or top-k question
    with no availability word. A model form that leaves that out is not disagreeing about
    the question, so the default is compared only when the model states the attribute,
    and then it has to say the same. Until 14 October 2026 the default was compared like
    the rest, and 20 and 20.0 were different limits (verifier finding). A model filter on
    an attribute the rules never derived stays a difference, as it was: the stored census
    parse has five such rows, a brand as a title filter among them, and they are what the
    DIFF lines are printed for, to be read by hand.
    """
    # The negation is part of the quantifier since comparison v2 (22 October 2026): "is
    # there a listing without M" is not "does every listing have M" (verifier finding).
    if (rules.quantifier, rules.negated, rules.objective, rules.population, rules.k) != \
            (model.quantifier, model.negated, model.objective, model.population, model.k):
        return False
    stated = {(f.attribute, f.op): comparable(f.value) for f in model.filters}
    for condition in rules.filters:
        key = (condition.attribute, condition.op)
        derived = f"filter:{condition.attribute}" in rules.evidence
        if (derived or key in stated) and stated.pop(key, None) != comparable(condition.value):
            return False
    return not stated


def propose(question: str, model: str, key: str, page: page_module.Page | None = None) -> dict:
    """The model's form of one question, as the box would use it, with everything that
    made it: the form as the model wrote it (`raw`), the form normalised to the page's own
    words (`form`) and each change, the reply's text, the error when there is no form,
    whether the call itself failed, and what it was charged. A request that fails, an HTTP
    error, a timeout or a body that is not JSON, is a failed call with no cost rather than
    the end of the probe, and a success whose body holds no completion is one too, with
    whatever it was charged. No retry, so the figure stays one call per question. Taken out
    of `probe_one` on 20 October 2026 so the paraphrase probe fails the same way; since 22
    October 2026 the form is normalised as the box normalises it (box v13)."""
    charged: list[float | None] = []
    replies: list[str] = []
    providers: list[str | None] = []      # the provider each call was served from

    def call(prompt: str) -> str:
        text, cost, _, served = call_model(key, model, prompt)     # the probe keeps the charge
        providers.append(served)
        charged.append(cost)
        replies.append(text)
        return text

    raw, error, failed = None, None, False
    try:
        raw = form.from_model(question, page, call)
    # Request failures before ValueError: requests' `JSONDecodeError`, raised for a 200
    # whose body is not JSON, is both, and until 14 October 2026 the ValueError handler
    # took it as a model problem, so `calls_failed` undercounted (verifier finding).
    except requests.exceptions.RequestException as fault:
        error, failed = f"request failed: {fault}", True
    except UnexpectedReply as fault:
        error, failed = f"reply not a completion: {fault}", True
        charged.append(fault.cost)
        providers.append(fault.served)
    except ValueError as fault:         # a reply that is not a form in the vocabulary
        error = str(fault)
    normalised, changes = normalise.normalise(raw, question, page) if raw is not None else (None, [])
    return {"raw": raw, "form": normalised, "changes": changes,
            "reply": replies[0] if replies else None, "error": error, "failed": failed,
            "cost": charged[0] if charged else None, "provider": providers[0] if providers else None}


def model_fields(got: dict, question: str, page: page_module.Page | None) -> dict:
    """A row's model fields from `propose`: the form the box would use, the form as the
    model wrote it and each change between them, and the problems that would stop the box
    using it, its own gate (`normalise.problems`), or the error when there is no form."""
    proposed = got["form"]
    return {"model": proposed.record() if proposed else None,
            "model_raw": got["raw"].record() if got["raw"] is not None else None,
            "normalised": list(got["changes"]),
            "model_problems": (normalise.problems(proposed, question, page) if proposed
                               else [] if got["failed"] else [got["error"]]),
            "error": got["error"], "call_failed": got["failed"], "cost_usd": got["cost"],
            # The provider OpenRouter served the call from (23 October 2026).
            "provider": got["provider"]}


def probe_one(name: str, question: str, model: str, key: str) -> dict:
    """One question: the rules' form on the page it names, the model's form as the box
    would use it, whether the two agree, and what the call cost, a failed call recorded on
    the row (`propose`)."""
    page = results_page(question)
    rules = form.from_rules(question, page)
    got = propose(question, model, key, page)
    return {"file": name, "question": question,
            "rules": rules.record(), "rules_problems": form.verify(rules, page),
            **model_fields(got, question, page),
            "agree": got["form"] is not None and agree(rules, got["form"])}


def print_row(row: dict) -> None:
    cost = f"${row['cost_usd']:.5f}" if row["cost_usd"] is not None else "cost unknown"
    print(f"{'same' if row['agree'] else 'DIFF'} {row['file']:20} "
          f"{row['question'].split('. ', 1)[-1][:70]}")
    print(f"     rules: {summary(row['rules'])}")
    print(f"            {'; '.join(row['rules_problems']) or 'sound'}")
    print(f"     model: {summary(row['model']) if row['model'] else 'no form: ' + str(row['error'])}")
    print(f"            {'; '.join(row['model_problems']) or 'sound'}")
    print(f"     {cost}")


def report(rows: list[dict], model: str, key: str, before: float | None) -> pathlib.Path:
    """The summary lines and the result file, for however many questions ran."""
    after = plan_probe.usage(key)
    spent = round(after - before, 4) if (before is not None and after is not None) else None
    charged_total = sum(r["cost_usd"] for r in rows if r["cost_usd"] is not None)
    failed = sum(1 for r in rows if r["call_failed"])
    print(f"\nagree on {sum(r['agree'] for r in rows)} of {len(rows)} questions")
    print(f"model forms failing verification: "
          f"{sum(1 for r in rows if r['model_problems'])} of {len(rows)}")
    print(f"charged per call, summed: ${charged_total:.5f}")
    print(f"account delta: {('$%.4f' % spent) if spent is not None else 'unknown'}")
    print(f"calls failed: {failed} of {len(rows)}")

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out = RESULTS / f"parse-probe-{stamp}.json"
    out.write_text(json.dumps({"ran_at": stamp, "model": model, "temperature": 0,
                               # The routing every call carried, None when off (23 October 2026).
                               "provider_routing": provider_routing.routing_for(model),
                               "form_version": form.VERSION,
                               "prompt_version": form.PROMPT_VERSION,
                               "normalise_version": normalise.VERSION,
                               "commit": repository_commit(),
                               "spend_usd": spent, "charged_usd": charged_total,
                               "calls_failed": failed, "rows": rows}, indent=2) + "\n")
    print(f"written: {out}")
    return out


# ---------------------------------------------------------------------------
# Reworded questions, `--questions FILE` (20 October 2026)

# Bumped when the comparison of a reworded question with its template changes: what the
# expected form is, the tiers, or the words for the box's outcome. Result files made under
# different versions are not pooled.
#
#   1  20 October 2026. The expected form is the rules' form of the template on the stored
#      page, read in the census table's four tiers, and the outcome in the task files' words
#   2  22 October 2026, the verifier's audit. The negation is compared with the quantifier,
#      in every tier and in `agree`: a negated universal reaches no tier against a form that
#      is not negated. A file made under 1 holds no negated form, so its tiers are the same
#      read again under 2 (`paraphrase_scores.scores` checks that before it reads one)
COMPARISON_VERSION = 2
# Comparisons a file may have been made under and still be read today, each because no
# figure changes for a file made under it: its stored tiers are re-derived under today's
# comparison and must all agree.
READ_AGAIN = (1,)

# Paraphrase files the model parser was tuned on, and what was tuned on each. A probe of one
# is in sample whatever the version, and says so with every figure (LESSONS 19).
IN_SAMPLE = {"paraphrases_v1.json": "prompt version 2 and normalisation versions 1 and 2 were "
                                    "written from this file's model failures, on 22 October 2026"}

# The census whose charge per call prices a probe of other questions: one call each, text
# only, and the same prompt but for the question and the op "<", which form v9 added to the
# schema's list.
CENSUS = "parse-probe-20261014T112047.json"

# How far a form agrees with the expected one. Each tier includes those before it, as the
# census table in docs/content/today.md was read: the quantifier picks the primitive, the
# objective is what it compares, the population what it ranges over, and every field is
# `agree`, which adds k and the filters. tests/test_probe.py reproduces that table from the
# stored census with these.
TIERS = {"quantifier": "same quantifier",
         "objective": "same quantifier and objective",
         "population": "same on those and the population",
         "every field": "same on every field"}

# What the box can do with a question, in the words of the task files' "box" field, and
# "error" for a plan `box.decide` refuses to compose because it is unsound.
OUTCOMES = ("plan", "fallback", "ask", "refuse", "bypass", "error")


def tiers(expected: form.Form, got: form.Form | None) -> dict[str, bool]:
    """Which tiers `got` reaches against `expected`. No form reaches none."""
    if got is None:
        return dict.fromkeys(TIERS, False)
    quantifier = (got.quantifier, got.negated) == (expected.quantifier, expected.negated)
    objective = quantifier and got.objective == expected.objective
    population = objective and got.population == expected.population
    return {"quantifier": quantifier, "objective": objective, "population": population,
            "every field": population and agree(expected, got)}


def load_questions(path: pathlib.Path) -> tuple[dict, list[dict]]:
    """The paraphrase file, and each entry with the question as the box gets it, the file's
    lead, a space and the text, as the audit put them, and its template's question. Of the
    task file the templates come from only each task's id and query are read, never an
    answer. A template the task file does not hold, or one that does not start with the
    lead, is refused: the question would be compared with nothing, or in another frame."""
    spec = json.loads(path.read_text())
    tasks = json.loads((paths.TASKS / spec["templates"]).read_text())["tasks"]
    templates = {task["id"]: task["query"].format(base=spec["base_url"]) for task in tasks}
    lead = spec["lead"].format(base=spec["base_url"])
    entries = []
    for entry in spec["paraphrases"]:
        template = templates.get(entry["template"])
        if template is None:
            raise ValueError(f"paraphrase {entry['id']} rewords {entry['template']!r}, which "
                             f"{spec['templates']} does not hold")
        if not template.startswith(f"{lead} "):
            raise ValueError(f"paraphrase {entry['id']}: its template {entry['template']} does "
                             f"not start with the lead {lead!r}")
        entries.append({**entry, "question": f"{lead} {entry['text']}",
                        "template_question": template})
    return spec, entries


def stored_page(suite: pathlib.Path) -> page_module.Page:
    """The results page as the box read it in a stored batch, from the `box.page` record of
    its suite.json. Every row must hold the same one, so the page is the batch's and not
    one row's."""
    rows = json.loads(suite.read_text())["rows"]
    records = {json.dumps(row["box"]["page"], sort_keys=True) for row in rows
               if row.get("box") and row["box"].get("page")}
    if len(records) != 1:
        raise ValueError(f"{suite} holds {len(records)} different page records, not one")
    return page_module.from_record(json.loads(records.pop()))


def outcome(question: str, page: page_module.Page, reply: str | None = None) -> dict:
    """What `box.decide` does with the question, with no reply, in the words of the task
    files' "box" field: plan, ask, refuse, fallback or bypass, and the kind planned. For an
    ask, the kind is the one planned once the menu reading answers it, as
    tests/test_apparel_v2.py reads it, and None for the ask for a price limit, which no
    reading answers. A plan `decide` refuses to compose, by raising, is "error".

    With `reply`, a model's reply already paid for, the box decides under the model parser
    with that reply as its call, so no second call is made (22 October 2026), and the
    outcome says whose form it used and why the rules' when it was. An ask that offers no
    reading is "unlisted" when the form names a seller or listing the page does not list,
    "other" when the form holds a word the model reads two ways other than the shop's own,
    and "price limit" otherwise, the order in which the box asks them."""
    parsed = {} if reply is None else {"parser": "model", "call": lambda prompt: reply}
    try:
        decision = box.decide(question, page, **parsed)
    except ValueError as fault:
        return {"outcome": "error", "kind": None, "ask": None, "reading_by": None,
                "detail": str(fault)}
    found = {"outcome": "plan", "kind": decision.kind, "ask": None,
             "reading_by": decision.reading_by, "detail": None}
    if decision.bypass:
        found.update(outcome="bypass", detail=box.BYPASS_REASON)
    elif decision.refuse:
        found.update(outcome="refuse", detail=decision.refuse)
    elif decision.query is None:
        # The box asks about a seller or listing the page does not list, then about another
        # word, then for a price limit, in that order (`box.decide`, box v14).
        unlisted = decision.form is not None and bool(box.unlisted(decision.form, decision.question, page))
        other = decision.form is not None and any(
            not normalise.reads_availability(entry) for entry in decision.form.ambiguities)
        found.update(outcome="ask", detail=decision.ask.text,
                     ask="reading" if decision.ask.readings else "unlisted" if unlisted
                     else "other" if other else "price limit")
        if decision.ask.readings:
            try:
                found["kind"] = box.decide(question, page, reply="menu", **parsed).kind
            except ValueError as fault:
                found["detail"] += f" Read as the menu, it is refused: {fault}"
    elif decision.form.fallback:
        found["outcome"] = "fallback"
    if reply is not None:
        # A refusal on the model's own form, the one failure an attribute the shop does not
        # show (box v15), is said to be the model's: `parsed_by` alone would not tell it from
        # the model's reading planned.
        found.update(parsed_by=decision.parse.used, fallback_reason=decision.parse.fallback_reason,
                     declined=decision.parse.declined)
    return found


def same_outcome(a: dict, b: dict) -> bool:
    """The same outcome, kind and ask, as the task files' "box" field would record them."""
    return (a["outcome"], a["kind"], a["ask"]) == (b["outcome"], b["kind"], b["ask"])


def meets_audit(expected: str, found: dict) -> bool:
    """Whether the outcome is the one the audit expected, by the audit's own rule: "ASK" is
    met by any ask, "REFUSE" by a refusal and "BYPASS" by a bypass, and any other word is
    the kind a plan must have, the fallback's included."""
    words = {"ASK": "ask", "REFUSE": "refuse", "BYPASS": "bypass"}
    if expected in words:
        return found["outcome"] == words[expected]
    return found["outcome"] in ("plan", "fallback") and found["kind"] == expected


def outcome_words(found: dict) -> str:
    """An outcome in a few words, for the printed rows."""
    if found["outcome"] == "ask":
        if found["ask"] == "other":
            return "ask about another reading the model found"
        if found["ask"] == "unlisted":
            return "ask about a seller or listing the page does not list"
        return ("ask for a price limit" if found["ask"] == "price limit"
                else f"ask for a reading, then {found['kind']}")
    if found["outcome"] in ("plan", "fallback"):
        chosen = ", the box chose the reading" if found["reading_by"] == "box" else ""
        return f"{found['outcome']} {found['kind']}{chosen}"
    if found.get("declined"):
        return "refuse, declined on the model's form"
    return found["outcome"]


def rules_half(entry: dict, page: page_module.Page) -> tuple[dict, form.Form]:
    """One paraphrase's free half: the expected form, the rules' form of the paraphrase and
    the tiers it reaches, and what the box does with the paraphrase and with its template.
    The expected form comes back too, for the model's half."""
    expected = form.from_rules(entry["template_question"], page)
    rules = form.from_rules(entry["question"], page)
    row = {"id": entry["id"], "template": entry["template"], "label": entry["label"],
           "audit_expected": entry["audit_expected"], "text": entry["text"],
           "question": entry["question"], "expected": expected.record(),
           "rules": rules.record(), "rules_problems": form.verify(rules, page),
           "rules_tiers": tiers(expected, rules),
           "box": outcome(entry["question"], page),
           "template_box": outcome(entry["template_question"], page)}
    return row, expected


def model_half(row: dict, expected: form.Form, page: page_module.Page, model: str,
               key: str) -> dict:
    """The row with the model's form added, one call: the form the box would use and the
    tiers it reaches, which are the figures, and beside them the form as the model wrote it
    with its own tiers and each change, and what `box.decide` does under the model parser
    with the same reply."""
    got = propose(row["question"], model, key, page)
    return {**row, **model_fields(got, row["question"], page),
            "model_tiers": tiers(expected, got["form"]),
            "model_raw_tiers": tiers(expected, got["raw"]),
            "model_box": (outcome(row["question"], page, reply=got["reply"])
                          if got["reply"] is not None else None)}


def reached(found: dict[str, bool]) -> str:
    met = [tier for tier in TIERS if found[tier]]
    return "agrees on " + (", ".join(met) if met else "nothing")


def print_paraphrase(row: dict) -> None:
    """One paraphrase: its words, the form expected, the rules' form and, once the model has
    been called, the model's, each with the tiers it reaches, and what the box does."""
    print(f"{row['id']:>2} {row['template']}, labelled {row['label'] or '-'}: {row['text']}")
    print(f"     expected: {summary(row['expected'])}")
    print(f"     rules:    {summary(row['rules'])}")
    print(f"               {reached(row['rules_tiers'])}; {'; '.join(row['rules_problems']) or 'sound'}")
    if "model_tiers" in row:
        print(f"     model:    {summary(row['model']) if row['model'] else 'no form: ' + str(row['error'])}")
        print(f"               {reached(row['model_tiers'])}; {'; '.join(row['model_problems']) or 'sound'}")
        print(f"               {'$%.5f' % row['cost_usd'] if row['cost_usd'] is not None else 'cost unknown'}")
        # What normalisation changed, and what the form as written reached (22 Oct 2026).
        for change in row.get("normalised") or []:
            print(f"               normalised: {change}")
        if row.get("normalised"):
            print(f"               as written: {summary(row['model_raw'])}; {reached(row['model_raw_tiers'])}")
    met = "met" if meets_audit(row["audit_expected"], row["box"]) else "not met"
    print(f"     box:      {outcome_words(row['box'])}; the template: "
          f"{outcome_words(row['template_box'])}; the audit expected {row['audit_expected']}, {met}")
    if row.get("model_box"):
        found = row["model_box"]
        why = f", since {found['fallback_reason']}" if found.get("fallback_reason") else ""
        whose = {"rules": "the rules'", "model": "the model's"}[found["parsed_by"]]
        print(f"     model box: {outcome_words(found)}, by {whose} form{why}")


def question_totals(rows: list[dict], with_model: bool) -> dict:
    """Every count the summary prints and the result file keeps, from the rows, so the two
    cannot differ."""
    def count(test) -> int:
        return sum(1 for row in rows if test(row))

    totals = {"paraphrases": len(rows),
              "rules": {tier: count(lambda r: r["rules_tiers"][tier]) for tier in TIERS}}
    if with_model:
        totals["model"] = {tier: count(lambda r: r["model_tiers"][tier]) for tier in TIERS}
        totals["model_only"] = {tier: count(lambda r: r["model_tiers"][tier] and not r["rules_tiers"][tier])
                                for tier in TIERS}
        totals["rules_only"] = {tier: count(lambda r: r["rules_tiers"][tier] and not r["model_tiers"][tier])
                                for tier in TIERS}
    totals["box"] = {name: count(lambda r: r["box"]["outcome"] == name) for name in OUTCOMES}
    if with_model:
        # Under the model parser, from each row's own reply (22 October 2026), and how
        # many of those decisions used the rules' form instead. Zero in a file written
        # before, whose rows have no model_box.
        totals["model_box"] = {name: count(lambda r: (r.get("model_box") or {}).get("outcome") == name)
                               for name in OUTCOMES}
        totals["model_box_by_rules"] = count(lambda r: (r.get("model_box") or {}).get("parsed_by") == "rules")
    totals["box_as_template"] = count(lambda r: same_outcome(r["box"], r["template_box"]))
    totals["box_as_audit_expected"] = count(lambda r: meets_audit(r["audit_expected"], r["box"]))
    for label in ("ambiguous", "clear"):
        totals[f"labelled_{label}"] = {
            "paraphrases": count(lambda r: r["label"] == label),
            "asked": count(lambda r: r["label"] == label and r["box"]["outcome"] == "ask")}
    return totals


def print_totals(totals: dict, with_model: bool) -> None:
    n = totals["paraphrases"]
    print(f"\nagainst the expected form, the rules' form of each template, {n} paraphrases:")
    if with_model:
        print(f"  {'':34} {'rules':>5} {'model':>5} {'model only':>10} {'rules only':>10}")
    for tier, name in TIERS.items():
        line = f"  {name:34} {totals['rules'][tier]:>5}"
        if with_model:
            line += (f" {totals['model'][tier]:>5} {totals['model_only'][tier]:>10} "
                     f"{totals['rules_only'][tier]:>10}")
        print(f"{line} of {n}")
    print(f"box.decide under the rules: "
          f"{', '.join(f'{name} {got}' for name, got in totals['box'].items())}")
    # Printed only for a file that has them, so a file written before 22 October 2026
    # prints what it always printed.
    if with_model and any((totals.get("model_box") or {}).values()):
        print(f"box.decide under the model parser: "
              f"{', '.join(f'{name} {got}' for name, got in totals['model_box'].items())}; "
              f"by the rules' form {totals['model_box_by_rules']}")
    print(f"  the same outcome and kind as its template's  {totals['box_as_template']} of {n}")
    print(f"  the outcome the audit expected               {totals['box_as_audit_expected']} of {n}")
    for label in ("ambiguous", "clear"):
        got = totals[f"labelled_{label}"]
        print(f"  labelled {label} by the verifier: {got['paraphrases']}, asked back on {got['asked']}")


def census_charge(path: pathlib.Path | None = None) -> tuple[float, int, str]:
    """What the census was charged in all, over how many charged calls, and to which model."""
    census = json.loads((path or paths.RESULTS / CENSUS).read_text())
    charged = [row["cost_usd"] for row in census["rows"] if row["cost_usd"] is not None]
    return sum(charged), len(charged), census["model"]


def prompt_scale(prompts: list[str], path: pathlib.Path | None = None) -> float:
    """How much longer these prompts are, on average, than the ones the census sent, which
    were prompt version 1's (22 October 2026: version 2's worked examples make it about five
    times as long, and the census's charge per call no longer prices a call)."""
    census = json.loads((path or paths.RESULTS / CENSUS).read_text())
    sent = [len(form.prompt(row["question"], version=1)) for row in census["rows"]]
    return (sum(map(len, prompts)) / len(prompts)) / (sum(sent) / len(sent))


def print_estimate(prompts: list[str], model: str) -> None:
    """The calls a probe of these prompts makes, and what they would cost: the census's
    charge per call, scaled by how much longer these prompts are (`prompt_scale`). The whole
    charge is scaled, the reply's share with the prompt's, so the figure is high rather than
    low: the reply does not grow with the prompt."""
    total, charged, census_model = census_charge()
    per_call = total / charged * prompt_scale(prompts)
    calls = len(prompts)
    print(f"{calls} calls to {model}, text only, no browser. Nothing was sent.")
    print(f"estimate: ${calls * per_call:.4f}, {calls} calls at ${per_call:.5f}, the census's charge "
          f"per call ({CENSUS}: ${total:.4f} for {charged} calls to {census_model}) times "
          f"{prompt_scale(prompts):.2f}, how much longer these prompts are than the census's")
    if model != census_model:
        print(f"warning: the census called {census_model}, so its charge does not price {model}")


def report_questions(rows: list[dict], path: pathlib.Path, spec: dict, page: page_module.Page,
                     model: str, key: str, before: float | None) -> pathlib.Path:
    """The summary and the result file of a paid paraphrase probe, for however many ran,
    with every version the rows depend on."""
    after = plan_probe.usage(key)
    spent = round(after - before, 4) if (before is not None and after is not None) else None
    charged_total = sum(r["cost_usd"] for r in rows if r["cost_usd"] is not None)
    failed = sum(1 for r in rows if r["call_failed"])
    totals = question_totals(rows, with_model=True)
    print_totals(totals, with_model=True)
    print(f"model forms failing verification: "
          f"{sum(1 for r in rows if r['model_problems'])} of {len(rows)}")
    print(f"charged per call, summed: ${charged_total:.5f}")
    print(f"account delta: {('$%.4f' % spent) if spent is not None else 'unknown'}")
    print(f"calls failed: {failed} of {len(rows)}")

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out = RESULTS / f"parse-probe-{path.stem}-{stamp}.json"
    out.write_text(json.dumps({
        "ran_at": stamp, "questions": path.name, "comparison_version": COMPARISON_VERSION,
        "model": model, "temperature": 0,
        # The routing every call carried, None when off (23 October 2026).
        "provider_routing": provider_routing.routing_for(model), "form_version": form.VERSION,
        "prompt_version": form.PROMPT_VERSION, "normalise_version": normalise.VERSION,
        "box_version": box.VERSION, "primitives_version": primitives.VERSION,
        "planner_version": planner.VERSION, "strategy_version": targeting.VERSION,
        "commit": repository_commit(), "page_from": spec["page_from"], "page": page.record(),
        "limits": limits(path, page), "in_sample": path.name in IN_SAMPLE,
        "spend_usd": spent, "charged_usd": charged_total, "calls_failed": failed,
        "totals": totals, "rows": rows}, indent=2) + "\n")
    print(f"written: {out}")
    return out


def limits(path: pathlib.Path, page: page_module.Page) -> list[str]:
    """What a probe of this file on this page cannot show, printed before its figures and
    kept in its result file: that the parser was tuned on the file, so its figures are
    development evidence only (LESSONS 19), and that the stored page kept no titles, so a
    title filter is known to restate the page only by the search word (22 October 2026)."""
    found = []
    if path.name in IN_SAMPLE:
        found.append(f"in sample: {IN_SAMPLE[path.name]}, so these figures are development "
                     f"evidence only, never a claim (LESSONS 19)")
    if not normalise.titles_kept(page):
        found.append("the stored page record keeps no listing titles, so a title filter is "
                     "dropped as restating the page only when it restates the search word, "
                     "where the box on a live page would also drop the product's own words")
    return found


def probe_questions(path: pathlib.Path, model: str, dry_run: bool) -> int:
    """The paraphrase probe. The rules' half of every question first, free, on the stored
    page each question must name; then, in a paid run, the model's half, one call each with
    no retry and the result file written whatever stops the loop, as the census."""
    spec, entries = load_questions(path)
    page = stored_page(paths.RESULTS / spec["page_from"] / "suite.json")
    for entry in entries:
        named = box.results_url(entry["question"])
        if named != page.url:
            raise ValueError(f"paraphrase {entry['id']} names {named}, not the stored page {page.url}")
    halves = [rules_half(entry, page) for entry in entries]
    for line in limits(path, page):
        print(f"note: {line}")
    if dry_run:
        for n, (row, _) in enumerate(halves, 1):
            print(f"=== prompt {n} of {len(halves)}, paraphrase {row['id']} of {row['template']}")
            print(form.prompt(row["question"]))
            print()
        print(f"=== the rules' half, free, on the page the box read in batch {spec['page_from']}")
        for row, _ in halves:
            print_paraphrase(row)
        print_totals(question_totals([row for row, _ in halves], with_model=False), with_model=False)
        print_estimate([form.prompt(row["question"], page) for row, _ in halves], model)
        return 0

    key = plan_probe.load_key()
    if not key:
        print("no OPENROUTER_API_KEY")
        return 1
    before = plan_probe.usage(key)
    rows: list[dict] = []
    try:
        for row, expected in halves:
            rows.append(model_half(row, expected, page, model, key))
            print_paraphrase(rows[-1])
    finally:
        # Whatever stopped the loop, the rows that ran and their charges are on disk.
        report_questions(rows, path, spec, page, model, key, before)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="print every prompt that would be sent, and send nothing")
    parser.add_argument("--model", default=None)
    parser.add_argument("--questions", type=pathlib.Path, default=None,
                        help="a paraphrase file, such as experiments/tasks/paraphrases_v1.json: "
                             "probe its questions instead of the census, each against the "
                             "rules' form of the question it rewords")
    args = parser.parse_args()

    model = args.model or plan_probe.model_name()
    if args.questions is not None:
        return probe_questions(args.questions, model, args.dry_run)
    questions = census()
    if args.dry_run:
        for n, (name, question) in enumerate(questions, 1):
            print(f"=== prompt {n} of {len(questions)}, {name}")
            print(form.prompt(question))
            print()
        print(f"{len(questions)} calls to {model}, text only, no browser. Nothing was sent.")
        return 0

    key = plan_probe.load_key()
    if not key:
        print("no OPENROUTER_API_KEY")
        return 1
    before = plan_probe.usage(key)

    rows: list[dict] = []
    try:
        for name, question in questions:
            rows.append(probe_one(name, question, model, key))
            print_row(rows[-1])
    finally:
        # Whatever stopped the loop, the rows that ran and their charges are on disk.
        report(rows, model, key, before)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
