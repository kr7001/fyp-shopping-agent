#!/usr/bin/env python3
"""Run one timed-out slot of the fresh matched-briefing study once more, its clock doubled.

Amendment 4 (notes/fresh-market-2-nov/amendment-4-2-nov.md, points 3 and 6, 2 November 2026)
reruns each slot of Study B whose primary record reached its 1800 s clock, once, with the clock
doubled to 3600 s and nothing else changed. The frozen runner, `matched_briefing.py`,
byte-identical to commit afba41b, refuses any clock but 1800 s, and stays unchanged. This runs
the same code through `matched_briefing_study.py`, as every primary slot ran, with one change:
the clock handed to suite.py is 3600 s. The frozen runner still checks every other argument
exactly as for a primary slot, seeing `--clock 1800`, and nothing else is touched, so the text
each arm receives and the records it writes are the frozen runner's, with `clock_s` 3600.

Used only by Study B's timeout-rerun stage, whose launcher pins this file by its SHA-256
(tools/guarded_matched_briefing.py). Costs money unless given --dry-run, like every script here.
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths  # noqa: E402,F401  (puts runners/ on the path)
import matched_briefing  # noqa: E402
import matched_briefing_study  # noqa: E402

PRIMARY_CLOCK_S, RERUN_CLOCK_S = 1800, 3600


def frozen_argv(argv: list[str]) -> list[str]:
    """The arguments as the frozen runner checks them: a rerun gives `--clock 3600` exactly once,
    and the frozen runner is shown the primary slots' 1800 s in its place."""
    at = [i for i, arg in enumerate(argv) if arg == "--clock"]
    if (len(at) != 1 or at[0] + 1 >= len(argv) or argv[at[0] + 1] != str(RERUN_CLOCK_S)
            or any(arg.startswith("--clock=") for arg in argv)):
        raise SystemExit(f"refusing: a rerun gives --clock {RERUN_CLOCK_S} exactly once")
    return argv[:at[0] + 1] + [str(PRIMARY_CLOCK_S)] + argv[at[0] + 2:]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if {"-h", "--help"} & set(argv):
        print(__doc__)
        return 0
    checked = frozen_argv(argv)
    frozen = matched_briefing.suite_argv

    def suite_argv(args):
        handed = frozen(args)
        at = handed.index("--clock")
        if handed[at + 1] != str(PRIMARY_CLOCK_S):
            raise SystemExit("refusing: the frozen runner did not hand on its own 1800 s clock")
        return handed[:at + 1] + [str(RERUN_CLOCK_S)] + handed[at + 2:]

    matched_briefing.suite_argv = suite_argv
    try:
        return matched_briefing_study.main(checked)
    finally:
        matched_briefing.suite_argv = frozen


if __name__ == "__main__":
    raise SystemExit(main())
