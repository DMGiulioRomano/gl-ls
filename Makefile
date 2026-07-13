VENV := .venv
PY := $(VENV)/bin/python
PIP := $(VENV)/bin/pip

.PHONY: help venv install tests unit-tests e2e-tests run clean

help:
	@echo "Target disponibili:"
	@echo "  make install     - crea il venv e installa gl-ls in editable (+dev)"
	@echo "  make tests       - tutta la suite (unit + e2e)"
	@echo "  make unit-tests  - solo unit test"
	@echo "  make e2e-tests   - solo e2e (protocollo LSP su subprocess)"
	@echo "  make run         - avvia il server su stdio (debug)"
	@echo "  make clean       - rimuove venv e artefatti"

$(VENV)/bin/glls:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"

venv: $(VENV)/bin/glls

install: venv

tests: venv
	$(PY) -m pytest tests -q

unit-tests: venv
	$(PY) -m pytest tests/unit -q

e2e-tests: venv
	$(PY) -m pytest tests/e2e -q

run: venv
	$(VENV)/bin/glls

clean:
	rm -rf $(VENV) build dist *.egg-info src/*.egg-info .pytest_cache
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
