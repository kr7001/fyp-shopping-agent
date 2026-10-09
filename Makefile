# Short names for the free commands. Every target here is free: no model is called.
#
# There is deliberately no target for a paid run. The workbench spend guard reads the
# command line, and `make run` would hide the paid script from it. Paid runs are typed in
# full, as WORKFLOW.md shows.

PY ?= python3
BATCH ?= experiments/results/20261007T112057
TASKS ?= tasks_apparel.json

.PHONY: help check test regression mod facts compare verify dry site site-check

help:
	@echo "make check        everything below that checks code: test, regression, mod"
	@echo "make test         unit tests, about a minute. The figure tests need the local logs"
	@echo "make regression   the planner renders every question the same as targeting.py"
	@echo "make mod          the workbench mod's own tests (needs the claude CLI)"
	@echo "make facts        every clothing-cell figure on the results page, from the raw runs"
	@echo "make compare      the cell comparisons, with both readings of 'offer'"
	@echo "make verify BATCH=experiments/results/<stamp>   re-derive one batch, every answer in full"
	@echo "make dry TASKS=tasks_apparel.json                the tasks a suite would run, running nothing"
	@echo "make site         rebuild docs/site-data.js from the run files"
	@echo "make site-check   fail if docs/site-data.js is stale"

check: test regression mod

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

site:
	$(PY) docs/build_site.py

site-check:
	$(PY) docs/build_site.py --check
