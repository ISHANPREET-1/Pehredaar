PYTHON := python3

.PHONY: install test lint scan api

install:
	$(PYTHON) -m pip install -r requirements.txt -r requirements-dev.txt

test:
	PYTHONPATH=src $(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check src tests

scan:
	PYTHONPATH=src $(PYTHON) -m pehredaar.cli scan $(DOMAIN)

api:
	PYTHONPATH=src $(PYTHON) -m uvicorn pehredaar.handlers.api:app --host 127.0.0.1 --port 8000
