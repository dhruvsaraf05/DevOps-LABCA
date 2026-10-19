.PHONY: test run docker-test docker-run

IMAGE_TEST ?= flaky-ci-test

test:
	python -m pytest

run:
	python -m uvicorn app.main:app --reload --port 8000

docker-test:
	docker build --target test -t $(IMAGE_TEST) .
	docker run --rm $(IMAGE_TEST)

docker-run:
	docker compose up --build
