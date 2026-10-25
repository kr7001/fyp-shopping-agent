caffeinate -i env -u BROWSER_WORKER_TEMPERATURE -u BROWSER_WORKER_TOP_P -u BROWSER_MODEL_TEMPERATURE -u BROWSER_MODEL_TOP_P -u MODEL_TEMPERATURE -u MODEL_TOP_P IGR_ESTIMATE_USD=5.00 IGR_PROVIDER_ROUTING='{"deepseek/deepseek-v4-flash":{"order":["gmicloud","deepinfra","streamlake"],"allow_fallbacks":false,"quantizations":["fp8"]}}' bash <<'CHAIN'
# The second claim run, stage 1 RESUMED on Wexcombe after the 25 October 13:50 stop (the account read
# failed once, so the cap gate stopped the chain at 65 of 87 invocations, $18.59 spent). This runs the
# 22 invocations that had not started, then the voids of every batch and the reading tests, appending to
# the same manifest. The cap stays $60.00 for the whole stage, counted from the first start's usage.
# Made from claim2b-stage1.command.sh: lines 77-141 (done) dropped; START fixed; the account read retried.
set -u
cd /Users/kaironglee/projects/shopping-agent-against-information-gated-retrieval
T=experiments/tasks/tasks_tee_claim.json
F=experiments/tasks/claim2_analysis.json
MODEL=deepseek/deepseek-v4-flash
TAG=claim2b-stage1
BRAND=Wexcombe
MANIFEST=experiments/results/$TAG.manifest
DONE=experiments/results/$TAG.done
CAP=60.00
rm -f "$DONE"
trap 'date +%FT%T > "$DONE"; kill ${WATCHDOG:-} 2>/dev/null' EXIT
# The runner refills a sampling key the shell left unset from .env: stop if .env sets one, in
# any form python-dotenv reads (an optional 'export ', spaces around '='). Key names only are
# read, never a value.
SAMPLING=$(grep -oE '^[[:space:]]*(export[[:space:]]+)?(BROWSER_WORKER_TEMPERATURE|BROWSER_WORKER_TOP_P|BROWSER_MODEL_TEMPERATURE|BROWSER_MODEL_TOP_P|MODEL_TEMPERATURE|MODEL_TOP_P)[[:space:]]*=' .env 2>/dev/null | sed -E 's/^[[:space:]]*(export[[:space:]]+)?//; s/[[:space:]]*=$//' | sort -u | tr '\n' ' ' | sed 's/ $//')
[ -z "$SAMPLING" ] || { echo "STOP .env sets the sampling key(s) $SAMPLING, which the runner would refill after the chain unset them" >> "$MANIFEST"; exit 10; }
usage() {
python3 - <<'PY'
import sys, time
sys.path[:0] = ["experiments", "experiments/analysis"]
import cell_facts
for attempt in range(3):
    u = cell_facts.account_usage()
    if u is not None:
        break
    time.sleep(10)
print("None" if u is None else f"{u:.4f}")
PY
}
START=102.9550
NOW=$(usage)
[ "$NOW" != "None" ] || { echo "STOP the account could not be read at the resume" >> "$MANIFEST"; exit 4; }
echo "conditions resume $(date +%FT%T) usage $NOW start-usage $START cap $CAP commit $(git rev-parse HEAD 2>/dev/null) browser $("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version 2>/dev/null | tr -d '\n')" >> "$MANIFEST"
.venv-naive/bin/python env/check_aplus_market.py --fixture env/fixtures/tee_claim.json >> experiments/results/$TAG.livecheck 2>&1 || { echo "STOP the live check failed" >> "$MANIFEST"; exit 5; }
fits() {
  python3 -c 'import sys; s, n, c, h = sys.argv[1:]; sys.exit(0 if "None" not in (s, n) and float(n) - float(s) + float(h) < float(c) else 1)' "$START" "$(usage)" "$CAP" "$1"
}
# The brand's search_query rows, before and after each invocation: which searches the shop
# has seen, since each adds a "Related search terms" block to the results page.
terms() {
  echo "search-terms|$1|$BRAND|$(python3 env/check_aplus_market.py --search-terms "$BRAND" 2>/dev/null | tr '\t' ',' | tr '\n' ';')|$2" >> "$MANIFEST"
}
# The routing check: one DeepSeek probe on the 30 development rewordings (about $0.02);
# every call must be served by a provider the routing allows, else stop before any agent runs.
fits 0.10 || { echo "STOP before the routing check" >> "$MANIFEST"; exit 3; }
rprobe=$(python3 experiments/runners/parse_probe.py --questions experiments/tasks/paraphrases_v1.json --model $MODEL 2>&1 | tee -a "experiments/results/$TAG.log" | sed -n 's#^written: \(.*\)$#\1#p' | tail -1)
echo "probe|$rprobe|model=$MODEL routing check" >> "$MANIFEST"
ROUTED=$(python3 - "$rprobe" <<'PY'
import json, os, sys
try:
    rows = json.load(open(sys.argv[1]))['rows']
    allowed = {p.lower() for v in json.loads(os.environ['IGR_PROVIDER_ROUTING']).values() for p in v.get('order', [])}
    served = [str(r.get('provider') or r.get('served_by') or '').lower().replace(' ', '') for r in rows]
    ok = rows and not any(r.get('call_failed') for r in rows) and all(s in allowed for s in served)
    print('ok' if ok else 'fail ' + ','.join(sorted(set(served))))
except Exception as e:
    print('fail ' + type(e).__name__)
PY
)
echo "routing-check|$ROUTED" >> "$MANIFEST"
[ "$ROUTED" = ok ] || { echo "STOP the routing check failed: $ROUTED" >> "$MANIFEST"; exit 7; }
# The watchdog: every 20 s, stops any suite.py once spent reaches the cap less $0.30.
( while [ ! -f "$DONE" ]; do u=$(usage); if [ "$u" != None ] && python3 -c "import sys; sys.exit(0 if $u - $START >= $CAP - 0.30 - 1e-6 else 1)"; then for p in $(pgrep -f '[Pp]ython[0-9.]* experiments/runners/suite.py'); do echo "WATCHDOG $(date +%FT%T) spent $(python3 -c "print(round($u-$START,4))"): stopped pid $p" >> "$MANIFEST"; pkill -TERM -P $p; kill -TERM $p; done; fi; sleep 20; done ) &
WATCHDOG=$!
run() {
  arm=$1; high=$2; round=$3; shift 3
  fits "$high" || { echo "STOP spent + high \$$high would reach \$$CAP $(date +%FT%T): $arm round $round $*" >> "$MANIFEST"; exit 3; }
  MODEL_NAME=$MODEL python3 experiments/analysis/claim.py --protocol "$F" --preflight "$arm" --flags "$FLAGS" >> experiments/results/$TAG.preflight 2>&1 || { echo "STOP preflight refused $arm" >> "$MANIFEST"; exit 6; }
  terms before "$arm round $round $*"
  folder=$(MODEL_NAME=$MODEL python3 experiments/runners/suite.py --tasks "$T" --repeats 1 --repeat-start "$round" $FLAGS "$@" 2>&1 | tee -a "experiments/results/$TAG.log" | sed -n 's#^full results: \(.*\)/suite.json$#\1#p' | tail -1)
  echo "batch|$folder|model=$MODEL arm=$arm round=$round --repeats 1 --repeat-start $round $FLAGS $*" >> "$MANIFEST"
  terms after "$arm round $round $*"
}
FLAGS='--box --parser model --reading own --page-reader rendered --max-steps 300 --clock 1800'; run 'the block (model)' 0.58 3 --only tee-xs-price tee-promo-check decline-delivery decline-fit decline-scarcity
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-headline
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-target-price
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-cheapest-target
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-all-stocked
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-count-stocked
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-count-buyable
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-exists-under
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-top-3
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-xs-price
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only tee-promo-check
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only decline-delivery
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only decline-fit
FLAGS='--max-steps 300 --clock 1800'; run 'shipped' 0.31 3 --only decline-scarcity
FLAGS='--exhaustive --exhaustive-wording product --max-steps 300 --clock 1800'; run 'open everything (product)' 1.22 3 --only tee-target-price
FLAGS='--exhaustive --exhaustive-wording product --max-steps 300 --clock 1800'; run 'open everything (product)' 1.22 3 --only tee-cheapest-target
FLAGS='--exhaustive --exhaustive-wording product --max-steps 300 --clock 1800'; run 'open everything (product)' 1.22 3 --only tee-all-stocked
FLAGS='--exhaustive --exhaustive-wording product --max-steps 300 --clock 1800'; run 'open everything (product)' 1.22 3 --only tee-count-stocked
FLAGS='--exhaustive --exhaustive-wording product --max-steps 300 --clock 1800'; run 'open everything (product)' 1.22 3 --only tee-count-buyable
FLAGS='--exhaustive --exhaustive-wording product --max-steps 300 --clock 1800'; run 'open everything (product)' 1.22 3 --only tee-exists-under
FLAGS='--exhaustive --exhaustive-wording product --max-steps 300 --clock 1800'; run 'open everything (product)' 1.22 3 --only tee-top-3
FLAGS='--exhaustive --exhaustive-wording product --max-steps 300 --clock 1800'; run 'open everything (product)' 1.22 3 --only tee-xs-price
# Voids, decided from the log before any answer is judged, re-run once under the same routing.
while IFS='|' read -r _ folder args; do
  [ -n "$folder" ] && [ -d "$folder" ] || continue
  report=$(python3 experiments/analysis/voids.py "$folder" </dev/null)
  vflags=$(printf '%s\n' "$report" | sed -n 's/^  re-run the [0-9]* void, each with \(.*\):$/\1/p')
  [ -n "$vflags" ] || continue
  arm=$(printf '%s' "$args" | sed -n 's/.* arm=\(.*\) round=.*/\1/p')
  while read -r only; do
    fits 2.50 || { echo "STOP before a void re-run $(date +%FT%T): $folder $only" >> "$MANIFEST"; exit 3; }
    MODEL_NAME=$MODEL python3 experiments/analysis/claim.py --protocol "$F" --preflight "$arm" --flags "$vflags $only" >> experiments/results/$TAG.preflight 2>&1 </dev/null || { echo "STOP preflight refused the re-run of $arm" >> "$MANIFEST"; exit 6; }
    terms before "re-run $arm $only"
    again=$(MODEL_NAME=$MODEL python3 experiments/runners/suite.py $vflags $only </dev/null 2>&1 | tee -a "experiments/results/$TAG.log" | sed -n 's#^full results: \(.*\)/suite.json$#\1#p' | tail -1)
    echo "rerun|$again|$folder $only" >> "$MANIFEST"
    terms after "re-run $arm $only"
  done < <(printf '%s\n' "$report" | sed -n 's/^    \(--only .*\)$/\1/p')
