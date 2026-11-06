# Retrieval Policies for Shopping Agents

**A question-aware retrieval policy for shopping facts hidden behind product options.**

Final Year Project · NUS Data Science and Analytics · August–November 2026

**Student:** Lee Kai Rong · **Supervisor:** A/Prof. Markus Kirchberg

A product card may advertise “from $10” while the requested size costs $18 or is sold out.
This project investigates that gap between the first observation and the information a
shopping question actually needs. It extends the openJiuwen browser agent with a retrieval
block and evaluates it on a self-hosted WebArena-Verified shop with reproducible variant prices.

[User guide](docs/user-guide.md) · [Experimental protocol](docs/content/claim2-protocol.md)

## Quick start: free checks

Use Python 3.11 or later. These checks use synthetic inputs and released records, and need neither an API key nor a shop.

```bash
git clone https://github.com/kr7001/fyp-shopping-agent.git
cd fyp-shopping-agent
python3 -m venv .venv
.venv/bin/python -m pip install -r experiments/requirements.txt
make check-reproduction PY=.venv/bin/python
```

To recompute the primary Wexcombe and two-round Quenby results without installing dependencies:

```bash
python3 tools/reproduce_report.py
```

This reproduces counts, medians and exact tests from [192 released measurements](experiments/artifacts/README.md). It does not independently audit raw traces or human grading.

For browser experiments, follow the [environment setup](docs/user-guide.md)
and [pinned agent setup](agent/README.md). They additionally require Docker, Node.js/npm,
`uv`, Playwright and the local agent patch. The storefront runs at `http://localhost:7770`.
The final report is submitted separately and is not included in this repository.

## What the project found

- **RQ1, what gating looks like.** A hand check of 12 clothing listings on Shopee, Lazada and
  Amazon, picked for their varying prices, found 11 that hid some variants' prices until those
  variants were chosen (final report, Section 3.4). Every
  listing opened on one variant and showed that variant's price.
- **RQ2, why the shipped agent misses it.** On the design market Thornwood, openJiuwen as
  shipped, with Claude Haiku 4.5, answered correctly in 4 of 15 runs and never said it had not retrieved enough. Its
  card reader skips the cards outside the browser window without saying so. Turning that limit
  off raised correct answers to 11 of 15, at almost three times the cost.
- **RQ3, the retrieval block.** The block turns the question into a checked description of what
  to find, asks the shopper back when a word is ambiguous, and hands openJiuwen a plan. For the
  cheapest price, the plan opens listings by advertised price until no unopened one can be
  cheaper.

## Results at a glance

Primary studies, each on a held-out market drawn after its protocol was frozen. One row is one
study and one model. Rows are never pooled. Accuracy is on the questions whose answer does not
depend on how an ambiguous word is read. Listings and charge are medians per run on the
questions that need gated information. Each cell gives the block first, then the comparison,
with the exact test's Holm-adjusted *p* within the study.

| Study, market, model | Scored by | Correct: block vs shipped | Listings opened: block vs open everything | Charge a run: block vs open everything |
| --- | --- | --- | --- | --- |
| Claim 1, Ashcombe (15 listings), Claude Haiku 4.5 | automatic scorer | 12/12 vs 4/12, *p* = .0010 | 6 vs 15, *p* = .0005 | $0.197 vs $0.405, *p* = 4.9e-5 |
| Claim 1, Ashcombe, DeepSeek V4 Flash | automatic scorer | 12/12 vs 5/12, *p* = .005 | 6 vs 15, *p* = .002 | $0.028 vs $0.109, *p* = 4.9e-5 |
| Claim 2, Wexcombe (45 listings, two pages), DeepSeek V4 Flash | blind human reading | 21/21 vs 13/21, *p* = .004 | 5 vs 45, *p* = 1.3e-7 | $0.0497 vs $0.2210, *p* = 7.7e-7 |
| Replication, Quenby (45 listings), DeepSeek V4 Flash | blind human reading | 14/14 vs 9/13, *p* = .083, not significant | 6 vs 45, *p* = .0010 | $0.047 vs $0.215, *p* = .0019 |

On Wexcombe the model-parsing block asked the shopper back on 13 of 14 questions labelled
ambiguous and on 1 of 68 labelled clear, where neither baseline asked. It also read held-out
shopper wordings better than the rule-based parser: 36/36 against 29/36 correct (*p* = .004). The gap is not conclusive once
the ambiguous templates are removed. Count questions leave nothing to prune, so there the block
opens as much as exhaustive retrieval.

Supplementary studies are small. All but one are descriptive, with no significance test.
Browser Use on the fresh market Rookmere had one test, fixed before that market was drawn:

