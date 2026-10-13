# Execution Plan: Flaky Test Detection & Automatic Quarantine

**Title (as submitted):** Flaky Test Detection and Automatic Quarantine in a Containerized CI Pipeline Using Repeated Runs, Pytest and GitHub Actions

**Course:** DevOps (216U01E744), Sem VII, LAB CA Activity 2: Mini project, 25 marks
**Rubric items to cover:** Git/GitHub · application build · automated testing · Docker · CI/CD with GitHub Actions · deployment · documentation · working demo

**Cost:** ₹0. Uses a public GitHub repo, GitHub Actions, GHCR and the Vercel Hobby (free) plan.

---

## 0. The one-paragraph pitch (use this in the report intro and the viva)

Flaky tests pass and fail on the same code. They make CI untrustworthy: teams start hitting "re-run" until the build goes green, and real failures get ignored. This project builds a CI/CD pipeline for a containerized FastAPI service. The pipeline runs the test suite N times in parallel Docker containers and classifies every test from the results:

- **stable:** passes in every run.
- **flaky:** has mixed results across runs.
- **broken:** fails in every run.

Flaky tests are automatically quarantined: they are recorded in `quarantine.json`, stop blocking the build, and a PR is opened to persist the quarantine. Broken tests still block the build. Only code that passes the gate is released: the runtime Docker image is pushed to GHCR as the versioned release artifact, the same commit is deployed to Vercel through the Vercel CLI, and a post-deploy smoke test verifies the live version.

---

## 1. Final architecture

```
Developer ── git push / PR ──► GitHub
                                 │
                     GitHub Actions: ci.yml
 ┌───────────────────────────────┼──────────────────────────────────┐
 │ 1. lint          ruff + detector unit tests                      │
 │ 2. build-test    docker build --target test → saved as artifact   │
 │ 3. test-matrix   10 parallel jobs, each: docker run test image →  │
 │                  pytest (random order) → junit-<n>.xml            │
 │ 4. analyze/gate  flaky_detector.py over all 10 XMLs               │
 │                  → report.md (job summary) + report.json          │
 │                  → FAIL if any non-quarantined test is BROKEN     │
 │ 5. quarantine-pr (main only) opens a PR adding new flaky tests    │
 │ 6. build-push    (main only) runtime image → ghcr.io :sha :latest │
 │ 7. deploy        (main only) vercel pull → build → deploy         │
 │                  --prebuilt --prod (same commit, SHA baked in)    │
 │ 8. smoke-test    check /version returns this commit SHA,          │
 │                  then hit /health and POST /notes                 │
 └──────────────────────────────────────────────────────────────────┘
                                 │
                 Vercel (live URL, serverless function)
```

Plus `naive-ci.yml`, a manual workflow that runs pytest once with no detector. It is only used in the demo to show the "before" state.

---

## 2. Tech stack (pin these)

| Layer | Choice |
|---|---|
| App | Python 3.12, FastAPI, Uvicorn, a simple in-memory "Notes" API |
| Tests | pytest, pytest-randomly (random test order exposes order-dependent flakes), httpx (`TestClient`) |
| Lint | ruff |
| Detector | Plain Python 3.12 stdlib (`xml.etree`, `json`). No extra deps, so it's easy to explain |
| Container | Multi-stage Dockerfile: `base` → `test` → `runtime` (non-root user) |
| CI/CD | GitHub Actions, using the current major versions of `actions/checkout`, `docker/*`, `actions/upload-artifact` / `download-artifact`, `peter-evans/create-pull-request` |
| Registry | GHCR (`ghcr.io/<owner>/<repo>`), package set to **public**. Holds the release image; also what `docker compose` runs locally |
| Deploy | Vercel Hobby plan. FastAPI auto-detected at `app/main.py` and run as a serverless function. Deployed by the Vercel CLI from GitHub Actions, **not** by Vercel's Git integration, so the gate controls every deploy |
| Local | Docker Compose + Makefile |

---

## 3. Repo layout (target end state)