done < <(grep '^batch|' "$MANIFEST")
# The reading tests (protocol, Secondary measures): after the stage's last block run and its voids,
# each held-out file parsed once per model, with the brand, limit, seller and promo figure and the
# page from the claim market, on the entries whose template the market holds or that have none.
first_block=$(grep '^batch|' "$MANIFEST" | grep 'arm=the block' | cut -d'|' -f2 | grep -v '^$' | head -1)
[ -n "$first_block" ] || { echo "STOP no block batch for the reading test" >> "$MANIFEST"; exit 8; }
fits 0.30 || { echo "STOP before the reading test $(date +%FT%T): deepseek/deepseek-v4-flash experiments/tasks/paraphrases_v2.json" >> "$MANIFEST"; exit 3; }
rt=$(python3 experiments/runners/parse_probe.py --questions experiments/tasks/paraphrases_v2.json --only-templates tee-headline tee-target-price tee-cheapest-target tee-all-stocked tee-count-stocked tee-count-buyable tee-exists-under tee-top-3 tee-xs-price tee-promo-check decline-delivery decline-fit decline-scarcity --spec-from "$T" --page-from "$first_block" --model deepseek/deepseek-v4-flash 2>&1 | tee -a "experiments/results/$TAG.log" | sed -n 's#^written: \(.*\)$#\1#p' | tail -1)
echo "reading-test|$rt|model=deepseek/deepseek-v4-flash questions=experiments/tasks/paraphrases_v2.json page-from $first_block" >> "$MANIFEST"
fits 0.30 || { echo "STOP before the reading test $(date +%FT%T): deepseek/deepseek-v4-flash experiments/tasks/paraphrases_v3.json" >> "$MANIFEST"; exit 3; }
rt=$(python3 experiments/runners/parse_probe.py --questions experiments/tasks/paraphrases_v3.json --only-templates tee-headline tee-target-price tee-cheapest-target tee-all-stocked tee-count-stocked tee-count-buyable tee-exists-under tee-top-3 tee-xs-price tee-promo-check decline-delivery decline-fit decline-scarcity --spec-from "$T" --page-from "$first_block" --model deepseek/deepseek-v4-flash 2>&1 | tee -a "experiments/results/$TAG.log" | sed -n 's#^written: \(.*\)$#\1#p' | tail -1)
echo "reading-test|$rt|model=deepseek/deepseek-v4-flash questions=experiments/tasks/paraphrases_v3.json page-from $first_block" >> "$MANIFEST"
fits 0.30 || { echo "STOP before the reading test $(date +%FT%T): anthropic/claude-haiku-4.5 experiments/tasks/paraphrases_v2.json" >> "$MANIFEST"; exit 3; }
rt=$(env -u IGR_PROVIDER_ROUTING python3 experiments/runners/parse_probe.py --questions experiments/tasks/paraphrases_v2.json --only-templates tee-headline tee-target-price tee-cheapest-target tee-all-stocked tee-count-stocked tee-count-buyable tee-exists-under tee-top-3 tee-xs-price tee-promo-check decline-delivery decline-fit decline-scarcity --spec-from "$T" --page-from "$first_block" --model anthropic/claude-haiku-4.5 2>&1 | tee -a "experiments/results/$TAG.log" | sed -n 's#^written: \(.*\)$#\1#p' | tail -1)
echo "reading-test|$rt|model=anthropic/claude-haiku-4.5 questions=experiments/tasks/paraphrases_v2.json page-from $first_block" >> "$MANIFEST"
fits 0.30 || { echo "STOP before the reading test $(date +%FT%T): anthropic/claude-haiku-4.5 experiments/tasks/paraphrases_v3.json" >> "$MANIFEST"; exit 3; }
rt=$(env -u IGR_PROVIDER_ROUTING python3 experiments/runners/parse_probe.py --questions experiments/tasks/paraphrases_v3.json --only-templates tee-headline tee-target-price tee-cheapest-target tee-all-stocked tee-count-stocked tee-count-buyable tee-exists-under tee-top-3 tee-xs-price tee-promo-check decline-delivery decline-fit decline-scarcity --spec-from "$T" --page-from "$first_block" --model anthropic/claude-haiku-4.5 2>&1 | tee -a "experiments/results/$TAG.log" | sed -n 's#^written: \(.*\)$#\1#p' | tail -1)
echo "reading-test|$rt|model=anthropic/claude-haiku-4.5 questions=experiments/tasks/paraphrases_v3.json page-from $first_block" >> "$MANIFEST"
echo "end $(date +%FT%T) usage $(usage)" >> "$MANIFEST"
CHAIN