| Study | Result | Protocol |
| --- | --- | --- |
| Matched briefing, Quenby, 16 trials | Full block 8 of 8 correct. openJiuwen given the same facts without the plan 7 of 8, a difference the pre-set rule calls no observable difference. The block cost more in every pair. Final report, Section 8.4 | [protocol](docs/content/matched-briefing-29-oct-protocol.md) |
| Browser Use transfer, Quenby | Browser Use with the block 6 of 8, then 14 of 16 in two added repeats. Browser Use alone 3 of 8, then 7 of 16. Final report, Section 8.5 | [protocol](docs/content/browser-use-transfer-31-oct-protocol.md), [repeats](docs/content/browser-use-repeat-1-nov-protocol.md) |
| Matched briefing, fresh market Rookmere, 16 trials | Complete, graded blind. Full block 5 of 8 correct, one miss a timeout. The factual briefing 7 of 8, including one count trial run again on the student's ruling after the study's own budget stop ended its first start, and 6 of 7 without it. On the three cheapest M the briefing's lead of two is beyond the pre-set margin. In the pairs both arms got right the block saved little. Final report, Section 8.4 | [protocol](fresh-market-protocol/protocol.md), [plan B](fresh-market-protocol/analysis-plan-B.md) |
| Browser Use transfer, fresh market Rookmere | Complete, graded blind. Browser Use with the block 14 of 15 correct, alone 8 of 14, *p* = .014. Three of 32 planned slots were technical voids. One sensitivity analysis gave *p* = .083. Final report, Section 8.5 | [protocol](fresh-market-protocol/protocol.md), [plan A](fresh-market-protocol/analysis-plan-A.md) |

How to reproduce:

- Wexcombe and Quenby, from the released measurements, with no dependencies:
  `python3 tools/reproduce_report.py`.
