#!/usr/bin/env python3
"""A paraphrase probe's figures, reported the way its paraphrase file fixed before any call.

    python3 experiments/analysis/paraphrase_scores.py experiments/results/parse-probe-paraphrases_v1-<stamp>.json
    python3 experiments/analysis/paraphrase_scores.py <result file> --json PATH

`runners/parse_probe.py --questions` writes one result file per paid run. For each reworded
question it holds the rules' form and the model's form against the rules' form of the
question it rewords (the expected form), in four tiers, and records what box.decide does
with the question and with its template. The paraphrase file the run probed decided, on
20 October 2026 before any model call (37a8f66), that the comparison is reported over the
entries whose meaning is the template's, `meaning_kept`: 24 of the 30 in
paraphrases_v1.json. On the other 6 a correct parse cannot equal the template's form, so
they are read one by one and never counted (the file's _about).

So this prints the run's conditions, then for the rules and for the model the four tiers
over the 24, with box.decide's outcome against each template's. Then it lists the 6, each
with the expected form, the rules' form and the model's form beside `meaning_differs`.

Every count is parse_probe's own: `question_totals` on the 24 rows, printed by
`print_totals`. The tiers the file stores are computed again with `parse_probe.tiers` from
the forms it stores, as a check, and nothing here re-implements a comparison. Written on
20 October 2026, before the first paid paraphrase run.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402  (puts box/, runners/, analysis/, water/ on the path)
import form  # noqa: E402
import parse_probe  # noqa: E402  (the comparison: tiers, question_totals, the printing)

# Bumped when a figure this prints would change for the same result file, or what it reads.
#   1  20 October 2026, before the first paid paraphrase run
#   2  22 October 2026. A file made under an earlier comparison that parse_probe can still
#      read (`parse_probe.READ_AGAIN`) is scored when every tier it stores re-derives the
#      same under today's comparison, and refused otherwise; the paraphrase file's v1
#      result is one, made under comparison 1. And the limits a result file states, that it
#      is in sample or that its page kept no titles, are printed before the figures
#   3  24 October 2026. An entry with no template, the v3 held-out file's reading-test-only
#      entries, is a third group beside meaning_kept and meaning_differs, compared with its
#      expected outcome alone and needing no meaning_kept flag; it has no tiers to recompute
VERSION = 3

# The run's conditions, as the result file names them, printed and kept in the JSON. The
# prompt and the normalisation joined on 22 October 2026 (box v13): a file written before
# then has neither, prints None for both, and was made under prompt version 1 with no
# normalisation, which its form_version 9 says.
CONDITIONS = ("questions", "comparison_version", "model", "temperature", "form_version",
              "prompt_version", "normalise_version",
              "box_version", "primitives_version", "planner_version", "strategy_version",
              "commit", "page_from", "ran_at", "calls_failed", "charged_usd", "spend_usd")


def paraphrase_file(result: dict) -> dict:
    """The paraphrase file the run probed, by the name its result file records."""
    return json.loads((paths.TASKS / result["questions"]).read_text())


def recomputed(row: dict) -> list[str]:
    """Each tier the row stores that `parse_probe.tiers` computes otherwise, from the forms
    the row stores: the expected form against the rules' form, and against the model's. A
    row with no template (24 October 2026) stores no expected form and no tiers: nothing to
    recompute."""
    if row.get("expected") is None:
        return []
    expected = form.from_record(row["expected"], "rules")
    found = []
    for who in ("rules", "model"):
        if f"{who}_tiers" not in row:
            continue
        got = form.from_record(row[who], who) if row[who] else None
        today = parse_probe.tiers(expected, got)
        if today != row[f"{who}_tiers"]:
            whose = {"rules": "rules'", "model": "model's"}[who]
            found.append(f"paraphrase {row['id']}: the file stores the {whose} tiers "
                         f"{row[f'{who}_tiers']}, parse_probe.tiers gives {today}")
    return found


def scores(result: dict, spec: dict) -> dict:
    """Every figure, as data: `render` prints it and the JSON is it.

    Refused, by SystemExit: a result made under another comparison version, which
    parse_probe never pools; an entry that does not say whether it keeps its template's
    meaning, since that was to be decided before any call and cannot be filled in after;
    and a row that is not its entry as the file stands (an id the file lacks, another text
    or template, or the same id twice), since the flags would then describe another
    question. Reported beside the figures: an entry with no row, from a run that stopped
    early, and a stored tier that `parse_probe.tiers` computes otherwise."""
    version = result.get("comparison_version")
    if version != parse_probe.COMPARISON_VERSION and version not in parse_probe.READ_AGAIN:
        raise SystemExit(f"the result was compared under version {version}, "
                         f"parse_probe is at {parse_probe.COMPARISON_VERSION}: not scored together")
    if version != parse_probe.COMPARISON_VERSION:
        moved = [text for row in result["rows"] for text in recomputed(row)]
        if moved:
            raise SystemExit(f"the result was compared under version {version}, and read again "
                             f"under {parse_probe.COMPARISON_VERSION} its tiers move: {moved[0]}")
    entries = {entry["id"]: entry for entry in spec["paraphrases"]}
    # An entry with no template (24 October 2026) keeps or changes no template's meaning: it
    # is a third group, compared with its expected outcome alone, and needs no flag.
    untemplated = {n for n, entry in entries.items() if entry.get("template") is None}
    unflagged = sorted(n for n, entry in entries.items()
                       if n not in untemplated and not isinstance(entry.get("meaning_kept"), bool))
    if unflagged:
        raise SystemExit(f"{result['questions']} does not say whether entries {unflagged} keep "
                         f"their template's meaning, and that is decided before any call")
    ids = [row["id"] for row in result["rows"]]
    twice = sorted({n for n in ids if ids.count(n) > 1})
    if twice:
        raise SystemExit(f"the result holds rows {twice} more than once")
    for row in result["rows"]:
        entry = entries.get(row["id"])
        if entry is None or (entry["text"], entry["template"]) != (row["text"], row["template"]):
            raise SystemExit(f"row {row['id']} is not entry {row['id']} of {result['questions']} as "
                             f"the file stands, so its meaning_kept says nothing about it")
    problems = [text for row in result["rows"] for text in recomputed(row)]
    rows = sorted(result["rows"], key=lambda row: row["id"])
    without = [row for row in rows if row["id"] in untemplated]
    kept = [row for row in rows if row["id"] not in untemplated and entries[row["id"]]["meaning_kept"]]
    differ = [row for row in rows if row["id"] not in untemplated and not entries[row["id"]]["meaning_kept"]]
    with_model = all("model_tiers" in row for row in rows)
    return {
        "version": VERSION, "comparison_version": parse_probe.COMPARISON_VERSION,
        # The entries with no template, compared with their expected outcome alone (24
        # October 2026): their totals' audit figures are the ones that say anything.
        "without_template": {
            "entries": len(untemplated), "ids": [row["id"] for row in without],
            "no_row": sorted(n for n in untemplated if n not in ids),
            "totals": parse_probe.question_totals(without, with_model) if without else None},
        "conditions": {key: result.get(key) for key in CONDITIONS},
        # What the probe itself said its figures cannot show (parse_probe.limits); none in a
        # file written before 22 October 2026.
        "limits": list(result.get("limits") or []),
        "problems": problems,
        "with_model": with_model,
        "meaning_kept": {
            "entries": sum(1 for entry in entries.values() if entry["meaning_kept"]),
            "ids": [row["id"] for row in kept],
            "no_row": sorted(n for n, entry in entries.items() if entry["meaning_kept"] and n not in ids),
            "totals": parse_probe.question_totals(kept, with_model),
            "model_forms_failing_verification": (sum(1 for row in kept if row["model_problems"])
                                                 if with_model else None),
            "calls_failed": sum(1 for row in kept if row.get("call_failed")) if with_model else None},
        "meaning_differs": {
            "entries": sum(1 for entry in entries.values() if not entry["meaning_kept"]),
            "no_row": sorted(n for n, entry in entries.items() if not entry["meaning_kept"] and n not in ids),
            "rows": [{**row, "meaning_differs": entries[row["id"]].get("meaning_differs")}
                     for row in differ]},
    }


def render(found: dict) -> str:
    """The report: the conditions, the 24 in parse_probe's own table, then the 6."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        c = found["conditions"]
        print(f"The paraphrase probe, scored as {c['questions']} fixed before any call "
              f"(paraphrase_scores.py v{found['version']}, comparison v{found['comparison_version']})")
        print("run: " + "; ".join(f"{key} {c[key]:.5f}" if isinstance(c[key], float) else f"{key} {c[key]}"
                                  for key in CONDITIONS if key != "questions"))
        for line in found["limits"]:
            print(f"note: {line}")
        print(f"\nProblems found: {len(found['problems'])}")
        for text in found["problems"]:
            print(f"  {text}")

        kept = found["meaning_kept"]
        print(f"\nThe {len(kept['ids'])} paraphrases whose meaning is the template's (meaning_kept), "
              f"of the {kept['entries']} the file flags"
              + (f"; no row for {kept['no_row']}, the run stopped before them" if kept["no_row"] else ""))
        parse_probe.print_totals(kept["totals"], found["with_model"])
        if found["with_model"]:
            n = len(kept["ids"])
            print(f"model forms failing verification: {kept['model_forms_failing_verification']} of {n}; "
                  f"calls failed: {kept['calls_failed']} of {n}")

        without = found.get("without_template") or {}
        if without.get("entries"):
            t = without["totals"] or {}
            print(f"\nThe {len(without['ids'])} with no template, compared with the expected outcome alone, of "
                  f"the {without['entries']} the file holds"
                  + (f"; no row for {without['no_row']}" if without["no_row"] else ""))
            if t:
                print(f"  the outcome the audit expected, the rules {t['box_as_audit_expected']} of {t['paraphrases']}"
                      + (f", the model parser {t['model_box_as_audit_expected']} of {t['paraphrases']}"
                         if "model_box_as_audit_expected" in t else ""))

        differ = found["meaning_differs"]
        print(f"\nThe {len(differ['rows'])} whose meaning differs from the template's, read by hand and "
              f"never counted" + (f"; no row for {differ['no_row']}" if differ["no_row"] else ""))
        for row in differ["rows"]:
            block = io.StringIO()
            with contextlib.redirect_stdout(block):
                parse_probe.print_paraphrase(row)
            lines = block.getvalue().splitlines()
            # Beside the question, why a correct parse cannot equal the template's form.
            print("\n".join(lines[:1] + [f"     meaning differs: {row['meaning_differs']}"] + lines[1:]))
    return out.getvalue().rstrip("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("result", type=pathlib.Path,
                        help="a result file parse_probe.py --questions wrote")
    parser.add_argument("--json", type=pathlib.Path, help="write the figures here as well")
    args = parser.parse_args(argv)
    result = json.loads(args.result.read_text())
    found = scores(result, paraphrase_file(result))
    print(render(found))
    if args.json is not None:
        args.json.write_text(json.dumps(found, indent=2) + "\n")
        print(f"\nthe same figures as JSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
