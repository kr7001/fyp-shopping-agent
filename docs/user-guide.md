# User guide

This guide separates three different kinds of reproduction. Start with the first two;
neither requires an API key or a running shop.

| Goal | What you need | What it establishes |
| --- | --- | --- |
| Check the implementation | Git checkout, Python and the listed dependencies | Synthetic checks and planner regression work on your machine |
| Recompute the headline table | Git checkout and Python's standard library | The released measurements produce the primary counts, medians and exact tests |
| Reanalyse or rerun the experiments | Original result bundle, or a configured shop, agent and paid model access | Reanalysis of recorded evidence, or a new experimental replication |

The [technical overview](index.html) explains the method. The frozen
[Claim 1](content/claim-protocol.md), [Claim 2](content/claim2-protocol.md) and
[Quenby replication](content/replication-28-oct-protocol.md) protocols specify the designs.
A successful software test does not reproduce a model's answers.

## 1. Install and run the free checks

Use Python 3.11 or later and a **Git clone** so you can record the exact revision tested.
The offline checks do not require the agent submodule to be installed. Run commands from
the repository root.

```bash
git clone https://github.com/kr7001/fyp-shopping-agent.git
cd fyp-shopping-agent
python3 -m venv .venv
.venv/bin/python -m pip install -r experiments/requirements.txt
make check-reproduction PY=.venv/bin/python
```

`make check-reproduction` runs the protocol and review-tool suites, planner regression,
selected form/parser/page-reader/block tests, and the report-metrics tests. Model calls are
stubbed. A few parser regressions read the historical suite records included in Git, but no
private trace, API key, live shop or installed agent submodule is needed.

`make check-offline` is a smaller set of three protocol/review suites; it does not check all
implementation modules. `make check` is a broader historical suite requiring some unpublished
traces. `make check-all` additionally requires the optional legacy Claude plugin. Neither is
the clean-clone entry point.

The result-reproduction command below and its own tests need only Python's standard library:

```bash
python3 -m unittest discover -s experiments/tests -p test_reproduce_report.py
```

## 2. Recompute the headline results without a model

```bash
shasum -a 256 -c experiments/artifacts/SHA256SUMS
python3 tools/reproduce_report.py
python3 tools/reproduce_report.py --json
```

The first command prints the headline table and primary tests; the second emits the same
computed results as JSON. Both are free and need no dependencies beyond Python.
The input is [report-metrics-31-oct.json](../experiments/artifacts/report-metrics-31-oct.json):
192 derived trial records covering the Wexcombe primary comparisons (including its held-out
wording test) and **both completed Quenby rounds**. It contains task IDs, arm, repeat, original
human verdict, separate automatic verdict, trial outcome, listings opened and provider
charge. No answers, browser traces, private paths or blind-review codes are included.

The command checks fixture, task and protocol hashes, then validates the complete
arm/task/repeat grids. It calculates:

| Market | Correct, block / shipped | Median listings, block / exhaustive | Median USD per trial, block / exhaustive |
| --- | --- | --- | --- |
| Wexcombe, three rounds | 21/21 / 13/21 | 5 / 45 | 0.049683 / 0.221002 |
| Quenby, two rounds | 14/14 / 9/13 | 6 / 45 | 0.046883 / 0.215486 |

Correctness uses seven shared, reading-independent templates. Quenby has 14 shipped trials,
but one answer was marked **unscorable** by the human reader and is excluded from correctness
under the frozen rule. It has not been changed to an incorrect answer. Resource comparisons
use eight gated templates, giving 24 trials per arm in Wexcombe and 16 in Quenby. Provider
charges include parsing where used, but exclude local browser and infrastructure costs.
Human correctness concerns the final committed answer, not every explanatory sentence.

The command also recomputes the prespecified two-sided exact tests:

| Test | Comparison | Wexcombe Holm p | Quenby Holm p |
| --- | --- | --- | --- |
| H1 | Model block vs shipped correctness | 0.004 | 0.0833333 |
| H2 | Model block vs exhaustive listings opened | 0.000000125 | 0.00102881 |
| H3 | Model block vs exhaustive provider charge | 0.000000767578 | 0.00193139 |
| H4 | Model vs rules on held-out wording | 0.004 | Not part of this replication |

