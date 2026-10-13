# CLAUDE.md

College DevOps mini project (KJSCE, Sem VII, LAB CA). Full plan is in `PLAN.md`; read it before starting any phase and follow it exactly. Work one phase at a time.

## What this is
A CI/CD pipeline that detects flaky tests by running a pytest suite 10 times in parallel Docker containers on GitHub Actions, classifies each test (stable / flaky / broken), auto-quarantines flaky ones via `quarantine.json` + a bot PR, blocks the build only on broken tests, then pushes the runtime image to GHCR (release artifact) → deploys the same commit to Vercel via the Vercel CLI → smoke-tests `/version` for the commit SHA.

## Stack
Python 3.12 · FastAPI · pytest + pytest-randomly · ruff · Docker (multi-stage: base → test → runtime, non-root) · GitHub Actions · GHCR · Vercel Hobby (FastAPI as a serverless function, `app` instance in `app/main.py`). Everything must stay free.

## Commands
- `make test`: run tests once (quarantine applied as xfail)
- `make test-n N=10`: run N times, JUnit XML to `results/`
- `python tools/flaky_detector.py --results results/ --quarantine quarantine.json --out-json report.json --out-md report.md --write-quarantine quarantine.new.json`
- `docker compose up`: run app on :8000
- `ruff check .` and `pytest tools/`: lint + detector tests

## Rules
- `tools/flaky_detector.py` uses the stdlib only. Keep it readable; it will be explained in a viva.
- The 3 flaky tests in `tests/test_flaky.py` are intentional. Don't "fix" them. They're driven by `FLAKE_RATE` (default 0.3).
- Detection runs set `IGNORE_QUARANTINE=1` so results are raw. Quarantine is applied at the gate, never by hiding failures.
- Gate: exit 1 only if a non-quarantined test fails every run. Flaky tests never block.
- Never print or echo secrets (`VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`). Use minimal `permissions:` in workflows.
- Vercel deploys only from CI. The Vercel project is not connected to the Git repo; never suggest enabling Vercel's Git integration.
- Vercel is serverless: the in-memory store doesn't persist across requests in production. Smoke tests use single-request checks only.
- Vercel does not run Docker images. Docker is for tests, local runs and the GHCR release artifact. Never claim otherwise in docs.
- Keep the app tiny. The pipeline is the project, not the app.
- Before saying a phase is done, run its "Done when" checks from PLAN.md and show the output.
- Conventional commit messages (`feat:`, `ci:`, `test:`, `docs:`, `chore:`). Commit at the end of each phase.
