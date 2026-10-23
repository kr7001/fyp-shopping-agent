"""Emit a claim stage's command from the protocol (moved from a scratchpad on 24 October 2026).

Written for the A+ design (tee and water). Its mechanics were dry-run by the verifier on 23 October
(order, flags, preflight under the run's model, exit codes 3-8, the routing gate, the watchdog,
the voids loop, the reading test). The tee-only redesign of 24 October must adapt its question
lists, cost table and pilot gate before use (docs/content/claim2-handover.md).

The emitted text is what the verifier checks and the guard sees; this script only writes it.
Usage:
  python3 make_stage1.py --tasks experiments/tasks/tasks_<market>.json --fixture <fixture.json> \
      --model deepseek/deepseek-v4-flash --tag claim2-stage1 --cap 70 \
      --held-rounds 1 [--routing '<json>'] > stage1_command.txt
"""
import argparse
import json
import pathlib

ROOT = pathlib.Path("/Users/kaironglee/projects/shopping-agent-against-information-gated-retrieval")
F = "experiments/tasks/claim2_analysis.json"

TEMPLATES = ["tee-headline", "tee-target-price", "tee-cheapest-target", "tee-all-stocked",
             "tee-count-stocked", "tee-count-buyable", "tee-exists-under", "tee-top-3",
             "water-target-price", "water-cheapest-target", "water-all-stocked",
             "water-count-buyable", "water-best-per-litre", "decline-delivery", "decline-taste"]
GATED = [t for t in TEMPLATES if t not in ("tee-headline", "decline-delivery", "decline-taste")]

# Pilot costs per block run on Larchmere (DeepSeek, model parser, pilot's provider prices).
BOX_PILOT = {"tee-headline": 0.036, "tee-target-price": 0.273, "tee-cheapest-target": 0.226,
             "tee-all-stocked": 0.025, "tee-count-stocked": 0.027, "tee-count-buyable": 0.474,
             "tee-exists-under": 0.032, "tee-top-3": 0.032, "water-target-price": 0.612,
             "water-cheapest-target": 0.112, "water-all-stocked": 0.048,
             "water-count-buyable": 0.215, "water-best-per-litre": 0.977,
             "decline-delivery": 0.001, "decline-taste": 0.001}
# Open everything, unmeasured on two pages: 1.3 x the dearer of the question's block cost and
# its product's count plan; shipped at the verifier's $0.33.
def oe_est(q):
    base = BOX_PILOT["tee-count-buyable"] if q.startswith("tee") else BOX_PILOT["water-target-price"]
    return round(1.3 * max(BOX_PILOT[q], base), 3)
SHIPPED_EST = 0.33
HIGH = 2.0          # each invocation's high is twice its estimate at the pilot's prices