H1 is stratified by question. H4 uses 36 held-out wordings per parser and is stratified by
template; its human-scored counts are 36/36 versus 29/36. H2 and H3 use equal-weight exact
rank tests within questions. Holm adjustment uses the complete four-test Wexcombe family
and three-test Quenby family separately. Quenby's H1 does not reach the 0.05 threshold;
that does not establish that the arms have equal accuracy. Closed slots have no human
answer grade, count as not correct for correctness, and are excluded from resource tests.

This is **reanalysis of released measurements**, not an independent audit of how raw traces
were measured or answers graded. Source SHA-256 hashes identify the preserved analyses,
completed human sheets and mappings; they do not make private evidence available. The
[artifact description](../experiments/artifacts/README.md) states its coverage and limits.
This command does not reproduce every report figure, sensitivity analysis or reader-agreement
result. It never pools the markets and does not include the pending matched-briefing study.

## 3. Rebuild the saved tasks and keys

To reproduce the accepted market, use its committed fixture. Drawing another seed produces
a different experiment. The Quenby fixture is `env/fixtures/tee_replication_28_oct.json`;
its search history is recorded in `env/manifests/tee_replication_28_oct-search.json`.

Regenerate the tasks into a temporary directory so the frozen originals remain unchanged:

```bash
TASK_CHECK_DIR=$(mktemp -d)
.venv/bin/python env/generate_aplus_tasks.py \
  --fixture env/fixtures/tee_replication_28_oct.json \
  --out "$TASK_CHECK_DIR/tasks_tee_replication_28_oct.json" \
  --readings-out "$TASK_CHECK_DIR/readings_tee_replication_28_oct.json"
cmp experiments/tasks/tasks_tee_replication_28_oct.json \
  "$TASK_CHECK_DIR/tasks_tee_replication_28_oct.json"
cmp experiments/tasks/readings_tee_replication_28_oct.json \
  "$TASK_CHECK_DIR/readings_tee_replication_28_oct.json"
```

Expected: 13 task definitions, and both `cmp` commands exit successfully without output.
Both files were checked byte-for-byte in the clean-clone validation. The replication uses
predeclared subsets of these tasks, not every task in every arm.

For a free text-only preview of the unassisted questions:

```bash
make dry PY=.venv/bin/python TASKS=tasks_tee_replication_28_oct.json
```

This previews the task file with the Makefile's three-repeat default. It is not the
replication's execution schedule and makes no model calls.

## 4. Set up the browser and agent for a new replication

Browser experiments additionally need Docker, Node.js/npm, `uv`, Google Chrome and
Playwright's Chromium. Follow the [agent instructions](../agent/README.md) to initialise
and patch the pinned submodule:

```bash
git submodule update --init agent/agent-core
git -C agent/agent-core apply --check ../openjiuwen-local.patch
git -C agent/agent-core apply ../openjiuwen-local.patch
(cd agent/agent-core && uv sync)
python3 -m venv .venv-naive
.venv-naive/bin/python -m pip install requests playwright
.venv-naive/bin/python -m playwright install chromium
```

Apply the patch once to a fresh submodule. It is the same compatibility patch in every arm,
including the shipped baseline. `.venv-naive` is also used by the block's rendered-page
reader and the live market checker; its name does not mean that a second agent is required.
The browser tool used by openJiuwen is pinned to Playwright MCP 0.0.83 in the runner.

### Start a dedicated local shop

The following commands create and modify a local benchmark shop. Use a dedicated instance
with no experiment running. They have not been executed as part of the clean-clone offline
check above.

```bash
docker pull --platform linux/amd64 am1n3e/webarena-verified-shopping
docker run -d --platform linux/amd64 --name webarena-shopping \
  -p 127.0.0.1:7770:80 -p 127.0.0.1:7771:8877 \
  am1n3e/webarena-verified-shopping
docker exec webarena-shopping supervisorctl status
docker exec webarena-shopping wget -qO- http://localhost:9200/_cluster/health
```

Wait for the services and Elasticsearch to become healthy. A storefront HTTP 200 alone
does not show that its catalogue search works. The image is amd64; Apple Silicon needs
emulation and first boot can be slow. If Elasticsearch appears stuck, check Docker Desktop's
Rosetta setting and the service logs before changing the database.