```
flaky-quarantine-ci/
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI app: /health, /version, /notes CRUD (`app` instance → Vercel auto-detects it)
│   ├── store.py           # in-memory store (module-level state → used by the order-dependent flaky test)
│   └── _version.py        # GIT_SHA = "dev"; overwritten by CI with the commit SHA before deploy
├── tests/
│   ├── conftest.py        # TestClient fixture; applies quarantine marks for local runs
│   ├── test_notes_api.py  # stable tests (~12-15)
│   └── test_flaky.py      # 3 deliberately flaky tests, clearly labelled
├── tools/
│   ├── flaky_detector.py  # parses JUnit XMLs, classifies, gates, updates quarantine
│   └── test_flaky_detector.py   # unit tests for the detector itself
├── quarantine.json        # source of truth for quarantined tests
├── Dockerfile             # multi-stage
├── docker-compose.yml
├── .dockerignore
├── Makefile               # make test / test-n / detect / run / docker-test
├── pyproject.toml         # runtime deps in [project.dependencies]; test/lint deps in a `dev` extra; ruff + pytest config
├── vercel.json            # function config (maxDuration etc.), kept minimal
├── .vercelignore          # exclude tests/, tools/, docs/, results/ from the Vercel bundle
├── .github/workflows/
│   ├── ci.yml
│   └── naive-ci.yml
├── docs/
│   ├── architecture.md    # mermaid diagrams
│   ├── screenshots/
│   └── REPORT.md          # submission report (convert to PDF/DOCX at the end)
├── CLAUDE.md
├── PLAN.md                # this file
└── README.md
```

---

## 4. Key design decisions (lock these in before coding)

**4.1 The three seeded flaky tests.** Each one represents a real-world flakiness category, which makes for a good viva talking point.

| Test | Category | Mechanism |
|---|---|---|
| `test_flaky_random_dependency` | Non-determinism | Simulated external call fails with probability `FLAKE_RATE` |
| `test_flaky_timing` | Timing/race | Operation has random latency; test asserts it finishes under a tight deadline |
| `test_flaky_order_dependent` | Shared state | Relies on store state left by another test; fails depending on random order (pytest-randomly) |

`FLAKE_RATE` is an env var (default `0.3`) so the demo is tunable. Every flaky test has a docstring saying it is intentionally flaky.

**4.2 Why 10 runs (viva math).** For a test with failure probability p = 0.3, the chance it passes all 10 runs and escapes detection is 0.7¹⁰ ≈ **2.8%**, so detection works about 97% of the time. The chance a genuinely flaky test fails all 10 and gets misclassified as broken is 0.3¹⁰ ≈ 0.0006%. Put this in the report.

**4.3 Classification and gate rules** (implemented in `flaky_detector.py`)

- `passed == runs` → **stable**
- `failed == runs` → **broken**
- otherwise → **flaky**; `flake_rate = failed / runs`
- A test missing from some runs is treated as an error and reported.

**Gate:**
1. Any **broken** test that is not quarantined → exit 1 (build blocked).
2. Any **flaky** test not yet quarantined → added to the new quarantine list and marked "newly quarantined". Does not block.
3. Already-quarantined tests never block, but are always listed in the report. This trade-off is the main viva question: quarantine can hide a real bug, so the report keeps quarantined tests visible.
4. Otherwise → exit 0.

**4.4 `quarantine.json` schema**

```json
{
  "version": 1,
  "tests": [
    {
      "id": "tests/test_flaky.py::test_flaky_timing",
      "flake_rate": 0.3,
      "runs": 10,
      "detected_at": "2026-10-14T10:22:00Z",
      "commit": "abc1234",
      "reason": "mixed results across repeated runs"
    }
  ]
}
```

**4.5 Detection runs are raw.** The matrix runs set `IGNORE_QUARANTINE=1` so pytest reports true results. Quarantine is applied at the gate, not by hiding failures. `conftest.py` only applies `xfail(strict=False)` to quarantined tests during normal local runs.

