install:
	python -m pip install -r requirements-dev.txt

lint:
	ruff check .

test:
	pytest -q

check: lint test
	python -m compileall -q .

run:
	uvicorn app:app --reload --port 8787

docker:
	docker compose up --build