def product(q):
    return "tee" if q.startswith("tee") or q == "decline-delivery" else "water"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--fixture", required=True)
    ap.add_argument("--model", default="deepseek/deepseek-v4-flash")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--cap", type=float, required=True)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--held-rounds", type=int, nargs="*", default=[1])
    ap.add_argument("--routing", default=None, help="IGR_PROVIDER_ROUTING JSON, or none")
    ap.add_argument("--held-prefix", default="rw-", help="id prefix of the held-out rewordings")
    a = ap.parse_args()

    arms = json.loads((ROOT / F).read_text())["arms"]
    flags = {name: arm["flags"] for name, arm in arms.items()}
    tasks_by_id = {t["id"]: t for t in json.loads((ROOT / a.tasks).read_text())["tasks"]}
    held = [tid for tid in tasks_by_id if tid.startswith(a.held_prefix)]
    import re
    def template_of(tid):
        if tasks_by_id[tid].get("template"):
            return tasks_by_id[tid]["template"]
        m = re.search(r"of ([a-z0-9-]+) \(paraphrases", tasks_by_id[tid].get("note", ""))
        if not m:
            raise SystemExit(f"no template found in {tid}'s note")
        return m.group(1)
    held_by_product = {p: [t for t in held if tasks_by_id[t].get("product") == p] for p in ("tee", "water")}

    # (arm, label, est, only-list) per invocation, rounds rotated as the protocol says.
    order = [["shipped", "open everything (product)", "the block (rules)", "the block (model)"],
             ["open everything (product)", "the block (rules)", "the block (model)", "shipped"],
             ["the block (rules)", "the block (model)", "shipped", "open everything (product)"]]
    invocations = []
    for r in range(1, a.rounds + 1):
        for arm in order[(r - 1) % 3]:
            if arm == "shipped":
                for q in TEMPLATES:
                    invocations.append((r, arm, SHIPPED_EST, [q]))
            elif arm.startswith("open everything"):
                for q in GATED:
                    invocations.append((r, arm, oe_est(q), [q]))
            else:
                for p in ("tee", "water"):
                    qs = [q for q in TEMPLATES if product(q) == p]
                    invocations.append((r, arm, sum(BOX_PILOT[q] for q in qs), qs))
                    if r in a.held_rounds and held_by_product[p]:
                        # each kept rewording at its template's pilot cost
                        est = sum(BOX_PILOT.get(template_of(t), 0.25) for t in held_by_product[p])
                        invocations.append((r, arm, est, held_by_product[p]))
    est_total = sum(e for _, _, e, _ in invocations) + (0.05 if a.routing and a.routing != "none" else 0.02)

    env = f"IGR_ESTIMATE_USD={est_total:.2f}"
    routing = ""
    if a.routing and a.routing != "none":
        json.loads(a.routing)
        routing = f" IGR_PROVIDER_ROUTING='{a.routing}'"
    out = [f"caffeinate -i env {env}{routing} bash <<'CHAIN'",
           f"# The second claim run, stage {a.tag}: {a.model}, {len(invocations)} invocations, rounds {a.rounds},",
           f"# held-out rewordings in rounds {a.held_rounds}. Expected ${est_total:.2f} at the pilot's provider prices;",
           f"# every invocation runs only if spent + 2 x its estimate stays under the cap ${a.cap:.2f}; a watchdog",
           "# stops any run once spent reaches the cap less $0.30. Generated by tools/claim2_stage_command.py.",
           "set -u",
           f"cd {ROOT}",
           f"T={a.tasks}",
           f"F={F}",
           f"MODEL={a.model}",
           f"TAG={a.tag}",
           "MANIFEST=experiments/results/$TAG.manifest",
           "DONE=experiments/results/$TAG.done",
           f"CAP={a.cap:.2f}",
           'rm -f "$DONE"',
           "trap 'date +%FT%T > \"$DONE\"; kill ${WATCHDOG:-} 2>/dev/null' EXIT",
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
           'echo "conditions commit $(git rev-parse HEAD) browser $("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version | tr -d \'\\n\')" >> "$MANIFEST"',
           f".venv-naive/bin/python env/check_aplus_market.py --fixture {a.fixture} >> experiments/results/$TAG.livecheck 2>&1 || {{ echo \"STOP the live check failed\" >> \"$MANIFEST\"; exit 5; }}",
           "fits() {",
           "  python3 -c 'import sys; s, n, c, h = sys.argv[1:]; sys.exit(0 if \"None\" not in (s, n) and float(n) - float(s) + float(h) < float(c) else 1)' \"$START\" \"$(usage)\" \"$CAP\" \"$1\"",
           "}",
           "# The routing check, when routing is on: one DeepSeek probe on the 30 development rewordings",
           "# (about $0.02); every call must be served by a provider the routing allows, else stop.",
           *([
             "fits 0.10 || { echo \"STOP before the routing check\" >> \"$MANIFEST\"; exit 3; }",
             "rprobe=$(python3 experiments/runners/parse_probe.py --questions experiments/tasks/paraphrases_v1.json --model $MODEL 2>&1 | tee -a \"experiments/results/$TAG.log\" | sed -n 's#^written: \\(.*\\)$#\\1#p' | tail -1)",
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
             "[ \"$ROUTED\" = ok ] || { echo \"STOP the routing check failed: $ROUTED\" >> \"$MANIFEST\"; exit 7; }",
           ] if routing else []),
           "# The watchdog: stops any suite.py once spent reaches the cap less $0.30.",
           "( while [ ! -f \"$DONE\" ]; do u=$(usage); if [ \"$u\" != None ] && python3 -c \"import sys; sys.exit(0 if $u - $START >= $CAP - 0.30 - 1e-6 else 1)\"; then for p in $(pgrep -f 'bin/python3 experiments/runners/suite.py'); do echo \"WATCHDOG $(date +%FT%T) spent $(python3 -c \"print(round($u-$START,4))\"): stopped pid $p\" >> \"$MANIFEST\"; pkill -TERM -P $p; kill -TERM $p; done; fi; sleep 20; done ) &",
           "WATCHDOG=$!",
           "run() {",
           "  arm=$1; high=$2; round=$3; shift 3",
           "  fits \"$high\" || { echo \"STOP spent + high \\$$high would reach \\$$CAP $(date +%FT%T): $arm round $round $*\" >> \"$MANIFEST\"; exit 3; }",
           "  MODEL_NAME=$MODEL python3 experiments/analysis/claim.py --protocol \"$F\" --preflight \"$arm\" --flags \"$FLAGS\" >> experiments/results/$TAG.preflight 2>&1 || { echo \"STOP preflight refused $arm\" >> \"$MANIFEST\"; exit 6; }",
           "  folder=$(MODEL_NAME=$MODEL python3 experiments/runners/suite.py --tasks \"$T\" --repeats 1 --repeat-start \"$round\" $FLAGS \"$@\" 2>&1 | tee -a \"experiments/results/$TAG.log\" | sed -n 's#^full results: \\(.*\\)/suite.json$#\\1#p' | tail -1)",
           "  echo \"batch|$folder|model=$MODEL arm=$arm round=$round $FLAGS $*\" >> \"$MANIFEST\"",
           "}"]
    for r, arm, est, qs in invocations:
        out.append(f"FLAGS='{flags[arm]}'; run '{arm}' {HIGH * est:.2f} {r} --only {' '.join(qs)}")
    out += ["# Voids, decided from the log before any answer is judged, re-run once (as the pilot's chain).",
            "grep '^batch|' \"$MANIFEST\" | while IFS='|' read -r _ folder args; do",
            "  [ -n \"$folder\" ] && [ -d \"$folder\" ] || continue",
            "  report=$(python3 experiments/analysis/voids.py \"$folder\")",
            "  vflags=$(printf '%s\\n' \"$report\" | sed -n 's/^  re-run the [0-9]* void, each with \\(.*\\):$/\\1/p')",
            "  [ -n \"$vflags\" ] || continue",
            "  printf '%s\\n' \"$report\" | sed -n 's/^    \\(--only .*\\)$/\\1/p' | while read -r only; do",
            "    fits 2.50 || { echo \"STOP before a void re-run $(date +%FT%T): $folder $only\" >> \"$MANIFEST\"; exit 3; }",
            "    again=$(MODEL_NAME=$MODEL python3 experiments/runners/suite.py $vflags $only 2>&1 | tee -a \"experiments/results/$TAG.log\" | sed -n 's#^full results: \\(.*\\)/suite.json$#\\1#p' | tail -1)",
            "    echo \"rerun|$again|$folder $only\" >> \"$MANIFEST\"",
            "  done",
            "done",
            "# The reading test (protocol, Secondary measures): after the stage's last block run and its voids,",
            "# the 36 held-out entries parsed once, with the brand, limit and page from the claim market.",
            "fits 0.10 || { echo \"STOP before the reading test $(date +%FT%T)\" >> \"$MANIFEST\"; exit 3; }",
            "first_block=$(grep '^batch|' \"$MANIFEST\" | grep 'arm=the block' | cut -d'|' -f2 | grep -v '^$' | head -1)",
            "[ -n \"$first_block\" ] || { echo \"STOP no block batch for the reading test\" >> \"$MANIFEST\"; exit 8; }",
            "rt=$(python3 experiments/runners/parse_probe.py --questions experiments/tasks/paraphrases_v2.json --spec-from \"$T\" --page-from \"$first_block\" --model $MODEL 2>&1 | tee -a \"experiments/results/$TAG.log\" | sed -n 's#^written: \\(.*\\)$#\\1#p' | tail -1)",
            "echo \"reading-test|$rt|model=$MODEL page-from $first_block\" >> \"$MANIFEST\"",
            "echo \"end $(date +%FT%T) usage $(usage)\" >> \"$MANIFEST\"",
            "CHAIN"]
    print("\n".join(out))


if __name__ == "__main__":
    main()
