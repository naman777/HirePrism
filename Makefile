PYTHON=.venv/bin/python
PIP=.venv/bin/pip
STREAMLIT=.venv/bin/streamlit
PYTEST=.venv/bin/pytest
PROFILE_PYTHON=$(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,.venv/bin/python)

install:
	$(PIP) install -e .

profile:
	$(PROFILE_PYTHON) -m src.ingestion.load_json

flatten:
	$(PROFILE_PYTHON) -m src.ingestion.flatten_offers

clean_data:
	$(PROFILE_PYTHON) -m src.cleaning.build_clean

quality:
	$(PROFILE_PYTHON) -m src.quality.scorer

db:
	$(PROFILE_PYTHON) -m src.modeling.build_tables

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
