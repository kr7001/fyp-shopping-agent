#!/usr/bin/env python3
"""How far the two hand readers agree, as the second claim's protocol asks.

    python3 experiments/analysis/reader_agreement.py \
        --sheet <the student's filled sheet>.csv \
        --second <the second reader's file>.csv \
        --codes <the sheet's name>.second-reader.json [--json]

The protocol (docs/content/claim2-protocol.md, "Measures and scoring") has the verifier read
40 rows of the blind hand-reading sheet as second reader, and says the agreement of the two
readers, the share of rows read alike and Cohen's kappa, is computed by a short script
committed with the results. This is that script.

`claim.py --sheet` writes the sheet and `<name>.second-reader.json`, which lists the codes the
second reader reads. The student's sheet has the columns code, question, key, answer,
hand_verdict, note. The second reader's file has code, verdict, note. Only the code and the
verdict are read from either, and no question, key or answer text is printed.

A verdict is `correct`, `not correct` or `unscorable`. Anything else is refused by code, and so
is a listed code that is missing or blank in either file, a code twice in a file, and a code in
the second reader's file that the list does not hold. Kappa is the unweighted one over the three
categories. Where both readers used a single category and the same one, chance agreement is 1
and kappa has no value, so it is printed as undefined, not as 1 or 0.

Free: no model is called.
"""
import argparse
import csv
import json
import pathlib

VERDICTS = ("correct", "not correct", "unscorable")


def clean(cell) -> str:
    """A verdict as claim.py reads one (read_hand_sheet): spaces collapsed, lower-cased, so the
    two scripts take the same cells to mean the same verdict."""
    return " ".join((cell or "").split()).lower()


def load_codes(path: pathlib.Path) -> list[str]:
    """The second reader's codes from `<name>.second-reader.json`. claim.py writes them under
    "codes" (its "rows" is their count); a file that lists them under "rows" is read as well."""
    data = json.loads(path.read_text())
    codes = data.get("codes") if isinstance(data.get("codes"), list) else data.get("rows")
    if not isinstance(codes, list) or not codes:
        raise SystemExit(f"refused: {path} lists no codes (neither \"codes\" nor \"rows\" is a list)")
    codes = [str(code).strip() for code in codes]
    if len(set(codes)) != len(codes) or "" in codes:
        raise SystemExit(f"refused: {path} lists a code twice or a blank one")
    if isinstance(data.get("rows"), int) and data["rows"] != len(codes):
        raise SystemExit(f"refused: {path} says {data['rows']} rows and lists {len(codes)} codes")
    return codes


def read_verdicts(path: pathlib.Path, verdict_column: str, listed: list[str], strict_codes: bool) -> dict:
    """code -> verdict for the listed codes, from the code column and the verdict column only.
    Every fault found is gathered and refused together, each naming its code. `strict_codes` is
    the second reader's file, which may hold nothing outside the list; the student's sheet holds
    every row of the market and is read only at the listed ones."""
    with path.open(newline="", encoding="utf-8-sig") as handle:      # newline="": cells hold newlines
        reader = csv.DictReader(handle)
        missing = [c for c in ("code", verdict_column) if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"refused: {path} has no column {', '.join(missing)}")
        rows = [(row["code"], row[verdict_column]) for row in reader]
    found, problems, seen = {}, [], set()
    for code, cell in rows:
        code = (code or "").strip()
        if not code:
            if clean(cell):
                problems.append(f"{path.name}: a verdict with no code")
            continue
        if code in seen:
            if code in listed or strict_codes:
                problems.append(f"{path.name}: the code {code} is there twice")
            continue
        seen.add(code)
        if code not in listed:
            if strict_codes:
                problems.append(f"{path.name}: the code {code} is not on the list")
            continue
        verdict = clean(cell)
        if not verdict:
            problems.append(f"{path.name}: the code {code} has no verdict")
        elif verdict not in VERDICTS:
            problems.append(f"{path.name}: the code {code} has a verdict that is not one of "
                            f"{', '.join(VERDICTS)}")
        else:
            found[code] = verdict
    problems += [f"{path.name}: the code {code} is missing" for code in listed if code not in seen]
    if problems:
        raise SystemExit("refused:\n  " + "\n  ".join(problems))
    return found


def agreement(first: dict, second: dict) -> dict:
    """Agreement of two readers over the same codes. kappa = (po - pe) / (1 - pe), done in whole
    numbers as (alike * n - sum of row total * column total) / (n * n - that sum), so that
    "chance agreement is 1" is an exact test and not a float comparison. None where it is."""
    codes = sorted(first)
    n = len(codes)
    table = {a: {b: 0 for b in VERDICTS} for a in VERDICTS}
    for code in codes:
        table[first[code]][second[code]] += 1
    alike = sum(table[v][v] for v in VERDICTS)
    chance = sum(sum(table[a].values()) * sum(table[b][a] for b in VERDICTS) for a in VERDICTS)
    kappa = None if chance == n * n else (alike * n - chance) / (n * n - chance)
    return {"n": n, "alike": alike, "share_alike": alike / n, "kappa": kappa, "table": table,
            "differ": [{"code": c, "student": first[c], "second": second[c]} for c in codes
                       if first[c] != second[c]]}


def render(result: dict) -> str:
    kappa = result["kappa"]
    shown = ("undefined (chance agreement is 1: both readers used the one same category)"
             if kappa is None else f"{kappa:.3f}")
    width = max(len(v) for v in VERDICTS) + 2
    lines = [f"Reader agreement over n = {result['n']} rows",
             f"read alike: {result['alike']} of {result['n']} ({result['share_alike']:.1%})",
             f"Cohen's kappa (unweighted, three categories): {shown}",
             "table: rows are the student's reading, columns the second reader's",
             " " * width + "".join(v.rjust(width) for v in VERDICTS)]
    for a in VERDICTS:
        lines.append(a.ljust(width) + "".join(str(result["table"][a][b]).rjust(width) for b in VERDICTS))
    lines.append(f"read differently: {len(result['differ'])}")
    lines += [f"  {d['code']}: student {d['student']}, second {d['second']}" for d in result["differ"]]
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--sheet", required=True, type=pathlib.Path, help="the student's filled sheet (CSV)")
    parser.add_argument("--second", required=True, type=pathlib.Path, help="the second reader's file (CSV)")
    parser.add_argument("--codes", required=True, type=pathlib.Path, help="<name>.second-reader.json")
    parser.add_argument("--json", action="store_true", help="print the same figures as JSON")
    args = parser.parse_args(argv)
    listed = load_codes(args.codes)
    student = read_verdicts(args.sheet, "hand_verdict", listed, strict_codes=False)
    second = read_verdicts(args.second, "verdict", listed, strict_codes=True)
    result = agreement(student, second)
    print(json.dumps(result, indent=2) if args.json else render(result))


if __name__ == "__main__":
    main()