**4.6 Versioning and what gets deployed.** Vercel runs FastAPI as a serverless function from source; it cannot run a Docker image. So:
- **Docker** = the test environment (all 10 matrix runs) + the versioned release artifact in GHCR (`:sha`, `:latest`), which also runs locally via `docker compose`.
- **Vercel** = the live environment, deployed from the **same commit** that passed the gate.
- Before both the image build and the Vercel build, CI writes the commit SHA into `app/_version.py`. `/version` returns `GIT_SHA` env if set, else `app/_version.GIT_SHA`. The smoke test uses this to prove the right commit is live.

**4.7 Serverless means no shared memory between requests.** Vercel may serve requests from different instances, so the in-memory store is not guaranteed to persist across requests in production. That's acceptable for this project (the pipeline is the focus), but: the smoke test must only use **single-request checks** (`/health`, `/version`, and `POST /notes` checking the response body), never create-then-get. Mention this in Limitations; it's also a good viva answer.

---

## 5. Phases (one Claude Code session per phase, commit at the end of each)

> **How to drive Claude Code:** start each phase in plan mode (Shift+Tab), paste the phase prompt, review its plan, then let it implement. End every phase with "run the checks in the Done-when list and show me the output". Commit and push before moving on.

### Phase 0: Setup (≈30 min, do this by hand)

1. Create a **public** GitHub repo `flaky-quarantine-ci` and add teammates as collaborators.
2. Repo **Settings → Actions → General**:
   - Workflow permissions: **Read and write**.
   - Tick **"Allow GitHub Actions to create and approve pull requests"**. The quarantine PR needs this.
3. Install locally: Docker Desktop, Python 3.12, `gh` CLI (`gh auth login`).
4. Create a free Vercel account (sign in with GitHub) and install the CLI: `npm i -g vercel`. Don't create the project yet; that's Phase 6.
5. Clone the repo and drop in `CLAUDE.md` and `PLAN.md`. Commit: `chore: add project plan`.

**Done when:** the repo exists with both files on `main`.

### Phase 1: App, stable tests, Docker (≈1.5 h)

**Prompt for Claude Code:**
> Read CLAUDE.md and PLAN.md sections 2–4. Implement Phase 1: the FastAPI Notes API in `app/main.py` (the FastAPI instance must be named `app` so Vercel auto-detects it) with `/health`, `/version` (returns `GIT_SHA` env if set, else `app/_version.GIT_SHA`, default "dev"), and CRUD on `/notes` using the in-memory store in `app/store.py`. `POST /notes` must return the created note in the response body. Write 12–15 stable pytest tests in `tests/test_notes_api.py` using a `TestClient` fixture in `tests/conftest.py`. Set up `pyproject.toml` (runtime deps only in `[project.dependencies]`; pytest, pytest-randomly, httpx, ruff in a `dev` extra; ruff and pytest config). Add a `.vercelignore` excluding tests/, tools/, docs/, results/. Write a multi-stage Dockerfile (base → test → runtime; runtime runs as non-root on port 8000), a `.dockerignore`, `docker-compose.yml`, and a Makefile with `test`, `run`, `docker-test`, `docker-run`. Do NOT add flaky tests yet.

**Done when:**
- `make test` is green.
- `docker build --target test .` then running it is green.
- `docker compose up` serves `localhost:8000/health`.
- `ruff check .` is clean.

### Phase 2: Seed the flaky tests (≈45 min)

**Prompt:**
> Implement PLAN.md §4.1: add `tests/test_flaky.py` with the three intentionally flaky tests (random dependency, timing, order-dependent), all driven by `FLAKE_RATE` (default 0.3). Add the minimal app/store support they need without changing existing API behaviour. Add a `make test-n N=10` target that runs pytest N times with `--junitxml=results/run-$i.xml` and continues on failure. Run `make test-n N=10` and show me pass/fail counts per test.

**Done when:**
- Across 10 local runs, each of the 3 flaky tests has mixed results.
- Every stable test passes 10/10.
- If any flaky test came out 10/10 or 0/10, have Claude Code tune it.

