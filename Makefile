PYTHON ?= python
PYTEST_ARGS ?=

.PHONY: install lint format typecheck test check bench-smoke bench-controls clean

install:
	$(PYTHON) -m pip install -e ".[dev]" -e packages/agentbridge-bench

lint:
	$(PYTHON) -m ruff check src packages tests
	$(PYTHON) -m ruff format --check src packages tests

format:
	$(PYTHON) -m ruff format src packages tests
	$(PYTHON) -m ruff check --fix src packages tests

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest -p no:cacheprovider $(PYTEST_ARGS)

coverage:
	$(PYTHON) -m pytest -p no:cacheprovider --cov=agentbridge --cov=agentbridge_bench --cov-report=term-missing $(PYTEST_ARGS)

check: lint typecheck test

bench-smoke:
	$(PYTHON) -m agentbridge_bench.cli run smoke -c mock-oracle -c mock-noop

bench-controls:
	$(PYTHON) -m agentbridge_bench.cli run core -c mock-oracle -c mock-noop -c antigravity-remote

clean:
	$(PYTHON) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('build', 'dist', 'htmlcov')]"
