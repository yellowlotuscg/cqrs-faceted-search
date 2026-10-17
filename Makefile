.PHONY: seed test run rebuild bench web-build bicep-build

PYTHON ?= python3.12

seed:
	PYTHONPATH=src $(PYTHON) scripts/seed.py

test:
	PYTHONPATH=src $(PYTHON) -m pytest

run:
	PYTHONPATH=src $(PYTHON) -m uvicorn catalog.api:app --reload

rebuild:
	PYTHONPATH=src $(PYTHON) -m catalog rebuild

bench:
	PYTHONPATH=src $(PYTHON) scripts/bench.py

web-build:
	cd web && npm ci && npm run build && npm test

bicep-build:
	bicep build infra/main.bicep
