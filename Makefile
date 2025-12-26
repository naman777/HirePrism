PYTHON=.venv/bin/python
PIP=.venv/bin/pip
STREAMLIT=.venv/bin/streamlit
PYTEST=.venv/bin/pytest

install:
	$(PIP) install -e .

profile:
	$(PYTHON) -m src.ingestion.load_json

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

app:
	$(STREAMLIT) run src/app/main.py

test:
	$(PYTEST) --cov=src

lint:
	.venv/bin/ruff check .
	.venv/bin/black --check .

format:
	.venv/bin/ruff check . --fix
	.venv/bin/black .