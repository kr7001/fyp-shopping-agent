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

    python experiments/runners/parse_probe.py --dry-run     # prints the prompts, calls nothing
    python experiments/runners/parse_probe.py               # paid: one call per question
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
import form
import page as page_module
import plan_probe  # the key, the model name and the account usage, read the same way
import planner

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
    for it, so the charge comes with it when the body says one, and the row keeps it.
    Until 14 October 2026 the KeyError stopped the loop and lost the row (verifier
    finding)."""

    def __init__(self, why: str, cost: float | None):
        super().__init__(why)
        self.cost = cost


def call_model(key: str, model: str, prompt: str) -> tuple[str, float | None]:
    """One call, and what the provider charged for it, or None when it did not say. A
    200 with a body that is not JSON raises requests' own `JSONDecodeError`, a request
    failure; a JSON body without the completion raises `UnexpectedReply`."""
    reply = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "temperature": 0, "usage": {"include": True},
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    reply.raise_for_status()
    payload = reply.json()
    usage = payload.get("usage") if isinstance(payload, dict) else None
    cost = usage.get("cost") if isinstance(usage, dict) else None
    cost = float(cost) if cost is not None else None
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as fault:
        raise UnexpectedReply(f"the reply holds no choices[0].message.content "
                              f"({type(fault).__name__}: {fault}): {str(payload)[:200]!r}", cost)
    return text, cost


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
    if (rules.quantifier, rules.objective, rules.population, rules.k) != \
            (model.quantifier, model.objective, model.population, model.k):
        return False
    stated = {(f.attribute, f.op): comparable(f.value) for f in model.filters}
    for condition in rules.filters:
        key = (condition.attribute, condition.op)
        derived = f"filter:{condition.attribute}" in rules.evidence
        if (derived or key in stated) and stated.pop(key, None) != comparable(condition.value):
            return False
    return not stated


def probe_one(name: str, question: str, model: str, key: str) -> dict:
    """One question: the rules' form on the page it names, the model's form, whether the
    two agree, and what the call cost. A request that fails, an HTTP error, a timeout or
    a body that is not JSON, is recorded on the row with no cost rather than ending the
    probe, and a success whose body holds no completion is recorded the same way, with
    whatever it was charged. No retry, so the figure stays one call per question."""
    page = results_page(question)
    rules = form.from_rules(question, page)
    charged: list[float | None] = []

    def call(prompt: str) -> str:
        text, cost = call_model(key, model, prompt)
        charged.append(cost)
        return text

    proposed, error, failed = None, None, False
    try:
        proposed = form.from_model(question, None, call)
    # Request failures before ValueError: requests' `JSONDecodeError`, raised for a 200
    # whose body is not JSON, is both, and until 14 October 2026 the ValueError handler
    # took it as a model problem, so `calls_failed` undercounted (verifier finding).
    except requests.exceptions.RequestException as fault:
        error, failed = f"request failed: {fault}", True
    except UnexpectedReply as fault:
        error, failed = f"reply not a completion: {fault}", True
        charged.append(fault.cost)
    except ValueError as fault:         # a reply that is not a form in the vocabulary
        error = str(fault)
    return {"file": name, "question": question,
            "rules": rules.record(), "rules_problems": form.verify(rules, page),
            "model": proposed.record() if proposed else None,
            "model_problems": (form.verify(proposed, page) if proposed
                               else [] if failed else [error]),
            "error": error, "call_failed": failed,
            "agree": proposed is not None and agree(rules, proposed),
            "cost_usd": charged[0] if charged else None}


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
                               "form_version": form.VERSION, "commit": repository_commit(),
                               "spend_usd": spent, "charged_usd": charged_total,
                               "calls_failed": failed, "rows": rows}, indent=2) + "\n")
    print(f"written: {out}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="print every prompt that would be sent, and send nothing")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()

    model = args.model or plan_probe.model_name()
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
