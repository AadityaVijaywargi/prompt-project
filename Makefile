# On Windows run with `mingw32-make <target>` (or install GNU make). Extra flags go in ARGS,
# e.g.  make run-e1 ARGS="--pilot --yes"
ifeq ($(OS),Windows_NT)
PY ?= .venv/Scripts/python.exe
else
PY ?= .venv/bin/python
endif
export PYTHONIOENCODING := utf-8
export PYTHONUTF8 := 1
ARGS ?=

.PHONY: setup test data-check qc-export qc-import budget budget-pilot pilot pilot-report \
        run-e1 run-e2 run-e2b run-e3 run-a run-e5 stats stats-b stats-a stats-e5 package app reproduce reproduce-pilot

setup:
	uv venv --python 3.12 .venv
	uv pip install --python $(PY) -e ".[dev]"

test:
	$(PY) -m pytest -q

data-check:
	$(PY) -m lb.data_check

qc-export:
	$(PY) -m lb.qc export

qc-import:
	$(PY) -m lb.qc import data/qc/to_verify.csv

budget:
	$(PY) -m lb.budget $(ARGS)

budget-pilot:
	$(PY) -m lb.budget --pilot $(ARGS)

# Phase 0 pilot: E1 + E2 on the pilot judges. Prints the budget; add ARGS=--yes to actually call judges.
pilot:
	$(PY) -m lb.runners.e1_pointwise --pilot $(ARGS)
	$(PY) -m lb.runners.e2_pairwise --pilot $(ARGS)

run-e1:
	$(PY) -m lb.runners.e1_pointwise $(ARGS)

run-e2:
	$(PY) -m lb.runners.e2_pairwise $(ARGS)

run-e2b:
	$(PY) -m lb.runners.e2_pairwise --e2b $(ARGS)

run-e3:
	$(PY) -m lb.runners.e3_wrong $(ARGS)

# Gap A: verified wrong twins scored pointwise in all four forms (E1 rubric and prompt)
run-a:
	$(PY) -m lb.runners.a_wrong_pointwise $(ARGS)

# E1-E3 tables per analysis/plan.md -> results/tables/main_<variant>_*, results/thresholds.json
stats:
	$(PY) -m lb.analysis $(ARGS)

# Section B (post hoc): criterion leakage and judge-comment coding -> results/tables/main_<variant>_b*
stats-b:
	$(PY) -m lb.leakage $(ARGS)

# Gap A: error-detection leniency on wrong twins -> results/tables/main_<variant>_a*
stats-a:
	$(PY) -m lb.wrong_leniency $(ARGS)

# E5: one variant per run on the 60-item subset, e.g. make run-e5 ARGS="--variant bias_aware --yes"
run-e5:
	$(PY) -m lb.runners.e5_mitigation $(ARGS)

# E5 tables (each variant vs baseline, plus majority vote) -> results/tables/main_e5*
stats-e5:
	$(PY) -m lb.mitigation $(ARGS)

# Re-audit zip of every tracked file -> dist/lb-auditor_<date>.zip (refuses uncommitted changes)
package:
	$(PY) scripts/package.py $(ARGS)

app:
	@echo "'$@' is built in Phase 3 (brief section 11); not available yet." && exit 1

# Regenerate every main-study call from cached responses with no network access (judges with no logged
# main-study run are skipped; any other cache miss is an error). Then rebuild the tables with the stats targets.
reproduce: data-check
	$(PY) -m lb.runners.e1_pointwise --offline $(ARGS)
	$(PY) -m lb.runners.e2_pairwise --offline $(ARGS)
	$(PY) -m lb.runners.e3_wrong --offline $(ARGS)
	$(PY) -m lb.runners.a_wrong_pointwise --offline $(ARGS)

pilot-report:
	$(PY) scripts/pilot_report.py $(ARGS)

reproduce-pilot: data-check
	$(PY) -m lb.runners.e1_pointwise --pilot --offline $(ARGS)
	$(PY) -m lb.runners.e2_pairwise --pilot --offline $(ARGS)
	$(PY) scripts/pilot_report.py $(ARGS)
