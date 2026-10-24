#!/usr/bin/env python3
"""Emit one of the second claim run's two paid commands (24 October 2026, the tee-only design).

Written for the A+ design on 23 October, when the verifier dry-ran its mechanics (the order,
the flags, the preflight under the run's model, exit codes 3 to 8, the routing gate, the
watchdog, the voids loop, the reading test). Adapted on 24 October for the tee-only design
and the morning's two taps (docs/content/claim2-handover.md, section 6): the plan and the
cost table moved to experiments/analysis/stage_plan.py, which the pilot check shares, so the
command that runs and the check that judges it read one plan.

The emitted text is what the verifier checks and the guard sees; this script only writes it.
Each command declares its own IGR_ESTIMATE_USD and runs under caffeinate -i, as the guard reads
them, and every paid invocation in it runs only if the spend so far plus twice its estimate
stays under the cap, after `claim.py --preflight` under the run's model, with a watchdog that
stops any suite once the spend reaches the cap less $0.30.

  --stage pilot   command 1, tap 1 at 10:00: the live check of the development market (exit 5),
                  the routing gate (exit 7), twelve runs on the development market
                  (`stage_plan.PILOT_PLAN`, one question each), then the pilot check
                  (experiments/analysis/pilot_check.py) into the manifest and a summary file;
                  exit 9 when a check fails.
                  Exit 10, either command, when .env sets a sampling key (SAMPLING_KEYS).
  --stage 1       command 2, tap 2 at about 10:45: the live check of the claim market, the
                  routing gate, stage 1's invocations (`stage_plan.stage1_invocations`: every
                  round of the model's design, the arms rotated, small invocations), the voids
                  re-run once under the same routing, then the reading tests: DeepSeek, then
                  Haiku with IGR_PROVIDER_ROUTING unset, each on every paraphrase file given,
                  text only, with --spec-from the claim task file, --page-from the stage's first
                  block batch and --only-templates the market's templates (exit 8 with no block
                  batch).

Exit codes of a chain: 3 the cap gate (before the routing check, an invocation, a void re-run
or a reading test), 4 the account unreadable at the start, 5 the live check, 6 the preflight,
7 the routing check, 8 no block batch for the reading test, 9 the pilot check failed.

A dry run of the mechanics: `--root` points the chain at another tree, one whose runners,
check, preflight, voids and account reader are stubs (tests/test_stage_command.py builds one
and drives every exit code, the cap gate, the watchdog, the voids loop and the summary), so the
verifier executes each emitted chain end to end with no paid call. `--watchdog-interval` is for
that test alone; the real chains read the account every 20 seconds.

Usage:
  python3 tools/claim2_stage_command.py --stage pilot --tasks experiments/tasks/tasks_<dev>.json \\
      --fixture <dev fixture>.json --stage1-tasks experiments/tasks/tasks_<claim>.json \\
      --tag pilot-20261024 --cap 6 --stage1-cap 69 \\
      --routing '<json>' --out stage_pilot_command.txt
  python3 tools/claim2_stage_command.py --stage 1 --tasks experiments/tasks/tasks_<claim>.json \\
      --fixture <claim fixture>.json --tag claim2-stage1 --cap 69 --routing '<json>' \\
      --reading-files experiments/tasks/paraphrases_v2.json experiments/tasks/paraphrases_v3.json \\
      --out stage1_command.txt
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments"))
import paths  # noqa: E402
import stage_plan  # noqa: E402

ANALYSIS = "experiments/tasks/claim2_analysis.json"
V1 = "experiments/tasks/paraphrases_v1.json"      # the routing gate's 30 development rewordings
HAIKU = "anthropic/claude-haiku-4.5"
EXIT_PILOT_CHECK = 9
# The agent reads BROWSER_WORKER_* and BROWSER_MODEL_* before MODEL_*, and the runner refills a
# key the shell left unset from .env, so the chain unsets all six and stops if .env sets any
# (the verifier's re-check of the audit fixes, 24 October 2026). Only key names are read from
# .env, never a value.
SAMPLING_KEYS = ("BROWSER_WORKER_TEMPERATURE", "BROWSER_WORKER_TOP_P", "BROWSER_MODEL_TEMPERATURE",
                 "BROWSER_MODEL_TOP_P", "MODEL_TEMPERATURE", "MODEL_TOP_P")
EXIT_ENV_SAMPLING = 10


def header(a, est_total: float, routing: str, invocations: int, what: str, brand: str) -> list[str]:
    """The chain up to and including the `run` function: the manifest, the account at the
    start, the conditions line, the live check, the cap gate, the routing check and the
    watchdog. The same for both commands. The six sampling keys (`SAMPLING_KEYS`) are unset for
    the whole chain, so the agent's code defaults, 0.2 and 0.1, hold whatever the shell carried
    (the verifier's logic audit at cd49128), and the chain stops (exit 10) if .env sets any of
    them, since the runner would refill it; the brand's search_query rows are written to the
    manifest before and after each invocation (`terms`), since a search adds a "Related search
    terms" block to the results page."""
    env = f"IGR_ESTIMATE_USD={est_total:.2f}"
    unset = " ".join(f"-u {key}" for key in SAMPLING_KEYS)
    out = [f"caffeinate -i env {unset} {env}{routing} bash <<'CHAIN'",
           f"# The second claim run, {what}: {a.model}, {invocations} invocations. Expected ${est_total:.2f}",
           f"# at list price (the 23 October pilot's charges over {stage_plan.PILOT_PRICE_FACTOR}, a growing question",
           f"# scaled by the listings ratio to the power {a.growth:g}). Every invocation runs only if spent + 2 x its",
           f"# estimate stays under the cap ${a.cap:.2f}; a watchdog stops any run once spent reaches the cap less",
           f"# $0.30. Generated by tools/claim2_stage_command.py from {a.analysis} (stage_plan v{stage_plan.VERSION}).",
           "set -u",
           f"cd {a.root}",
           f"T={a.tasks}",
           f"F={a.analysis}",
           f"MODEL={a.model}",
           f"TAG={a.tag}",
           f"BRAND={brand}",
           "MANIFEST=experiments/results/$TAG.manifest",
           "DONE=experiments/results/$TAG.done",
           f"CAP={a.cap:.2f}",
           'rm -f "$DONE"',
           "trap 'date +%FT%T > \"$DONE\"; kill ${WATCHDOG:-} 2>/dev/null' EXIT",
           "# The runner refills a sampling key the shell left unset from .env: stop if .env sets one, in",
           "# any form python-dotenv reads (an optional 'export ', spaces around '='). Key names only are",
           "# read, never a value.",
           f"SAMPLING=$(grep -oE '^[[:space:]]*(export[[:space:]]+)?({'|'.join(SAMPLING_KEYS)})[[:space:]]*=' .env 2>/dev/null"
           " | sed -E 's/^[[:space:]]*(export[[:space:]]+)?//; s/[[:space:]]*=$//' | sort -u | tr '\\n' ' ' | sed 's/ $//')",
           f'[ -z "$SAMPLING" ] || {{ echo "STOP .env sets the sampling key(s) $SAMPLING, which the runner would refill '
           f'after the chain unset them" >> "$MANIFEST"; exit {EXIT_ENV_SAMPLING}; }}',
           "usage() {",
           "python3 - <<'PY'",
           "import sys",
           'sys.path[:0] = ["experiments", "experiments/analysis"]',
           "import cell_facts",
           "u = cell_facts.account_usage()",
           'print("None" if u is None else f"{u:.4f}")',
           "PY",
           "}",
           "START=$(usage)",
           'echo "start $(date +%FT%T) usage $START cap $CAP" >> "$MANIFEST"',
           '[ "$START" != "None" ] || { echo "STOP the account could not be read at the start" >> "$MANIFEST"; exit 4; }',
           'echo "conditions commit $(git rev-parse HEAD 2>/dev/null) browser $("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version 2>/dev/null | tr -d \'\\n\')" >> "$MANIFEST"',
           f".venv-naive/bin/python env/check_aplus_market.py --fixture {a.fixture} >> experiments/results/$TAG.livecheck 2>&1 || {{ echo \"STOP the live check failed\" >> \"$MANIFEST\"; exit 5; }}",
           "fits() {",
           "  python3 -c 'import sys; s, n, c, h = sys.argv[1:]; sys.exit(0 if \"None\" not in (s, n) and float(n) - float(s) + float(h) < float(c) else 1)' \"$START\" \"$(usage)\" \"$CAP\" \"$1\"",
           "}",
           "# The brand's search_query rows, before and after each invocation: which searches the shop",
           "# has seen, since each adds a \"Related search terms\" block to the results page.",
           "terms() {",
           "  echo \"search-terms|$1|$BRAND|$(python3 env/check_aplus_market.py --search-terms \"$BRAND\" 2>/dev/null | tr '\\t' ',' | tr '\\n' ';')|$2\" >> \"$MANIFEST\"",
           "}"]
    if routing:
        out += ["# The routing check: one DeepSeek probe on the 30 development rewordings (about $0.02);",
                "# every call must be served by a provider the routing allows, else stop before any agent runs.",
                "fits 0.10 || { echo \"STOP before the routing check\" >> \"$MANIFEST\"; exit 3; }",
                f"rprobe=$(python3 experiments/runners/parse_probe.py --questions {V1} --model $MODEL 2>&1 | tee -a \"experiments/results/$TAG.log\" | sed -n 's#^written: \\(.*\\)$#\\1#p' | tail -1)",
                "echo \"probe|$rprobe|model=$MODEL routing check\" >> \"$MANIFEST\"",
                "ROUTED=$(python3 - \"$rprobe\" <<'PY'",
                "import json, os, sys",
                "try:",
                "    rows = json.load(open(sys.argv[1]))['rows']",
                "    allowed = {p.lower() for v in json.loads(os.environ['IGR_PROVIDER_ROUTING']).values() for p in v.get('order', [])}",
                "    served = [str(r.get('provider') or r.get('served_by') or '').lower().replace(' ', '') for r in rows]",
                "    ok = rows and not any(r.get('call_failed') for r in rows) and all(s in allowed for s in served)",
                "    print('ok' if ok else 'fail ' + ','.join(sorted(set(served))))",
                "except Exception as e:",
                "    print('fail ' + type(e).__name__)",
                "PY",
                ")",
                "echo \"routing-check|$ROUTED\" >> \"$MANIFEST\"",
                "[ \"$ROUTED\" = ok ] || { echo \"STOP the routing check failed: $ROUTED\" >> \"$MANIFEST\"; exit 7; }"]
    out += [f"# The watchdog: every {a.watchdog_interval} s, stops any suite.py once spent reaches the cap less $0.30.",
            "( while [ ! -f \"$DONE\" ]; do u=$(usage); if [ \"$u\" != None ] && python3 -c \"import sys; sys.exit(0 if $u - $START >= $CAP - 0.30 - 1e-6 else 1)\"; then for p in $(pgrep -f '[Pp]ython[0-9.]* experiments/runners/suite.py'); do echo \"WATCHDOG $(date +%FT%T) spent $(python3 -c \"print(round($u-$START,4))\"): stopped pid $p\" >> \"$MANIFEST\"; pkill -TERM -P $p; kill -TERM $p; done; fi; sleep "
            f"{a.watchdog_interval}; done ) &",
            "WATCHDOG=$!",
            "run() {",
            "  arm=$1; high=$2; round=$3; shift 3",
            "  fits \"$high\" || { echo \"STOP spent + high \\$$high would reach \\$$CAP $(date +%FT%T): $arm round $round $*\" >> \"$MANIFEST\"; exit 3; }",
            "  MODEL_NAME=$MODEL python3 experiments/analysis/claim.py --protocol \"$F\" --preflight \"$arm\" --flags \"$FLAGS\" >> experiments/results/$TAG.preflight 2>&1 || { echo \"STOP preflight refused $arm\" >> \"$MANIFEST\"; exit 6; }",
            "  terms before \"$arm round $round $*\"",
            "  folder=$(MODEL_NAME=$MODEL python3 experiments/runners/suite.py --tasks \"$T\" --repeats 1 --repeat-start \"$round\" $FLAGS \"$@\" 2>&1 | tee -a \"experiments/results/$TAG.log\" | sed -n 's#^full results: \\(.*\\)/suite.json$#\\1#p' | tail -1)",
            # --repeats and --repeat-start on the line too, so a reader of the manifest alone
            # knows the round the invocation asked for (claim.intended reads --repeat-start).
            "  echo \"batch|$folder|model=$MODEL arm=$arm round=$round --repeats 1 --repeat-start $round $FLAGS $*\" >> \"$MANIFEST\"",
            "  terms after \"$arm round $round $*\"",
            "}"]
    return out


def run_lines(invocations, analysis, spec, costs) -> tuple[list[str], float]:
    """One `run` line per invocation, with its high (twice its estimate), and the sum of the
    estimates."""
    flags = {name: arm["flags"] for name, arm in analysis["arms"].items()}
    out, total = [], 0.0
    for inv in invocations:
        est = stage_plan.invocation_estimate(inv, analysis, spec, costs)
        total += est
        out.append(f"FLAGS='{flags[inv.arm]}'; run '{inv.arm}' {stage_plan.HIGH * est:.2f} {inv.round} "
                   f"--only {' '.join(inv.questions)}")
    return out, total


def voids_lines() -> list[str]:
    # Both loops read their lines by process substitution, never through a pipe: a `| while`
    # body runs in a subshell, where `exit 3` would end the loop and not the chain. Found by
    # the dry run on 24 October 2026, when a refused re-run was followed by the reading tests.
    # The commands in the loops take stdin from /dev/null so none can eat the loop's lines.
    return ["# Voids, decided from the log before any answer is judged, re-run once under the same routing.",
            "while IFS='|' read -r _ folder args; do",
            "  [ -n \"$folder\" ] && [ -d \"$folder\" ] || continue",
            "  report=$(python3 experiments/analysis/voids.py \"$folder\" </dev/null)",
            "  vflags=$(printf '%s\\n' \"$report\" | sed -n 's/^  re-run the [0-9]* void, each with \\(.*\\):$/\\1/p')",
            "  [ -n \"$vflags\" ] || continue",
            # The arm the batch line names, for the re-run's preflight (the verifier's audit at
            # cd49128: a re-run is an invocation too, checked like every other before it runs).
            "  arm=$(printf '%s' \"$args\" | sed -n 's/.* arm=\\(.*\\) round=.*/\\1/p')",
            "  while read -r only; do",
            "    fits 2.50 || { echo \"STOP before a void re-run $(date +%FT%T): $folder $only\" >> \"$MANIFEST\"; exit 3; }",
            "    MODEL_NAME=$MODEL python3 experiments/analysis/claim.py --protocol \"$F\" --preflight \"$arm\" --flags \"$vflags $only\" >> experiments/results/$TAG.preflight 2>&1 </dev/null || { echo \"STOP preflight refused the re-run of $arm\" >> \"$MANIFEST\"; exit 6; }",
            "    terms before \"re-run $arm $only\"",
            "    again=$(MODEL_NAME=$MODEL python3 experiments/runners/suite.py $vflags $only </dev/null 2>&1 | tee -a \"experiments/results/$TAG.log\" | sed -n 's#^full results: \\(.*\\)/suite.json$#\\1#p' | tail -1)",
            "    echo \"rerun|$again|$folder $only\" >> \"$MANIFEST\"",
            "    terms after \"re-run $arm $only\"",
            "  done < <(printf '%s\\n' \"$report\" | sed -n 's/^    \\(--only .*\\)$/\\1/p')",
            "done < <(grep '^batch|' \"$MANIFEST\")"]


def reading_test_lines(a, templates: list[str]) -> list[str]:
    """The reading tests after the stage's last block run and its voids: each paraphrase file
    parsed once by the run's model, then once by Haiku with the routing unset, text only, on
    the entries whose template the market holds or that have none."""
    only = " ".join(templates)
    out = ["# The reading tests (protocol, Secondary measures): after the stage's last block run and its voids,",
           "# each held-out file parsed once per model, with the brand, limit, seller and promo figure and the",
           "# page from the claim market, on the entries whose template the market holds or that have none.",
           "first_block=$(grep '^batch|' \"$MANIFEST\" | grep 'arm=the block' | cut -d'|' -f2 | grep -v '^$' | head -1)",
           "[ -n \"$first_block\" ] || { echo \"STOP no block batch for the reading test\" >> \"$MANIFEST\"; exit 8; }"]
    for model, prefix in ((a.model, ""), (a.haiku_model, "env -u IGR_PROVIDER_ROUTING ")):
        for path in a.reading_files:
            out += [f"fits 0.30 || {{ echo \"STOP before the reading test $(date +%FT%T): {model} {path}\" >> \"$MANIFEST\"; exit 3; }}",
                    f"rt=$({prefix}python3 experiments/runners/parse_probe.py --questions {path} --only-templates {only} "
                    f"--spec-from \"$T\" --page-from \"$first_block\" --model {model} 2>&1 | tee -a \"experiments/results/$TAG.log\" "
                    f"| sed -n 's#^written: \\(.*\\)$#\\1#p' | tail -1)",
                    f"echo \"reading-test|$rt|model={model} questions={path} page-from $first_block\" >> \"$MANIFEST\""]
    return out


def pilot_check_lines(a) -> list[str]:
    """The pilot check into the manifest and the summary file; exit 9 on a failed check."""
    files = " ".join(str(p) for p in a.reading_files)
    return ["# The pilot check (experiments/analysis/pilot_check.py): four rules on the records alone, never on",
            "# whether an answer is right; the summary the student reads, and the verdict into the manifest.",
            'echo "end $(date +%FT%T) usage $(usage)" >> "$MANIFEST"',
            f"python3 experiments/analysis/pilot_check.py --manifest \"$MANIFEST\" --protocol \"$F\" --pilot-tasks \"$T\" "
            f"--stage1-tasks {a.stage1_tasks} --stage1-cap {a.stage1_cap:.2f} --model $MODEL --haiku-model {a.haiku_model} "
            f"--chunk {a.chunk} --reading-files {files} > experiments/results/$TAG.summary 2>&1",
            "status=$?",
            'echo "pilot-check|$([ $status -eq 0 ] && echo PASS || echo FAIL)|experiments/results/$TAG.summary" >> "$MANIFEST"',
            f"[ $status -eq 0 ] || exit {EXIT_PILOT_CHECK}"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stage", choices=("pilot", "1"), required=True)
    ap.add_argument("--tasks", required=True, help="the task file the stage runs, under the root")
    ap.add_argument("--fixture", required=True, help="the fixture its live check reads, by name under env/fixtures or a path")
    ap.add_argument("--analysis", default=ANALYSIS, help="the analysis file, under the root")
    ap.add_argument("--model", default="deepseek/deepseek-v4-flash")
    ap.add_argument("--haiku-model", default=HAIKU)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--cap", type=float, required=True)
    ap.add_argument("--routing", default=None, help="IGR_PROVIDER_ROUTING JSON, or none")
    ap.add_argument("--chunk", type=int, default=8, help="a block invocation's most questions")
    ap.add_argument("--growth", type=float, default=1.0,
                    help="the power of the listings ratio a growing question's cost is scaled by: 1, the "
                         "default, is linear; 2 the steeper case where the re-sent context grows with every "
                         "listing opened (stage_plan.scale_for)")
    ap.add_argument("--reading-files", nargs="*", default=["experiments/tasks/paraphrases_v2.json",
                                                          "experiments/tasks/paraphrases_v3.json"],
                    help="the held-out paraphrase files the reading tests parse, under the root")
    ap.add_argument("--stage1-tasks", default=None, help="--stage pilot: the claim market's task file, for the projection")
    ap.add_argument("--stage1-cap", type=float, default=None, help="--stage pilot: stage 1's cap, for the projection")
    ap.add_argument("--root", default=str(ROOT), help="the tree the chain runs in; a stub tree for a dry run")
    ap.add_argument("--watchdog-interval", type=int, default=20, help="seconds between the watchdog's readings")
    ap.add_argument("--out", type=pathlib.Path, default=None, help="write the chain here (never over a file) and print its sha1")
    a = ap.parse_args()
    if a.stage == "pilot" and None in (a.stage1_tasks, a.stage1_cap):
        ap.error("--stage pilot needs --stage1-tasks and --stage1-cap, for the projection")

    root = pathlib.Path(a.root)
    analysis = stage_plan.load(root / a.analysis)
    spec = stage_plan.load(root / a.tasks)
    fixture = pathlib.Path(a.fixture)
    fixture = fixture if fixture.exists() else paths.FIXTURES / a.fixture
    costs = stage_plan.costs_for(fixture, growth=a.growth)
    # The routing the chain exports is held to the analysis file's for the run's model (the
    # verifier's logic audit at cd49128): another object, or none for a model the file routes,
    # is refused here, where the preflight would refuse every invocation later.
    given = json.loads(a.routing).get(a.model) if a.routing and a.routing != "none" else None
    wanted = (analysis.get("provider_routing") or {}).get(a.model)
    if given != wanted:
        ap.error(f"--routing gives {a.model} {json.dumps(given)}, where {a.analysis} requires {json.dumps(wanted)}")
    routing = ""
    if a.routing and a.routing != "none":
        routing = f" IGR_PROVIDER_ROUTING='{a.routing}'"

    if a.stage == "pilot":
        invocations = stage_plan.pilot_invocations(analysis, spec)
        extras = stage_plan.probe_estimates(0, 0)
        extras = {"routing gate": extras["routing gate"]} if routing else {}
        what = f"the pilot (tap 1) on {spec.get('brand', 'the development market')}"
    else:
        invocations = stage_plan.stage1_invocations(analysis, spec, a.model, a.chunk)
        missing = [p for p in a.reading_files if not (root / p).exists()]
        if missing:
            ap.error(f"the reading tests' files are not there: {', '.join(missing)}")
        entries = stage_plan.reading_entries([root / p for p in a.reading_files], stage_plan.templates_of(spec))
        extras = stage_plan.probe_estimates(entries, entries)
        if not routing:
            extras.pop("routing gate")
        what = f"stage 1 (tap 2) on {spec.get('brand', 'the claim market')}"
    lines, runs_total = run_lines(invocations, analysis, spec, costs)
    est_total = runs_total + sum(extras.values())

    out = header(a, est_total, routing, len(invocations), what, spec.get("brand", "")) + lines
    if a.stage == "pilot":
        out += pilot_check_lines(a)
    else:
        out += voids_lines() + reading_test_lines(a, stage_plan.templates_of(spec))
        out.append('echo "end $(date +%FT%T) usage $(usage)" >> "$MANIFEST"')
    out.append("CHAIN")
    text = "\n".join(out) + "\n"

    summary = (f"{a.stage}: {len(invocations)} invocations, runs ${runs_total:.2f}"
               + "".join(f", {name} ${value:.3f}" for name, value in extras.items())
               + f"; IGR_ESTIMATE_USD={est_total:.2f}, cap ${a.cap:.2f}, listings scale {costs.scale:.3f} "
               f"(ratio to the power {a.growth:g})")
    if a.out is not None:
        if a.out.exists():
            ap.error(f"{a.out} is already there; move it away first")
        a.out.write_text(text)
        print(f"written {a.out}, sha1 {hashlib.sha1(text.encode()).hexdigest()}", file=sys.stderr)
        print(summary, file=sys.stderr)
    else:
        print(text, end="")
        print(summary, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
