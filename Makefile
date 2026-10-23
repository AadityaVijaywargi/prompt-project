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

.PHONY: setup test data-check qc-export qc-import budget budget-pilot pilot \
        run-e1 run-e2 run-e2b run-e3 run-e5 stats app reproduce

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

run-e5 stats app:
	@echo "'$@' is built in Phase 3 (brief section 11); not available yet." && exit 1

# Regenerate everything from cached responses with no network access.
reproduce: data-check
	$(PY) -m lb.runners.e1_pointwise --offline $(ARGS)
	$(PY) -m lb.runners.e2_pairwise --offline $(ARGS)
	$(PY) -m lb.runners.e3_wrong --offline $(ARGS)
