# experiments

Everything that asks the agent a question, scores the answer, or checks the scoring. Each
folder has one job, and one rule about money.

| Folder | What is in it | Costs money? |
| --- | --- | --- |
| `box/` | The pre-processing box. `targeting.py` and `planner.py` decide what to retrieve from the question, before any page is opened, and never read an answer key. `sufficiency.py` and `policy.py` judge whether a finished answer is supported by what the run saw, and today read the answer key's market size and floor, so they are evaluation tools until box v1 takes both from the page | Never. No model calls |
| `runners/` | What drives an agent: `suite.py` runs a task file several times and scores it, `run_browser_task.py` runs openJiuwen once, `naive_agent.py` is the second agent, `see_everything.py` is the one-setting patch for cell 2, `plan_probe.py` asks a model for a plan, `run.sh` runs one question | **Yes**, every script here, unless given `--dry-run` or `--help`. The spend guard refuses them without a verifier pass, a declared cost and your yes |
| `analysis/` | Reading results back: `score.py` and `trace_stats.py` (used live by the suite too), `verify_cells.py` re-derives a batch from its raw files, `compare_cells.py` and `cell_facts.py` print every published figure, `rescore.py` re-applies a corrected scorer, `reveal_race.py` reproduces the 60 ms reveal on the local shop | Never |
| `water/` | The first study, September 2026, on the small fixture and the two water-bottle markets (Rivenhall, Calderwood): arm comparisons, the confidence baseline, the gate replay, and the task generator for those markets. Kept so those results reproduce | Never |
| `tasks/` | The question files, each with its answer key. Generated ones say so in their `_about` and are checked byte for byte by `tests/test_catalogues.py` | |
| `tests/` | Unit tests, `make test` from the repository root | Never |
| `results/` | One folder per batch: `suite.json`, one record per run, and the raw log of each run. Logs are gitignored, about 1.7 GB, and stay on the laptop | |
| `runs/` | Single runs made outside a batch | |

`paths.py` holds every location in one place. A script reaches it, and through it every
other folder, with two lines at the top:

```python
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import paths
```

The two runners that need their own interpreter, `run_browser_task.py` (uv, inside
`agent/agent-core`) and `naive_agent.py` (`.venv-naive`), find their folders directly and do
not import it.

## The everyday commands

```bash
make check                                    # unit tests, planner regression, mod tests
make facts                                    # every clothing-cell figure on the results page
python3 experiments/analysis/verify_cells.py experiments/results/<batch> --answers
python3 experiments/runners/suite.py --tasks experiments/tasks/tasks_apparel.json --repeats 3 --dry-run
```

A paid run is typed in full, because the spend guard reads the command line:

```bash
IGR_ESTIMATE_USD=<dollars> caffeinate -i python3 experiments/runners/suite.py \
    --tasks experiments/tasks/tasks_apparel.json --repeats 3
```

## Where things were before 8 October 2026

Until 8 October 2026 every script and task file sat directly in `experiments/`. The decision
log, the notes and the archived pages quote commands from that time. Read them with this
table. `suite.py` also accepts an old `--tasks experiments/tasks_*.json` path and says where
it read the file from instead.

| Old path | New path |
| --- | --- |
| `experiments/targeting.py`, `planner.py`, `policy.py`, `sufficiency.py` | `experiments/box/` |
| `experiments/suite.py`, `run_browser_task.py`, `naive_agent.py`, `see_everything.py`, `plan_probe.py`, `run.sh` | `experiments/runners/` |
| `experiments/score.py`, `trace_stats.py`, `verify_cells.py`, `compare_cells.py`, `cell_facts.py`, `rescore.py`, `reveal_race.py` | `experiments/analysis/` |
| `experiments/arms.py`, `headline.py`, `replay_gate.py`, `confidence_curve.py`, `backfill_draw.py`, `make_scaled_tasks.py` | `experiments/water/` |
| `experiments/tasks*.json` | `experiments/tasks/` |

The move changed no behaviour. Before and after, 34 free commands were run and their
output compared line by line: every figure script, every dry run, the planner regression,
the catalogue generators and the mod tests. All 34 matched, apart from the clock times in
openJiuwen's own start-up log.