Seed the saved Quenby fixture, install the observation-gating theme and reindex:

```bash
.venv/bin/python env/seed_variants.py seed --fixture tee_replication_28_oct.json
.venv/bin/python env/install_gated_theme.py --install
docker exec webarena-shopping php /var/www/magento2/bin/magento indexer:reindex
docker exec webarena-shopping php /var/www/magento2/bin/magento cache:flush
.venv-naive/bin/python env/check_aplus_market.py --fixture tee_replication_28_oct.json
```

The checker should finish with zero failures. It checks both result pages, variant prices,
stock and labels, and that the gating check distinguishes the ordinary and gated themes.
The recorded Quenby check completed 60 checks. `--no-browser` is a partial check and is not
a substitute for this full browser check. Seeding is idempotent for existing SKUs; it does
not repair arbitrary edits to an existing product. A failed check must be resolved before
running the experiment. The [environment guide](../env/README.md) documents the mechanism
and its observation limits.

The seed tool defaults to the benchmark image's documented local test account,
`admin` / `admin1234`, at `http://localhost:7770`; its help lists overrides. Do not dump
Magento's environment configuration or API credentials into logs. The optional separate
admin container is unnecessary for these scripted storefront fixtures.

For an existing shop, `docker start webarena-shopping` starts it and the live checker above
checks the selected market. `env/start.sh` currently tests for the older Rivenhall market,
so its empty-search message is not a reliable health test for a fresh Quenby-only instance.
Use `docker stop webarena-shopping` when finished; removing the container also removes
its catalogue data unless you have arranged persistence.

### Check the frozen conditions

[claim2_replication_28_oct.json](../experiments/tasks/claim2_replication_28_oct.json)
is the machine-readable source for the arms, task sets and required versions.

| Condition | Recorded replication setting |
| --- | --- |
| Browser and parser model | `deepseek/deepseek-v4-flash` |
| Agent revision | `18d45d6e90d3735ef72c1ee9ad2467821212f7db`, plus the common local patch |
| Agent step / wall allowance | 300 steps / 1,800 seconds per trial |
| Browser sampling | temperature 0.2, top-p 0.1 |
| Parser | frozen prompt v4, temperature 0; model proposes a form, code checks it |
| Page reading | rendered results pages, including pagination |
| Provider routing | fp8; gmicloud, deepinfra, streamlake; fallbacks disabled |
| Trial schedule | 24 trials per round: shipped 7, exhaustive 8, model block 9; two rounds |

Record `git rev-parse HEAD`, `git submodule status`, the patch digest, installed package and
browser versions, and the Docker image digest with each new run. Preserve the fixture,
task, protocol and source hashes. A seed alone does not reproduce a changed generator,
agent, browser or model provider. The provider service may change despite a stable model
identifier, and new model outputs need not be byte-identical to the recorded answers.

The machine-readable schedule can be inspected without model calls:

```bash
.venv/bin/python - <<'PY_PLAN'
import json, sys
from pathlib import Path
sys.path.insert(0, 'experiments/analysis')
import stage_plan
protocol = json.loads(Path('experiments/tasks/claim2_replication_28_oct.json').read_text())
tasks = json.loads(Path('experiments/tasks/tasks_tee_replication_28_oct.json').read_text())
for item in stage_plan.stage1_invocations(protocol, tasks, 'deepseek/deepseek-v4-flash', 1):
    print(item.round, item.arm, ', '.join(item.questions))
PY_PLAN
```

Expected: 48 one-question invocations. The arm order rotates in round two. Do not replace
this with three unrestricted calls over all 13 questions: that changes the comparison.

## Paid runs and verification

All commands above are free of model charges. Docker setup and seeding still change local
state. Model-block `suite.py --dry-run` is also free, but it reads the live shop and needs
the Playwright environment; it does not test a real model parse. Keep `--dry-run` present
when inspecting a command.

Paid runs require OpenRouter credentials in an ignored local `.env`, an independently
checked exact command, a declared estimate, a budget stop and account-owner approval.
Use `.env.example` as the template. Explicitly set the model and provider routing from the
protocol; do not rely on the runner's default model. Remove inherited sampling overrides
and verify the actual recorded settings before accepting a run.

