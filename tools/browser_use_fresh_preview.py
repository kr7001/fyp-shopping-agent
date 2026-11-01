#!/usr/bin/env python3
"""The exact text every Study A trial would send on the fresh market, with no model call.

Free. It builds the 32-slot schedule with the runner's own `preview`, reads each question's
results page once with the runner's own rendered reader (a local browser on the local shop),
and builds each slot's text with the runner's own `build_query`, as a paid run does.

The block arm reads the question through the model parser in a paid run. Here the parser's
call is a stub that returns the rules' form of the same question, written as a model's reply,
so the box's model path (reply parsing, normalisation, the checks, the plan) runs on it and
the stub's own text is shown. On Quenby the model's form equalled the rules' form in all 16
block trials of the repeats 2-3 cohort, so this is the text the block sends when the model
reads a question as it did there. The rules' own text is shown beside it, and each slot says
whether the two are the same. A model that reads a question differently would send another
text; only a paid run can show that.

    python3 tools/browser_use_fresh_preview.py --config notes/fresh-market-2-nov/study-a-command.json \\
        --out notes/fresh-market-2-nov/study-a-preview.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import paths  # noqa: E402,F401
import browser_use_transfer as study  # noqa: E402
import box as box_module  # noqa: E402
import form as form_module  # noqa: E402

# The fields of a model parser's reply (`form.parse_reply`).
REPLY_FIELDS = ("quantifier", "objective", "filters", "population", "k", "negated", "reading",
                "unknowns", "ambiguities", "evidence")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest() if text is not None else None


def rules_reply(question, page):
    """The rules' form of a question, written as the model parser's reply."""
    form = form_module.from_rules(question, page).record()
    return json.dumps({field: form[field] for field in REPLY_FIELDS})


def slot_text(slot, observed):
    """One slot's text as the paid run builds it, the block's from a stub reply, with what
    produced it and, for the block, the rules' own text."""
    question = slot["question"]
    row = {"id": slot["id"], "condition": slot["condition"], "repeat": slot["repeat"],
           "task": question["id"], "question": question["query"]}
    if slot["condition"] == "baseline":
        text, _ = study.build_query(question, "baseline", observed)
        row.update(text=text, text_sha256=digest(text), parser_calls=0)
        return row
    prompts = []

    def stub(prompt):
        prompts.append(prompt)
        return rules_reply(question["query"], observed)

    text, decision = study.build_query(question, "block", observed, call=stub)
    parse = decision.record()["parse"]
    rules = box_module.decide(question["query"], observed, reply=None, parser="rules", rate="bound")
    rules_text = (study.COMMON_BRIEFING + "\n\n" + rules.query) if rules.query else None
    row.update(text=text, text_sha256=digest(text), parser_calls=0, stub_prompts=len(prompts),
               parse_used=parse["used"], fallback_reason=parse["fallback_reason"],
               kind=decision.kind, rules_text_sha256=digest(rules_text),
               same_as_rules=text == rules_text)
    return row


def preview_texts(config, read=study.read_observation):
    plan = study.preview(config)
    pages = {}
    rows = []
    for slot in plan["slots"]:
        question = slot["question"]
        if question["id"] not in pages:
            pages[question["id"]] = read(config, question)
        rows.append(slot_text(slot, pages[question["id"]]))
    first = next(iter(pages.values()))
    return {"study_id": plan["study_id"], "stage": plan["stage"], "model_calls": 0,
            "warning_sha256": plan["warning_sha256"], "slots": rows,
            "page": {"reader": first.reader, "listings": len(first.listings), "total": first.total,
                     "pages_read": len(pages), "listing_urls_sha256": digest(json.dumps(
                         [item.url for item in first.listings]))},
            "stub": "block slots: the rules' form of the same question, written as the model's reply"}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error(f"{args.out} exists; move it away first")
    result = preview_texts(json.loads(args.config.read_text()))
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    rows = result["slots"]
    block = [r for r in rows if r["condition"] == "block"]
    print(f"{len(rows)} slots, no model call; block slots planned by the stub reply "
          f"{sum(r['parse_used'] == 'model' for r in block)}/{len(block)}, the same text as the "
          f"rules' {sum(r['same_as_rules'] for r in block)}/{len(block)}; written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
