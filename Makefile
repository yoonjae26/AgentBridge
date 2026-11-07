PYTHON ?= python
PYTEST_ARGS ?=

.PHONY: install lint format typecheck test check bench-smoke bench-controls clean

install:
	$(PYTHON) -m pip install -e ".[dev]"

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests

format:
	$(PYTHON) -m ruff format src tests
	$(PYTHON) -m ruff check --fix src tests

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest -p no:cacheprovider $(PYTEST_ARGS)

coverage:
	$(PYTHON) -m pytest -p no:cacheprovider --cov=agentbridge --cov-report=term-missing $(PYTEST_ARGS)

check: lint typecheck test

bench-smoke:
	$(PYTHON) -m agentbridge benchmark run smoke -c mock-oracle -c mock-noop

bench-controls:
	$(PYTHON) -m agentbridge benchmark run core -c mock-oracle -c mock-noop -c antigravity-remote

clean:
	$(PYTHON) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('build', 'dist', 'htmlcov')]"