### Phase 3: The detector (≈2 h, the heart of the project)

**Prompt:**
> Implement `tools/flaky_detector.py` exactly per PLAN.md §4.3–4.5. CLI: `python tools/flaky_detector.py --results results/ --quarantine quarantine.json --out-json report.json --out-md report.md --write-quarantine quarantine.new.json --commit $SHA`. Stdlib only. Parse JUnit XMLs (treat `failure` and `error` as failed, `skipped` as not run), classify each test, apply the gate rules, write a Markdown report: summary counts, then a table of test / status / pass-fail / flake rate / quarantined?, with sections for Newly quarantined, Broken (blocking), and Already quarantined. Exit 1 only per the gate rules. Write thorough unit tests in `tools/test_flaky_detector.py` using small synthetic XML fixtures: stable, flaky, broken, broken-but-quarantined, test missing from some runs, empty results dir. Also create an initial empty `quarantine.json`. Then run it against the results from `make test-n N=10`.

**Done when:**
- All detector unit tests pass.
- Running the detector on real results correctly flags the 3 flaky tests.
- `report.md` reads well.
- Exit code is 0.

### Phase 4: CI pipeline, part 1 (detection and gate) (≈2 h)

**Prompt:**
> Create `.github/workflows/ci.yml` for push and pull_request on main, with jobs: `lint` (ruff + detector unit tests); `build-test-image` (buildx with GHA cache, build `--target test`, `docker save | gzip`, upload as artifact); `test-matrix` (matrix run: 1..10, fail-fast false; load the image, run pytest in the container with `IGNORE_QUARANTINE=1`, `FLAKE_RATE` from a workflow env, `--junitxml` mounted out, `continue-on-error` at step level so the job reports results not failure, upload `junit-<n>`); `analyze` (download all junit artifacts merged into one dir, run the detector, append report.md to `$GITHUB_STEP_SUMMARY`, upload report.json, report.md and quarantine.new.json as an artifact, fail per the detector exit code). Use concurrency to cancel superseded runs on the same ref and minimal `permissions`. Also create `naive-ci.yml` (workflow_dispatch only): checkout, install, run pytest once, nothing else.

Then push and watch the run: `gh run watch`.

**Done when:**
- A green run on GitHub.
- The job summary shows the flaky table.
- The 10 matrix jobs are visible in the Actions graph.
- Triggering `naive-ci` 3–4 times produces at least one red run. Screenshot it, because that's your "before" evidence.

### Phase 5: CI pipeline, part 2 (automatic quarantine) (≈1 h)

**Prompt:**
> Add job `quarantine-pr` to ci.yml: runs only on push to main, after `analyze`, if the detector reported newly quarantined tests (expose this as a job output). Download quarantine.new.json, overwrite quarantine.json, and open or update a PR with peter-evans/create-pull-request: branch `bot/quarantine`, title `chore: quarantine N flaky test(s)`, body = report.md. Then update `tests/conftest.py` so that, unless `IGNORE_QUARANTINE=1`, tests listed in quarantine.json get `pytest.mark.xfail(strict=False, reason="quarantined: flaky")`. Add a test for that conftest behaviour if feasible.

**Done when:**
- A push to main opens the quarantine PR automatically.
- Merging it updates `quarantine.json`.
- A local `make test` now shows the 3 flaky tests as xfail/xpass instead of failing.

### Phase 6: Build, push, deploy, smoke test (≈1.5 h)

**By hand first (Vercel project, linked by CLI only):**
1. In the repo locally: `vercel login`, then `vercel link`. Create a new project, and **do not connect the Git repository** when asked. If Vercel's Git integration auto-deploys every push, the pipeline's gate becomes meaningless; CI must be the only thing that deploys.
2. Run `vercel deploy --prod` once by hand to confirm the app works on Vercel. Note the production URL (`https://<project>.vercel.app`).
3. Open the `.vercel/project.json` file that `vercel link` created and copy `orgId` and `projectId`. Make sure `.vercel/` is in `.gitignore`.
4. Vercel dashboard → Account Settings → Tokens → create a token for this project.
5. GitHub repo → Settings → Secrets and variables → Actions:
   - Secrets: `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`
   - Variable: `APP_URL` = your production URL
