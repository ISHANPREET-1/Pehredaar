PYTHON := python3

.PHONY: install test lint scan

install:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

test:
	PYTHONPATH=src $(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests

scan:
	PYTHONPATH=src $(PYTHON) -m pehredaar.cli scan $(DOMAIN)
