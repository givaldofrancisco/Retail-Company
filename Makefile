.PHONY: setup setup-poetry test qa-gate docker-build

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

setup-poetry:
	poetry install

docker-build:
	docker build -t retail-assistant:latest .

test:
	@if [ -d ".venv" ]; then \
		.venv/bin/python run_tests.py; \
	else \
		poetry run python run_tests.py; \
	fi

qa-gate:
	@if [ -d ".venv" ]; then \
		.venv/bin/python -m src.evaluation.qa_gate; \
	else \
		poetry run python -m src.evaluation.qa_gate; \
	fi