The dated `tools/guarded_replication.py` launcher was built for the authorised 28 October
runs. Its cutoff dates and private receipt/configuration are not a reusable launch service
for a fresh checkout. A new run needs a newly reviewed configuration and suitable watchdog.
Do not disable its checks to make an old command run on a different date.

The optional Claude workbench hook intercepts Claude's Bash tool only. It does not protect
Codex or arbitrary shells, and `IGR_ESTIMATE_USD` alone is not an enforced spending cap.
Record technical failures and any separately authorised retries before inspecting answers.

## Reanalyse original evidence and score new answers

Full reanalysis needs more than the metrics artifact. For each study it needs the manifest,
all referenced `suite.json` and per-trial records, raw action logs, the completed human
sheet and its code mapping. Reader-agreement analysis additionally needs the reader files.
The public checkout omits private raw logs and review files, so it cannot independently
repeat trace extraction or the entire report audit. Section 2 reproduces the released
primary comparisons without those private files. A full evidence bundle is a separate
deliverable, with consent and sanitisation required before release.

For the **original completed evidence**, restore its manifests, result folders, human sheets
and mappings to their recorded repository-relative locations first. The following commands
write new outputs to a temporary directory, leaving the originals intact:

```bash
REANALYSIS_DIR=$(mktemp -d)
.venv/bin/python experiments/analysis/claim.py \
  --protocol experiments/tasks/claim2_analysis.json \
  --hand experiments/results/claim2b-stage1.sheet.csv \
  --json "$REANALYSIS_DIR/wexcombe.json" \
  experiments/results/claim2b-stage1.manifest > "$REANALYSIS_DIR/wexcombe.txt"

.venv/bin/python -c 'import csv, runpy; csv.field_size_limit(4000000); runpy.run_path("experiments/analysis/claim.py", run_name="__main__")' \
  --protocol experiments/tasks/claim2_replication_28_oct.json \
  --hand experiments/results/claim2-replication-28-oct-both-rounds.sheet.csv \
  --json "$REANALYSIS_DIR/quenby.json" \
  experiments/results/claim2-replication-28-oct-both-rounds.manifest > "$REANALYSIS_DIR/quenby.txt"
```

The Quenby wrapper raises only the CSV reader's field-size limit because one preserved
answer exceeds Python's default. It does not truncate the answer, change its grade or
modify the frozen analysis. These commands require the private evidence; they are not
part of the clean-clone quick start. Their outputs include answer text, so keep them local.

Human primary results are under `models[model].hand_reading.tests` in the analysis JSON.
Top-level tables retain automatic scores. Do not label those automatic scores as human
verdicts. Additional human-scored sensitivities require their supplementary derivations;
`make facts` covers the earlier clothing-cell figures, not every report result.

For **new answers**, generate a fresh coded sheet from that run's manifest and protocol,
then use the [blind-reading rules](content/claim2-reading-rules.md). Keep the task/answer/key
columns and random codes unchanged. Complete the review before opening the arm mapping or
automatic analysis. The helper can create an offline reader and validate/import a downloaded
CSV without reading the mappings:

```bash
.venv/bin/python tools/hand_review.py --sheet PATH_TO_NEW_SHEET.csv \
  --output PATH_TO_NEW_READER.html
.venv/bin/python tools/hand_review.py --sheet PATH_TO_NEW_SHEET.csv \
  --import-verdicts PATH_TO_COMPLETED_DOWNLOAD.csv
```

These are explicit placeholders for a new run's paths. `tools/hand_review.py --score` is a
shortcut for the original Wexcombe sheet only. A replication requires `claim.py --protocol`
with its own configuration, completed sheet and manifest. Keep human and automatic scores
separate. Do not combine markets, models or intervention versions into one arm, or substitute a one-round summary for the planned two-round inference.

## Artifact availability

Included in the reproduction package: source code, fixed tasks and fixtures, frozen
protocols, the derived-measurements artifact and the offline commands above. Local-only:
intermediate notes, the report draft, blind review files and raw traces. A code release and
a full evidence release are different deliverables. Record `git rev-parse HEAD` when
reporting a reproduction so readers know which code and measurements were used.
