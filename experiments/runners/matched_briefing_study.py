#!/usr/bin/env python3
"""Run one slot of a later matched-briefing study through the unchanged 29 October runner.

`matched_briefing.py`, byte-identical to commit afba41b, holds its study identity as a
module constant: it refuses a protocol file of any other identity and stamps that identity on
every record. A later study of the same design on another market, the fresh held-out market
of 2 November 2026 (notes/fresh-market-2-nov/analysis-plan-B.md), runs that same code under
its own identity. This reads the identity from the protocol file named on the command line,
refuses one this file does not list, sets the constant, and calls the frozen runner's own
`main` with the same arguments. Nothing else is touched, so the text each arm receives, the
suite it drives and the records it writes are the frozen runner's.

Costs money unless given --dry-run, like every script in this folder.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401
import matched_briefing  # noqa: E402

# The later studies this may run. The 29 October study ran matched_briefing.py directly.
STUDIES = ("matched-briefing-fresh-2026-11-02",)


def study_of(argv: list[str]) -> str:
    """The study identity of the protocol file the arguments name, if this file lists it."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--protocol", type=pathlib.Path, required=True)
    known, _ = parser.parse_known_args(argv)
    study = json.loads(known.protocol.read_text()).get("study_id")
    if study not in STUDIES:
        raise SystemExit(f"refusing: {known.protocol} is not a protocol of a study this runs")
    return study


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if not {"-h", "--help"} & set(argv):  # the frozen runner's own help needs no protocol
        matched_briefing.STUDY_ID = study_of(argv)
    return matched_briefing.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
