.PHONY: install test run docker

install:
	python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt

test:
	.venv/bin/pytest -q

run:
	.venv/bin/uvicorn app.main:app --reload --port 8080

docker:
	docker compose up -d --build