6. After the first `build-push` run, go to GitHub → your profile → Packages → the package → set visibility to **Public**.

**Prompt:**
> Add jobs to ci.yml, all only on push to main: `build-push` (needs analyze; write `GIT_SHA = "${{ github.sha }}"` into `app/_version.py`, log in to GHCR with GITHUB_TOKEN, build `--target runtime`, push tags `:sha` and `:latest`; permissions packages: write); `deploy` (needs build-push; env VERCEL_ORG_ID and VERCEL_PROJECT_ID from secrets; write the SHA into `app/_version.py` the same way; `npm i -g vercel`, then `vercel pull --yes --environment=production --token=$VERCEL_TOKEN`, `vercel build --prod --token=$VERCEL_TOKEN`, `vercel deploy --prebuilt --prod --token=$VERCEL_TOKEN`; never echo the token; attach a GitHub environment `production` with url `${{ vars.APP_URL }}`); `smoke-test` (needs deploy; poll `${{ vars.APP_URL }}/version` every 10 s for up to 3 min until it returns this commit's SHA; then assert `/health` is 200 and `POST /notes` returns 201 with the note in the body. Single-request checks only, no create-then-get, per PLAN §4.7). Add `.vercel` to `.gitignore`. Check the current Vercel CLI docs for these commands before writing the workflow.

**Done when:**
- A push to main runs the whole chain: lint → test-matrix → analyze → build-push → deploy → smoke-test, all green.
- `<APP_URL>/version` shows the latest commit SHA.
- The Vercel dashboard shows deployments only from CI, none from Git pushes directly.

> **If `vercel build` / `--prebuilt` gives trouble:** drop to a plain `vercel deploy --prod --token=$VERCEL_TOKEN` (Vercel builds remotely). Since the deploy step writes `_version.py` before uploading, the SHA check still works.

### Phase 7: Branch protection and the demo scenarios (≈1 h)

1. Settings → Branches → protect `main`: require PR, and require the `analyze` and `lint` checks to pass.
2. Prepare three demo branches so the live demo never depends on luck:

| Scenario | What to show |
|---|---|
| **A: Before** | Run `naive-ci` a few times: random red/green on identical code. Also keep a screenshot ready as backup. |
| **B: Detection** | A PR from `demo/new-flaky` that adds a 4th flaky test. Show the matrix, the job summary flagging it, the gate staying green, and the quarantine PR opening after merge. |
| **C: Real bug** | A PR from `demo/real-bug` that breaks `/notes` (e.g. wrong status code). Show the broken tests 0/10, the gate red, the merge blocked by branch protection, and that the Vercel dashboard has no new deployment. |
| **D: Delivery** | Merge a harmless change. Show build-push → deploy → smoke test, then the live `/version` on Vercel showing the new SHA, plus the new image tag in GHCR. |

**Done when:** each scenario has been run once end-to-end and screenshotted into `docs/screenshots/`.

### Phase 8: Documentation and report (≈2 h; split this across teammates)

**Prompt:**
> Write README.md (problem, architecture mermaid diagram, how to run locally, pipeline walkthrough per job, how quarantine works, demo scenarios, screenshots) and docs/architecture.md (pipeline flow and classification state diagram in mermaid). Then write docs/REPORT.md for college submission with sections: Title page info, Abstract, Introduction & Problem Statement, Objectives, Literature/Background (flaky tests, quarantine vs retry), System Architecture, Tools & Technologies, Implementation (app, Docker, detector algorithm, each CI/CD job), Results (detection table from a real run, screenshots referenced from docs/screenshots), Probability analysis from PLAN §4.2, Limitations & Future Scope, Conclusion, References. Keep it factual to what the repo actually does.

Then convert REPORT.md to PDF or DOCX, whatever the faculty wants.

**Done when:** the report is ready with real screenshots, not placeholders.

---

## 6. Timeline

| Day | Work |
|---|---|
| Day 1 | Phase 0 → 3 (app, flaky tests, detector working locally) |
| Day 2 | Phase 4 → 6 (full pipeline green, live on Vercel) |
| Day 3 | Phase 7 → 8 (demo branches, screenshots, report), plus one full dry-run demo |

If you're pushed, Day 1 and Day 2 can merge into one long day. Phases 3 and 4 are where the time goes.

**Split for 3 people** (Claude Code does the bulk; people own and verify):

- **Person 1:** Phases 1–3 (app, flaky tests, detector) + explaining the detector in the viva.
- **Person 2:** Phases 4–6 (workflows, GHCR, Vercel) + explaining the pipeline.
- **Person 3:** Phase 7–8 (demo branches, screenshots, README, report) + presenting.

Everyone should be able to answer the viva questions below.

---

## 7. Stretch goals (only if everything above is done)

1. **Sticky PR comment** with the flaky report on every PR.
2. **Un-quarantine suggestion:** if a quarantined test passes 10/10 on main for 3 consecutive runs, the report suggests removing it.
3. **Flakiness history:** keep `flaky-history.json` across runs and show the trend in the report.
4. **Retry comparison:** add a job using `pytest-rerunfailures` to show that retries make CI green but hide flakiness, while this system makes it visible. This is good for the "why not just retry?" question.

---

## 8. Viva prep: questions you'll get

1. **Why not just retry failed tests?** Retries hide flakiness and make CI slower forever. Quarantine makes it visible and tracked, and keeps the gate meaningful.
2. **Can quarantine hide a real bug?** Yes. That's why quarantined tests still run, are always listed in the report, and the quarantine goes through a reviewable PR.
3. **Why 10 runs?** Use the §4.2 math: about 97% detection at p = 0.3. More runs means better detection but more CI time.
4. **Why run tests inside Docker?** Same environment locally and in CI, so "works on my machine" is ruled out as a cause of flakiness.
5. **Why multi-stage Docker?** Test dependencies stay out of the runtime image, which keeps it smaller with a smaller attack surface, and the image runs as non-root.
6. **CI vs CD here?** CI is lint → matrix → gate. CD is build-push → deploy → smoke test, only on main after the gate.
7. **How do you know the deploy worked?** The smoke test checks that `/version` returns the exact commit SHA, not just that the service is up.
8. **Why push to GHCR if Vercel doesn't run the image?** The image is the versioned, portable release artifact: SHA-tagged, immutable, runnable anywhere with Docker (locally via compose, or on any container host). Vercel is a serverless target that builds from the same gated commit. Be upfront about this; don't claim Vercel runs the container.
9. **Why not let Vercel auto-deploy from GitHub?** Then every push deploys, even ones that fail the gate. Deploying only from CI makes the pipeline the single gatekeeper.
10. **Why doesn't the smoke test create a note and then read it back?** Serverless instances don't share memory, so the in-memory store isn't guaranteed to persist between requests. A real app would use a database (e.g. Postgres); that's in Future Scope.
11. **What does pytest-randomly do?** It shuffles test order each run, which exposes hidden order dependencies.
12. **Limitations?** Detection is probabilistic, and low flake-rate tests can slip through. Matrix runs cost CI minutes. Quarantine needs human follow-up to actually fix tests. The production app has no persistent storage.

---

## 9. Final checklist before the demo

- [ ] Latest `main` run fully green, all 8 jobs
- [ ] Vercel production URL opened once before the demo (first request after idle has a cold start)
- [ ] `naive-ci` red-run screenshot saved
- [ ] Demo branches `demo/new-flaky` and `demo/real-bug` ready, PRs drafted
- [ ] Quarantine PR example exists in PR history
- [ ] Report PDF/DOCX done with real screenshots
- [ ] Each teammate has rehearsed their part
