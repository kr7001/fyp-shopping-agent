# experiments

Everything that asks the agent a question, scores the answer, or checks the scoring. Each
folder has one job, and one rule about money.

| Folder | What is in it | Costs money? |
| --- | --- | --- |
| `box/` | The pre-processing box, version 2 since 14 October. Before the agent starts: `page.py` fetches and parses the results page (the only file here that does I/O), `form.py` parses the question into its logical form (quantifier, objective, filters, population) by rules, or by a model through an injected call, and verifies five soundness properties, `ambiguity.py` decides whether to ask the user back, `normalise.py` (since 22 October) puts a model's form in the page's own words and holds it to the checks it must pass before the box uses it, `primitives.py` composes the retrieval from seven primitives and renders the exact text, with `targeting.py` and `planner.py` holding the frozen strategy texts and the planner's tables, and `box.py` puts them together, with the rules reading the question by default or a model with `decide(parser="model")`. None of them reads an answer key, and a test checks each. After the agent answers: `box.check` runs the primitive's own check on top of `policy.gate_from_page`, which takes the market size and the floor from the page; `sufficiency.py` holds the rules, and the older `policy.gate` takes its numbers from the answer key and is kept for the September replays | Never. No model calls inside the box |
| `runners/` | What drives an agent: `suite.py` runs a task file several times and scores it (with `--box --parser model`, a model reads each question for the box, one call per run, charged to the run), `run_browser_task.py` runs openJiuwen once, `naive_agent.py` is the second agent, `see_everything.py` is the one-setting patch for cell 2, `plan_probe.py` asks a model for a plan, `parse_probe.py` asks a model for every question's logical form and compares it with the rules', or with `--questions` holds the rules' and the model's form of each reworded question against its template's, the model's as the box would use it (the current prompt, then `normalise.py`), and since 24 October 2026 with `--only-templates` on the entries whose template the market holds, or that have none, `run.sh` runs one question | **Yes**, every script here, unless given `--dry-run` or `--help`. The spend guard refuses them without a verifier pass, a declared cost and your yes |
| `analysis/` | Reading results back: `score.py` and `trace_stats.py` (used live by the suite too), `verify_cells.py` re-derives a batch from its raw files, `compare_cells.py` and `cell_facts.py` print every clothing-cell figure (the four claim-grade cells, then the box's in-sample development cell), `replay_box.py` replays the box's own answer check over a batch's runs from the stored page record and the logs, `rescore.py` re-applies a corrected scorer, `reveal_race.py` reproduces the 60 ms reveal on the local shop. For the second claim run (24 October 2026): `stage_plan.py` holds the stage plan read from the analysis file and the task file, the question kinds and the cost table from the 23 October pilot at list price, shared by the stage command generator `tools/claim2_stage_command.py` and by `pilot_check.py`, the pilot's gate, four rules on the pilot's records alone, never on whether an answer is right | Never |
| `water/` | The first study, September 2026, on the small fixture and the two water-bottle markets (Rivenhall, Calderwood): arm comparisons, the confidence baseline, the gate replay, and the task generator for those markets. Kept so those results reproduce | Never |
| `tasks/` | The question files, each with its answer key. Generated ones say so in their `_about`. The three generated from a seed are checked byte for byte by `tests/test_catalogues.py`, and so are `tasks_apparel_v2.json` and `readings_apparel_v2.json`, the box v2 batch's questions, written by `env/generate_apparel_v2_tasks.py` from the clothing fixture and the pilot's two files. `tasks_reviews.json` is read from the live shop's database, so no test regenerates it. `readings_apparel.json` holds the scripted user's second reading of the two ambiguous clothing questions. `paraphrases_v1.json` holds thirty rewordings of the Thornwood questions, written by the verifier without looking at the rules' patterns, with no answer keys: no agent runs on them, `parse_probe.py --questions` parses them, and `tests/test_probe.py` pins them so none is edited. `tasks_aplus_dev.json` and `readings_aplus_dev.json` (22 October 2026) are the second protocol's question templates on the A+ development market (Larchmere, tees and water across two results pages), written by `env/generate_aplus_tasks.py` from `env/fixtures/aplus_dev.json` and checked byte for byte by `tests/test_aplus_market.py`. Development only: no claim is made on that market. `pilot/` (23 October 2026) holds a pilot's task files, never a claim's: `tasks_pilot_v1rw_larchmere.json` and its readings are those 15 templates and the development rewordings of `paraphrases_v1.json` re-branded to Larchmere (pv1-NN, with their templates' keys, and the ones left out listed with why in `_skipped`), written by the same generator with `--rewordings experiments/tasks/paraphrases_v1.json` and checked byte for byte by `tests/test_pilot.py`. A batch records a file there as `pilot/<name>`, its path under `tasks/`, where every reader looks | |
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
make dry TASKS=tasks_apparel.json             # the exact text each task sends, sending nothing
python3 experiments/runners/suite.py --tasks experiments/tasks/tasks_apparel.json --repeats 3 --box --reading menu --dry-run
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
