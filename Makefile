.PHONY: test test-n run docker-test docker-run clean-results

IMAGE_TEST ?= flaky-ci-test
N ?= 10

# run-1 ... run-N. The sequence comes from Python so this works with cmd.exe and sh alike.
RUNS := $(addprefix run-,$(shell python -c "print(*range(1,$(N)+1))"))
.PHONY: $(RUNS)

test:
	python -m pytest

# Run the suite N times (random order each time), one JUnit XML per run in results/.
# The leading '-' keeps going when a run fails: failures are the data we want.
test-n: clean-results $(RUNS)

clean-results:
	python -c "import shutil; shutil.rmtree('results', ignore_errors=True)"

$(RUNS): run-%:
	-python -m pytest --junitxml=results/run-$*.xml -q

run:
	python -m uvicorn app.main:app --reload --port 8000

docker-test:
	docker build --target test -t $(IMAGE_TEST) .
	docker run --rm $(IMAGE_TEST)

docker-run:
	docker compose up --build
