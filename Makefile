# Short names for the free commands. Every target here is free: no model is called.
#
# There is deliberately no target for a paid run. The workbench spend guard reads the
# command line, and `make run` would hide the paid script from it. Paid runs are typed in
# full, as WORKFLOW.md shows.

PY ?= python3
BATCH ?= experiments/results/20261007T112057
TASKS ?= tasks_apparel.json

.PHONY: help check check-all check-offline check-reproduction test regression mod facts compare verify dry

help:
	@echo "make check        unit tests and planner regression (no Claude dependency)"
	@echo "make check-all    make check plus the optional legacy Claude plugin tests"
	@echo "make check-offline synthetic protocol/review checks; no private logs or model calls"
	@echo "make check-reproduction curated implementation and artifact checks; no shop, API calls or private logs"
	@echo "make test         unit tests, about a minute. The figure tests need the local logs"
	@echo "make regression   the planner renders every question the same as targeting.py"
	@echo "make mod          the workbench mod's own tests (needs the claude CLI)"
	@echo "make facts        every clothing-cell figure on the results page, from the raw runs"
	@echo "make compare      the cell comparisons, with both readings of 'offer'"
	@echo "make verify BATCH=experiments/results/<stamp>   re-derive one batch, every answer in full"
	@echo "make dry TASKS=tasks_apparel.json                the exact text each task would send, sending nothing"

check: test regression

check-all: check mod

check-offline:
	$(PY) -m unittest discover -s experiments/tests -p test_hand_review_tools.py
	$(PY) -m unittest discover -s experiments/tests -p test_reader_agreement.py
	$(PY) -m unittest discover -s experiments/tests -p test_claim2_analysis.py

# Explicit selection excludes private trace replays and the locally patched submodule.
# Model calls are stubbed by these tests. Some parser regressions read public historical
# suite records; no pending study, private log or live shop is needed.
check-reproduction: check-offline regression
	PYTHONPATH=experiments/tests IGR_OFFLINE_TESTS=1 $(PY) -m unittest \
		test_form test_model_parser test_model_decline test_design_b \
		test_page.Parser test_page.EveryPage test_page.NeverTheStore \
		test_box.Classifier test_box.Planner test_box.Bodies test_box.Ambiguity \
		test_box.Decide test_box.Bypass test_box.V1Bytes test_box.NumericalAsk \
		test_box.Refusal test_box.PageRecord test_box.NoAnswerKey \
		test_reproduce_report

test:
	$(PY) -m unittest discover -s experiments/tests -t experiments/tests

regression:
	$(PY) experiments/box/planner.py --regression

mod:
	cd tools/workbench/igr-workbench && claude plugin test

facts:
	$(PY) experiments/analysis/cell_facts.py --no-account

compare:
	$(PY) experiments/analysis/compare_cells.py

verify:
	$(PY) experiments/analysis/verify_cells.py $(BATCH) --answers

dry:
	$(PY) experiments/runners/suite.py --tasks experiments/tasks/$(TASKS) --repeats 3 --dry-run

# Optional commands for private working material; absent in a clean clone.
-include Makefile.local
