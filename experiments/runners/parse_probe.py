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

    python experiments/runners/parse_probe.py --dry-run     # prints the prompts, calls nothing
    python experiments/runners/parse_probe.py               # paid: one call per question
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import form
import plan_probe  # the key, the model name and the account usage, read the same way
import planner

RESULTS = paths.RESULTS
ENDPOINT = plan_probe.ENDPOINT


def census() -> list[tuple[str, str]]:
    """Every question in the project's task files, with the file each came from."""
    return planner.questions()


def call_model(key: str, model: str, prompt: str) -> tuple[str, float | None]:
    """One call, and what the provider charged for it, or None when it did not say."""
    reply = requests.post(
        ENDPOINT,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "temperature": 0, "usage": {"include": True},
              "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    reply.raise_for_status()
    payload = reply.json()
    cost = (payload.get("usage") or {}).get("cost")
    return payload["choices"][0]["message"]["content"], (float(cost) if cost is not None else None)


def summary(parsed: form.Form) -> str:
    filters = ", ".join(f"{f.attribute} {f.op} {f.value}" for f in parsed.filters) or "none"
    k = f" k={parsed.k}" if parsed.k else ""
    return f"{parsed.quantifier} {parsed.objective} over {parsed.population}{k}, filters: {filters}"


def agree(rules: form.Form, model: form.Form) -> bool:
    """The same retrieval: quantifier, objective, population, k and the same conditions."""
    return (rules.quantifier, rules.objective, rules.population, rules.k) == \
        (model.quantifier, model.objective, model.population, model.k) and \
        {(f.attribute, f.op, str(f.value)) for f in rules.filters} == \
        {(f.attribute, f.op, str(f.value)) for f in model.filters}


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

    rows = []
    for name, question in questions:
        rules = form.from_rules(question)
        charged = []

        def call(prompt: str) -> str:
            text, cost = call_model(key, model, prompt)
            charged.append(cost)
            return text

        error = None
        proposed = None
        try:
            proposed = form.from_model(question, None, call)
        except ValueError as fault:
            error = str(fault)
        same = proposed is not None and agree(rules, proposed)
        rows.append({"file": name, "question": question,
                     "rules": rules.record(), "rules_problems": form.verify(rules),
                     "model": proposed.record() if proposed else None,
                     "model_problems": form.verify(proposed) if proposed else [error],
                     "agree": same, "cost_usd": charged[0] if charged else None})
        row = rows[-1]
        cost = f"${row['cost_usd']:.5f}" if row["cost_usd"] is not None else "cost unknown"
        print(f"{'same' if same else 'DIFF'} {name:20} {question.split('. ', 1)[-1][:70]}")
        print(f"     rules: {summary(rules)}")
        print(f"            {'; '.join(row['rules_problems']) or 'sound'}")
        print(f"     model: {summary(proposed) if proposed else 'no form: ' + str(error)}")
        print(f"            {'; '.join(row['model_problems']) or 'sound'}")
        print(f"     {cost}")

    after = plan_probe.usage(key)
    spent = round(after - before, 4) if (before is not None and after is not None) else None
    charged_total = sum(r["cost_usd"] for r in rows if r["cost_usd"] is not None)
    print(f"\nagree on {sum(r['agree'] for r in rows)} of {len(rows)} questions")
    print(f"model forms failing verification: "
          f"{sum(1 for r in rows if r['model_problems'])} of {len(rows)}")
    print(f"charged per call, summed: ${charged_total:.5f}")
    print(f"account delta: {('$%.4f' % spent) if spent is not None else 'unknown'}")

    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    out = RESULTS / f"parse-probe-{stamp}.json"
    out.write_text(json.dumps({"ran_at": stamp, "model": model, "temperature": 0,
                               "form_version": form.VERSION, "spend_usd": spent,
                               "charged_usd": charged_total, "rows": rows}, indent=2) + "\n")
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
