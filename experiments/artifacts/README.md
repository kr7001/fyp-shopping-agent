# Released measurements

`report-metrics-31-oct.json` contains derived measurements for the report's primary
Wexcombe and Quenby comparisons. Recompute the results from the repository root:

```bash
shasum -a 256 -c experiments/artifacts/SHA256SUMS
python3 tools/reproduce_report.py
python3 tools/reproduce_report.py --json
python3 -m unittest discover -s experiments/tests -p test_reproduce_report.py
```

Python 3.11 or later is sufficient. These commands need no API key, model, browser,
shop, private trace or third-party package. The [user guide](../../docs/user-guide.md)
covers the wider implementation checks and the requirements for a new experiment.

## Coverage

| Dataset | Template-comparison rows | Held-out wording rows | Primary tests |
| --- | ---: | ---: | --- |
| Wexcombe | 72 (three rounds) | 72 (36 questions, two parsers, one round) | H1, H2, H3, H4 |
| Quenby | 48 (two rounds) | 0 | H1, H2, H3 |

Rows are the union of the primary comparisons, not every trial in the study.
The full Wexcombe study also includes controls, keyless questions and other arms
outside this release. No pending matched-briefing data is included.

## Fields and provenance

Each row has an arm, task ID and repeat, together with:

- `hand_verdict`: the student's original completed verdict, either `correct`,
  `not correct` or `unscorable`. It is null for a slot closed before an answer was
  produced. That null is not an AI-generated human grade.
- `automatic_verdict`: the frozen analysis's automatic verdict, kept separately.
- `outcome`: whether an answer was produced or the block closed the slot.
- `opened`: measured distinct product listings opened, using the original analysis.
- `cost_usd`: provider charges for the completed trial, including parsing where used.
  Local infrastructure and interrupted-attempt costs are outside this measure.

The exported source analysis files were `claim2b-stage1.analysis.json` and
`claim2-replication-28-oct-both-rounds.hand.analysis.json`. Human verdicts were joined
from their completed `.sheet.csv` files using the retained private code mappings and
`(batch, task, repeat)`. Only the fields above were exported. The file records SHA-256
hashes of each source analysis, human sheet and mapping. These private source hashes
are provenance records, not publicly downloadable evidence.

Fixture, task and protocol files are public. Their hashes are checked at runtime,
and the expected arm/task/repeat grids are derived from those frozen definitions.
The script uses human correctness for inference, excludes human-unscorable answers
from correctness, and treats a closed slot as not correct under the original rule.
Closed slots are excluded from resource comparisons. The original automatic verdict
never replaces the human verdict.

The exact-test code is a standard-library implementation of the definitions in
`experiments/analysis/compare_cells.py::stratified_exact` and
`experiments/analysis/claim.py::stratified_rank_test`. The tests cover known conditional
and rank-test cases, ties, the complete Holm family, invalid grids and source hashes,
and agreement with the original primary-analysis values. H1 is stratified by question;
H4 by template. H2 and H3 use equal weights with tied values assigned mid-ranks.
The markets have separate Holm families of four and three tests.

## What this can and cannot reproduce

The release reproduces primary human-scored counts, medians and inferential tests
from the released measurements. It does not independently validate trace extraction,
human judgment, technical exclusions or the absence of experimental leakage. It does
not reproduce the entire report, every sensitivity analysis or reader agreement.
A complete raw-evidence audit requires the original private traces and review records.

Quenby has one original human-unscorable answer: the shipped correctness denominator
is 13 assessable answers out of 14 trials. The post hoc analysis counting this answer
as incorrect is a sensitivity analysis, not the primary result in this package.
The 192 rows contain no answers, browser logs, private paths or blind-review codes.
