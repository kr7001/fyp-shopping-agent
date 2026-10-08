# How the work is done

Five modules in Claude Code, one job each, set up on 8 October 2026 after weeks of work that
drifted from the objective and spent credit without warning. Each module hands to the next,
and nothing reaches a paid model, a document or the site without passing the one before it.

## The five modules

| Module | Where | Its job | It writes | It never |
| --- | --- | --- | --- | --- |
| Main conversation | the session you talk to | Plans with you, splits the work, sends each piece to the right module, holds the work to `OBJECTIVE.md` | plans, `PARKED.md` | skips the verifier, or starts a paid run without your yes |
| coder | `.claude/agents/coder.md` | Every code change, with tests where each rule must fire and stay quiet, then a commit | `experiments/`, `env/`, `tools/`, `docs/build_site.py` | runs a paid script, touches `agent/agent-core`, commits a credential |
| verifier | `.claude/agents/verifier.md` | Fairness, bugs and figures, checked against the raw files. PASS or FAIL with evidence | only the stamp, through `tools/verification_stamp.py` | edits code, results or documents |
| insights | `.claude/agents/insights.md` | Verified results into findings, each with the command that reproduces it. Keeps the site and the decision log current | `docs/content/`, `README.md`, `docs/site-data.js` through `make site` | types a number by hand, or pools across markets, models or agents |
| workbench mod | `tools/workbench/` | Puts the north star in every prompt, flags a turn that drifts, refuses paid commands, keeps `/objective`, `/park` and `/guard` | `PARKED.md`, the spend ledger in `.verification/` | lets a paid run through without an estimate, `caffeinate -i`, a fresh stamp and your yes |

## The order

1. **Objective.** Every task names the part of `OBJECTIVE.md` it serves. Anything else goes to
   `PARKED.md` with `/park <idea>`.
2. **Code.** The coder changes code, runs `make check`, and commits.
3. **Verify.** The verifier checks the commit: the diff, the tests, the dry runs, fairness.
   Before a paid run it states the exact command and, on a pass, stamps it.
4. **Paid run.** Only with a declared cost, under `caffeinate -i`, at the stamped commit, and
   after you say yes in the guard's dialog.
5. **Verify the outputs.** Every answer read in full, the suspended run rule, cost against the
   account, figures re-derived from the raw files.
6. **Insights.** Findings, the site and the decision log, from verified results only.

## Commands every module uses

```bash
make check                     # unit tests, planner regression, the mod's tests. Free
make facts                     # every published figure, from the raw runs. Free
make verify BATCH=experiments/results/<stamp>   # one batch re-derived, every answer printed
make dry TASKS=tasks_apparel.json               # what a batch would send, sending nothing
make site                      # rebuild docs/site-data.js from the repository
make site-check                # fail if the site is stale
```

A paid run is always typed in full, because the guard reads the command line. The Makefile
has no paid target for that reason.

```bash
IGR_ESTIMATE_USD=<dollars> caffeinate -i python3 experiments/runners/suite.py \
    --tasks experiments/tasks/<file>.json --repeats 3
```

## Keeping the site current

The site is `docs/index.html`. Its numbers, tables and code excerpts come from
`docs/site-data.js`, which `docs/build_site.py` writes. Nobody edits figures in the page.

| To change | Edit | Then |
| --- | --- | --- |
| A result | the run files, through a verified batch. A new cell goes into `compare_cells.CELLS` (coder) | `make site` |
| The weekly record, the plan, the open problems | `docs/content/weeks.md`, `plan.md`, `open-problems.md` (insights) | `make site` |
| The objective, the lessons, parked ideas | `OBJECTIVE.md`, `LESSONS.md`, `PARKED.md` | `make site` |
| The market ledger | its table in `README.md` | `make site` |
| A new kind of figure or table | `cell_facts.facts()` or `docs/build_site.py` (coder), then the page (insights) | `make site` |

The verifier runs `make site-check` and checks any new claim against the command that
reproduces it. The source and `docs/site-data.js` are committed together, with a dated
entry in the README decision log.

## Rules every module follows

- `LESSONS.md` lists every mistake already paid for and who prevents it now. Read it before
  starting. Add to it whenever a new mistake is found.
- No credentials in the repository, no HAR files, no DOM dumps. Never commit `agent/agent-core`,
  so stage files by name.
- A claim about code cites the file and line. A number in a document has a command that
  reproduces it.
- The box may use only what the agent could see: the question and the pages. Never a fixture,
  an answer key or `_instance`.
