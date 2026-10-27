#!/usr/bin/env python3
"""Prepare a local blind reader; validate/import verdicts without opening any arm key.

The HTML contains only the existing blind CSV and frozen reading rules. No model is
called. --score is an explicit unblinding step and refuses an incomplete sheet.
"""
import argparse
import csv
import hashlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "experiments/results/claim2b-stage1.sheet.csv"
COLUMNS = ["code", "question", "key", "answer", "hand_verdict", "note"]
IMMUTABLE = COLUMNS[:4]
VERDICTS = {"correct", "not correct", "unscorable"}


def read_sheet(path):
    with pathlib.Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise ValueError("Expected the six original columns in their original order.")
        rows = list(reader)
    seen = set()
    for index, row in enumerate(rows, 1):
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Row {index}: malformed CSV.")
        if not row["code"] or row["code"] in seen:
            raise ValueError(f"Row {index}: blank or duplicate code.")
        seen.add(row["code"])
        verdict = " ".join(row["hand_verdict"].split()).lower()
        if verdict and verdict not in VERDICTS:
            raise ValueError(f"Row {index}: use correct, not correct, or unscorable.")
        row["hand_verdict"] = verdict
    if not rows:
        raise ValueError("The sheet is empty.")
    return rows


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def merge_verdicts(original, incoming):
    by_code = {row["code"]: row for row in incoming}
    if set(by_code) != {row["code"] for row in original}:
        raise ValueError("Import refused: the row codes do not match the original sheet.")
    merged = []
    for row in original:
        new = by_code[row["code"]]
        if any(row[key] != new[key] for key in IMMUTABLE):
            raise ValueError(f"Import refused: question, key or answer changed for {row['code']}.")
        if row["hand_verdict"] and not new["hand_verdict"]:
            raise ValueError(f"Import refused: {row['code']} would lose a completed verdict. Use your latest download.")
        merged.append({**row, "hand_verdict": new["hand_verdict"], "note": new["note"]})
    return merged


def summary(rows):
    done = sum(bool(row["hand_verdict"]) for row in rows)
    return f"{done}/{len(rows)} reviewed; {len(rows)-done} remaining. No arm labels or scorer verdicts read."


def make_html(rows, sheet):
    # Cache belongs to this exact source revision, including any imported grades.
    # Otherwise an older partial browser cache can overwrite a newer filled CSV.
    identity = json.dumps(rows, ensure_ascii=False)
    payload = {"rows": rows, "filename": pathlib.Path(sheet).name,
               "identity": hashlib.sha256(identity.encode()).hexdigest(),
               "rules": (ROOT / "docs/content/claim2-reading-rules.md").read_text()}
    # A literal closing script tag in an answer must stay inert.
    encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
    return (ROOT / "tools/hand_review.html").read_text().replace("/* REVIEW_PAYLOAD */", encoded)


def score(sheet, rows):
    if any(not row["hand_verdict"] for row in rows):
        raise ValueError("Scoring refused: finish every row before unblinding.")
    if sheet.resolve() != DEFAULT.resolve():
        raise ValueError("This scoring shortcut is only for the original stage-1 sheet.")
    jobs = [
        ("claim2b-stage1.hand.txt", ["experiments/analysis/claim.py", "--protocol",
         "experiments/tasks/claim2_analysis.json", "--hand", str(sheet),
         "experiments/results/claim2b-stage1.manifest"]),
        ("claim2b-stage1.agreement.txt", ["experiments/analysis/reader_agreement.py",
         "--sheet", str(sheet), "--second", "experiments/results/claim2b-stage1.second-reader.verdicts.csv",
         "--codes", "experiments/results/claim2b-stage1.sheet.second-reader.json"]),
    ]
    for name, arguments in jobs:
        target = sheet.parent / name
        with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as handle:
            temporary = pathlib.Path(handle.name)
            result = subprocess.run([sys.executable, *arguments], cwd=ROOT, stdout=handle)
        if result.returncode:
            temporary.unlink()
            raise ValueError(f"Scoring failed ({result.returncode}); existing {name} was preserved.")
        temporary.replace(target)
        print(f"Wrote {target}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", type=pathlib.Path, default=DEFAULT)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--output", type=pathlib.Path, help="write a standalone offline review HTML")
    actions.add_argument("--import-verdicts", type=pathlib.Path, help="validate and import a downloaded CSV; back up original")
    actions.add_argument("--score", action="store_true", help="after completing review, explicitly unblind and write both result files")
    args = parser.parse_args()
    try:
        rows = read_sheet(args.sheet)
        if args.import_verdicts:
            rows = merge_verdicts(rows, read_sheet(args.import_verdicts))
            stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
            backup = args.sheet.with_name(args.sheet.name + ".backup-" + stamp)
            shutil.copy2(args.sheet, backup)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=args.sheet.parent, delete=False) as handle:
                temporary = pathlib.Path(handle.name)
                handle.write(csv_text(rows))
            temporary.replace(args.sheet)
            print(f"Imported verdicts only. Original backup: {backup}")
        elif args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(make_html(rows, args.sheet), encoding="utf-8")
            print(f"Open {args.output.resolve()}")
        elif args.score:
            score(args.sheet, rows)
        if not args.score:
            print(summary(rows))
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