- Claim 1, from the recorded runs: `python3 experiments/analysis/claim.py --json claim1.json
  experiments/results/claim-20261020.manifest` (Haiku), and the same with
  `night-20261020.manifest` (DeepSeek). These need the raw browser logs, which are not in the
  repository (see [Reproducing and checking the work](#reproducing-and-checking-the-work)).
- Wexcombe's ask-back counts, from the recorded runs: `python3 experiments/analysis/claim.py
  --json wexcombe-asks.json --protocol experiments/tasks/claim2_analysis.json
  experiments/results/claim2b-stage1.manifest`. The counts are in `wexcombe-asks.json`, under
  the model's `secondary` entry, in `asks_by_label`. Like Claim 1, this needs the raw browser logs.
- Thornwood's cells behind RQ2, from the recorded runs: `make facts`. This also needs the raw
  browser logs.
- The run records and manifests of the openJiuwen studies are in `experiments/results/`. The
  Browser Use run records stay local.

## Research question

Can an agent retrieve the facts needed for a shopping question more accurately than the
shipped agent, while spending less than opening every listing? When a question is ambiguous
or asks for information the shop does not provide, the policy should clarify or decline.

The project's full title is *Retrieval Policies for Shopping Agents Under Interaction-Gated
Information*.

## How it works

1. Read the question and rendered search-result pages.
2. Parse the question into a structured form, using rules or a model with validation and fallback.
3. Ask for clarification, decline an unsupported attribute, or construct a retrieval plan.
4. Give openJiuwen the plan: select the requested options, read their revealed prices and stock,
   and stop when the question's evidence requirements are met.

For minimum-price questions, an advertised lower bound can rule out listings that cannot beat
an observed candidate. This guarantee requires valid bounds, the correct interpretation and
faithful execution. The agent can still misread a page or fail to follow the plan.

## Evaluation

The comparison conditions are shipped openJiuwen, an open-everything instruction, and the block
with rules or model parsing. They share a pinned agent version and the documented local
compatibility patch. Seeded fixtures, answer keys, version checks and recorded costs support
reproduction. Ambiguous questions are scored under the reading actually used.

- [Claim 1 protocol](docs/content/claim-protocol.md): the earlier held-out clothing-market study.
- [Claim 2 protocol](docs/content/claim2-protocol.md): the frozen tee-market design, hypotheses,
  exclusions and amendments.
- [Blind scoring rules](docs/content/claim2-reading-rules.md): human scoring with automatic
  scores and a separate reader-agreement analysis alongside it. The file's title still says
  “(DRAFT)”. It was frozen with the claim 2 protocol before any grading, and later studies
  check its hash, so the title was not edited. The rules have not changed since.

The [Quenby replication protocol](docs/content/replication-28-oct-protocol.md) extends the test to a second held-out market. The [released primary analyses](experiments/artifacts/README.md) retain the original human verdicts and automatic scores separately, and analyse the markets separately.

The supplementary studies have their own dated protocols, each frozen before its runs:

- [Matched briefing](docs/content/matched-briefing-29-oct-protocol.md): the full block against
  openJiuwen given the same facts without the plan, on Quenby.
- [Browser Use transfer](docs/content/browser-use-transfer-31-oct-protocol.md), with its
  [pilot recovery](docs/content/browser-use-pilot-recovery-1-nov-protocol.md),
  [overnight](docs/content/browser-use-overnight-1-nov-protocol.md),
  [monitored](docs/content/browser-use-monitored-1-nov-protocol.md),
  [repeat](docs/content/browser-use-repeat-1-nov-protocol.md) and
  [repeat recovery](docs/content/browser-use-repeat-recovery-1-nov-protocol.md) protocols: the
  unchanged block in front of a second browser agent.
- [Fresh market](fresh-market-protocol/protocol.md), with analysis plans
  [A](fresh-market-protocol/analysis-plan-A.md) and [B](fresh-market-protocol/analysis-plan-B.md):
  both supplementary studies repeated unchanged on a newly drawn market, Rookmere (seed 1002).

The second experiment is a constrained stress test: it combines hidden variant prices with
deliberately false promotional/stock labels, and only the block receives a label warning.
The generator selects markets with useful bounds. Findings concern that distribution and the
block as a whole. They do not show how common the problem is in typical markets or the effect
of the stopping rule alone. Shipping, combined discounts and automated access to live
commercial shops are outside this evaluation.

## Repository structure

```text
agent/                 Pinned openJiuwen submodule and compatibility patch
experiments/box/        Question interpretation, retrieval plans and checks
experiments/runners/    Browser execution and experiment orchestration
experiments/analysis/   Scoring, costs, statistical comparisons and audits
experiments/tasks/      Versioned task definitions and answer keys
experiments/tests/      Unit, synthetic and historical regression checks
experiments/results/   Historical experiment records
experiments/artifacts/ Sanitized measurements for reproducing primary results
env/                   Magento fixtures, generators, seeding and live checks
docs/user-guide.md     Setup, execution and reproduction guide
docs/content/          Frozen protocols and scoring rules
fresh-market-protocol/  Frozen protocol and analysis plans of the fresh-market studies
tools/                 Blind review, guarded launchers and analyses of the later studies
tools/workbench/       Optional Claude Code plugin that gated paid runs
LICENSE                Apache License 2.0 for the project's own code
```

`fresh-market-protocol/` holds the frozen protocol and two analysis plans of the fresh-market
studies, with a short README. They were committed under `notes/fresh-market-2-nov/` before the
market was drawn and moved here afterwards with the same bytes. The market's seed-search record,
the matched-briefing task file and the run records still cite that original path, with SHA-256
hashes that the moved files match, and `git log --follow` shows the move. Working notes, the
report source and the assistants' files stay local.

## Reproducing and checking the work

| Command | Purpose |
| --- | --- |
| `python3 tools/reproduce_report.py` | Recompute primary counts, medians and exact tests without dependencies |
| `make check-reproduction` | Curated implementation, protocol, review-tool and released-artifact checks. The entry point for a clean clone |
| `make check-offline` | Synthetic protocol, blind-review and reader-agreement checks |
| `make check` | Full unit suite and planner regression. It also needs the openJiuwen submodule with its local patch applied and a `.env` file, and some tests need local historical logs |
| `make check-all` | Full checks plus the optional legacy Claude plugin tests |
| `make dry TASKS=tasks_apparel.json` | Print the planned task text without making model calls |
| `make facts` | Recompute the original clothing-cell figures from local traces |

The [experiment guide](experiments/README.md) describes data layout and analysis commands.
Raw browser traces, credentials, assistant state and the private report remain local. A clone
does not contain every trace needed by the full historical checks. Result paths recorded in
the run records are unchanged, and most run manifests name the commit they ran at, so the
exact code of a run can be checked out from the history. Comments in some run code were tidied
after the runs without changing what the code does, so a file's hash at the latest commit can
differ from the hash a run recorded.

Paid runs use OpenRouter and require a declared estimate, budget stop, verified command and
explicit approval. The optional Claude workbench hook is specific to Claude Code and does not
protect other clients automatically. See the [user guide](docs/user-guide.md#paid-runs-and-verification).

## Research provenance and acknowledgements

The frozen protocols, task definitions and recorded experiment artifacts support the research
claims. Personal planning notes, meeting updates and intermediate drafts are kept locally.

The student directs the research and is responsible for the submitted work. Claude Code assisted
with much of the implementation, experiments and documentation. Codex assisted with review,
report wording, blind-review tooling and repository maintenance. The student graded every
human-scored answer blind. A classmate independently graded 62 of them with the same rubric and
answer keys: all 32 answers where the student's grade and the automatic scorer disagreed, and
30 agreements sampled at random, across Wexcombe and Quenby. The two readers agreed on all 62.
This targeted check does not estimate reliability over all answers. AI assistance is not
presented as independent human validation.

The environment extension was proposed in
[WebArena-Verified issue #60](https://github.com/ServiceNow/webarena-verified/issues/60) and
offered as [pull request #61](https://github.com/ServiceNow/webarena-verified/pull/61), which
is open and not merged.

## Licence

Copyright 2026 Lee Kai Rong. The project's own code and documentation are released
under the [Apache License 2.0](LICENSE), the licence openJiuwen uses. Third-party parts keep
their own licences: the openJiuwen submodule in `agent/agent-core` (Apache 2.0) and the
Magento-derived template in `env/gated_theme/`, whose OSL-3.0 and AFL-3.0 notice is kept in the
file.
