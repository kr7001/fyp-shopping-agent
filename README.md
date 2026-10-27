# Retrieval Policies for Shopping Agents

**A question-aware retrieval policy for shopping facts hidden behind product options.**

Final Year Project · NUS Data Science and Analytics · August–November 2026

**Student:** Kayleen Lee Kai Rong · **Supervisor:** A/Prof. Markus Kirchberg

A product card may advertise “from $10” while the requested size costs $18 or is sold out.
This project investigates that gap between the first observation and the information a
shopping question actually needs. It extends the openJiuwen browser agent with a retrieval
block and evaluates it on a self-hosted WebArena-Verified shop with reproducible variant prices.

[Project overview](docs/index.html) · [Implementation guide](experiments/README.md) ·
[Experimental protocols](docs/content/claim2-protocol.md) · [Research record](docs/archive/README.md)

## Quick start: free checks

Use Python 3.11 or later. These checks use synthetic data and need neither an API key nor a shop.

```bash
git clone https://github.com/kr7001/fyp-shopping-agent.git
cd fyp-shopping-agent
python3 -m venv .venv
.venv/bin/python -m pip install -r experiments/requirements.txt
make check-offline PY=.venv/bin/python
```

For browser experiments, follow the [environment setup](docs/guides/environment-setup.md)
and [pinned agent setup](agent/README.md). They additionally require Docker, Node.js/npm,
`uv`, Playwright and the local agent patch. The storefront runs at `http://localhost:7770`.
The private report PDF is not distributed in this repository.

## Research question

Can an agent retrieve the facts needed for a shopping question more accurately than the
shipped agent, while spending less than opening every listing? When a question is ambiguous
or asks for information the shop does not provide, the policy should clarify or decline.

The registered title is *Ambiguity Without Adversary, Why Injection Defences Miss a Common
Agent Failure in Commerce*. The motivating failure needs no injected instruction. This
project evaluates retrieval policies; it does not experimentally evaluate injection defences.

## How it works

1. Read the question and rendered search-result pages.
2. Parse the question into a structured form, using rules or a model with validation and fallback.
3. Ask for clarification, decline an unsupported attribute, or construct a retrieval plan.
4. Give openJiuwen the plan: select the requested options, read their revealed prices and stock,
   and stop when the question's evidence requirements are met.

For minimum-price questions, an advertised lower bound can rule out listings that cannot beat
an observed candidate. This guarantee requires valid bounds, the correct interpretation and
faithful execution. The agent can still misread a page or fail to follow the plan.

## Evaluation and current evidence

The comparison conditions are shipped openJiuwen, an open-everything instruction, and the block
with rules or model parsing. They share a pinned agent version and the documented local
compatibility patch. Seeded fixtures, answer keys, version checks and recorded costs support
reproduction; ambiguous questions are scored under the reading actually used.

- [Claim 1 protocol](docs/content/claim-protocol.md): the earlier held-out clothing-market study.
- [Claim 2 protocol](docs/content/claim2-protocol.md): the frozen tee-market design, hypotheses,
  exclusions and amendments.
- [Blind scoring rules](docs/content/claim2-reading-rules.md): human scoring with automatic
  scores and a separate reader-agreement analysis alongside it.

**Status, 27 October 2026:** the second claim run has finished execution; its human scoring
is still in progress. Its accuracy conclusions are not yet final. Historical checkpoint
figures are retained with their original context in the archive.

The second experiment is a constrained stress test: it combines hidden variant prices with
deliberately false promotional/stock labels, and only the block receives a label warning.
The generator selects markets with useful bounds. Findings concern that distribution and the
whole block package, not typical-market prevalence or the stopping rule alone. Shipping,
combined discounts and automated access to live commercial shops are outside this evaluation.

## Repository structure

```text
agent/                 Pinned openJiuwen submodule and compatibility patch
experiments/box/        Question interpretation, retrieval plans and checks
experiments/runners/    Browser execution and experiment orchestration
experiments/analysis/   Scoring, costs, statistical comparisons and audits
experiments/tasks/      Versioned task definitions and answer keys
experiments/tests/      Unit, synthetic and historical regression checks
experiments/results/   Recorded experiment artifacts used for reproduction
env/                   Magento fixtures, generators, seeding and live checks
docs/content/          Protocols and research specifications
docs/guides/           Setup and contribution guides
docs/archive/          Dated checkpoints and the research decision log
notes/                 Supporting research notes and current review materials
tools/                 Blind-review helper and experiment tooling
```

## Reproducing and checking the work

| Command | Purpose |
| --- | --- |
| `make check-offline` | Synthetic protocol, blind-review and reader-agreement checks |
| `make check` | Full unit suite and planner regression; some tests require local historical logs |
| `make check-all` | Full checks plus the optional legacy Claude plugin tests |
| `make dry TASKS=tasks_apparel.json` | Print the planned task text without making model calls |
| `make facts` | Recompute the original clothing-cell figures from local traces |

The [experiment guide](experiments/README.md) describes data layout and analysis commands.
Raw browser traces, credentials, assistant state and the private report remain local; a clone
does not contain every trace needed by the full historical checks. Recorded result paths and
frozen experiment code are retained so this cleanup does not break their provenance.

Paid runs use OpenRouter and require a declared estimate, budget stop, verified command and
explicit approval. The optional Claude workbench hook is specific to Claude; it does not
protect other clients automatically. See [WORKFLOW.md](WORKFLOW.md).

## Research provenance and acknowledgements

The [decision log](docs/archive/research-log.md), [lessons](LESSONS.md),
[market ledger](docs/content/market-ledger.md) and [research notes](notes/README.md) explain the
choices and corrections behind the work. They are supporting evidence, separate from this overview.

The student directs the research and is responsible for the submitted work. Claude Code assisted
with much of the implementation, experiments and documentation. Codex assisted with review,
report wording, blind-review tooling and repository maintenance. Human review of the second
claim's answers is pending; AI assistance is not presented as independent human validation.

The environment extension has been proposed in
[WebArena-Verified issue #60](https://github.com/ServiceNow/webarena-verified/issues/60).
No upstream PR has been merged. openJiuwen and the Magento-derived template retain their
upstream licence notices; this repository does not currently provide a project-wide licence.
