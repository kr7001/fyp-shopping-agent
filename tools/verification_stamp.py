#!/usr/bin/env python3
"""Record the verifier's verdict on the code at the current commit.

The workbench guard (tools/workbench/igr-workbench) lets a paid run through only when the
latest stamp is a pass, was made at the commit that is checked out now, and no experiment
code has changed since. So a stamp always describes committed code, and any later edit
or commit sends the code back through the verifier.

Only the verifier subagent runs this. The guard refuses it from the main conversation and
from any other agent, and refuses any other way of writing into .verification/.

    python3 tools/verification_stamp.py --scope "cell 4 suite, box v1" \\
        --checks "planner regression 37/37" "dry run read" "held-constant table"
    python3 tools/verification_stamp.py --fail --scope "..." --checks "..."
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
STAMP_DIR = ROOT / ".verification"

# The code a paid run depends on. Results and run logs change with every run, so they are
# not code, and are left out. Kept identical to CODE_PATHS in the guard.
CODE_PATHS = ["experiments", "env", "tools",
              ":(exclude)experiments/results", ":(exclude)experiments/runs"]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True,
                          check=True).stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scope", required=True,
                        help="one line: what was verified, for what run")
    parser.add_argument("--checks", nargs="+", required=True,
                        help="each check that was run, with its result")
    parser.add_argument("--fail", action="store_true",
                        help="record a failed verification, which unlocks nothing")
    args = parser.parse_args()

    dirty = git("status", "--porcelain", "--", *CODE_PATHS)
    if dirty:
        print("refusing to stamp: experiment code has uncommitted changes, so the stamp "
              "would not describe what runs. Commit first, then verify that commit.")
        print(dirty)
        return 1

    stamp = {
        "verdict": "fail" if args.fail else "pass",
        "commit": git("rev-parse", "HEAD"),
        "scope": args.scope,
        "checks": args.checks,
        "at": dt.datetime.now().isoformat(timespec="seconds"),
    }
    STAMP_DIR.mkdir(exist_ok=True)
    (STAMP_DIR / "latest.json").write_text(json.dumps(stamp, indent=2) + "\n")
    with (STAMP_DIR / "history.jsonl").open("a") as history:
        history.write(json.dumps(stamp) + "\n")
    print(f"stamped {stamp['verdict']} at {stamp['commit'][:10]}: {stamp['scope']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
